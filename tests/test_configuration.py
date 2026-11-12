import copy
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from squad.cli import execute, parser
from squad.configuration import configuration_template, settings, validate_profile
from squad.demo import DemoClock, spec_fixture
from squad.engine import Engine
from squad.portfolio import Portfolio
from squad.storage import FROZEN, adopt, backup, backup_due, open_store
from squad.store import Store
from squad.util import ROOT, canonical
from tests.fixtures import completed_profile, native_environment


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.path = self.folder / "profile.json"
        self.profile = completed_profile(self.folder)

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *args):
        with patch.dict(os.environ, native_environment(self.profile)):
            return execute(parser().parse_args(list(args)))

    def test_fresh_checkout_has_no_personal_profile_or_implicit_database(self):
        with patch.dict(os.environ, {}, clear=True):
            result = execute(parser().parse_args(["doctor"]))
            self.assertEqual(result["stage"], "ONBOARDING_REQUIRED")
            self.assertFalse(result["database_created"])
            with self.assertRaisesRegex(ValueError, "Onboarding"):
                execute(parser().parse_args(["init"]))

    def test_template_is_unconfigured_and_cannot_initialize(self):
        template = configuration_template()
        with self.assertRaises(ValueError):
            validate_profile(template)

    def test_storage_proposal_can_be_reviewed_without_database_consent(self):
        self.profile["storage"]["decision_accepted"] = False
        result = self.cli("storage-plan")
        self.assertFalse(result["decision_accepted"])
        self.assertFalse(Path(self.profile["storage"]["database_path"]).exists())
        with self.assertRaisesRegex(ValueError, "discussion/decision"):
            self.cli("init")

    def test_removed_configuration_file_interfaces_are_rejected(self):
        import contextlib
        import io
        for arguments in (['--profile', str(self.path), 'init'], ['configure', '--file', str(self.path)], ['--db', '/private/ledger.sqlite3', 'status']):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parser().parse_args(arguments)
        self.assertFalse(self.path.exists())

    def test_profile_and_database_must_live_outside_checkout(self):
        self.profile["storage"]["database_path"] = str(ROOT / "state" / "private.sqlite3")
        with self.assertRaisesRegex(ValueError, "outside"):
            validate_profile(self.profile)

    def test_statistical_rules_cannot_be_overridden_by_private_profile(self):
        self.profile["family_alpha"] = 1
        with self.assertRaisesRegex(ValueError, "shared validation"):
            validate_profile(self.profile)

    def test_arbitrary_exchange_currency_budget_and_fractional_lots(self):
        profile = completed_profile(self.folder, currency="EUR", cash="2575.00", timezone="Europe/Berlin", lot="0.25")
        store = open_store(settings(profile), initialize=True)
        try:
            clock = DemoClock()
            store.clock = clock
            engine = Engine(store, settings(profile))
            portfolio = Portfolio(engine)
            portfolio.fill("actual-report", "SYNTH", "buy", "0.75", "20", "1", clock())
            balance = portfolio.balance()
            self.assertEqual(balance["currency"], "EUR")
            self.assertEqual(balance["cash"], "2559.00")
            self.assertEqual(balance["holdings"], {"SYNTH": "0.75"})
            with self.assertRaisesRegex(ValueError, "lot size"):
                portfolio.fill("bad-lot", "SYNTH", "buy", "0.1", "20", "0", clock())
        finally:
            store.close()

    def test_quote_currency_mismatch_rejected_without_assumed_fx(self):
        engine_settings = settings(self.profile)
        store = open_store(engine_settings, initialize=True)
        try:
            engine = Engine(store, engine_settings)
            with self.assertRaisesRegex(ValueError, "currency"):
                engine.record_price("SYNTH", store.clock(), 10, currency="EUR", source="synthetic://quote")
        finally:
            store.close()

    def test_two_profiles_cannot_share_or_relabel_one_ledger(self):
        first = settings(self.profile)
        store = open_store(first, initialize=True)
        identity = store.identity
        store.close()
        other = copy.deepcopy(self.profile)
        other["profile_id"] = "different-owner"
        with self.assertRaisesRegex(ValueError, "another profile"):
            open_store(settings(other), initialize=True)
        store = open_store(first)
        self.assertEqual(store.identity, identity)
        store.close()

    def test_budget_change_cannot_recalculate_existing_cash(self):
        store = open_store(settings(self.profile), initialize=True)
        store.close()
        self.profile["starting_cash"] = "5000"
        with self.assertRaisesRegex(ValueError, "Frozen"):
            open_store(settings(self.profile))

    def test_newer_schema_blocks_without_silent_migration(self):
        store = open_store(settings(self.profile), initialize=True)
        store.db.execute("PRAGMA user_version=2")
        store.close()
        with self.assertRaisesRegex(ValueError, "schema"):
            open_store(settings(self.profile))

    def test_read_commands_do_not_initialize_missing_database(self):
        self.assertEqual(self.cli("doctor")["stage"], "DATABASE_NOT_INITIALIZED")
        with self.assertRaises(ValueError):
            self.cli("status")
        self.assertFalse(Path(self.profile["storage"]["database_path"]).exists())

    def test_existing_unbound_database_requires_explicit_backup_and_adoption(self):
        cfg = settings(self.profile)
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
        store = open_store(settings(self.profile), initialize=True)
        try:
            store.event("backup-proof", proof="present")
            target = self.folder / "backups" / "snapshot.sqlite3"
            backup(store, target)
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(ValueError, "already exists"):
                backup(store, target)
            reader = sqlite3.connect(target)
            try:
                self.assertEqual(reader.execute("SELECT COUNT(*) FROM events WHERE kind='backup-proof'").fetchone()[0], 1)
            finally:
                reader.close()
        finally:
            store.close()

    def test_legacy_incompatible_trade_data_blocks_adoption_without_rebinding(self):
        cfg = settings(self.profile)
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

    def test_profile_revisions_are_preserved_once_per_content_hash(self):
        for _ in range(2):
            store = open_store(settings(self.profile), initialize=True)
            store.close()
        self.profile["notification"]["destination"] = "synthetic://changed-destination"
        store = open_store(settings(self.profile))
        try:
            self.assertEqual(store.db.execute("SELECT COUNT(*) FROM events WHERE kind='profile_revision'").fetchone()[0], 2)
        finally:
            store.close()

    def test_financial_exports_cannot_be_written_into_checkout(self):
        self.cli("init")
        for command in ("export", "backup"):
            with self.assertRaisesRegex(ValueError, "outside"):
                self.cli(command, "--output", str(ROOT / "private-record.json"))

    def test_monitoring_blocks_before_native_deployment(self):
        self.cli("init")
        with self.assertRaisesRegex(ValueError, "Deployment"):
            self.cli("run", "--offline")
        preflight = self.cli("run", "--offline", "--preflight")
        self.assertEqual(preflight["registered"], [])

    def test_backup_policy_skips_recent_copy_and_recovers_missing_copy(self):
        cfg = settings(self.profile)
        store = open_store(cfg, initialize=True)
        try:
            first = backup_due(store, cfg)
            self.assertTrue(first["created"])
            self.assertFalse(backup_due(store, cfg)["created"])
            Path(first["backup"]).unlink()
            recovered = backup_due(store, cfg)
            self.assertTrue(recovered["created"])
            self.assertTrue(Path(recovered["backup"]).is_file())
        finally:
            store.close()
