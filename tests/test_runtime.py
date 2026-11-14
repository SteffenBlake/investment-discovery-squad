import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from investment_engine.runtime import owner_lock


class RuntimeTests(unittest.TestCase):
    def test_independent_writer_stops_while_owner_lock_held(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = {'storage': {'database_path': str(Path(directory) / 'data' / 'ledger.sqlite3')}}
            code = """import sys
from investment_engine.runtime import owner_lock
try:
    with owner_lock({'storage': {'database_path': sys.argv[1]}}):
        print('acquired')
except ValueError as error:
    print(str(error))
    raise SystemExit(1)
"""
            with owner_lock(cfg, create=True):
                with owner_lock(cfg):  # Same command can call nested backup operations.
                    result = subprocess.run([sys.executable, '-c', code, cfg['storage']['database_path']], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn('Central owner busy', result.stdout)
            result = subprocess.run([sys.executable, '-c', code, cfg['storage']['database_path']], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn('acquired', result.stdout)
            self.assertEqual((Path(directory) / 'data' / '.squad-lock').stat().st_mode & 0o777, 0o600)

    def test_read_attempt_never_provisions_missing_owner_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'missing' / 'ledger.sqlite3'
            with self.assertRaisesRegex(ValueError, 'directory missing'):
                with owner_lock({'storage': {'database_path': str(path)}}):
                    self.fail('Missing owner unexpectedly provisioned')
            self.assertFalse(path.parent.exists())
