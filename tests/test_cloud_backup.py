import json
import sqlite3
import shutil
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from pathlib import Path

from investment_engine.backups import cloud_backup, current_backup, restore, snapshot, verify_archive, start_upload, accept_upload, retry_upload
from investment_engine.configuration import build_runtime_settings
from investment_engine.knowledge import Knowledge
from investment_engine.engine import Engine
from investment_engine.provisioning import open_store
from tests.fixtures import completed_installation, native_environment, research_batch, spec_fixture


class FakeDrive:
    """Connected-tool results simulated by test agent; runtime has no transport."""
    def __init__(self):
        self.files = {}
        self.upload_calls = 0
        self.lose_next_response = False
        self.wrong_size = False
        self.download_calls = 0
        self.revisions = {}

    def upload(self, path, file_id=None):
        self.upload_calls += 1
        identifier = file_id or 'synthetic-drive-' + str(self.upload_calls)
        if identifier in self.files:
            self.revisions.setdefault(identifier, []).append(self.files[identifier])
        metadata = {'id': identifier, 'name': path.name, 'size': str(path.stat().st_size),
                    'mimeType': 'application/zip', 'createdTime': f'{self.upload_calls:08d}'}
        self.files[identifier] = (metadata, path.read_bytes())
        if self.lose_next_response:
            self.lose_next_response = False
            raise ValueError('Synthetic lost response after remote upload')
        return {**metadata, 'size': '0'} if self.wrong_size else metadata


class CloudBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = build_runtime_settings(completed_installation(self.root))
        self.store = open_store(self.settings, initialize=True)
        with Knowledge(self.settings, self.store.identity, create=True) as graph:
            graph.ingest(research_batch())
        self.drive = FakeDrive()

    def inventory(self):
        path = self.root / 'inventory.json'
        path.write_text(json.dumps({'folder_id': 'fictional-folder', 'complete': True,
                                   'files': [row[0] for row in self.drive.files.values()]}))
        return path

    def backup(self):
        result = cloud_backup(self.settings, self.store, inventory=self.inventory())
        if result.get('action') in {'upload', 'update'}:
            start_upload(self.settings, self.store)
            metadata = self.drive.upload(Path(result['arguments']['file_uri']), result['arguments'].get('fileId'))
            result = accept_upload(self.settings, self.store, {'file_id': metadata['id'], 'folder_id': 'fictional-folder',
                                   'name': metadata['name'], 'size': metadata['size'], 'receipt': metadata})
        if result.get('created'):
            if not result['current']:
                return self.backup()
        return result

    def restore_to(self, settings, file_id, identity):
        self.drive.download_calls += 1
        path = self.root / 'download.zip'
        path.write_bytes(self.drive.files[file_id][1])
        return restore(settings, path, identity, file_id=file_id)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_connected_upload_acceptance_needs_no_remote_checksum_or_download(self):
        self.store.event('prediction-proof', proof='committed in WAL')
        result = self.backup()
        self.assertTrue(result['current'])
        self.assertTrue(result['receipt']['upload_accepted'])
        self.assertFalse(result['receipt']['remote_integrity_verified'])
        self.assertEqual(self.drive.download_calls, 0)
        self.assertEqual(self.drive.upload_calls, 1)
        self.assertFalse(self.backup()['created'])
        self.assertEqual(list(Path(self.settings['storage']['backup_directory']).glob('*.backup.zip')), [])
        self.store.event('new-evidence', proof='must be backed up')
        self.assertFalse(current_backup(self.settings, self.store)['current'])

    def test_uncertain_upload_requires_inventory_or_confirmed_creation_failure(self):
        result = cloud_backup(self.settings, self.store, inventory=self.inventory())
        start_upload(self.settings, self.store)
        self.assertEqual(cloud_backup(self.settings, self.store, inventory=self.inventory())['action'], 'inspect_upload')
        with self.assertRaisesRegex(ValueError, 'uncertain'):
            start_upload(self.settings, self.store)
        with self.assertRaisesRegex(ValueError, 'before remote creation'):
            retry_upload(self.settings, self.store, {'reason': 'search missed it'})
        self.assertTrue(Path(result['arguments']['file_uri']).exists())
        retry_upload(self.settings, self.store, {'failed_before_creation': True, 'reason': 'connector rejected local file before upload'})
        self.assertEqual(cloud_backup(self.settings, self.store, inventory=self.inventory())['action'], 'upload')

    def test_update_receipt_must_keep_same_file_id(self):
        initial = self.backup()
        self.store.event('new-evidence')
        prepared = cloud_backup(self.settings, self.store, inventory=self.inventory())
        self.assertEqual(prepared['action'], 'update')
        self.assertEqual(prepared['arguments']['fileId'], initial['receipt']['file_id'])
        with self.assertRaisesRegex(ValueError, 'receipt'):
            accept_upload(self.settings, self.store, {'file_id': 'different-file', 'folder_id': 'fictional-folder',
                          'name': prepared['arguments']['name'], 'receipt': {'id': 'different-file'}})
        self.assertTrue(Path(prepared['arguments']['file_uri']).exists())

    def test_command_handoff_records_connector_receipt(self):
        from investment_engine.cli import execute, parser
        with patch.dict('os.environ', native_environment(completed_installation(self.root))):
            prepared = execute(parser().parse_args(['backup', 'cloud', '--inventory', str(self.inventory())]))
            execute(parser().parse_args(['backup', 'started']))
            remote = self.drive.upload(Path(prepared['arguments']['file_uri']))
            path = self.root / 'receipt.json'
            path.write_text(json.dumps({'file_id': remote['id'], 'folder_id': 'fictional-folder',
                                       'name': remote['name'], 'receipt': remote}))
            result = execute(parser().parse_args(['backup', 'accept', '--file', str(path)]))
            self.assertTrue(result['receipt']['upload_accepted'])
            self.assertFalse(result['receipt']['remote_integrity_verified'])

    def test_lost_upload_response_recovers_without_duplicate_remote_copy(self):
        self.drive.lose_next_response = True
        with self.assertRaisesRegex(ValueError, 'lost response'):
            self.backup()
        self.assertFalse(current_backup(self.settings, self.store)['current'])
        pending = Path(self.settings['storage']['backup_directory']) / 'pending-upload.json'
        self.assertTrue(pending.exists())
        self.assertEqual(len(list(pending.parent.glob('*.backup.zip'))), 1)
        result = self.backup()
        self.assertTrue(result['current'])
        self.assertEqual(self.drive.upload_calls, 1)
        self.assertFalse(pending.exists())
        self.assertEqual(list(pending.parent.glob('*.backup.zip')), [])

    def test_reported_size_mismatch_preserves_pending_archive(self):
        self.drive.wrong_size = True
        with self.assertRaisesRegex(ValueError, 'size mismatch'):
            self.backup()
        self.assertFalse(current_backup(self.settings, self.store)['current'])

    def test_repeated_backups_replace_same_file_and_preserve_versions(self):
        identifiers = []
        for index in range(5):
            self.store.event('new-evidence', index=index)
            identifiers.append(self.backup()['receipt']['file_id'])
        self.assertEqual(len(set(identifiers)), 1)
        self.assertEqual(len(self.drive.files), 1)
        self.assertEqual(len(self.drive.revisions[identifiers[0]]), 4)
        self.assertEqual(self.drive.download_calls, 0)

    def test_lost_update_response_recovers_same_file_without_another_write(self):
        initial = self.backup()
        self.store.event('new-evidence')
        self.drive.lose_next_response = True
        with self.assertRaisesRegex(ValueError, 'lost response'):
            self.backup()
        recovered = self.backup()
        self.assertTrue(recovered['current'])
        self.assertEqual(recovered['receipt']['file_id'], initial['receipt']['file_id'])
        self.assertEqual(self.drive.upload_calls, 2)
        self.assertEqual(len(self.drive.files), 1)

    def test_pending_old_upload_is_finished_then_new_evidence_backed_up(self):
        self.drive.lose_next_response = True
        with self.assertRaises(ValueError):
            self.backup()
        self.store.event('evidence-after-ambiguous-upload', value='preserve both versions')
        result = self.backup()
        self.assertTrue(result['current'])
        self.assertEqual(self.drive.upload_calls, 2)

    def test_secret_bearing_spec_rejected_before_persistence_and_archive(self):
        from investment_engine.cli import read_json
        with patch.dict('os.environ', {'BROKER_API_TOKEN': 'fictional-vault-only-token'}):
            for field, value in (("mechanism", "copied fictional-vault-only-token"), ("api_key", "private-value")):
                spec = {**spec_fixture("secret-import"), field: value}
                file = self.root / "import.json"
                import json
                file.write_text(json.dumps(spec))
                with self.assertRaises(ValueError):
                    read_json(file)
                with self.assertRaises(ValueError):
                    Engine(self.store, self.settings).discover(spec)
            self.assertEqual(self.store.db.execute("SELECT count(*) FROM specs").fetchone()[0], 0)
            path = self.root / 'secret-exclusion.zip'
            snapshot(self.settings, self.store, path)
        with zipfile.ZipFile(path) as archive:
            self.assertTrue(all(b'fictional-vault-only-token' not in archive.read(name) for name in archive.namelist()))

    def test_quiet_monitor_runs_leave_accepted_backup_current(self):
        from investment_engine.runner import run
        self.backup()
        for _ in range(2):
            result = run(Engine(self.store, self.settings), offline=True)
            self.assertEqual(result['errors'], [])
            self.assertFalse(self.backup()['created'])
        self.assertEqual(self.drive.upload_calls, 1)

    def test_observation_without_event_and_new_cache_invalidate_cloud_copy(self):
        self.backup()
        Engine(self.store, self.settings).record_price('SYNTH', self.store.clock(), 10, source='synthetic://observation')
        self.assertFalse(current_backup(self.settings, self.store)['current'])
        self.backup()
        cache = self.store.path.parent / 'cache'
        cache.mkdir()
        (cache / 'new-source.txt').write_text('New source evidence, not yet in any event')
        self.assertFalse(current_backup(self.settings, self.store)['current'])

    def test_full_restore_into_new_empty_owner_keeps_original_identity(self):
        result = self.backup()
        target = build_runtime_settings(completed_installation(self.root / 'replacement'))
        restored = self.restore_to(target, result['receipt']['file_id'], self.store.identity)
        self.assertEqual(restored['setup_identity'], self.store.identity)
        with Knowledge(target, self.store.identity) as graph:
            self.assertEqual(graph.search('congestion')['results'][0]['claim']['id'], 'claim:one')
        other = open_store(target)
        try:
            self.assertEqual(other.identity, self.store.identity)
            self.assertEqual(other.db.execute("SELECT COUNT(*) FROM events WHERE kind='restore_completed'").fetchone()[0], 1)
        finally:
            other.close()
        with self.assertRaisesRegex(ValueError, 'empty'):
            self.restore_to(target, result['receipt']['file_id'], self.store.identity)

    def test_restore_reuses_downloaded_file_as_next_update_target(self):
        initial = self.backup()
        target = build_runtime_settings(completed_installation(self.root / 'replacement'))
        self.restore_to(target, initial['receipt']['file_id'], self.store.identity)
        restored = open_store(target)
        try:
            prepared = cloud_backup(target, restored, inventory=self.inventory())
            self.assertEqual(prepared['action'], 'update')
            self.assertEqual(prepared['arguments']['fileId'], initial['receipt']['file_id'])
            start_upload(target, restored)
            metadata = self.drive.upload(Path(prepared['arguments']['file_uri']), prepared['arguments']['fileId'])
            accepted = accept_upload(target, restored, {'file_id': metadata['id'], 'folder_id': 'fictional-folder',
                                     'name': metadata['name'], 'receipt': metadata})
            self.assertTrue(accepted['current'])
            self.assertEqual(len(self.drive.files), 1)
        finally:
            restored.close()

    def test_snapshot_refuses_archive_path_traversal_and_tampered_member(self):
        path = self.root / 'snapshot.zip'
        snapshot(self.settings, self.store, path)
        for mode in ('traversal', 'tampered'):
            bad = self.root / (mode + '.zip')
            with zipfile.ZipFile(path) as source, zipfile.ZipFile(bad, 'w') as out:
                for name in source.namelist():
                    data = source.read(name)
                    out.writestr(name, data + b'changed' if mode == 'tampered' and name == 'ledger.sqlite3' else data)
                if mode == 'traversal':
                    out.writestr('../outside.txt', b'no')
            with self.assertRaises(ValueError):
                verify_archive(bad, self.settings, self.store.identity, self.root / ('stage-' + mode))
        self.assertFalse((self.root / 'outside.txt').exists())

    def test_wrong_installation_and_ledger_identity_rejected(self):
        path = self.root / 'snapshot.zip'
        snapshot(self.settings, self.store, path)
        with self.assertRaisesRegex(ValueError, 'identity'):
            verify_archive(path, self.settings, 'wrong', self.root / 'wrong-stage')

    def test_restore_finalization_interruption_keeps_marker_at_original_paths(self):
        from investment_engine.ledger import Store
        self.store.event('deployment_applied', legacy='historical receipt preserved')
        result = self.backup()
        identity = self.store.identity
        self.store.close()
        shutil.rmtree(self.store.path.parent)
        original_event = Store.event
        def interrupted(store, kind, *args, **kwargs):
            if kind == 'restore_completed':
                self.assertTrue((store.path.parent / '.restore-in-progress.json').exists())
                raise RuntimeError('Interrupted before recovery commit')
            return original_event(store, kind, *args, **kwargs)
        with patch.object(Store, 'event', interrupted), self.assertRaisesRegex(RuntimeError, 'recovery commit'):
            self.restore_to(self.settings, result['receipt']['file_id'], identity)
        with self.assertRaisesRegex(ValueError, 'Interrupted restore'):
            open_store(self.settings)
        reader = sqlite3.connect(self.store.path)
        try:
            self.assertEqual(reader.execute("SELECT value FROM meta WHERE key='setup_identity'").fetchone()[0], identity)
            self.assertEqual(reader.execute("SELECT count(*) FROM events WHERE kind='restore_completed'").fetchone()[0], 0)
            self.assertEqual(reader.execute("SELECT count(*) FROM events WHERE kind='deployment_applied'").fetchone()[0], 1)
        finally:
            reader.close()
