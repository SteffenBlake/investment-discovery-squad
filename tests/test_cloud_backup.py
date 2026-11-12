import copy
import hashlib
import json
import sqlite3
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from pathlib import Path

from squad.backups import cloud_backup, current_backup, restore, snapshot, verify_archive
from squad.configuration import settings
from squad.knowledge import Knowledge
from squad.engine import Engine
from squad.storage import open_store
from tests.fixtures import completed_profile, research_batch


class FakeDrive:
    """Deterministic remote blob transport; never a real account/activation receipt."""
    def __init__(self):
        self.files = {}
        self.upload_calls = 0
        self.lose_next_response = False
        self.corrupt_download = False

    def upload(self, path, manifest, sha256):
        for identifier, (metadata, data) in self.files.items():
            if metadata['appProperties']['sha256'] == sha256:
                return metadata
        self.upload_calls += 1
        identifier = 'synthetic-drive-' + str(self.upload_calls)
        metadata = {'id': identifier, 'size': str(path.stat().st_size), 'appProperties': {'sha256': sha256, 'setup_identity': manifest['setup_identity']}}
        self.files[identifier] = (metadata, path.read_bytes())
        if self.lose_next_response:
            self.lose_next_response = False
            raise ValueError('Synthetic lost response after remote upload')
        return metadata

    def download(self, file_id, *, expected_identity=None):
        metadata, data = self.files[file_id]
        if metadata['appProperties']['setup_identity'] != expected_identity:
            raise ValueError('Wrong remote identity')
        return metadata, data + b'corrupt' if self.corrupt_download else data


class CloudBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = settings(completed_profile(self.root))
        self.store = open_store(self.settings, initialize=True)
        with Knowledge(self.settings, self.store.identity, create=True) as graph:
            graph.ingest(research_batch())
        self.drive = FakeDrive()

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_cloud_backup_downloads_and_restores_both_stores(self):
        self.store.event('prediction-proof', proof='committed in WAL')
        result = cloud_backup(self.settings, self.store, drive=self.drive)
        self.assertTrue(result['current'])
        self.assertTrue(result['receipt']['restore_tested'])
        self.assertEqual(self.drive.upload_calls, 1)
        self.assertFalse(cloud_backup(self.settings, self.store, drive=self.drive)['created'])
        self.store.event('new-evidence', proof='must be backed up')
        self.assertFalse(current_backup(self.settings, self.store)['current'])

    def test_lost_upload_response_recovers_without_duplicate_remote_copy(self):
        self.drive.lose_next_response = True
        with self.assertRaisesRegex(ValueError, 'lost response'):
            cloud_backup(self.settings, self.store, drive=self.drive)
        self.assertFalse(current_backup(self.settings, self.store)['current'])
        pending = Path(self.settings['storage']['backup_directory']) / 'pending-upload.json'
        self.assertTrue(pending.exists())
        result = cloud_backup(self.settings, self.store, drive=self.drive)
        self.assertTrue(result['current'])
        self.assertEqual(self.drive.upload_calls, 1)
        self.assertFalse(pending.exists())

    def test_corrupt_remote_copy_never_becomes_durability_receipt(self):
        self.drive.corrupt_download = True
        with self.assertRaisesRegex(ValueError, 'bytes'):
            cloud_backup(self.settings, self.store, drive=self.drive)
        self.assertFalse(current_backup(self.settings, self.store)['current'])

    def test_pending_old_upload_is_finished_then_new_evidence_backed_up(self):
        self.drive.lose_next_response = True
        with self.assertRaises(ValueError):
            cloud_backup(self.settings, self.store, drive=self.drive)
        self.store.event('evidence-after-ambiguous-upload', value='preserve both versions')
        result = cloud_backup(self.settings, self.store, drive=self.drive)
        self.assertTrue(result['current'])
        self.assertEqual(self.drive.upload_calls, 2)

    def test_runtime_credentials_not_in_complete_archive(self):
        with patch.dict('os.environ', {'SQUAD_GOOGLE_REFRESH_TOKEN': 'fictional-vault-only-token'}):
            path = self.root / 'secret-exclusion.zip'
            snapshot(self.settings, self.store, path)
        with zipfile.ZipFile(path) as archive:
            self.assertTrue(all(b'fictional-vault-only-token' not in archive.read(name) for name in archive.namelist()))

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
        target = settings(completed_profile(self.root / 'replacement'))
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

    def test_wrong_profile_and_ledger_identity_rejected(self):
        path = self.root / 'snapshot.zip'
        snapshot(self.settings, self.store, path)
        with self.assertRaisesRegex(ValueError, 'identity'):
            verify_archive(path, self.settings, 'wrong', self.root / 'wrong-stage')

    def test_interrupted_restore_marker_blocks_ordinary_ledger_access(self):
        marker = self.store.path.parent / '.restore-in-progress.json'
        marker.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Interrupted restore'):
            open_store(self.settings)
