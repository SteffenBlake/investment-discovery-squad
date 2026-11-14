import copy
import io
import json
import os
import sqlite3
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from investment_engine.cli import execute, parser
from tests.fixtures import DemoClock, acceptance, historical_fixture, spec_fixture, demo_settings
from investment_engine.engine import Engine
from investment_engine.feeds import fetch_json, observed_feature, record_attention
from investment_engine.portfolio import Portfolio
from investment_engine.runner import run
from investment_engine.ledger import Store
from investment_engine.util import canonical, digest, stamp
from tests.fixtures import completed_installation, native_environment, formal_test, prepare_test_fixture


class SquadTests(unittest.TestCase):
    def setUp(self):
        remote = patch('investment_engine.drive.Drive.list', return_value=[])
        remote.start()
        self.addCleanup(remote.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.sqlite3"
        self.clock = DemoClock()
        self.settings = demo_settings()
        self.store = Store(self.path, mode="synthetic", clock=self.clock)
        self.engine = Engine(self.store, self.settings)
        self.spec = spec_fixture()
        self.engine.discover(self.spec)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def validated(self):
        return formal_test(self.engine, self.spec["id"], historical_fixture())

    def predict(self, event="episode-1"):
        return self.engine.register(self.spec["id"], event,
                                    event_available_at=self.clock() - timedelta(seconds=1),
                                     quote_at=self.clock(),
                                    reference_price=10, source="synthetic://test", feature_value=1.0)

    def snapshot(self, cash="1000.00", holdings=None):
        return {"cash": cash, "currency": "USD", "holdings": holdings or {}, "as_of": stamp(self.clock())}

    def outcome(self, win=True):
        self.clock.advance(days=1)
        self.engine.record_price(self.spec["symbol"], self.clock(), 10.2 if win else 9.8,
                                 source="synthetic://market")
        self.engine.evaluate()
        self.clock.advance(minutes=1)

    def qualified(self):
        self.validated()
        for index in range(3):
            self.predict(f"episode-{index}")
            self.outcome()

    def test_required_acceptance_fixture(self):
        result = acceptance(self.settings)
        self.assertTrue(result["passed"])
        self.assertEqual(result["full_record"]["successes"], 3)
        self.assertEqual(result["full_record"]["failures"], 1)
        self.assertEqual(result["persisted_state_after_restart"], "ALERTED")
        self.assertEqual(result["alert_count_after_repeat_and_restart"], 1)

    def test_historical_pass_is_not_live_success(self):
        result = self.validated()
        self.assertTrue(result["passed"])
        self.assertEqual(self.store.state(self.spec["id"]), "QUALIFIED")
        self.assertEqual(self.engine.record(self.spec["id"])["successes"], 0)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0], 1)

    def test_portfolio_context_combines_graph_with_complete_live_counts(self):
        from investment_engine.briefing import portfolio_context
        from investment_engine.knowledge import Knowledge
        from tests.fixtures import research_batch
        self.validated()
        for index, win in enumerate((True, True, False, True)):
            self.predict('context-episode-' + str(index))
            self.outcome(win)
        self.settings['storage'] = {'knowledge_path': str(Path(self.temp.name) / 'research.lbdb')}
        with Knowledge(self.settings, self.store.identity, create=True) as graph:
            graph.ingest(research_batch())
        result = portfolio_context(self.engine, {'cash': '1000', 'currency': 'USD', 'holdings': {'SYNTH': '0'}})
        signal = result['signals'][0]
        self.assertEqual((signal['forward']['registered'], signal['forward']['successes'], signal['forward']['failures']), (4, 3, 1))
        self.assertEqual(signal['state'], 'QUALIFIED')
        self.assertTrue(signal['historical']['passed'])
        self.assertEqual(signal['historical']['rule']['direction'], 'up')
        self.assertEqual(signal['definition']['mechanism'], self.spec['mechanism'])
        self.assertEqual(len(result['knowledge']['claims']), 1)
        self.assertTrue(result['portfolio_supplied_by_user'])
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM fills').fetchone()[0], 0)

    def test_look_ahead_rejected(self):
        dataset = historical_fixture()
        dataset["rows"][0]["available_at"] = dataset["rows"][0]["exit_at"]
        with self.assertRaisesRegex(ValueError, "Look-ahead"):
            formal_test(self.engine, self.spec["id"], dataset)

    def test_overlapping_historical_windows_rejected(self):
        dataset = historical_fixture()
        dataset["rows"][1] = copy.deepcopy(dataset["rows"][0])
        with self.assertRaisesRegex(ValueError, "disjoint"):
            formal_test(self.engine, self.spec["id"], dataset)

    def test_unverified_historical_availability_cannot_pass(self):
        holdout = prepare_test_fixture(self.engine, self.spec['id'], historical_fixture())
        holdout['availability_verified'] = False
        result = self.engine.backtest(self.spec['id'], holdout)
        self.assertFalse(result['passed'])
        self.assertEqual(self.store.state(self.spec['id']), 'REJECTED')

    def test_supplied_pass_flag_cannot_override_baseline_failure(self):
        dataset = historical_fixture()
        dataset["passed"] = True
        for row in dataset["rows"]:
            row["exit_price"] = row["entry_price"]
        result = formal_test(self.engine, self.spec["id"], dataset)
        self.assertFalse(result["passed"])

    def test_hypothesis_correction_counts_rejected_trials(self):
        dataset = historical_fixture()
        for row in dataset['rows'][540:]:
            row['exit_price'] = row['entry_price']
        self.assertFalse(formal_test(self.engine, self.spec['id'], dataset)['passed'])
        self.settings['max_candidates_per_day'] = 2
        other = {**spec_fixture('candidate-2'), 'input_id': 'shipping:delays', 'feature_formula': {'operation': 'difference'}}
        self.engine.discover(other)
        self.clock.advance(days=4000)
        result = formal_test(self.engine, other['id'], historical_fixture(start=self.clock() - timedelta(days=2000)))
        self.assertEqual(result['trial_number'], 2)
        self.assertAlmostEqual(result['alpha'], 0.05 / 6)

    def test_holdout_cannot_be_retested(self):
        self.validated()
        with self.assertRaises(ValueError):
            self.validated()

    def test_holdout_does_not_choose_threshold_or_direction(self):
        dataset = historical_fixture()
        result = formal_test(self.engine, self.spec["id"], dataset)
        from investment_engine.backtesting import validate
        for row in dataset["rows"][540:]:
            row["exit_price"] = 100
        plan = json.loads(self.store.db.execute('SELECT data FROM test_plans').fetchone()[0])
        altered = validate({**dataset, 'rows': dataset['rows'][540:]}, self.spec, plan, self.clock())
        self.assertEqual(result["rule"], altered["rule"])
        self.assertFalse(altered["passed"])

    def test_synthetic_evidence_cannot_enter_production(self):
        production = Store(Path(self.temp.name) / "production.sqlite3", clock=self.clock, create=True)
        try:
            engine = Engine(production, self.settings)
            engine.discover(self.spec)
            with self.assertRaisesRegex(ValueError, "Synthetic"):
                formal_test(engine, self.spec["id"], historical_fixture())
        finally:
            production.close()

    def test_synthetic_db_cannot_reopen_as_production(self):
        with self.assertRaisesRegex(ValueError, "mode"):
            Store(self.path)

    def test_live_registration_requires_validated_history(self):
        with self.assertRaisesRegex(ValueError, "Historical validation"):
            self.predict()

    def test_future_or_stale_reference_quote_rejected(self):
        self.validated()
        for age in (timedelta(minutes=16), timedelta(seconds=-1)):
            with self.assertRaises(ValueError):
                self.engine.register(self.spec["id"], str(age), event_available_at=self.clock(),
                                      quote_at=self.clock() - age,
                                     reference_price=10, source="synthetic://test", feature_value=1.0)

    def test_live_windows_cannot_overlap(self):
        self.validated()
        self.predict()
        with self.assertRaisesRegex(ValueError, "unresolved"):
            self.predict("different-event")

    def test_event_cannot_count_twice_after_maturity(self):
        self.validated()
        self.predict()
        self.outcome()
        with self.assertRaisesRegex(ValueError, "already registered"):
            self.predict()

    def test_prediction_and_outcome_immutable(self):
        self.validated()
        prediction = self.predict()
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.db.execute("UPDATE predictions SET due_at=? WHERE id=?", (stamp(self.clock()), prediction))
        self.outcome()
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.db.execute("DELETE FROM outcomes")

    def test_waits_for_horizon_and_actual_endpoint(self):
        self.validated()
        self.predict()
        self.engine.record_price(self.spec["symbol"], self.clock(), 100, source="synthetic://early")
        self.assertEqual(self.engine.evaluate(), [])
        self.clock.advance(days=1)
        self.assertEqual(self.engine.evaluate(), [])
        self.assertEqual(self.engine.record(self.spec["id"])["pending"], 1)
        self.engine.record_price(self.spec["symbol"], self.clock(), 10.2, source="synthetic://mature")
        self.assertEqual(len(self.engine.evaluate()), 1)
        self.assertEqual(self.engine.evaluate(), [])

    def test_failure_is_retained(self):
        self.validated()
        self.predict()
        self.outcome(False)
        record = self.engine.record(self.spec["id"])
        self.assertEqual((record["successes"], record["failures"]), (0, 1))

    def test_price_revision_does_not_rewrite_outcome(self):
        self.validated()
        self.predict()
        self.clock.advance(days=1)
        self.engine.record_price(self.spec["symbol"], self.clock(), 9.8, source="synthetic://first")
        self.engine.record_price(self.spec["symbol"], self.clock(), 10.5, source="synthetic://revision")
        self.engine.evaluate()
        self.assertEqual(self.engine.record(self.spec["id"])["failures"], 1)

    def test_claim_prevents_duplicate_delivery_across_connections(self):
        self.qualified()
        alert_id = self.store.db.execute("SELECT id FROM outbox").fetchone()[0]
        claim = self.engine.claim(alert_id)
        other_store = Store(self.path, mode="synthetic", clock=self.clock)
        try:
            other = Engine(other_store, self.settings)
            self.assertIsNone(other.claim(alert_id))
            self.engine.acknowledge(alert_id, claim["token"], "synthetic://receipt")
            self.assertIsNone(other.claim(alert_id))
        finally:
            other_store.close()

    def test_confirmed_non_delivery_can_retry_but_unknown_delivery_cannot(self):
        self.qualified()
        alert_id = self.store.db.execute("SELECT id FROM outbox").fetchone()[0]
        first = self.engine.claim(alert_id)
        self.assertIsNone(self.engine.claim(alert_id))
        with self.assertRaises(ValueError):
            self.engine.release(alert_id, first["token"], "")
        self.engine.release(alert_id, first["token"], "Transport explicitly rejected before sending")
        retry = self.engine.claim(alert_id)
        self.assertNotEqual(first["token"], retry["token"])

    def test_cannot_manually_qualify_signal(self):
        with self.assertRaises(ValueError):
            self.engine.change_state(self.spec["id"], "QUALIFIED", "Trust me")

    def test_invalidated_signal_cannot_qualify(self):
        self.validated()
        self.predict()
        self.engine.change_state(self.spec["id"], "INVALIDATED", "Source withdrew evidence")
        self.outcome()
        self.assertEqual(self.store.state(self.spec["id"]), "INVALIDATED")

    def test_indicator_first_seen_cannot_be_backdated(self):
        rows = [{"at": stamp(self.clock() - timedelta(days=i)), "captured_at": stamp(self.clock()), "value": 100}
                for i in range(1, 31)]
        record_attention(self.store, {"key": "wikipedia:Gold", "source": "synthetic://wiki", "rows": rows})
        self.assertIsNone(observed_feature(self.store, "Gold", as_of=self.clock() - timedelta(days=1)))
        self.assertIsNotNone(observed_feature(self.store, "Gold", as_of=self.clock()))

    def test_reported_fill_is_saved_once_without_reconstructing_account(self):
        portfolio = Portfolio(self.engine)
        args = ("reported-fill-1", "SYNTH", "buy", 2, "20", "0", self.clock())
        self.assertTrue(portfolio.fill(*args))
        self.assertFalse(portfolio.fill(*args))
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM fills").fetchone()[0], 1)
        self.assertFalse(portfolio.balance()["available"])

    def test_reported_fills_can_include_external_account_activity(self):
        portfolio = Portfolio(self.engine)
        for side, units in (("buy", 101), ("sell", 1)):
            self.assertTrue(portfolio.fill(side, "SYNTH", side, units, "10", "0", self.clock()))
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM fills").fetchone()[0], 2)

    def test_degraded_signal_blocks_purchase(self):
        self.validated()
        prediction = self.predict()
        self.engine.change_state(self.spec['id'], 'DEGRADED', 'Mechanism weakened')
        with self.assertRaisesRegex(ValueError, 'qualified'):
            Portfolio(self.engine).idea(prediction, self.snapshot())

    def test_idea_does_not_spend_cash_or_submit_trade(self):
        self.qualified()
        prediction = self.predict("fresh-opportunity")
        portfolio = Portfolio(self.engine)
        idea = portfolio.idea(prediction, self.snapshot())
        self.assertEqual(idea["status"], "recommendation_only")
        self.assertLessEqual(float(idea["notional"]), 1000)
        self.assertEqual(portfolio.balance()["cash"], "1000.00")
        self.assertEqual(portfolio.balance()["holdings"], {})

    def test_runner_returns_delivery_before_feeds_and_redacts_caught_errors(self):
        self.qualified()
        secret = "fake-bound-refresh-token"
        with patch.dict(os.environ, {"SQUAD_GOOGLE_REFRESH_TOKEN": secret}), patch("investment_engine.feeds.market", side_effect=OSError("failed " + secret)) as feed:
            first = run(self.engine)
            feed.assert_not_called()
            self.assertTrue(first["remaining_work"])
            result = run(self.engine, continue_work=True)
        self.assertEqual(len(result["alerts"]), 1)
        self.assertEqual(len(result["errors"]), 1)
        self.assertNotIn(secret, json.dumps(result))
        errors = self.store.db.execute("SELECT data FROM events WHERE kind='run_error'").fetchall()
        self.assertNotIn(secret, str([r[0] for r in errors]))
        self.assertFalse((self.path.parent / "knowledge.json").exists())

    def test_cli_initialization_is_not_claimed_as_live_activation(self):
        with patch.dict('os.environ', native_environment(completed_installation(self.temp.name))):
            init = execute(parser().parse_args(['init']))
            doctor = execute(parser().parse_args(['doctor']))
            self.assertFalse(init['monitoring_active'])
            self.assertTrue(doctor['repo_ready'])
            self.assertFalse(doctor['live_activation_verified'])
            status = execute(parser().parse_args(['status']))
            self.assertEqual(init['setup_identity'], status['setup_identity'])

    def test_historical_qualification_yields_before_portfolio_work(self):
        self.validated()
        with patch.object(Portfolio, 'balance') as balance:
            result = run(self.engine, offline=True)
        balance.assert_not_called()
        self.assertTrue(result['remaining_work'])
        self.assertEqual(len(result['alerts']), 1)
        self.assertEqual(self.engine.record(self.spec['id'])['successes'], 0)

    def test_deadline_comes_from_saved_pattern_duration(self):
        self.validated()
        prediction = self.predict()
        row = self.store.db.execute("SELECT due_at FROM predictions WHERE id=?", (prediction,)).fetchone()
        self.assertEqual(row["due_at"], stamp(self.clock() + timedelta(days=self.spec["horizon_days"])))

    def test_fractional_fill_rejected_without_truncation(self):
        with self.assertRaisesRegex(ValueError, "Fractional"):
            Portfolio(self.engine).fill("fractional", "SYNTH", "buy", 1.5, "10", "0", self.clock())

    def test_idea_expiry_cannot_outlive_quote_freshness(self):
        self.qualified()
        self.clock.advance(minutes=15)
        prediction = self.engine.register(self.spec["id"], "near-stale", event_available_at=self.clock() - timedelta(minutes=15),
                                           
                                           quote_at=self.clock() - timedelta(minutes=14), reference_price=10,
                                           source="synthetic://test", feature_value=1.0)
        idea = Portfolio(self.engine).idea(prediction, self.snapshot())
        self.assertEqual(idea["expires_at"], stamp(self.clock() + timedelta(minutes=1)))

    def test_ambiguous_claim_survives_restart_without_resend(self):
        self.qualified()
        alert_id = self.store.db.execute("SELECT id FROM outbox").fetchone()[0]
        self.engine.claim(alert_id)
        self.store.close()
        self.store = Store(self.path, mode="synthetic", clock=self.clock)
        self.engine = Engine(self.store, self.settings)
        self.assertIsNone(self.engine.claim(alert_id))
        self.assertEqual(self.store.db.execute("SELECT status FROM outbox").fetchone()[0], "claimed")

    def test_split_crossing_forecast_invalidates_instead_of_counting_a_win(self):
        self.validated()
        self.predict()
        split_time = self.clock() + timedelta(hours=12)
        self.clock.advance(days=1)
        with self.store.transaction():
            self.store.event("stock_split", self.spec["id"], market_at=stamp(split_time), ratio="1:10")
        self.engine.record_price(self.spec["symbol"], self.clock(), 100, source="synthetic://split-price")
        self.engine.evaluate()
        self.assertEqual(self.store.state(self.spec["id"]), "INVALIDATED")
        self.assertEqual(self.engine.record(self.spec["id"])["successes"], 0)

    def test_feed_archives_original_response_and_uses_completion_capture_time(self):
        folder = Path(self.temp.name) / "cache"
        request_time = self.clock()
        completion = request_time + timedelta(seconds=10)
        previous = os.umask(0o022)
        try:
            with patch("investment_engine.feeds.urllib.request.urlopen", return_value=io.BytesIO(b'{"value":1}')):
                with patch("investment_engine.feeds.now_utc", return_value=completion):
                    first = fetch_json("https://example.org/data", folder, request_time, ttl_seconds=0)
        finally:
            os.umask(previous)
        for directory in (folder, folder / "archive"):
            self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
        for file in folder.rglob("*.json"):
            self.assertEqual(file.stat().st_mode & 0o777, 0o600)
        with patch("investment_engine.feeds.urllib.request.urlopen", return_value=io.BytesIO(b'{"value":2}')):
            with patch("investment_engine.feeds.now_utc", return_value=completion + timedelta(seconds=1)):
                second = fetch_json("https://example.org/data", folder, completion, ttl_seconds=0)
        self.assertEqual(first["fetched_at"], stamp(completion))
        self.assertNotEqual(first["archive_hash"], second["archive_hash"])
        self.assertEqual(len(list((folder / "archive").glob("*.json"))), 2)
        original = json.loads((folder / "archive" / (first["archive_hash"] + ".json")).read_text())
        self.assertEqual(original["body"], {"value": 1})

    def test_runner_registers_eligible_event_once_without_premature_trade_idea(self):
        self.settings["max_candidates_per_day"] = 2
        spec = spec_fixture("runner-attention-v1")
        spec["article"] = "Gold"
        self.engine.discover(spec)
        dataset = historical_fixture()
        for row in dataset["rows"]:
            row["feature"] *= 2
        self.assertTrue(formal_test(self.engine, spec["id"], dataset)["passed"])
        market = {"symbol": spec["symbol"], "currency": "USD", "source": "synthetic://market",
                  "history": [], "quote": {"at": stamp(self.clock()), "price": 10}, "splits": []}
        observations = [{"at": stamp(self.clock() - timedelta(days=i)), "captured_at": stamp(self.clock()),
                         "value": 1000 if i == 1 else 100} for i in range(1, 101)]
        attention = {"key": "wikipedia:Gold", "source": "synthetic://wiki", "rows": observations}
        with patch("investment_engine.feeds.market", return_value=market), patch("investment_engine.feeds.attention", return_value=attention):
            first = run(self.engine, continue_work=True)
            second = run(self.engine, continue_work=True)
        self.assertEqual(first["errors"], [])
        self.assertEqual(len(first["registered"]), 1)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM ideas").fetchone()[0], 0)
        self.assertEqual(second["registered"], [])

    def test_discovery_enforces_daily_cap_with_idempotent_retry(self):
        self.assertFalse(self.engine.discover(self.spec))
        with self.assertRaisesRegex(ValueError, "candidate cap"):
            self.engine.discover(spec_fixture("over-cap"))
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM specs").fetchone()[0], 1)
        self.settings["timezone"] = "America/Edmonton"
        self.clock.advance(hours=10)
        with self.assertRaisesRegex(ValueError, "candidate cap"):
            self.engine.discover(spec_fixture("same-local-day"))
        self.clock.advance(hours=7)
        self.assertTrue(self.engine.discover(spec_fixture("next-day")))

    def test_malformed_spec_rejected_before_insertion(self):
        self.settings["max_candidates_per_day"] = 20
        for field, value in (("limitations", "bad string"), ("limitations", [""]), ("horizon_days", True), ("name", 12), ("extra", "unknown")):
            spec = {**spec_fixture("malformed"), field: value}
            with self.assertRaises(ValueError):
                self.engine.discover(spec)
        self.assertIsNone(self.store.db.execute("SELECT 1 FROM specs WHERE id='malformed'").fetchone())

    def test_expired_unresolved_forecast_blocks_registration(self):
        self.validated()
        self.predict()
        for day in range(3):
            self.clock.advance(days=1, minutes=1)
            with self.assertRaisesRegex(ValueError, "unresolved"):
                self.predict("expired-" + str(day))
        self.engine.record_price("SYNTH", self.clock(), 10.2, source="synthetic://late-close")
        self.engine.evaluate()
        self.assertEqual(self.engine.record(self.spec["id"])["successes"], 1)
        self.assertEqual(self.store.state(self.spec["id"]), "QUALIFIED")

    def test_reference_quote_must_follow_resolved_endpoint(self):
        self.validated()
        self.predict()
        self.outcome()
        with self.assertRaisesRegex(ValueError, "previous realized endpoint"):
            self.engine.register(self.spec["id"], "old-reference", event_available_at=self.clock() - timedelta(minutes=2),
                                  quote_at=self.clock() - timedelta(minutes=1),
                                 reference_price=10, source="synthetic://test", feature_value=1.0)

    def test_legacy_shared_close_gets_append_only_corrections(self):
        self.validated()
        first = self.predict()
        template = dict(self.store.db.execute("SELECT * FROM predictions WHERE id=?", (first,)).fetchone())
        for index in range(2):
            self.clock.advance(days=1, minutes=1)
            identifier = digest({"legacy": index})[:24]
            data = json.loads(template["data"])
            data["reference_at"] = stamp(self.clock())
            self.store.db.execute("INSERT INTO predictions VALUES(?,?,?,?,?,?)", (identifier, self.spec["id"], "legacy-" + str(index), stamp(self.clock()), stamp(self.clock() + timedelta(days=1)), canonical(data)))
        self.clock.advance(days=1, minutes=1)
        self.engine.record_price("SYNTH", self.clock(), 10.2, source="synthetic://shared-close")
        self.engine.evaluate()
        record = self.engine.record(self.spec["id"])
        self.assertEqual((record["successes"], record["invalidated"]), (1, 2))
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0], 3)
        self.assertEqual(self.store.state(self.spec["id"]), "INVALIDATED")
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0], 1)

    def test_runner_ingests_split_before_evaluating_stored_close(self):
        self.validated()
        self.predict()
        split_at = self.clock() + timedelta(hours=12)
        self.clock.advance(days=1)
        self.engine.record_price("SYNTH", self.clock(), 100, source="synthetic://stored-close")
        market = {"history": [], "quote": {"at": stamp(self.clock() + timedelta(minutes=1)), "price": 100}, "splits": [{"at": stamp(split_at), "ratio": "1:10"}], "source": "synthetic://market"}
        with patch("investment_engine.feeds.market", return_value=market):
            run(self.engine, continue_work=True)
        self.assertEqual(self.engine.record(self.spec["id"])["pending"], 1)
        self.assertEqual(self.store.state(self.spec["id"]), "INVALIDATED")

    def test_late_split_invalidates_support_and_cancels_queued_alert(self):
        start = self.clock()
        self.qualified()
        with self.store.transaction():
            self.store.event("stock_split", self.spec["id"], market_at=stamp(start + timedelta(hours=12)), ratio="1:10")
        self.engine.evaluate()
        record = self.engine.record(self.spec["id"])
        self.assertEqual((record["successes"], record["invalidated"]), (2, 1))
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0], 3)
        self.assertEqual(self.store.state(self.spec["id"]), "INVALIDATED")
        self.assertEqual(self.store.db.execute("SELECT status FROM outbox").fetchone()[0], "cancelled")
        self.engine.evaluate()
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM events WHERE kind='outcome_invalidated'").fetchone()[0], 1)

    def test_claimed_alert_after_late_split_preserves_ambiguity_until_release(self):
        start = self.clock()
        self.qualified()
        alert = self.store.db.execute("SELECT id FROM outbox").fetchone()[0]
        claim = self.engine.claim(alert)
        self.store.event("stock_split", self.spec["id"], market_at=stamp(start + timedelta(hours=12)), ratio="1:10")
        self.engine.evaluate()
        self.assertEqual(self.store.db.execute("SELECT status FROM outbox").fetchone()[0], "claimed")
        self.engine.release(alert, claim["token"], "Native history confirms nothing sent")
        self.assertIsNone(self.engine.claim(alert))
        self.assertEqual(self.store.db.execute("SELECT status FROM outbox").fetchone()[0], "cancelled")

    def test_subcent_actual_cash_cannot_fund_minimum_lot(self):
        self.settings["instruments"][0]["lot_size"] = "0.001"
        portfolio = Portfolio(self.engine)
        self.qualified()
        prediction = self.predict("subcent-idea")
        with self.assertRaisesRegex(ValueError, "Cannot afford"):
            portfolio.idea(prediction, self.snapshot(cash="0.006", holdings={"SYNTH": "1"}))
        self.assertEqual(portfolio.balance()["cash"], "0.006")

    def test_renamed_pattern_rejects_previously_examined_price_windows(self):
        self.validated()
        self.settings["max_candidates_per_day"] = 2
        other = spec_fixture("renamed-pattern")
        self.engine.discover(other)
        dataset = historical_fixture()
        dataset["source"] = "Same price windows under changed provenance text"
        with self.assertRaisesRegex(ValueError, "Same premise already"):
            formal_test(self.engine, other["id"], dataset)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM trials").fetchone()[0], 1)

    def test_forecast_requires_trigger_measurement_and_causal_quote(self):
        threshold = self.validated()["rule"]["threshold"]
        arguments = {"event_available_at": self.clock(), "quote_at": self.clock(),
                     "reference_price": 10, "source": "synthetic://measurement"}
        with self.assertRaisesRegex(ValueError, "frozen historical threshold"):
            self.engine.register(self.spec["id"], "below-trigger", feature_value=threshold, **arguments)
        arguments["quote_at"] = self.clock() - timedelta(seconds=1)
        with self.assertRaisesRegex(ValueError, "follow event availability"):
            self.engine.register(self.spec["id"], "pre-event-quote", feature_value=threshold + 1, **arguments)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM predictions").fetchone()[0], 0)

    def test_forecast_input_cannot_supply_its_own_deadline(self):
        self.validated()
        with self.assertRaises(TypeError):
            self.engine.register(self.spec["id"], "changed-deadline", event_available_at=self.clock(),
                                 quote_at=self.clock(), reference_price=10, feature_value=1,
                                 due_at=self.clock() + timedelta(days=8), source="synthetic://test")

    def test_purchase_uses_actual_cash_and_reserves_fixed_and_unit_fees(self):
        from decimal import Decimal
        self.settings["brokerage"].update(entry_fee_fixed="1", entry_fee_per_unit="0.02")
        self.qualified()
        prediction = self.predict("fee-aware-entry")
        portfolio = Portfolio(self.engine)
        idea = portfolio.idea(prediction, self.snapshot(cash="1001"))
        quantity = Decimal(idea["quantity"])
        limit = Decimal(idea["suggested_limit"])
        self.assertEqual(quantity, Decimal("99"))
        self.assertEqual(Decimal(idea["estimated_entry_fee"]), Decimal("2.98"))
        self.assertLessEqual(Decimal(idea["total_cash_required"]), Decimal("1001"))
        self.assertGreater((quantity + 1) * limit + 1 + (quantity + 1) * Decimal("0.02"), Decimal("1001"))
        self.assertEqual(portfolio.idea(prediction, self.snapshot(cash="1001")), idea)

    def test_purchase_uses_supplied_account_cash_after_external_deposit(self):
        from decimal import Decimal
        self.qualified()
        prediction = self.predict("external-deposit-entry")
        idea = Portfolio(self.engine).idea(prediction, self.snapshot(cash="2000", holdings={"SYNTH": "20"}))
        self.assertGreater(Decimal(idea["notional"]), Decimal(self.settings["starting_cash"]))
        self.assertLessEqual(Decimal(idea["total_cash_required"]), Decimal("2000"))
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM fills").fetchone()[0], 0)

    def test_missing_research_price_is_reported_without_repeated_permanent_events(self):
        self.validated()
        self.predict()
        self.clock.advance(days=9)
        first = run(self.engine, offline=True, continue_work=True)
        second = run(self.engine, offline=True, continue_work=True)
        self.assertEqual(first["blocked_predictions"], second["blocked_predictions"])
        self.assertEqual(len(first["blocked_predictions"]), 1)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM events WHERE kind='evaluation_blocked'").fetchone()[0], 1)


    def test_late_research_correction_is_returned_before_new_purchase(self):
        start = self.clock()
        self.qualified()
        alert = self.store.db.execute("SELECT id FROM outbox").fetchone()[0]
        claim = self.engine.claim(alert)
        self.engine.acknowledge(alert, claim["token"], "synthetic://receipt")
        prediction = self.predict("entry-before-correction")
        self.store.event("stock_split", self.spec["id"], market_at=stamp(start + timedelta(hours=12)), ratio="1:10")
        result = run(self.engine, offline=True)
        self.assertEqual(result["corrections"][0]["signal_id"], self.spec["id"])
        self.assertIn("Split", self.engine.report(self.spec["id"])["corrections"][0]["reason"])
        with self.assertRaisesRegex(ValueError, "qualified signal"):
            Portfolio(self.engine).idea(prediction, self.snapshot())



if __name__ == "__main__":
    unittest.main()
