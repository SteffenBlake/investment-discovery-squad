"""Explicit provisioning, ownership binding, schema checks and conservative legacy adoption."""

import json
import os
import sqlite3
from pathlib import Path

from .store import Store
from .util import canonical, digest, instant, stamp, now_utc

FROZEN = ("starting_cash", "base_currency", "round_trip_cost_bps", "family_alpha",
          "min_train_samples", "min_test_samples", "min_test_events")


def storage_plan(profile):
    return {"backend": "ladybug", "transaction_ledger": "sqlite", "knowledge_path": profile["storage"]["knowledge_path"],
            "runtime": profile["runtime"], "independent_backup": profile["storage"]["cloud_backup"], "database_path": profile["storage"]["database_path"],
            "backup_directory": profile["storage"]["backup_directory"],
            "backup_interval_hours": profile["storage"]["backup_interval_hours"],
            "retention_days": profile["storage"]["backup_retention_days"],
            "creates_database": False, "decision_accepted": profile["storage"]["decision_accepted"],
            "stores": ["hypotheses and source evidence", "complete historical datasets", "all live predictions/outcomes",
                       "lifecycle history", "notification claims/receipts", "human-reported fills and trade ideas"],
            "limits": ["One required central Dot cloud owner; serialize commands, never share live files over a network filesystem",
                       "No built-in encryption, server authentication, remote SQL backend or high availability",
                       "Use OS access controls/encrypted disk if needed; exports/backups include private financial records",
                       "Backup retention never deletes the immutable prediction ledger",
                       "Dot snapshots and local copies are not independent cloud backups; verify actual Drive recovery",
                       "Dot memory and Git are not substitutes for LadybugDB research knowledge or the SQLite ledger"]}


