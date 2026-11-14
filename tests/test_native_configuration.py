import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from investment_engine.cli import execute, parser
from investment_engine.configuration import load_configuration, redact, validate_installation
from tests.fixtures import completed_installation, native_environment


class NativeConfigurationTests(unittest.TestCase):
    def setUp(self):
        remote = patch('investment_engine.drive.Drive.list', return_value=[])
        remote.start()
        self.addCleanup(remote.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.installation = completed_installation(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_individual_typed_variables_are_the_only_configuration_source(self):
        with patch.dict(os.environ, native_environment(self.installation), clear=True):
            self.assertEqual(load_configuration(), self.installation)
        self.assertFalse(Path(self.installation['storage']['database_path']).exists())

    def test_every_personal_variable_must_be_explicit_even_null_model_preference(self):
        env = native_environment(self.installation)
        del env['SQUAD_WORKER_MODEL']
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(ValueError, 'Missing required.*SQUAD_WORKER_MODEL'):
                load_configuration()

    def test_secret_fields_rejected_and_runtime_credentials_not_copied(self):
        value = dict(self.installation, oauth_refresh_token='never-store-this')
        with self.assertRaises(ValueError):
            validate_installation(value)
        with patch.dict(os.environ, {**native_environment(self.installation), 'SQUAD_GOOGLE_REFRESH_TOKEN': 'runtime-only-token'}, clear=True):
            loaded = load_configuration()
            self.assertNotIn('runtime-only-token', json.dumps(loaded))
            self.assertEqual(redact('failed runtime-only-token'), 'failed [REDACTED]')

    def test_unknown_environment_key_and_bad_types_fail_before_database_creation(self):
        for extra in ({'SQUAD_TYPO_BUDGET': '100'}, {'SQUAD_STORAGE_BACKEND': 'override'}, {'SQUAD_MAX_CANDIDATES_PER_DAY': '"not-an-integer"'}):
            with patch.dict(os.environ, {**native_environment(self.installation), **extra}, clear=True):
                with self.assertRaises(ValueError):
                    load_configuration()
        self.assertFalse(Path(self.installation['storage']['database_path']).exists())

    def test_runtime_secret_in_ordinary_configuration_text_rejected(self):
        self.installation['brokerage']['constraints'] = 'Accidental copied credential: never-copy-this-token'
        with patch.dict(os.environ, {**native_environment(self.installation), 'SQUAD_GOOGLE_REFRESH_TOKEN': 'never-copy-this-token'}, clear=True):
            with self.assertRaisesRegex(ValueError, 'credentials cannot be copied'):
                load_configuration()

    def test_other_git_checkout_cannot_hold_live_state(self):
        other = Path(self.temp.name) / 'another-checkout'
        other.mkdir()
        (other / '.git').write_text('gitdir: /not/a/live/worktree')
        self.installation['storage']['database_path'] = str(other / 'private' / 'ledger.sqlite3')
        with patch.dict(os.environ, native_environment(self.installation), clear=True):
            with self.assertRaisesRegex(ValueError, 'every Git checkout'):
                load_configuration()


    def test_unknown_nested_configuration_field_rejected(self):
        self.installation['storage']['cloud_backup']['misspelled_budget'] = 10000
        with self.assertRaisesRegex(ValueError, 'Unknown or invalid'):
            validate_installation(self.installation)

    def test_unsupported_runtime_and_update_policy_rejected(self):
        for section, key, value in (('runtime', 'kind', 'local'), ('gitops', 'update_policy', 'manual'), ('brokerage', 'execution_mode', 'research_only')):
            installation = completed_installation(self.temp.name)
            installation[section][key] = value
            with self.assertRaises(ValueError):
                validate_installation(installation)

    def test_cloud_environment_cli_initializes_shared_identity_and_graph(self):
        with patch.dict(os.environ, {'HOME': os.environ['HOME'], **native_environment(self.installation)}, clear=True):
            result = execute(parser().parse_args(['init']))
            self.assertEqual(result['knowledge']['backend'], 'ladybug')
            self.assertEqual(result['setup_identity'], result['knowledge']['setup_identity'])
            self.assertFalse(result['monitoring_active'])
