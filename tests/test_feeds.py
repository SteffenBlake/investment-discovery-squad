import io
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from investment_engine.feeds import fetch_json, market
from investment_engine.util import UTC, stamp


class ClosingPriceTests(unittest.TestCase):
    instrument = {'currency': 'USD', 'exchange_timezone': 'America/New_York', 'exchange_calendar': 'XNYS'}

    def response(self, session, captured):
        timestamp = int(datetime.fromisoformat(session + 'T14:30:00+00:00').timestamp())
        return {'fetched_at': stamp(captured), 'body': {'chart': {'result': [
            {'meta': {'currency': 'USD', 'symbol': 'SYNTH'}, 'timestamp': [timestamp],
             'indicators': {'quote': [{'close': [100]}]}}]}}}

    def test_preclose_download_stays_ineligible_after_clock_advances(self):
        now = datetime(2026, 11, 13, 21, 30, tzinfo=UTC)
        captured = now - timedelta(minutes=31)
        with patch('investment_engine.feeds.fetch_json', return_value=self.response('2026-11-13', captured)):
            self.assertEqual(market('SYNTH', 'unused', now, self.instrument)['history'], [])

    def test_regular_and_early_close_require_thirty_minutes(self):
        for session, hour in [('2026-11-13', 21), ('2026-11-27', 18)]:
            close = datetime.fromisoformat(session).replace(hour=hour, tzinfo=UTC)
            for minutes, count in [(29, 0), (30, 1)]:
                now = close + timedelta(minutes=minutes)
                with patch('investment_engine.feeds.fetch_json', return_value=self.response(session, now)):
                    history = market('SYNTH', 'unused', now, self.instrument)['history']
                self.assertEqual(len(history), count)
                if history:
                    self.assertEqual(history[0]['at'], stamp(close))

    def test_missing_session_reports_warning_and_omits_price(self):
        now = datetime(2026, 11, 26, 23, tzinfo=UTC)
        with patch('investment_engine.feeds.fetch_json', return_value=self.response('2026-11-26', now)):
            data = market('SYNTH', 'unused', now, self.instrument)
        self.assertEqual(data['history'], [])
        self.assertIn('2026-11-26', data['warnings'][0])

    def test_close_boundary_forces_fresh_download_even_within_cache_lifetime(self):
        with tempfile.TemporaryDirectory() as folder:
            before = datetime(2026, 11, 13, 21, 10, tzinfo=UTC)
            ready = before + timedelta(minutes=20)
            with patch('investment_engine.feeds.urllib.request.urlopen', return_value=io.BytesIO(b'{"price":99}')), patch('investment_engine.feeds.now_utc', return_value=before):
                fetch_json('https://example.invalid/price', folder, before)
            with patch('investment_engine.feeds.urllib.request.urlopen', return_value=io.BytesIO(b'{"price":100}')) as download, patch('investment_engine.feeds.now_utc', return_value=ready):
                data = fetch_json('https://example.invalid/price', folder, ready, ttl_seconds=1800, minimum_capture_at=ready)
            download.assert_called_once()
            self.assertEqual(data['body']['price'], 100)
