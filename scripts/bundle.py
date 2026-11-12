"""Build native plugin/source release artifacts from public allowlisted paths only."""

import hashlib
import json
import zipfile
from pathlib import Path

from build_plugin import NAMES, ROOT, SETUP_REFERENCE, build


def public_files():
    names = {"README.md", "REQUIREMENTS.md", "AGENTS.md", "DOT_START_HERE.md", "pyproject.toml",
             "LICENSE", ".gitignore", ".env.example", "settings.json", "workflows.json",
             ".agents/plugins/marketplace.json", ".codex/config.toml", "docs/VERIFICATION.json",
             "examples/README.md", "examples/acceptance-result.json", "examples/acceptance-alert.md"}
    for folder, patterns in {"squad": ["*.py"], "tests": ["*.py"], "scripts": ["*.py", "*.sh"],
                             "docs": ["*.md"], ".github/workflows": ["*.yml", "*.yaml"]}.items():
        for pattern in patterns:
            names.update(str(p.relative_to(ROOT)) for p in (ROOT / folder).glob(pattern) if p.is_file())
    names.add(".agents/skills/compress-output/SKILL.md")
    names.update(f".agents/skills/{name}/SKILL.md" for name in NAMES)
    names.add(str(SETUP_REFERENCE))
    plugin = ROOT / "plugins" / "investment-discovery"
    names.add(str((plugin / "plugin.json").relative_to(ROOT)))
    names.update(str((plugin / "skills" / name / "SKILL.md").relative_to(ROOT)) for name in NAMES)
    names.add('plugins/investment-discovery/skills/squad-onboard/references/SETUP.md')
    return sorted(names)


def archive(name, entries):
    target = ROOT / "dist" / name
    target.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as output:
        for source, destination in entries:
            file = ROOT / source
            if file.is_symlink():
                raise ValueError("Release sources must not be symlinks: " + source)
            info = zipfile.ZipInfo(destination, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            output.writestr(info, file.read_bytes())
    return {"archive": str(target), "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "bytes": target.stat().st_size, "live_state_included": False}


if __name__ == "__main__":
    build(check=True)
    source = public_files()
    plugin_prefix = "plugins/investment-discovery/"
    results = [archive("investment-discovery-plugin.zip",
                       [(path, path.removeprefix(plugin_prefix)) for path in source if path.startswith(plugin_prefix)]),
               archive("investment-discovery-squad.zip", [(path, "investment-discovery-squad/" + path) for path in source])]
    print(json.dumps(results, indent=2))
