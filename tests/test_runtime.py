import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from investment_engine.knowledge import Knowledge
from investment_engine.runtime import ladybug_home, owner_lock


class RuntimeTests(unittest.TestCase):
    def test_ladybug_home_defaults_to_private_system_temporary_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {}, clear=True), patch('investment_engine.runtime.tempfile.gettempdir', return_value=directory):
                path = ladybug_home()
            self.assertEqual(path, Path(directory) / f'squad-runtime-{os.getuid()}' / 'ladybug')
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)

    def test_ladybug_uses_configured_directory_for_install_and_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / 'runtime cache'
            settings = {'profile_id': 'runtime-test', 'storage': {'knowledge_path': str(Path(directory) / 'graph.lbdb')}}
            with patch.dict(os.environ, {'SQUAD_LADYBUG_HOME': str(home)}):
                with Knowledge(settings, 'runtime-test', create=True) as graph:
                    self.assertEqual(graph.rows("CALL current_setting('home_directory') RETURN *"), [[str(home)]])
                    graph.ensure_index()
                self.assertTrue(any(home.rglob('*fts*')))
                with Knowledge(settings, 'runtime-test') as graph:
                    graph.ensure_index()

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