def _metadata(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        return dict(db.execute("SELECT key,value FROM meta")), db.execute("PRAGMA user_version").fetchone()[0]
    finally:
        db.close()


def open_store(settings, *, initialize=False):
    path = Path(settings["storage"]["database_path"])
    if (path.parent / ".restore-in-progress.json").exists():
        raise ValueError("Interrupted restore detected; preserve partial state and recover into a new empty target")
    frozen = canonical({key: settings[key] for key in FROZEN})
    if path.exists():
        metadata, version = _metadata(path)
        if metadata.get("profile_id") != settings["profile_id"]:
            raise ValueError("Database unbound or belongs to another profile. Review storage adoption; never reset/relabel automatically")
        if version != 1:
            raise ValueError("Unsupported schema version; explicit migration required")
        if metadata.get("frozen_settings") != frozen:
            raise ValueError("Frozen economic/statistical settings changed; restore profile or select a new experiment/ledger")
    elif not initialize:
        raise ValueError("Database not initialized. Review 'storage-plan', then explicitly run init")
    store = Store(path, create=initialize)
    if initialize:
        try:
            with store.transaction():
                metadata = dict(store.db.execute("SELECT key,value FROM meta"))
                if metadata.get("profile_id") not in (None, settings["profile_id"]):
                    raise ValueError("Concurrent initialization belongs to another profile")
                if metadata.get("frozen_settings") not in (None, frozen):
                    raise ValueError("Concurrent initialization has different economic settings")
                for key, value in {"profile_id": settings["profile_id"], "base_currency": settings["base_currency"],
                                   "frozen_settings": frozen, "storage_decision": canonical(settings["storage"])}.items():
                    store.db.execute("INSERT OR IGNORE INTO meta VALUES(?,?)", (key, value))
        except Exception:
            store.close()
            raise
    revision = digest(settings)
    with store.transaction():
        if not store.db.execute("SELECT 1 FROM events WHERE kind='profile_revision' AND json_extract(data,'$.hash')=?", (revision,)).fetchone():
            store.event("profile_revision", hash=revision, settings=settings)
    return store


def _backup_connection(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError("Backup already exists; choose a unique filename") from exc
    os.close(descriptor)
    return sqlite3.connect(path)


def backup(store, destination):
    path = Path(destination)
    target = _backup_connection(path)
    try:
        store.db.backup(target)
        if target.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("Backup integrity check failed")
    finally:
        target.close()
    with store.transaction():
        store.event("backup_created", path=str(path.resolve()), integrity="ok")
    return str(path)


def backup_due(store, settings):
    row = store.db.execute("SELECT at,data FROM events WHERE kind='backup_created' ORDER BY seq DESC LIMIT 1").fetchone()
    if row:
        previous = Path(json.loads(row["data"])["path"])
        age = (instant(store.clock()) - instant(row["at"])).total_seconds()
        directory = Path(settings["storage"]["backup_directory"]).resolve()
        if previous.is_file() and previous.parent == directory and 0 <= age < settings["storage"]["backup_interval_hours"] * 3600:
            return {"created": False, "last_backup": str(previous)}
    destination = Path(settings["storage"]["backup_directory"]) / ("knowledge-" + now_utc().strftime("%Y%m%dT%H%M%S%f") + ".sqlite3")
    return {"created": True, "backup": backup(store, destination)}


def adopt(settings, confirmed_currency, confirmed_cash):
    from .configuration import money
    if confirmed_currency != settings["base_currency"] or money(confirmed_cash) != money(settings["starting_cash"]):
        raise ValueError("Explicit adoption currency/cash must match the reviewed profile")
    path = Path(settings["storage"]["database_path"])
    metadata, version = _metadata(path)
    if metadata.get("profile_id"):
        raise ValueError("Already-owned database; do not adopt another user's ledger")
    if metadata.get("mode") != "production" or version not in (0, 1):
        raise ValueError("Only recognized legacy production ledgers can be adopted")
    old = json.loads(metadata.get("frozen_settings", "{}"))
    old_cash = old.get("starting_cash", old.get("starting_cash_cad"))
    if old_cash is None or money(old_cash) != money(confirmed_cash):
        raise ValueError("Legacy starting cash cannot be verified; manual migration required")
    if "starting_cash_cad" in old and confirmed_currency != "CAD":
        raise ValueError("Legacy currency differs; automatic FX migration is unsupported")
    for key in FROZEN:
        if key in old and key not in {"starting_cash", "base_currency"} and old[key] != settings[key]:
            raise ValueError(f"Legacy {key} differs; preserve historical settings")
    source = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        currencies = {r[0] for r in source.execute("SELECT DISTINCT json_extract(data,'$.currency') FROM prices") if r[0]}
        if currencies - {confirmed_currency}:
            raise ValueError("Stored observations have another currency")
        for row in source.execute("SELECT data FROM ideas"):
            idea = json.loads(row[0])
            if not {"notional", "expires_at"} <= idea.keys() or idea.get("currency") != confirmed_currency:
                raise ValueError("Legacy trade idea format needs explicit migration; preserve the original ledger")
        for row in source.execute("SELECT data FROM fills"):
            fill = json.loads(row[0])
            if not {"symbol", "side", "quantity", "price", "fee"} <= fill.keys() or fill.get("currency") != confirmed_currency:
                raise ValueError("Legacy fill format/currency needs explicit migration")
        folder = Path(settings["storage"]["backup_directory"])
        destination = folder / ("pre-adoption-" + now_utc().strftime("%Y%m%dT%H%M%S%f") + ".sqlite3")
        target = _backup_connection(destination)
        try:
            source.backup(target)
            if target.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("Legacy backup failed verification")
        finally:
            target.close()
    finally:
        source.close()
    store = Store(path)
    try:
        with store.transaction():
            for key, value in {"legacy_frozen_settings": canonical(old), "profile_id": settings["profile_id"],
                               "base_currency": settings["base_currency"], "storage_decision": canonical(settings["storage"]),
                               "frozen_settings": canonical({k: settings[k] for k in FROZEN})}.items():
                store.db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (key, value))
            store.event("legacy_adopted", profile_id=settings["profile_id"], backup=str(destination))
        store.db.execute("PRAGMA user_version=1")
        return {"adopted": True, "setup_identity": store.identity, "backup": str(destination)}
    finally:
        store.close()
