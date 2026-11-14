"""Complete versioned cloud recovery: ledger + portable Ladybug export + source artifacts."""

import hashlib
import importlib.metadata
import json
import os
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from . import __version__
from .configuration import private_directory, write_private_json
from .drive import read_inventory, check_capacity
from .knowledge import Knowledge
from .runtime import owner_lock
from .provisioning import frozen_settings_match, _open_store
from .ledger import IMMUTABLE
from .util import digest, instant, now_utc, stamp

BOOKKEEPING = ("cloud_backup_accepted", "cloud_backup_verified", "backup_created", "run_completed")


def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def covered_sequence(store):
    placeholders = ','.join('?' for _ in BOOKKEEPING)
    return store.db.execute(f"SELECT COALESCE(MAX(seq),0) FROM events WHERE kind NOT IN ({placeholders})", BOOKKEEPING).fetchone()[0]


def ledger_revision(store):
    # Some append-only observations have no event. Event sequence alone misses them.
    return digest({table: store.db.execute(f'SELECT COALESCE(MAX(rowid),0) FROM {table}').fetchone()[0]
                   for table in IMMUTABLE if table != 'events'})


def artifact_revision(store):
    entries = []
    for name in ('knowledge-sources', 'cache'):
        root = store.path.parent / name
        if root.is_symlink():
            raise ValueError('Source archive symlinks are unsupported')
        for path in sorted(root.rglob('*')):
            if path.is_symlink():
                raise ValueError('Source archive symlinks are unsupported')
            if path.is_file():
                stat = path.stat()
                entries.append((str(path.relative_to(store.path.parent)), stat.st_size, stat.st_mtime_ns))
    return digest(entries)


def _private_copy(source, destination):
    destination = Path(destination)
    private_directory(destination.parent)
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'wb') as out, Path(source).open('rb') as inp:
        shutil.copyfileobj(inp, out)


def snapshot(settings, store, destination):
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Recovery archive already exists')
    private_directory(destination.parent)
    with owner_lock(settings), tempfile.TemporaryDirectory(dir=destination.parent, prefix='.snapshot-') as temporary:
        stage = Path(temporary)
        ledger = stage / 'ledger.sqlite3'
        target = sqlite3.connect(ledger)
        try:
            store.db.backup(target)
            if target.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise ValueError('Snapshot ledger integrity failed')
        finally:
            target.close()
        os.chmod(ledger, 0o600)
        with Knowledge(settings, store.identity) as graph:
            graph_hash = graph.export(stage / 'graph')
            graph_revision = graph.meta('revision')
            graph_counts = graph.status()['counts']
        data = store.path.parent
        for name in ('knowledge-sources', 'cache'):
            original = data / name
            if original.is_symlink():
                raise ValueError('Source archive symlinks are unsupported')
            if not original.exists():
                continue
            for source in original.rglob('*'):
                if source.is_symlink():
                    raise ValueError('Source archive symlinks are unsupported')
                if source.is_file():
                    _private_copy(source, stage / name / source.relative_to(original))
        entries = sorted(p for p in stage.rglob('*') if p.is_file())
        if len(entries) > 9999 or sum(p.stat().st_size for p in entries) > 1024**3:
            raise ValueError('Recovery archive exceeds the supported file/unpacked-size limit')
        manifest = {'format_version': 1, 'application_version': __version__, 'ladybug_version': importlib.metadata.version('ladybug'),
                    'profile_id': settings['profile_id'], 'setup_identity': store.identity, 'created_at': stamp(now_utc()),
                    'ledger_schema': 1, 'graph_schema': '1', 'covered_seq': covered_sequence(store),
                    'ledger_revision': ledger_revision(store), 'artifact_revision': artifact_revision(store),
                    'graph_hash': graph_hash, 'graph_revision': graph_revision, 'graph_counts': graph_counts,
                    'files': {str(p.relative_to(stage)): {'sha256': file_hash(p), 'bytes': p.stat().st_size} for p in entries}}
        write_private_json(stage / 'manifest.json', manifest)
        descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(descriptor, 'wb') as stream, zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
                for path in [*entries, stage / 'manifest.json']:
                    archive.write(path, path.relative_to(stage))
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        if destination.stat().st_size > settings['storage']['cloud_backup']['max_archive_bytes']:
            destination.unlink()
            raise ValueError('Recovery archive exceeds configured archive-size budget')
        return manifest


