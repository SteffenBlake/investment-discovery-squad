import copy
import json
import os
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from investment_engine.cli import execute, parser
from investment_engine.configuration import configuration_template, build_runtime_settings, validate_installation
from tests.fixtures import DemoClock
from investment_engine.engine import Engine
from investment_engine.portfolio import Portfolio
from investment_engine.provisioning import FROZEN, adopt, open_store
from investment_engine.backups import snapshot
from investment_engine.ledger import Store
from investment_engine.util import ROOT, canonical
from tests.fixtures import completed_installation, native_environment


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        remote = patch('investment_engine.drive.Drive.list', return_value=[])
        remote.start()
        self.addCleanup(remote.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.installation = completed_installation(self.folder)

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *args):
        with patch.dict(os.environ, native_environment(self.installation)):
            return execute(parser().parse_args(list(args)))

    def test_fresh_checkout_requires_settings_before_initialization(self):
        with patch.dict(os.environ, {}, clear=True):
            result = execute(parser().parse_args(["doctor"]))
            self.assertEqual(result["stage"], "ONBOARDING_REQUIRED")
            self.assertFalse(result["database_created"])
            with self.assertRaisesRegex(ValueError, "Onboarding"):
                execute(parser().parse_args(["init"]))

    def test_template_is_unconfigured_and_cannot_initialize(self):
        template = configuration_template()
        with self.assertRaises(ValueError):
            validate_installation(template)

    def test_init_refuses_empty_databases_when_remote_backup_exists(self):
        with patch('investment_engine.drive.Drive.list', return_value=[{'id': 'existing-backup'}]):
            with self.assertRaisesRegex(ValueError, 'Existing Drive backup'):
                self.cli('init')
        for key in ('database_path', 'knowledge_path'):
            self.assertFalse(Path(self.installation['storage'][key]).exists())

    def test_init_preserves_existing_ledger_when_research_database_missing(self):
        initial = self.cli('init')
        Path(self.installation['storage']['knowledge_path']).unlink()
        with patch('investment_engine.drive.Drive.list', return_value=[{'id': 'existing-backup'}]):
            with self.assertRaisesRegex(ValueError, 'Existing Drive backup'):
                self.cli('init')
        self.assertFalse(Path(self.installation['storage']['knowledge_path']).exists())
        reader = sqlite3.connect(self.installation['storage']['database_path'])
        try:
            self.assertEqual(reader.execute("SELECT value FROM meta WHERE key='setup_identity'").fetchone()[0], initial['setup_identity'])
        finally:
            reader.close()

    def test_storage_proposal_can_be_reviewed_without_database_consent(self):
        self.installation["storage"]["decision_accepted"] = False
        result = self.cli("storage-plan")
        self.assertFalse(result["decision_accepted"])
        self.assertFalse(Path(self.installation["storage"]["database_path"]).exists())
        with self.assertRaisesRegex(ValueError, "discussion/decision"):
            self.cli("init")

    def test_database_must_live_outside_checkout(self):
        self.installation["storage"]["database_path"] = str(ROOT / "state" / "private.sqlite3")
        with self.assertRaisesRegex(ValueError, "outside"):
            validate_installation(self.installation)

    def test_personal_settings_preserve_shared_statistical_rules(self):
        self.installation["family_alpha"] = 1
        with self.assertRaisesRegex(ValueError, "shared validation"):
            validate_installation(self.installation)

    def test_arbitrary_exchange_currency_budget_and_fractional_lots(self):
        installation = completed_installation(self.folder, currency="EUR", cash="2575.00", timezone="Europe/Berlin", lot="0.25")
        store = open_store(build_runtime_settings(installation), initialize=True)
        try:
            clock = DemoClock()
            store.clock = clock
            engine = Engine(store, build_runtime_settings(installation))
            portfolio = Portfolio(engine)
            portfolio.fill("actual-report", "SYNTH", "buy", "0.75", "20", "1", clock())
            reported = json.loads(store.db.execute("SELECT data FROM fills").fetchone()[0])
            self.assertEqual(reported["currency"], "EUR")
            self.assertEqual(reported["quantity"], "0.75")
            self.assertEqual(reported["fee"], "1")
            with self.assertRaisesRegex(ValueError, "lot size"):
                portfolio.fill("bad-lot", "SYNTH", "buy", "0.1", "20", "0", clock())
        finally:
            store.close()

    def test_quote_currency_mismatch_rejected_without_assumed_fx(self):
        engine_settings = build_runtime_settings(self.installation)
        store = open_store(engine_settings, initialize=True)
        try:
            engine = Engine(store, engine_settings)
            with self.assertRaisesRegex(ValueError, "currency"):
                engine.record_price("SYNTH", store.clock(), 10, currency="EUR", source="synthetic://quote")
        finally:
            store.close()

    def test_installations_cannot_share_or_relabel_one_ledger(self):
        first = build_runtime_settings(self.installation)
        store = open_store(first, initialize=True)
        identity = store.identity
        store.close()
        other = copy.deepcopy(self.installation)
        other["profile_id"] = "different-owner"
        with self.assertRaisesRegex(ValueError, "another installation"):
            open_store(build_runtime_settings(other), initialize=True)
        store = open_store(first)
        self.assertEqual(store.identity, identity)
        store.close()

    def test_budget_change_cannot_recalculate_existing_cash(self):
        store = open_store(build_runtime_settings(self.installation), initialize=True)
        store.close()
        self.installation["starting_cash"] = "5000"
        with self.assertRaisesRegex(ValueError, "Frozen"):
            open_store(build_runtime_settings(self.installation))

    def test_newer_schema_blocks_without_silent_migration(self):
        store = open_store(build_runtime_settings(self.installation), initialize=True)
        store.db.execute("PRAGMA user_version=2")
        store.close()
        with self.assertRaisesRegex(ValueError, "schema"):
            open_store(build_runtime_settings(self.installation))

    def test_read_commands_do_not_initialize_missing_database(self):
        self.assertEqual(self.cli("doctor")["stage"], "DATABASE_NOT_INITIALIZED")
        with self.assertRaises(ValueError):
            self.cli("status")
        self.assertFalse(Path(self.installation["storage"]["database_path"]).exists())

    def test_existing_unbound_database_requires_explicit_backup_and_adoption(self):
        cfg = build_runtime_settings(self.installation)
        legacy = Store(cfg["storage"]["database_path"], create=True)
        frozen = {key: cfg[key] for key in FROZEN if key != "base_currency"}
        legacy.db.execute("INSERT INTO meta VALUES('frozen_settings',?)", (canonical(frozen),))
        legacy.event("legacy_evidence", note="Preserve this")
        identity = legacy.identity
        legacy.close()
        with self.assertRaisesRegex(ValueError, "unbound"):
            open_store(cfg, initialize=True)
        result = adopt(cfg, cfg["base_currency"], cfg["starting_cash"])
        self.assertTrue(Path(result["backup"]).exists())
        self.assertEqual(Path(result["backup"]).stat().st_mode & 0o777, 0o600)
        store = open_store(cfg)
        try:
            self.assertEqual(store.identity, identity)
            self.assertEqual(store.db.execute("SELECT COUNT(*) FROM events WHERE kind='legacy_evidence'").fetchone()[0], 1)
        finally:
            store.close()

    def test_online_backup_includes_committed_wal_events(self):
        store = open_store(build_runtime_settings(self.installation), initialize=True)
        try:
            store.event("backup-proof", proof="present")
            from investment_engine.knowledge import Knowledge
            with Knowledge(build_runtime_settings(self.installation), store.identity, create=True):
                pass
            target = self.folder / "backups" / "snapshot.zip"
            snapshot(build_runtime_settings(self.installation), store, target)
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(ValueError, "already exists"):
                snapshot(build_runtime_settings(self.installation), store, target)
            extracted = self.folder / "restored.sqlite3"
            with zipfile.ZipFile(target) as archive:
                extracted.write_bytes(archive.read("ledger.sqlite3"))
            reader = sqlite3.connect(extracted)
            try:
                self.assertEqual(reader.execute("SELECT COUNT(*) FROM events WHERE kind='backup-proof'").fetchone()[0], 1)
            finally:
                reader.close()
        finally:
            store.close()

    def test_legacy_incompatible_trade_data_blocks_adoption_without_rebinding(self):
        cfg = build_runtime_settings(self.installation)
        legacy = Store(cfg["storage"]["database_path"], create=True)
        legacy.db.execute("INSERT INTO meta VALUES('frozen_settings',?)",
                          (canonical({key: cfg[key] for key in FROZEN}),))
        legacy.db.execute("INSERT INTO ideas VALUES('old-idea','2025-01-01',?)",
                          (canonical({"notional_old_currency": "100", "expires_at": "2025-01-02"}),))
        legacy.close()
        with self.assertRaisesRegex(ValueError, "explicit migration"):
            adopt(cfg, cfg["base_currency"], cfg["starting_cash"])
        connection = sqlite3.connect(cfg["storage"]["database_path"])
        try:
            self.assertIsNone(connection.execute("SELECT value FROM meta WHERE key='profile_id'").fetchone())
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM ideas").fetchone()[0], 1)
        finally:
            connection.close()

    def test_configuration_revisions_saved_once_per_content_hash(self):
        for _ in range(2):
            store = open_store(build_runtime_settings(self.installation), initialize=True)
            store.close()
        self.installation["notification"]["destination"] = "synthetic://changed-destination"
        store = open_store(build_runtime_settings(self.installation))
        try:
            self.assertEqual(store.db.execute("SELECT COUNT(*) FROM events WHERE kind='profile_revision'").fetchone()[0], 2)
        finally:
            store.close()

    def test_financial_exports_cannot_be_written_into_checkout(self):
        self.cli("init")
        for command in ("export", "backup"):
            with self.assertRaisesRegex(ValueError, "outside"):
                self.cli(command, "--output", str(ROOT / "private-record.json"))

    def test_monitoring_uses_configuration_without_cached_deployment(self):
        self.cli("init")
        result = self.cli("run", "--offline")
        self.assertEqual(result["registered"], [])

    def test_known_legacy_currency_blocks_empty_ledger_relabel(self):
        for location in ("frozen", "metadata"):
            with self.subTest(location=location), tempfile.TemporaryDirectory() as folder:
                cfg = build_runtime_settings(completed_installation(folder))
                legacy = Store(cfg["storage"]["database_path"], create=True)
                frozen = {key: cfg[key] for key in FROZEN}
                if location == "frozen":
                    frozen["base_currency"] = "EUR"
                else:
                    legacy.db.execute("INSERT INTO meta VALUES('base_currency','EUR')")
                legacy.db.execute("INSERT INTO meta VALUES('frozen_settings',?)", (canonical(frozen),))
                legacy.event("legacy-proof", value="keep")
                before = list(legacy.db.execute("SELECT * FROM meta"))
                identity = legacy.identity
                legacy.close()
                with self.assertRaisesRegex(ValueError, "currency differs"):
                    adopt(cfg, "USD", cfg["starting_cash"])
                reader = sqlite3.connect(cfg["storage"]["database_path"])
                try:
                    self.assertEqual(reader.execute("SELECT * FROM meta").fetchall(), [tuple(r) for r in before])
                    self.assertEqual(reader.execute("SELECT value FROM meta WHERE key='setup_identity'").fetchone()[0], identity)
                    self.assertEqual(reader.execute("SELECT count(*) FROM events WHERE kind='legacy-proof'").fetchone()[0], 1)
                finally:
                    reader.close()

    def test_private_json_creates_private_directories_under_default_umask(self):
        from investment_engine.configuration import write_private_json
        ancestor = self.folder / "shared"
        ancestor.mkdir(mode=0o755)
        target = ancestor / "private" / "nested" / "data.json"
        previous = os.umask(0o022)
        try:
            write_private_json(target, {"private": "evidence"})
        finally:
            os.umask(previous)
        self.assertEqual(ancestor.stat().st_mode & 0o777, 0o755)
        for directory in (target.parent, target.parent.parent):
            self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_initialization_and_snapshot_create_private_missing_ancestors(self):
        root = self.folder / "new" / "owner"
        installation = completed_installation(root)
        installation["storage"]["backup_directory"] = str(root / "private" / "backups")
        previous = os.umask(0o022)
        try:
            with patch.dict(os.environ, native_environment(installation)):
                execute(parser().parse_args(["init"]))
                execute(parser().parse_args(["backup", "snapshot", "--output", str(root / "private" / "backups" / "copy.zip")]))
        finally:
            os.umask(previous)
        for directory in (root.parent, root, root / "data", root / "private", root / "private" / "backups"):
            self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
