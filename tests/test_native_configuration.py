import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from squad.cli import execute, parser
from squad.configuration import load_configuration, redact, validate_profile
from tests.fixtures import completed_profile, native_environment


class NativeConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.profile = completed_profile(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_individual_typed_variables_are_the_only_configuration_source(self):
        with patch.dict(os.environ, native_environment(self.profile), clear=True):
            self.assertEqual(load_configuration(), self.profile)
        self.assertFalse(Path(self.profile['storage']['database_path']).exists())

    def test_removed_file_and_json_blob_variables_are_rejected(self):
        for name in ('SQUAD_PROFILE', 'SQUAD_PROFILE_JSON'):
            with patch.dict(os.environ, {**native_environment(self.profile), name: '/private/unused.json'}, clear=True):
                with self.assertRaisesRegex(ValueError, 'Unsupported SQUAD'):
                    load_configuration()

    def test_fixed_architecture_has_no_native_override_switches(self):
        for name in ('SQUAD_RUNTIME_KIND', 'SQUAD_STORAGE_BACKEND', 'SQUAD_GITOPS_UPDATE_POLICY', 'SQUAD_BROKERAGE_EXECUTION_MODE'):
            with patch.dict(os.environ, {**native_environment(self.profile), name: 'alternative'}, clear=True):
                with self.assertRaisesRegex(ValueError, 'Unsupported SQUAD'):
                    load_configuration()

    def test_every_personal_variable_must_be_explicit_even_null_model_preference(self):
        env = native_environment(self.profile)
        del env['SQUAD_WORKER_MODEL']
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(ValueError, 'Missing required.*SQUAD_WORKER_MODEL'):
                load_configuration()

    def test_secret_fields_rejected_and_runtime_credentials_not_copied(self):
        value = dict(self.profile, oauth_refresh_token='never-store-this')
        with self.assertRaises(ValueError):
            validate_profile(value)
        with patch.dict(os.environ, {**native_environment(self.profile), 'SQUAD_GOOGLE_REFRESH_TOKEN': 'runtime-only-token'}, clear=True):
            loaded = load_configuration()
            self.assertNotIn('runtime-only-token', json.dumps(loaded))
            self.assertEqual(redact('failed runtime-only-token'), 'failed [REDACTED]')

    def test_unknown_environment_key_and_bad_types_fail_before_database_creation(self):
        for extra in ({'SQUAD_TYPO_BUDGET': '100'}, {'SQUAD_MAX_CANDIDATES_PER_DAY': '"not-an-integer"'}):
            with patch.dict(os.environ, {**native_environment(self.profile), **extra}, clear=True):
                with self.assertRaises(ValueError):
                    load_configuration()
        self.assertFalse(Path(self.profile['storage']['database_path']).exists())

    def test_runtime_secret_in_ordinary_configuration_text_rejected(self):
        self.profile['brokerage']['constraints'] = 'Accidental copied credential: never-copy-this-token'
        with patch.dict(os.environ, {**native_environment(self.profile), 'SQUAD_GOOGLE_REFRESH_TOKEN': 'never-copy-this-token'}, clear=True):
            with self.assertRaisesRegex(ValueError, 'credentials cannot be copied'):
                load_configuration()

    def test_other_git_checkout_cannot_hold_live_state(self):
        other = Path(self.temp.name) / 'another-checkout'
        other.mkdir()
        (other / '.git').write_text('gitdir: /not/a/live/worktree')
        self.profile['storage']['database_path'] = str(other / 'private' / 'ledger.sqlite3')
        with patch.dict(os.environ, native_environment(self.profile), clear=True):
            with self.assertRaisesRegex(ValueError, 'every Git checkout'):
                load_configuration()

    def test_rejected_legacy_file_setting_preserves_existing_state(self):
        database = Path(self.profile['storage']['database_path'])
        database.parent.mkdir(parents=True)
        database.write_bytes(b'existing evidence must remain intact')
        with patch.dict(os.environ, {'SQUAD_PROFILE': '/private/legacy-profile.json'}, clear=True):
            with self.assertRaisesRegex(ValueError, 'Unsupported SQUAD'):
                load_configuration()
        self.assertEqual(database.read_bytes(), b'existing evidence must remain intact')

    def test_unknown_nested_configuration_field_rejected(self):
        self.profile['storage']['cloud_backup']['misspelled_budget'] = 10000
        with self.assertRaisesRegex(ValueError, 'Unknown or invalid'):
            validate_profile(self.profile)

    def test_unsupported_runtime_and_update_policy_rejected(self):
        for section, key, value in (('runtime', 'kind', 'local'), ('gitops', 'update_policy', 'manual'), ('brokerage', 'execution_mode', 'research_only')):
            profile = completed_profile(self.temp.name)
            profile[section][key] = value
            with self.assertRaises(ValueError):
                validate_profile(profile)

    def test_cloud_environment_cli_initializes_shared_identity_and_graph(self):
        with patch.dict(os.environ, {'HOME': os.environ['HOME'], **native_environment(self.profile)}, clear=True):
            result = execute(parser().parse_args(['init']))
            self.assertEqual(result['knowledge']['backend'], 'ladybug')
            self.assertEqual(result['setup_identity'], result['knowledge']['setup_identity'])
            self.assertFalse(result['monitoring_active'])