def unpack_verified(path, stage, settings, expected_identity):
    """Treat archive paths/content as untrusted; extract only exact checksummed members."""
    stage = Path(stage)
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        names = [m.filename for m in members]
        if len(members) > 10_000 or len(set(names)) != len(names) or sum(m.file_size for m in members) > 1024**3:
            raise ValueError('Archive exceeds limits or contains duplicate member paths')
        for member in members:
            name = PurePosixPath(member.filename)
            if not name.parts or str(name) != member.filename or name.is_absolute() or '..' in name.parts or '\\' in member.filename or member.is_dir() or stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError('Unsafe recovery archive path/type')
            if member.filename not in {'manifest.json', 'ledger.sqlite3'} and name.parts[0] not in {'graph', 'cache', 'knowledge-sources'}:
                raise ValueError('Unexpected recovery archive member')
        info = archive.getinfo('manifest.json')
        if info.file_size > 5_000_000:
            raise ValueError('Recovery manifest exceeds size limit')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('format_version') != 1 or manifest.get('ledger_schema') != 1 or manifest.get('graph_schema') != '1':
            raise ValueError('Unsupported recovery archive/schema version')
        if manifest.get('profile_id') != settings['profile_id'] or manifest.get('setup_identity') != expected_identity:
            raise ValueError('Recovery archive installation/ledger identity mismatch')
        if manifest.get('ladybug_version') != importlib.metadata.version('ladybug'):
            raise ValueError('Restore with the pinned originating Ladybug version before a reviewed migration')
        if set(manifest['files']) != set(names) - {'manifest.json'}:
            raise ValueError('Archive inventory differs from manifest')
        if 'ledger.sqlite3' not in names or 'graph/schema.cypher' not in names:
            raise ValueError('Recovery archive missing ledger or graph schema')
        for member in members:
            if member.filename == 'manifest.json':
                continue
            target = stage / member.filename
            private_directory(target.parent)
            expected = manifest['files'][member.filename]
            if member.file_size != expected['bytes']:
                raise ValueError('Recovery archive member size mismatch')
            descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with archive.open(member) as source, os.fdopen(descriptor, 'wb') as out:
                shutil.copyfileobj(source, out)
            if file_hash(target) != expected['sha256']:
                raise ValueError('Recovery archive member checksum mismatch')
    return manifest


def verify_archive(path, settings, expected_identity, stage):
    stage = Path(stage)
    manifest = unpack_verified(path, stage, settings, expected_identity)
    ledger = sqlite3.connect((stage / 'ledger.sqlite3').as_uri() + '?mode=ro', uri=True)
    try:
        if ledger.execute('PRAGMA quick_check').fetchone()[0] != 'ok' or ledger.execute('PRAGMA user_version').fetchone()[0] != 1:
            raise ValueError('Restored ledger failed integrity/schema check')
        meta = dict(ledger.execute('SELECT key,value FROM meta'))
        if meta.get('mode') != 'production' or meta.get('profile_id') != settings['profile_id'] or meta.get('setup_identity') != expected_identity:
            raise ValueError('Restored ledger ownership/mode mismatch')
        if not frozen_settings_match(meta.get('frozen_settings'), settings):
            raise ValueError('Restored ledger economics differ from reviewed configuration')
    finally:
        ledger.close()
    restored_settings = json.loads(json.dumps(settings))
    restored_settings['storage']['knowledge_path'] = str(stage / 'restored.lbdb')
    with Knowledge(restored_settings, expected_identity, create=True) as graph:
        graph.import_export(stage / 'graph')
        if graph.fingerprint() != manifest['graph_hash'] or graph.status()['counts'] != manifest['graph_counts']:
            raise ValueError('Restored knowledge graph differs from exported evidence')
        first = graph.rows('MATCH (c:Claim) RETURN c.text LIMIT 1')
        if first:
            graph.search(first[0][0][:100], limit=1)
    return manifest


