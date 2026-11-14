"""SQLite is the numerical/accounting authority; research knowledge lives in LadybugDB."""

import json
import os
import sqlite3
import tempfile
import uuid
from pathlib import Path

from .util import canonical, now_utc, stamp
from .configuration import private_directory

IMMUTABLE = ("events", "specs", "datasets", "test_plans", "trials", "predictions", "outcomes", "prices", "indicators", "fills", "ideas")


class Store:
    def __init__(self, path, *, mode="production", clock=now_utc, create=False):
        self.path = Path(path)
        if not self.path.exists() and not create and mode != "synthetic":
            raise ValueError("Database does not exist; complete storage onboarding and run init explicitly")
        private_directory(self.path.parent)
        if not self.path.exists():
            try:
                descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(descriptor)
            except FileExistsError:
                pass
        self.clock = clock
        self.db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            self.db.close()
            raise ValueError("Unsupported database schema version; restore compatible code before opening")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(
          seq INTEGER PRIMARY KEY, at TEXT NOT NULL, kind TEXT NOT NULL, signal_id TEXT, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS specs(id TEXT PRIMARY KEY, at TEXT NOT NULL, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS signals(id TEXT PRIMARY KEY REFERENCES specs(id), state TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS datasets(hash TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS test_plans(
          signal_id TEXT PRIMARY KEY REFERENCES specs(id), at TEXT NOT NULL, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS trials(
          id INTEGER PRIMARY KEY AUTOINCREMENT, signal_id TEXT NOT NULL UNIQUE REFERENCES specs(id),
          at TEXT NOT NULL, dataset_hash TEXT NOT NULL, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS predictions(
          id TEXT PRIMARY KEY, signal_id TEXT NOT NULL REFERENCES specs(id), event_id TEXT NOT NULL,
          at TEXT NOT NULL, due_at TEXT NOT NULL, data TEXT NOT NULL, UNIQUE(signal_id,event_id));
        CREATE TABLE IF NOT EXISTS outcomes(
          prediction_id TEXT PRIMARY KEY REFERENCES predictions(id), at TEXT NOT NULL,
          success INTEGER NOT NULL CHECK(success IN (0,1)), data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS prices(
          symbol TEXT NOT NULL, market_at TEXT NOT NULL, captured_at TEXT NOT NULL,
          kind TEXT NOT NULL CHECK(kind IN ('quote','close')), data TEXT NOT NULL,
          PRIMARY KEY(symbol,market_at,kind));
        CREATE TABLE IF NOT EXISTS indicators(
          source TEXT NOT NULL, event_at TEXT NOT NULL, captured_at TEXT NOT NULL, data TEXT NOT NULL,
          PRIMARY KEY(source,event_at));
        CREATE TABLE IF NOT EXISTS outbox(
          id TEXT PRIMARY KEY, signal_id TEXT NOT NULL UNIQUE REFERENCES specs(id), at TEXT NOT NULL,
          status TEXT NOT NULL, token TEXT, receipt TEXT, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS fills(id TEXT PRIMARY KEY, at TEXT NOT NULL, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS ideas(id TEXT PRIMARY KEY, at TEXT NOT NULL, data TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS specs_symbol_at ON specs(json_extract(data,'$.symbol'), at DESC);
        """)
        for table in IMMUTABLE:
            for operation in ("UPDATE", "DELETE"):
                self.db.execute(f"""CREATE TRIGGER IF NOT EXISTS immutable_{table}_{operation}
                    BEFORE {operation} ON {table} BEGIN
                    SELECT RAISE(ABORT, 'Immutable evidence; append a correction event'); END""")
        self.db.execute("INSERT OR IGNORE INTO meta VALUES('mode',?)", (mode,))
        actual = self.db.execute("SELECT value FROM meta WHERE key='mode'").fetchone()[0]
        if actual != mode:
            self.db.close()
            raise ValueError(f"Database mode is {actual}; requested {mode}")
        self.mode = actual
        self.db.execute("INSERT OR IGNORE INTO meta VALUES('setup_identity',?)", (uuid.uuid4().hex,))
        self.identity = self.db.execute("SELECT value FROM meta WHERE key='setup_identity'").fetchone()[0]
        if create or mode == "synthetic":
            self.db.execute("PRAGMA user_version=1")

    def close(self):
        self.db.close()

    def transaction(self):
        return Transaction(self.db)

    def event(self, kind, signal_id=None, **data):
        self.db.execute("INSERT INTO events(at,kind,signal_id,data) VALUES(?,?,?,?)",
                        (stamp(self.clock()), kind, signal_id, canonical(data)))

    def spec(self, signal_id):
        row = self.db.execute("SELECT data FROM specs WHERE id=?", (signal_id,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown signal: {signal_id}")
        return json.loads(row[0])

    def state(self, signal_id):
        row = self.db.execute("SELECT state FROM signals WHERE id=?", (signal_id,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown signal: {signal_id}")
        return row[0]

    def export(self, destination):
        with self.transaction():
            data = {"mode": self.mode, "setup_identity": self.identity, "exported_at": stamp(self.clock())}
            for table in (*IMMUTABLE, "signals", "outbox"):
                rows = [dict(r) for r in self.db.execute(f"SELECT * FROM {table}")]
                for row in rows:
                    if "data" in row:
                        row["data"] = json.loads(row["data"])
                data[table] = rows
        dest = Path(destination)
        private_directory(dest.parent)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=dest.parent, prefix=".ledger-export-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(data, indent=2, allow_nan=False) + "\n")
        try:
            temporary.replace(dest)
        finally:
            temporary.unlink(missing_ok=True)
        return data


class Transaction:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        self.db.execute("BEGIN IMMEDIATE")
        return self

    def __exit__(self, cls, value, traceback):
        self.db.execute("ROLLBACK" if cls else "COMMIT")
