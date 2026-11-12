"""Required isolated checks; never inherit a user's configuration or credentials."""

import os
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent.parent
    env = {key: value for key, value in os.environ.items() if not key.startswith('SQUAD_')}
    checks = [
        (['-m', 'unittest', 'discover', '-s', 'tests', '-v'], False),
        (['scripts/build_plugin.py', '--check'], False),
        (['scripts/check_package.py'], False),
        (['-m', 'squad', 'demo'], True),
        (['-m', 'squad', 'onboarding'], True),
        (['-m', 'squad', 'doctor'], False),
    ]
    for arguments, quiet in checks:
        result = subprocess.run([sys.executable, *arguments], cwd=root, env=env,
                                stdout=subprocess.DEVNULL if quiet else None)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