def current_backup(settings, store):
    row = store.db.execute("SELECT data FROM events WHERE kind IN ('cloud_backup_accepted','cloud_backup_verified') ORDER BY seq DESC LIMIT 1").fetchone()
    if row is None:
        return {'current': False, 'reason': 'No accepted connected Drive upload recorded'}
    receipt = json.loads(row[0])
    with Knowledge(settings, store.identity) as graph:
        revision = graph.meta('revision')
    age = (instant(store.clock()) - instant(receipt.get('accepted_at') or receipt['verified_at'])).total_seconds()
    current = (receipt.get('folder_id') == settings['storage']['cloud_backup']['folder_id']
               and receipt.get('covered_seq') == covered_sequence(store) and receipt.get('graph_revision') == revision
               and receipt.get('ledger_revision') == ledger_revision(store) and receipt.get('artifact_revision') == artifact_revision(store)
               and 0 <= age < settings['storage']['backup_interval_hours'] * 3600)
    return {'current': current, 'receipt': receipt, 'reason': None if current else 'Evidence changed, backup interval elapsed or destination changed'}


def pending_upload(settings, store):
    folder = Path(settings['storage']['backup_directory']).resolve()
    operation = json.loads((folder / 'pending-upload.json').read_text())
    path = Path(operation['path'])
    if path.parent.resolve() != folder or file_hash(path) != operation['sha256']:
        raise ValueError('Pending upload archive was changed; preserve it and inspect before retry')
    manifest = operation['manifest']
    if (manifest['profile_id'] != settings['profile_id'] or manifest['setup_identity'] != store.identity
            or operation['folder_id'] != settings['storage']['cloud_backup']['folder_id']):
        raise ValueError('Pending archive belongs to another installation or backup folder')
    return operation


def cloud_backup(settings, store, *, inventory=None, force=False):
    folder = Path(settings['storage']['backup_directory'])
    private_directory(folder)
    pending = folder / 'pending-upload.json'
    with owner_lock(settings):
        current = current_backup(settings, store)
        if not force and not pending.exists() and current['current']:
            return {'created': False, **current}
        if inventory is None:
            return {'current': False, 'action': 'inventory', 'folder_id': settings['storage']['cloud_backup']['folder_id']}
        files = read_inventory(settings, inventory)
        if pending.exists():
            operation = pending_upload(settings, store)
        else:
            path = folder / ('recovery-' + now_utc().strftime('%Y%m%dT%H%M%S%f') + '.backup.zip')
            manifest = snapshot(settings, store, path)
            sha256 = file_hash(path)
            named = path.with_name(f"investment-discovery-{settings['profile_id']}-{store.identity}-{sha256}.backup.zip")
            path.rename(named)
            destination = settings['storage']['cloud_backup']['folder_id']
            previous = store.db.execute("""SELECT json_extract(data,'$.file_id') FROM events
              WHERE kind IN ('cloud_backup_accepted','cloud_backup_verified','restore_completed')
              AND json_extract(data,'$.folder_id')=? AND json_extract(data,'$.file_id') IS NOT NULL ORDER BY seq DESC LIMIT 1""", (destination,)).fetchone()
            operation = {'path': str(named.resolve()), 'sha256': sha256, 'manifest': manifest,
                         'folder_id': destination, 'file_id': previous[0] if previous else None, 'upload_started': False}
            write_private_json(pending, operation)
        path = Path(operation['path'])
        target_id = operation.get('file_id')
        matches = [item for item in files if item['name'] == path.name and int(item.get('size', -1)) == path.stat().st_size
                   and (target_id is None or item['id'] == target_id)]
        if matches:
            result = accept_upload(settings, store, {'file_id': matches[0]['id'], 'folder_id': operation['folder_id'],
                                   'name': path.name, 'size': path.stat().st_size, 'receipt': matches[0]})
            return result
        if target_id and not any(item['id'] == target_id for item in files):
            raise ValueError('Backup file missing from connected folder; inspect original file before updating')
        check_capacity(settings, path.stat().st_size, files, replace_file_id=target_id)
        arguments = {'file_uri': str(path), 'mime_type': 'application/zip'}
        if target_id:
            arguments.update(fileId=target_id, name=path.name)
        else:
            arguments.update(file_name=path.name, parent_folder_id=operation['folder_id'])
        return {'current': False, 'action': 'inspect_upload' if operation['upload_started'] else 'update' if target_id else 'upload',
                'tool': 'update_file' if target_id else 'upload_file', 'arguments': arguments,
                'sha256': operation['sha256']}


