"""Publish a complete public plugin archive atomically."""

import hashlib
import fnmatch
import json
import os
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(os.environ.get("SQUAD_REPO", Path(__file__).resolve().parents[6])).resolve()
PLUGIN = ROOT / '.agents/plugins/investment-discovery'
NAMES = ('squad-onboard', 'squad-monitor', 'squad-research', 'squad-reconcile', 'squad-trades')
EXCLUDED = ('__pycache__', '*.pyc', '*.pyo', '.venv', 'dist', 'build', '*.egg-info',
            '.env*', '*.local.json', '*.sqlite*', '*.lbdb*', '*.wal', '*.zip',
            'state', 'profiles', 'knowledge-sources', 'cache', '.squad-lock',
            'pending-upload.json', '.restore-in-progress.json', 'deployment.json', 'runtime.json')


def archive():
    required = [ROOT / 'LICENSE', PLUGIN / 'plugin.json']
    required.extend(PLUGIN / 'skills' / name / 'SKILL.md' for name in NAMES)
    required.extend(PLUGIN / 'skills/squad-onboard' / name for name in
                    ('scripts/main.py', 'scripts/requirements.txt', 'scripts/investment_engine/cli.py',
                     'references/settings.json', 'references/setup.md'))
    for path in required:
        if not path.is_file() or path.is_symlink():
            raise ValueError('Missing/unsafe release input: ' + str(path))
    entries = [(ROOT / 'LICENSE', 'LICENSE')]
    for path in sorted(PLUGIN.rglob('*')):
        if any(fnmatch.fnmatch(part, pattern) for part in path.relative_to(PLUGIN).parts for pattern in EXCLUDED):
            continue
        if path.is_symlink():
            raise ValueError('Release sources must not be symlinks: ' + str(path))
        if path.is_file():
            entries.append((path, str(path.relative_to(PLUGIN))))
    # Read every input before creating output; failed writes leave prior release intact.
    contents = [(name, path.read_bytes()) for path, name in entries]
    folder = ROOT / 'dist'
    folder.mkdir(exist_ok=True)
    target = folder / 'investment-discovery-plugin.zip'
    descriptor, temporary_name = tempfile.mkstemp(dir=folder, prefix='.plugin-', suffix='.tmp')
    try:
        with os.fdopen(descriptor, 'wb') as stream, zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as output:
            for name, data in contents:
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                output.writestr(info, data)
        os.replace(temporary_name, target)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return {'archive': str(target), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
            'bytes': target.stat().st_size}


if __name__ == '__main__':
    print(json.dumps(archive()))
