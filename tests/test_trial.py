import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from investment_engine.engine import Engine
from investment_engine.ledger import Store
from investment_engine.runner import run
from investment_engine.trial import review_trial, trial_status
from tests.fixtures import DemoClock, demo_settings, formal_test, historical_fixture, spec_fixture


class LiveTrialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clock = DemoClock()
        self.store = Store(Path(self.temp.name) / 'ledger.sqlite3', mode='synthetic', clock=self.clock)
        self.addCleanup(self.store.close)
        self.engine = Engine(self.store, demo_settings())
        self.spec = spec_fixture()
        self.engine.discover(self.spec)
        formal_test(self.engine, self.spec['id'], historical_fixture())

    def predict(self, event):
        return self.engine.register(self.spec['id'], event, event_available_at=self.clock(), quote_at=self.clock(),
                                    reference_price=10, feature_value=1, source='synthetic://event')

    def test_first_forecast_starts_thirty_days_and_expiry_stops_downloads(self):
        self.assertEqual(trial_status(self.engine)['status'], 'not_started')
        self.predict('first')
        self.assertEqual(trial_status(self.engine)['status'], 'active')
        self.clock.advance(days=30)
        with patch('investment_engine.feeds.market') as market:
            result = run(self.engine, continue_work=True)
        market.assert_not_called()
        self.assertEqual(result['trial']['status'], 'review_required')
        with self.assertRaisesRegex(ValueError, 'trial ended'):
            self.predict('blocked')

    def test_first_prediction_included_when_clock_advances_between_writes(self):
        value = self.clock()
        def ticking_clock():
            nonlocal value
            value += timedelta(microseconds=1)
            return value
        self.store.clock = ticking_clock
        self.predict('first')
        self.assertEqual(trial_status(self.engine)['signals'][0]['registered'], 1)

    def test_review_shows_losses_and_pending_and_requires_user_decision(self):
        self.predict('loss')
        self.clock.advance(days=1)
        self.engine.record_price('SYNTH', self.clock(), 9.8, source='synthetic://close')
        self.engine.evaluate()
        self.clock.advance(minutes=1)
        self.predict('pending')
        report = trial_status(self.engine)
        self.assertEqual(report['signals'][0]['failures'], 1)
        self.assertEqual(report['signals'][0]['pending'], 1)
        self.assertLess(report['signals'][0]['forecast_compounded_net_return'], 0)
        self.assertLess(report['signals'][0]['buy_and_hold_net_return'], 0)
        with self.assertRaisesRegex(ValueError, 'user approval'):
            review_trial(self.engine, decision='continue', reason='Reviewed results', user_approval='')
        review_trial(self.engine, decision='stop', reason='Reviewed results', user_approval='synthetic://user/stop')
        stopped = trial_status(self.engine)
        self.assertEqual(stopped['status'], 'stopped')
        self.assertEqual(stopped['signals'][0]['failures'], 1)
        with self.assertRaisesRegex(ValueError, '1 to 30'):
            review_trial(self.engine, decision='continue', reason='Reviewed results', user_approval='synthetic://user/continue', days=31)
        review_trial(self.engine, decision='continue', reason='Reviewed all results', user_approval='synthetic://user/continue', days=7)
        self.assertEqual(trial_status(self.engine)['status'], 'active')
        self.assertEqual(self.engine.record(self.spec['id'])['registered'], 2)
        self.clock.advance(days=7)
        self.assertEqual(trial_status(self.engine)['status'], 'review_required')
