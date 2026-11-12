"""Build native plugin skill copies from canonical repo skills; --check detects drift."""
import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAMES = ('squad-onboard', 'squad-monitor', 'squad-research', 'squad-reconcile', 'squad-trades')
SETUP_REFERENCE = Path('.agents/skills/squad-onboard/references/SETUP.md')

def build(check=False):
    changed = []
    setup = ROOT / SETUP_REFERENCE
    instructions = (ROOT / 'DOT_START_HERE.md').read_bytes()
    if not setup.is_file() or setup.read_bytes() != instructions:
        changed.append('squad-onboard/setup-guide')
        if not check:
            setup.parent.mkdir(parents=True, exist_ok=True)
            setup.write_bytes(instructions)
    for name in NAMES:
        source = ROOT / '.agents' / 'skills' / name
        target = ROOT / 'plugins' / 'investment-discovery' / 'skills' / name
        originals = {p.relative_to(source): p.read_bytes() for p in source.rglob('*') if p.is_file()}
        copies = {p.relative_to(target): p.read_bytes() for p in target.rglob('*') if p.is_file()} if target.exists() else {}
        if originals != copies:
            changed.append(name)
            if not check:
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(source, target)
    if check and changed:
        raise SystemExit('Plugin copies stale: ' + ', '.join(changed) + '; run python3 scripts/build_plugin.py')
    return changed

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--check', action='store_true')
    print(build(p.parse_args().check))