def start_upload(settings, store):
    with owner_lock(settings):
        operation = pending_upload(settings, store)
        if operation['upload_started']:
            raise ValueError('Upload outcome uncertain; inspect connected Drive inventory before retry')
        operation['upload_started'] = True
        write_private_json(Path(settings['storage']['backup_directory']) / 'pending-upload.json', operation)
        return {'upload_started': True, 'file_name': Path(operation['path']).name}


def retry_upload(settings, store, evidence):
    if evidence.get('failed_before_creation') is not True or not evidence.get('reason'):
        raise ValueError('Retry requires observed failure before remote creation and its reason; resolve ambiguous uploads through inventory')
    with owner_lock(settings):
        operation = pending_upload(settings, store)
        operation.update(upload_started=False, retry_evidence=evidence)
        write_private_json(Path(settings['storage']['backup_directory']) / 'pending-upload.json', operation)
        return {'retry_ready': True}


def accept_upload(settings, store, response):
    with owner_lock(settings):
        operation = pending_upload(settings, store)
        path = Path(operation['path'])
        if (not response.get('file_id') or response.get('folder_id') != operation['folder_id']
                or response.get('name') != path.name or not response.get('receipt')
                or operation.get('file_id') and response['file_id'] != operation['file_id']):
            raise ValueError('Connected Drive upload receipt must identify actual file, name and backup folder')
        if response.get('size') is not None and int(response['size']) != path.stat().st_size:
            raise ValueError('Connected Drive upload size mismatch')
        manifest = operation['manifest']
        receipt = {'provider': 'google_drive', 'folder_id': operation['folder_id'], 'file_id': response['file_id'],
                   'name': path.name, 'sha256': operation['sha256'], 'accepted_at': stamp(store.clock()),
                   'covered_seq': manifest['covered_seq'], 'graph_revision': manifest['graph_revision'],
                   'ledger_revision': manifest['ledger_revision'], 'artifact_revision': manifest['artifact_revision'],
                   'graph_hash': manifest['graph_hash'], 'upload_accepted': True, 'remote_integrity_verified': False,
                   'connector_receipt': response['receipt']}
        with store.transaction():
            store.event('cloud_backup_accepted', **receipt)
        (path.parent / 'pending-upload.json').unlink()
        path.unlink()
        return {'created': True, **current_backup(settings, store)}


def restore(settings, archive, expected_identity, *, file_id=None):
    archive = Path(archive)
    folder = Path(settings['storage']['backup_directory'])
    private_directory(folder)
    root = Path(settings['storage']['database_path']).parent
    with owner_lock(settings, create=True):
        if any(path.name != '.squad-lock' for path in root.iterdir()):
            raise ValueError('Restore target must be empty; existing state is never overwritten')
        with tempfile.TemporaryDirectory(dir=folder, prefix='.restore-') as temporary:
            temporary = Path(temporary)
            manifest = verify_archive(archive, settings, expected_identity, temporary / 'state')
            stage = temporary / 'state'
            marker = root / '.restore-in-progress.json'
            write_private_json(marker, {'file_id': file_id, 'setup_identity': expected_identity})
            # Marker deliberately survives an interrupted/partial installation; ordinary commands stop.
            _private_copy(stage / 'ledger.sqlite3', settings['storage']['database_path'])
            _private_copy(stage / 'restored.lbdb', settings['storage']['knowledge_path'])
            for name in ('knowledge-sources', 'cache'):
                if (stage / name).exists():
                    for path in (stage / name).rglob('*'):
                        if path.is_file():
                            _private_copy(path, root / name / path.relative_to(stage / name))
            store = _open_store(settings, restoring_identity=expected_identity)
            try:
                with store.transaction():
                    store.event('restore_completed', file_id=file_id, folder_id=settings['storage']['cloud_backup']['folder_id'],
                                sha256=file_hash(archive),
                                original_identity=expected_identity, requires_reconciliation=True)
            finally:
                store.close()
            marker.unlink()
        return {'restored': True, 'setup_identity': expected_identity, 'file_id': file_id,
                'next': 'Review saved automations and message history before resuming; preserve pending and uncertain deliveries'}
