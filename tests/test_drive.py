import json
import tempfile
import unittest
from pathlib import Path

from investment_engine.configuration import build_runtime_settings
from investment_engine.drive import read_inventory, check_capacity
from investment_engine.provisioning import check_initialization_target
from tests.fixtures import completed_installation


class DriveInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = build_runtime_settings(completed_installation(self.root))
        self.path = self.root / 'inventory.json'

    def inventory(self, **extra):
        self.path.write_text(json.dumps({'folder_id': 'fictional-folder', 'complete': True, 'files': [], **extra}))
        return self.path

    def test_init_requires_complete_inventory_of_configured_folder(self):
        with self.assertRaises(ValueError):
            check_initialization_target(self.settings)
        for value in ({'complete': False}, {'folder_id': 'other'}):
            with self.assertRaises(ValueError):
                check_initialization_target(self.settings, self.inventory(**value))
        check_initialization_target(self.settings, self.inventory())
        self.assertFalse(Path(self.settings['storage']['database_path']).exists())

    def test_inventory_detects_backup_without_app_properties(self):
        path = self.inventory(files=[{'id': 'actual-id', 'name': 'recovery.backup.zip', 'size': '100'}])
        with self.assertRaisesRegex(ValueError, 'Existing Drive backup'):
            check_initialization_target(self.settings, path)

    def test_inventory_deduplicates_overlapping_listing_and_search(self):
        row = {'id': 'actual-id', 'name': 'one.backup.zip', 'size': '100'}
        self.assertEqual(read_inventory(self.settings, self.inventory(files=[row, row])), [row])

    def test_budget_uses_folder_bytes_without_account_quota(self):
        check_capacity(self.settings, 100, [{'id': 'one', 'size': '100'}])
        with self.assertRaisesRegex(ValueError, 'project budget'):
            check_capacity(self.settings, 100, [{'size': str(self.settings['storage']['cloud_backup']['max_bytes'])}])
        with self.assertRaisesRegex(ValueError, 'size missing'):
            check_capacity(self.settings, 100, [{'id': 'missing-size'}])

    def test_replacement_budget_counts_new_contents_instead_of_previous_size(self):
        self.settings['storage']['cloud_backup'].update(max_bytes=10_000, max_archive_bytes=10_000)
        files = [{'id': 'same-backup', 'size': '8000'}]
        check_capacity(self.settings, 9000, files, replace_file_id='same-backup')
        with self.assertRaisesRegex(ValueError, 'project budget'):
            check_capacity(self.settings, 9000, files)
