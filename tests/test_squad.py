import copy
import io
import json
import sqlite3
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from squad.cli import execute, parser
from squad.demo import DemoClock, acceptance, historical_fixture, spec_fixture, demo_settings
from squad.engine import Engine
from squad.feeds import fetch_json, observed_feature, record_attention
from squad.portfolio import Portfolio
from squad.runner import run
from squad.store import Store
from squad.util import config, stamp
from tests.fixtures import completed_profile, native_environment


class SquadTests(unittest.TestCase):
    def setUp(self):
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
        return self.engine.backtest(self.spec["id"], historical_fixture())

    def predict(self, event="episode-1"):
        return self.engine.register(self.spec["id"], event,
                                    event_available_at=self.clock() - timedelta(seconds=1),
                                    due_at=self.clock() + timedelta(days=1), quote_at=self.clock(),
                                    reference_price=10, source="synthetic://test")

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
        self.assertEqual(self.store.state(self.spec["id"]), "FORWARD_TESTING")
        self.assertEqual(self.engine.record(self.spec["id"])["successes"], 0)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0], 0)

    def test_portfolio_context_combines_graph_with_complete_live_counts(self):
        from squad.briefing import portfolio_context
        from squad.knowledge import Knowledge
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
        self.assertFalse(result['reconciliation_required'])
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM fills').fetchone()[0], 0)

    def test_look_ahead_rejected(self):
        dataset = historical_fixture()
        dataset["rows"][0]["available_at"] = dataset["rows"][0]["exit_at"]
        with self.assertRaisesRegex(ValueError, "Look-ahead"):
            self.engine.backtest(self.spec["id"], dataset)

    def test_overlapping_historical_windows_rejected(self):
        dataset = historical_fixture()
        dataset["rows"][1] = copy.deepcopy(dataset["rows"][0])
        with self.assertRaisesRegex(ValueError, "disjoint"):
            self.engine.backtest(self.spec["id"], dataset)

    def test_unverified_historical_availability_cannot_pass(self):
        dataset = historical_fixture()
        dataset["availability_verified"] = False
        result = self.engine.backtest(self.spec["id"], dataset)
        self.assertFalse(result["passed"])
        self.assertEqual(self.store.state(self.spec["id"]), "REJECTED")

    def test_supplied_pass_flag_cannot_override_baseline_failure(self):
        dataset = historical_fixture()
        dataset["passed"] = True
        for row in dataset["rows"]:
            row["exit_price"] = row["entry_price"]
        result = self.engine.backtest(self.spec["id"], dataset)
        self.assertFalse(result["passed"])

    def test_hypothesis_correction_counts_rejected_trials(self):
        dataset = historical_fixture()
        dataset["availability_verified"] = False
        self.engine.backtest(self.spec["id"], dataset)
        other = spec_fixture("candidate-2")
        self.engine.discover(other)
        result = self.engine.backtest(other["id"], historical_fixture())
        self.assertEqual(result["trial_number"], 2)
        self.assertAlmostEqual(result["alpha"], 0.05 / 6)

    def test_holdout_cannot_be_retested(self):
        self.validated()
        with self.assertRaises(ValueError):
            self.validated()

    def test_holdout_does_not_choose_threshold_or_direction(self):
        dataset = historical_fixture()
        result = self.engine.backtest(self.spec["id"], dataset)
        from squad.research import validate
        for row in dataset["rows"][540:]:
            row["exit_price"] = 100
        altered = validate(dataset, self.spec, self.settings, 1, self.clock())
        self.assertEqual(result["rule"], altered["rule"])
        self.assertFalse(altered["passed"])

    def test_synthetic_evidence_cannot_enter_production(self):
        production = Store(Path(self.temp.name) / "production.sqlite3", clock=self.clock, create=True)
        try:
            engine = Engine(production, self.settings)
            engine.discover(self.spec)
            with self.assertRaisesRegex(ValueError, "Synthetic"):
                engine.backtest(self.spec["id"], historical_fixture())
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
                                     due_at=self.clock() + timedelta(days=1), quote_at=self.clock() - age,
                                     reference_price=10, source="synthetic://test")

    def test_live_windows_cannot_overlap(self):
        self.validated()
        self.predict()
        with self.assertRaisesRegex(ValueError, "Overlapping"):
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

    def test_reported_fill_only_changes_portfolio_once(self):
        portfolio = Portfolio(self.engine)
        args = ("reported-fill-1", "SYNTH", "buy", 2, "20", "0", self.clock())
        self.assertTrue(portfolio.fill(*args))
        self.assertFalse(portfolio.fill(*args))
        self.assertEqual(portfolio.balance()["cash"], "960.00")
        self.assertEqual(portfolio.balance()["holdings"], {"SYNTH": "2"})

    def test_fill_rejects_margin_and_shorting(self):
        portfolio = Portfolio(self.engine)
        for side, units in (("buy", 101), ("sell", 1)):
            with self.assertRaises(ValueError):
                portfolio.fill(side, "SYNTH", side, units, "10", "0", self.clock())

    def test_no_trade_idea_before_qualification(self):
        self.validated()
        prediction = self.predict()
        with self.assertRaisesRegex(ValueError, "qualified"):
            Portfolio(self.engine).idea(prediction)

    def test_idea_does_not_spend_cash_or_submit_trade(self):
        self.qualified()
        prediction = self.predict("fresh-opportunity")
        portfolio = Portfolio(self.engine)
        idea = portfolio.idea(prediction)
        self.assertEqual(idea["status"], "recommendation_only")
        self.assertLessEqual(float(idea["notional"]), 1000)
        self.assertEqual(portfolio.balance()["cash"], "1000.00")
        self.assertEqual(portfolio.balance()["holdings"], {})

    def test_runner_survives_feed_failure_and_exports_evidence(self):
        with patch("squad.feeds.market", side_effect=OSError("Source unavailable")):
            result = run(self.engine)
        self.assertEqual(len(result["errors"]), 1)
        self.assertTrue((self.path.parent / "knowledge.json").exists())
        self.assertEqual(self.engine.record(self.spec["id"])["successes"], 0)

    def test_cli_initialization_is_not_claimed_as_live_activation(self):
        with patch.dict('os.environ', native_environment(completed_profile(self.temp.name))):
            init = execute(parser().parse_args(['init']))
            doctor = execute(parser().parse_args(['doctor']))
            self.assertFalse(init['monitoring_active'])
            self.assertTrue(doctor['repo_ready'])
            self.assertFalse(doctor['live_activation_verified'])
            status = execute(parser().parse_args(['status']))
            self.assertEqual(init['setup_identity'], status['setup_identity'])

    def test_delivery_message_includes_losses_and_uncertainty(self):
        self.validated()
        for index, success in enumerate((True, True, False, True)):
            self.predict(f"message-episode-{index}")
            self.outcome(success)
        alert_id = self.store.db.execute("SELECT id FROM outbox").fetchone()[0]
        claim = self.engine.claim(alert_id)
        self.assertIn("3-of-4", claim["message"])
        self.assertIn("failure", claim["message"])
        self.assertIn("Wilson", claim["message"])
        self.assertIn("Evaluated / endpoint", claim["message"])
        self.assertIn("SYNTHETIC TEST", claim["message"])

    def test_horizon_cannot_change_after_backtest(self):
        self.validated()
        with self.assertRaisesRegex(ValueError, "horizon"):
            self.engine.register(self.spec["id"], "wrong-horizon", event_available_at=self.clock(),
                                 due_at=self.clock() + timedelta(hours=1), quote_at=self.clock(),
                                 reference_price=10, source="synthetic://test")

    def test_fractional_fill_rejected_without_truncation(self):
        with self.assertRaisesRegex(ValueError, "Fractional"):
            Portfolio(self.engine).fill("fractional", "SYNTH", "buy", 1.5, "10", "0", self.clock())

    def test_idea_expiry_cannot_outlive_quote_freshness(self):
        self.qualified()
        prediction = self.engine.register(self.spec["id"], "near-stale", event_available_at=self.clock(),
                                           due_at=self.clock() + timedelta(days=1),
                                           quote_at=self.clock() - timedelta(minutes=14), reference_price=10,
                                           source="synthetic://test")
        idea = Portfolio(self.engine).idea(prediction)
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
        with patch("squad.feeds.urllib.request.urlopen", return_value=io.BytesIO(b'{"value":1}')):
            with patch("squad.feeds.now_utc", return_value=completion):
                first = fetch_json("https://example.org/data", folder, request_time, ttl_seconds=0)
        with patch("squad.feeds.urllib.request.urlopen", return_value=io.BytesIO(b'{"value":2}')):
            with patch("squad.feeds.now_utc", return_value=completion + timedelta(seconds=1)):
                second = fetch_json("https://example.org/data", folder, completion, ttl_seconds=0)
        self.assertEqual(first["fetched_at"], stamp(completion))
        self.assertNotEqual(first["archive_hash"], second["archive_hash"])
        self.assertEqual(len(list((folder / "archive").glob("*.json"))), 2)
        original = json.loads((folder / "archive" / (first["archive_hash"] + ".json")).read_text())
        self.assertEqual(original["body"], {"value": 1})

    def test_runner_registers_eligible_event_once_without_premature_trade_idea(self):
        spec = spec_fixture("runner-attention-v1")
        spec["article"] = "Gold"
        self.engine.discover(spec)
        dataset = historical_fixture()
        for row in dataset["rows"]:
            row["feature"] *= 2
        self.assertTrue(self.engine.backtest(spec["id"], dataset)["passed"])
        market = {"symbol": spec["symbol"], "currency": "USD", "source": "synthetic://market",
                  "history": [], "quote": {"at": stamp(self.clock()), "price": 10}, "splits": []}
        observations = [{"at": stamp(self.clock() - timedelta(days=i)), "captured_at": stamp(self.clock()),
                         "value": 1000 if i == 1 else 100} for i in range(1, 101)]
        attention = {"key": "wikipedia:Gold", "source": "synthetic://wiki", "rows": observations}
        with patch("squad.feeds.market", return_value=market), patch("squad.feeds.attention", return_value=attention):
            first = run(self.engine)
            second = run(self.engine)
        self.assertEqual(first["errors"], [])
        self.assertEqual(len(first["registered"]), 1)
        self.assertEqual(first["ideas"], [])
        self.assertEqual(second["registered"], [])


if __name__ == "__main__":
    unittest.main()
