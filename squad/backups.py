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
from .configuration import write_private_json
from .drive import Drive
from .knowledge import Knowledge
from .runtime import owner_lock
from .storage import FROZEN, open_store
from .store import IMMUTABLE
from .util import canonical, digest, instant, now_utc, stamp

BOOKKEEPING = ("cloud_backup_verified", "backup_created", "deployment_applied")


def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def covered_sequence(store):
    return store.db.execute("SELECT COALESCE(MAX(seq),0) FROM events WHERE kind NOT IN (?,?,?)", BOOKKEEPING).fetchone()[0]


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
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'wb') as out, Path(source).open('rb') as inp:
        shutil.copyfileobj(inp, out)


def snapshot(settings, store, destination):
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Recovery archive already exists')
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
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
            raise ValueError('Recovery archive profile/ledger identity mismatch')
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
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
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
        if meta.get('frozen_settings') != canonical({key: settings[key] for key in FROZEN}):
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
    row = store.db.execute("SELECT data FROM events WHERE kind='cloud_backup_verified' ORDER BY seq DESC LIMIT 1").fetchone()
    if row is None:
        return {'current': False, 'reason': 'No independently verified cloud recovery archive'}
    receipt = json.loads(row[0])
    with Knowledge(settings, store.identity) as graph:
        revision = graph.meta('revision')
    age = (instant(store.clock()) - instant(receipt['verified_at'])).total_seconds()
    current = (receipt.get('folder_id') == settings['storage']['cloud_backup']['folder_id']
               and receipt.get('covered_seq') == covered_sequence(store) and receipt.get('graph_revision') == revision
               and receipt.get('ledger_revision') == ledger_revision(store) and receipt.get('artifact_revision') == artifact_revision(store)
               and 0 <= age < settings['storage']['backup_interval_hours'] * 3600)
    return {'current': current, 'receipt': receipt, 'reason': None if current else 'Evidence changed, backup interval elapsed or destination changed'}


def cloud_backup(settings, store, *, drive=None, force=False):
    drive = drive or Drive(settings)
    folder = Path(settings['storage']['backup_directory'])
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    pending = folder / 'pending-upload.json'
    with owner_lock(settings):
        if not force and not pending.exists():
            current = current_backup(settings, store)
            if current['current']:
                return {'created': False, **current}
        if pending.exists():
            operation = json.loads(pending.read_text())
            path = Path(operation['path'])
            if path.parent.resolve() != folder.resolve() or file_hash(path) != operation['sha256']:
                raise ValueError('Pending upload archive was changed; preserve it and inspect before retry')
        else:
            path = folder / ('recovery-' + now_utc().strftime('%Y%m%dT%H%M%S%f') + '.backup.zip')
            manifest = snapshot(settings, store, path)
            operation = {'path': str(path.resolve()), 'sha256': file_hash(path), 'manifest': manifest}
            write_private_json(pending, operation)
        manifest = operation['manifest']
        if manifest['profile_id'] != settings['profile_id'] or manifest['setup_identity'] != store.identity:
            raise ValueError('Pending archive belongs to another installation')
        remote = drive.upload(path, manifest, operation['sha256'])
        metadata, downloaded = drive.download(remote['id'], expected_identity=store.identity)
        if hashlib.sha256(downloaded).hexdigest() != operation['sha256']:
            raise ValueError('Uploaded backup bytes do not match the local recovery archive')
        with tempfile.TemporaryDirectory(dir=folder, prefix='.verify-') as temporary:
            temporary = Path(temporary)
            downloaded_path = temporary / 'download.zip'
            downloaded_path.write_bytes(downloaded)
            restored = verify_archive(downloaded_path, settings, store.identity, temporary / 'state')
        receipt = {'provider': 'google_drive', 'folder_id': settings['storage']['cloud_backup']['folder_id'],
                   'file_id': remote['id'], 'sha256': operation['sha256'], 'verified_at': stamp(store.clock()),
                   'covered_seq': restored['covered_seq'], 'graph_revision': restored['graph_revision'],
                   'ledger_revision': restored['ledger_revision'], 'artifact_revision': restored['artifact_revision'],
                   'graph_hash': restored['graph_hash'], 'restore_tested': True}
        with store.transaction():
            store.event('cloud_backup_verified', **receipt)
        pending.unlink()
        # Completing an older pending upload need not cover writes made since its creation.
        current = current_backup(settings, store)
        if not current['current']:
            return cloud_backup(settings, store, drive=drive, force=True)
        return {'created': True, **current}


def restore(settings, file_id, expected_identity, *, drive=None):
    drive = drive or Drive(settings)
    folder = Path(settings['storage']['backup_directory'])
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    root = Path(settings['storage']['database_path']).parent
    with owner_lock(settings, create=True):
        if any(path.name != '.squad-lock' for path in root.iterdir()):
            raise ValueError('Restore target must be empty; existing state is never overwritten')
        metadata, downloaded = drive.download(file_id, expected_identity=expected_identity)
        with tempfile.TemporaryDirectory(dir=folder, prefix='.restore-') as temporary:
            temporary = Path(temporary)
            archive = temporary / 'download.zip'
            archive.write_bytes(downloaded)
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
            marker.unlink()
        store = open_store(settings)
        try:
            with store.transaction():
                store.event('restore_completed', file_id=file_id, sha256=hashlib.sha256(downloaded).hexdigest(),
                            original_identity=expected_identity, requires_reconciliation=True)
        finally:
            store.close()
        return {'restored': True, 'setup_identity': expected_identity, 'file_id': file_id,
                'next': 'Reconcile deployment and actual notification history before resuming; never blindly resend'}
