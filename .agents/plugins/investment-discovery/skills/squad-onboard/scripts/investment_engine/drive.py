"""Validate connected-Drive observations supplied by the coordinating Dot."""

import json
from pathlib import Path


def read_inventory(settings, path):
    if path is None:
        raise ValueError('Connected Drive inventory required: collect folder listing and search pages, then pass --inventory FILE')
    value = json.loads(Path(path).read_text())
    if value.get('folder_id') != settings['storage']['cloud_backup']['folder_id']:
        raise ValueError('Drive inventory folder differs from configured backup destination')
    if value.get('complete') is not True or not isinstance(value.get('files'), list):
        raise ValueError('Complete connected Drive inventory required; partial/failed listing cannot authorize initialization or upload')
    files = {}
    for item in value['files']:
        if not isinstance(item.get('id'), str) or not item['id'] or not isinstance(item.get('name'), str):
            raise ValueError('Drive inventory requires actual file IDs and names')
        files[item['id']] = item
    return list(files.values())


def backup_files(files):
    return [item for item in files if item['name'].endswith('.backup.zip')]


def check_capacity(settings, size, files, *, replace_file_id=None):
    config = settings['storage']['cloud_backup']
    if size > config['max_archive_bytes']:
        raise ValueError('Snapshot exceeds configured archive-size budget')
    used = 0
    for item in files:
        if (replace_file_id is not None and item.get('id') == replace_file_id) or item.get('mimeType') == 'application/vnd.google-apps.folder':
            continue
        try:
            count = int(item['size'])
        except (KeyError, TypeError, ValueError):
            raise ValueError('Drive file size missing; read metadata before project-budget accounting') from None
        if count < 0:
            raise ValueError('Invalid Drive file size')
        used += count
    if used + size > config['max_bytes']:
        raise ValueError('Backup project budget exhausted; review folder usage or configured budget')
