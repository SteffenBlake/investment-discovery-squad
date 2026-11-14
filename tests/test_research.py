import json
import sqlite3
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from investment_engine.engine import Engine
from investment_engine.ledger import Store
from investment_engine.provisioning import check_initialization_target
from investment_engine.runner import run
from investment_engine.util import stamp
from tests.fixtures import DemoClock, completed_installation, demo_settings, historical_fixture, prepare_test_fixture, spec_fixture


class HistoricalResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clock = DemoClock()
        self.settings = demo_settings()
        self.settings['max_candidates_per_day'] = 20
        self.store = Store(Path(self.temp.name) / 'ledger.sqlite3', mode='synthetic', clock=self.clock)
        self.addCleanup(self.store.close)
        self.engine = Engine(self.store, self.settings)
        self.spec = spec_fixture()
        self.engine.discover(self.spec)

    def test_plan_required_and_immutable(self):
        with self.assertRaisesRegex(ValueError, 'prepare-test'):
            self.engine.backtest(self.spec['id'], historical_fixture())
        dataset = historical_fixture()
        prepare_test_fixture(self.engine, self.spec['id'], dataset)
        with self.assertRaisesRegex(ValueError, 'immutable'):
            prepare_test_fixture(self.engine, self.spec['id'], dataset)
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.db.execute('DELETE FROM test_plans')

    def test_broken_input_can_be_repaired_against_same_plan(self):
        holdout = prepare_test_fixture(self.engine, self.spec['id'], historical_fixture())
        damaged = {**holdout, 'rows': holdout['rows'][:-1]}
        result = self.engine.backtest(self.spec['id'], damaged)
        self.assertFalse(result['tested'])
        self.assertEqual(self.store.state(self.spec['id']), 'DISCOVERED')
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM trials').fetchone()[0], 0)
        self.assertTrue(self.engine.backtest(self.spec['id'], holdout)['passed'])
        with self.assertRaisesRegex(ValueError, 'One test'):
            self.engine.backtest(self.spec['id'], holdout)

    def test_invalid_number_records_error_and_allows_corrected_input(self):
        holdout = prepare_test_fixture(self.engine, self.spec['id'], historical_fixture())
        feature = holdout['rows'][-1]['feature']
        holdout['rows'][-1]['feature'] = float('nan')
        result = self.engine.backtest(self.spec['id'], holdout)
        self.assertFalse(result['tested'])
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM events WHERE kind='test_submission_invalid'").fetchone()[0], 1)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM trials').fetchone()[0], 0)
        holdout['rows'][-1]['feature'] = feature
        self.assertTrue(self.engine.backtest(self.spec['id'], holdout)['passed'])

    def test_related_retry_requires_new_input_and_operation_and_later_holdout(self):
        holdout = prepare_test_fixture(self.engine, self.spec['id'], historical_fixture())
        for row in holdout['rows']:
            row['exit_price'] = row['entry_price']
        self.assertFalse(self.engine.backtest(self.spec['id'], holdout)['passed'])
        for index, changes in enumerate([{}, {'input_id': 'shipping:delays'}, {'feature_formula': {'operation': 'difference'}}]):
            spec = {**spec_fixture('retry-' + str(index)), **changes}
            self.engine.discover(spec)
            with self.assertRaisesRegex(ValueError, 'different measured input'):
                prepare_test_fixture(self.engine, spec['id'], historical_fixture())
        spec = {**spec_fixture('new-premise'), 'input_id': 'shipping:delays', 'feature_formula': {'operation': 'difference'}}
        self.engine.discover(spec)
        with self.assertRaisesRegex(ValueError, 'untouched later'):
            prepare_test_fixture(self.engine, spec['id'], historical_fixture())
        self.clock.advance(days=4000)
        holdout = prepare_test_fixture(self.engine, spec['id'], historical_fixture(start=self.clock() - timedelta(days=2000)))
        result = self.engine.backtest(spec['id'], holdout)
        self.assertEqual(result['trial_number'], 2)
        self.assertAlmostEqual(result['alpha'], .05 / 6)
        self.assertTrue(result['passed'])

    def test_abandoned_plan_keeps_global_attempt_count(self):
        prepare_test_fixture(self.engine, self.spec['id'], historical_fixture())
        other = {**spec_fixture('unrelated'), 'family_id': 'other', 'input_id': 'shipping:delays', 'feature_formula': {'operation': 'difference'}}
        self.engine.discover(other)
        prepare_test_fixture(self.engine, other['id'], historical_fixture())
        plans = [json.loads(row[0])['trial_number'] for row in self.store.db.execute('SELECT data FROM test_plans ORDER BY at,signal_id')]
        self.assertEqual(sorted(plans), [1, 2])

    def test_rejected_idea_downloads_only_until_existing_prediction_finishes(self):
        holdout = prepare_test_fixture(self.engine, self.spec['id'], historical_fixture())
        self.engine.backtest(self.spec['id'], holdout)
        self.engine.register(self.spec['id'], 'episode', event_available_at=self.clock(), quote_at=self.clock(), reference_price=10, feature_value=1, source='synthetic://event')
        self.engine.change_state(self.spec['id'], 'DEGRADED', 'Source evidence changed')
        self.clock.advance(days=1)
        price = {'history': [{'at': stamp(self.clock()), 'price': 10.2}], 'quote': None, 'splits': [], 'source': 'synthetic://close'}
        with patch('investment_engine.feeds.market', return_value=price) as market, patch('investment_engine.feeds.attention') as attention:
            run(self.engine, continue_work=True)
            run(self.engine, continue_work=True)
        self.assertEqual(market.call_count, 1)
        attention.assert_not_called()

    def test_empty_initialization_checks_backups_and_preserves_target(self):
        installation = completed_installation(self.temp.name)
        for backups in [[{'id': 'existing', 'name': 'recovery.backup.zip'}], []]:
            with patch('investment_engine.drive.read_inventory', return_value=backups):
                if backups:
                    with self.assertRaisesRegex(ValueError, 'Existing Drive backup'):
                        check_initialization_target(installation)
                else:
                    check_initialization_target(installation)
        self.assertFalse(Path(installation['storage']['database_path']).exists())
        with patch('investment_engine.drive.read_inventory', side_effect=ValueError('Authorization required')):
            with self.assertRaisesRegex(ValueError, 'Authorization'):
                check_initialization_target(installation)
        self.assertFalse(Path(installation['storage']['knowledge_path']).exists())
