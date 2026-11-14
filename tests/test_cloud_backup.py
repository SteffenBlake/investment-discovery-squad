import sqlite3
import shutil
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from pathlib import Path

from investment_engine.backups import cloud_backup, current_backup, restore, snapshot, verify_archive
from investment_engine.configuration import build_runtime_settings
from investment_engine.knowledge import Knowledge
from investment_engine.drive import Drive, PROJECT
from investment_engine.engine import Engine
from investment_engine.provisioning import open_store
from tests.fixtures import completed_installation, research_batch, spec_fixture


class FakeDrive:
    """Deterministic remote blob transport; never a real account/activation receipt."""
    def __init__(self):
        self.files = {}
        self.upload_calls = 0
        self.lose_next_response = False
        self.corrupt_download = False
        self.corrupt_checksum = False
        self.profile_id = 'test-owner'
        self.config = {'folder_id': 'fictional-folder'}
        self.download_calls = 0

    def upload(self, path, manifest, sha256):
        for identifier, (metadata, data) in self.files.items():
            if metadata['appProperties']['sha256'] == sha256:
                return metadata
        self.upload_calls += 1
        identifier = 'synthetic-drive-' + str(self.upload_calls)
        import hashlib
        metadata = {'id': identifier, 'size': str(path.stat().st_size), 'createdTime': f'{self.upload_calls:08d}',
                    'parents': ['fictional-folder'], 'md5Checksum': hashlib.md5(path.read_bytes()).hexdigest(),
                    'appProperties': {'project': PROJECT, 'profile_id': 'test-owner', 'sha256': sha256, 'setup_identity': manifest['setup_identity']}}
        self.files[identifier] = (metadata, path.read_bytes())
        if self.lose_next_response:
            self.lose_next_response = False
            raise ValueError('Synthetic lost response after remote upload')
        return metadata

    verify_upload = Drive.verify_upload
    retain_latest = Drive.retain_latest

    def metadata(self, file_id):
        metadata = self.files[file_id][0]
        return {**metadata, 'md5Checksum': 'wrong'} if self.corrupt_checksum else metadata

    def list(self):
        return [metadata for metadata, data in self.files.values()]

    def request(self, method, path, **kwargs):
        import json
        file_id = path.rsplit('/', 1)[-1]
        if method == 'PATCH':
            self.files[file_id][0].update(json.loads(kwargs['body']))
        else:
            assert method == 'DELETE'
            del self.files[file_id]

    def download(self, file_id, *, expected_identity=None):
        self.download_calls += 1
        metadata, data = self.files[file_id]
        if metadata['appProperties']['setup_identity'] != expected_identity:
            raise ValueError('Wrong remote identity')
        return metadata, data + b'corrupt' if self.corrupt_download else data


class CloudBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = build_runtime_settings(completed_installation(self.root))
        self.store = open_store(self.settings, initialize=True)
        with Knowledge(self.settings, self.store.identity, create=True) as graph:
            graph.ingest(research_batch())
        self.drive = FakeDrive()

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_cloud_backup_checks_server_checksum_without_downloading(self):
        self.store.event('prediction-proof', proof='committed in WAL')
        result = cloud_backup(self.settings, self.store, drive=self.drive)
        self.assertTrue(result['current'])
        self.assertTrue(result['receipt']['checksum_verified'])
        self.assertEqual(self.drive.download_calls, 0)
        self.assertEqual(self.drive.upload_calls, 1)
        self.assertFalse(cloud_backup(self.settings, self.store, drive=self.drive)['created'])
        self.assertEqual(list(Path(self.settings['storage']['backup_directory']).glob('*.backup.zip')), [])
        self.store.event('new-evidence', proof='must be backed up')
        self.assertFalse(current_backup(self.settings, self.store)['current'])

    def test_lost_upload_response_recovers_without_duplicate_remote_copy(self):
        self.drive.lose_next_response = True
        with self.assertRaisesRegex(ValueError, 'lost response'):
            cloud_backup(self.settings, self.store, drive=self.drive)
        self.assertFalse(current_backup(self.settings, self.store)['current'])
        pending = Path(self.settings['storage']['backup_directory']) / 'pending-upload.json'
        self.assertTrue(pending.exists())
        self.assertEqual(len(list(pending.parent.glob('*.backup.zip'))), 1)
        result = cloud_backup(self.settings, self.store, drive=self.drive)
        self.assertTrue(result['current'])
        self.assertEqual(self.drive.upload_calls, 1)
        self.assertFalse(pending.exists())
        self.assertEqual(list(pending.parent.glob('*.backup.zip')), [])

    def test_corrupt_remote_copy_never_becomes_durability_receipt(self):
        self.drive.corrupt_checksum = True
        with self.assertRaisesRegex(ValueError, 'checksum'):
            cloud_backup(self.settings, self.store, drive=self.drive)
        self.assertFalse(current_backup(self.settings, self.store)['current'])

    def test_latest_three_successful_backups_retained_after_new_upload(self):
        for index in range(5):
            self.store.event('new-evidence', index=index)
            cloud_backup(self.settings, self.store, drive=self.drive)
        self.assertEqual(set(self.drive.files), {'synthetic-drive-3', 'synthetic-drive-4', 'synthetic-drive-5'})
        self.assertEqual(self.drive.download_calls, 0)

    def test_failed_checksum_preserves_earlier_successful_backups(self):
        for index in range(3):
            self.store.event('new-evidence', index=index)
            cloud_backup(self.settings, self.store, drive=self.drive)
        previous = set(self.drive.files)
        self.store.event('new-evidence', index=4)
        self.drive.corrupt_checksum = True
        with self.assertRaisesRegex(ValueError, 'checksum'):
            cloud_backup(self.settings, self.store, drive=self.drive)
        self.assertTrue(previous <= set(self.drive.files))

    def test_pending_old_upload_is_finished_then_new_evidence_backed_up(self):
        self.drive.lose_next_response = True
        with self.assertRaises(ValueError):
            cloud_backup(self.settings, self.store, drive=self.drive)
        self.store.event('evidence-after-ambiguous-upload', value='preserve both versions')
        result = cloud_backup(self.settings, self.store, drive=self.drive)
        self.assertTrue(result['current'])
        self.assertEqual(self.drive.upload_calls, 2)

    def test_secret_bearing_spec_rejected_before_persistence_and_archive(self):
        from investment_engine.cli import read_json
        with patch.dict('os.environ', {'SQUAD_GOOGLE_REFRESH_TOKEN': 'fictional-vault-only-token'}):
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

    def test_quiet_monitor_runs_leave_verified_backup_current(self):
        from investment_engine.runner import run
        cloud_backup(self.settings, self.store, drive=self.drive)
        for _ in range(2):
            result = run(Engine(self.store, self.settings), offline=True)
            self.assertEqual(result['errors'], [])
            self.assertFalse(cloud_backup(self.settings, self.store, drive=self.drive)['created'])
        self.assertEqual(self.drive.upload_calls, 1)

    def test_observation_without_event_and_new_cache_invalidate_cloud_copy(self):
        cloud_backup(self.settings, self.store, drive=self.drive)
        Engine(self.store, self.settings).record_price('SYNTH', self.store.clock(), 10, source='synthetic://observation')
        self.assertFalse(current_backup(self.settings, self.store)['current'])
        cloud_backup(self.settings, self.store, drive=self.drive)
        cache = self.store.path.parent / 'cache'
        cache.mkdir()
        (cache / 'new-source.txt').write_text('New source evidence, not yet in any event')
        self.assertFalse(current_backup(self.settings, self.store)['current'])

    def test_full_restore_into_new_empty_owner_keeps_original_identity(self):
        result = cloud_backup(self.settings, self.store, drive=self.drive)
        target = build_runtime_settings(completed_installation(self.root / 'replacement'))
        restored = restore(target, result['receipt']['file_id'], self.store.identity, drive=self.drive)
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
            restore(target, result['receipt']['file_id'], self.store.identity, drive=self.drive)

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
        result = cloud_backup(self.settings, self.store, drive=self.drive)
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
            restore(self.settings, result['receipt']['file_id'], identity, drive=self.drive)
        with self.assertRaisesRegex(ValueError, 'Interrupted restore'):
            open_store(self.settings)
        reader = sqlite3.connect(self.store.path)
        try:
            self.assertEqual(reader.execute("SELECT value FROM meta WHERE key='setup_identity'").fetchone()[0], identity)
            self.assertEqual(reader.execute("SELECT count(*) FROM events WHERE kind='restore_completed'").fetchone()[0], 0)
            self.assertEqual(reader.execute("SELECT count(*) FROM events WHERE kind='deployment_applied'").fetchone()[0], 1)
        finally:
            reader.close()
