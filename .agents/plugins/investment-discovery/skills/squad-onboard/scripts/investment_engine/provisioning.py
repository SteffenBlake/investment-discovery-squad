"""Explicit provisioning, ownership binding, schema checks and conservative legacy adoption."""

import json
import os
import sqlite3
from pathlib import Path

from .ledger import Store
from .configuration import private_directory
from .util import canonical, digest, now_utc

FROZEN = ("base_currency", "round_trip_cost_bps", "family_alpha",
          "min_train_samples", "min_test_samples", "min_test_events")


def frozen_settings_match(saved, settings):
    previous = json.loads(saved or '{}')
    return all(previous.get(key) == settings[key] for key in FROZEN)


def storage_plan(installation):
    return {"backend": "ladybug", "transaction_ledger": "sqlite", "knowledge_path": installation["storage"]["knowledge_path"],
            "runtime": installation["runtime"], "independent_backup": installation["storage"]["cloud_backup"], "database_path": installation["storage"]["database_path"],
            "backup_directory": installation["storage"]["backup_directory"],
            "backup_interval_hours": installation["storage"]["backup_interval_hours"],
            "backup_files": 1,
            "creates_database": False, "decision_accepted": installation["storage"]["decision_accepted"],
            "stores": ["hypotheses and source evidence", "complete historical datasets", "all live predictions/outcomes",
                       "lifecycle history", "notification claims/receipts"],
            "limits": ["One Dot cloud computer runs serialized operations on original local stores",
                       "Private file permissions protect research and financial records on the central cloud computer",
                       "Use OS access controls/encrypted disk if needed; exports/backups include private financial records",
                       "Google Drive versions retain earlier backup contents under normal expiry rules",
                       "Google Drive backup retains research and prediction history for recovery"]}


def _metadata(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        return dict(db.execute("SELECT key,value FROM meta")), db.execute("PRAGMA user_version").fetchone()[0]
    finally:
        db.close()


def open_store(settings, *, initialize=False):
    return _open_store(settings, initialize=initialize)


def check_initialization_target(settings, inventory=None):
    from .drive import read_inventory, backup_files
    ledger_exists = Path(settings['storage']['database_path']).exists()
    graph_exists = Path(settings['storage']['knowledge_path']).exists()
    if ledger_exists and graph_exists:
        return
    backups = backup_files(read_inventory(settings, inventory))
    if backups:
        raise ValueError('Existing Drive backup found; restore original databases before initialization')
    if ledger_exists or graph_exists:
        raise ValueError('Existing installation has a missing database; recover original records')


def _open_store(settings, *, initialize=False, restoring_identity=None):
    path = Path(settings["storage"]["database_path"])
    if restoring_identity is None and (path.parent / ".restore-in-progress.json").exists():
        raise ValueError("Interrupted restore detected; preserve partial state and recover into a new empty target")
    frozen = canonical({key: settings[key] for key in FROZEN})
    if path.exists():
        metadata, version = _metadata(path)
        if metadata.get("profile_id") != settings["profile_id"]:
            raise ValueError("Database unbound or belongs to another installation. Review storage adoption; never reset/relabel automatically")
        if version != 1:
            raise ValueError("Unsupported schema version; explicit migration required")
        if not frozen_settings_match(metadata.get("frozen_settings"), settings):
            raise ValueError("Frozen economic/statistical settings changed; restore installation or select a new experiment/ledger")
        if restoring_identity is not None and metadata.get("setup_identity") != restoring_identity:
            raise ValueError("Copied ledger identity differs from verified recovery archive")
    elif not initialize:
        raise ValueError("Database not initialized. Review 'storage-plan', then explicitly run init")
    store = Store(path, create=initialize)
    if initialize:
        try:
            with store.transaction():
                metadata = dict(store.db.execute("SELECT key,value FROM meta"))
                if metadata.get("profile_id") not in (None, settings["profile_id"]):
                    raise ValueError("Concurrent initialization belongs to another installation")
                if metadata.get("frozen_settings") is not None and not frozen_settings_match(metadata["frozen_settings"], settings):
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
    private_directory(path.parent)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError("Backup already exists; choose a unique filename") from exc
    os.close(descriptor)
    return sqlite3.connect(path)


def adopt(settings, confirmed_currency):
    if confirmed_currency != settings["base_currency"]:
        raise ValueError("Adoption currency must match reviewed configuration")
    path = Path(settings["storage"]["database_path"])
    metadata, version = _metadata(path)
    if metadata.get("profile_id"):
        raise ValueError("Already-owned database; do not adopt another user's ledger")
    if metadata.get("mode") != "production" or version not in (0, 1):
        raise ValueError("Only recognized legacy production ledgers can be adopted")
    old = json.loads(metadata.get("frozen_settings", "{}"))
    if "starting_cash_cad" in old and confirmed_currency != "CAD":
        raise ValueError("Legacy currency differs; automatic FX migration is unsupported")
    if any(currency != confirmed_currency for currency in (old.get("base_currency"), metadata.get("base_currency")) if currency):
        raise ValueError("Legacy currency differs; preserve original economics")
    for key in FROZEN:
        if key in old and key != "base_currency" and old[key] != settings[key]:
            raise ValueError(f"Legacy {key} differs; preserve historical settings")
    source = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        currencies = {r[0] for r in source.execute("SELECT DISTINCT json_extract(data,'$.currency') FROM prices") if r[0]}
        if currencies - {confirmed_currency}:
            raise ValueError("Stored observations have another currency")
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
