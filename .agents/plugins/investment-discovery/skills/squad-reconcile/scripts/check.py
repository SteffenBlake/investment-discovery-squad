"""Run isolated Python logic tests against the shared skill runtime."""

import os
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(os.environ.get("SQUAD_REPO", Path(__file__).resolve().parents[6])).resolve()
    env = {key: value for key, value in os.environ.items() if not key.startswith('SQUAD_')}
    env['PYTHONPATH'] = os.pathsep.join((str(root / '.agents/skills/squad-onboard/scripts'), str(root)))
    return subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-q'], cwd=root, env=env).returncode


if __name__ == '__main__':
    raise SystemExit(main())
