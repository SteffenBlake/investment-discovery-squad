"""Offline native-package contract and cross-file consistency checks; no user state."""

import json
import re
import tomllib

from build_plugin import NAMES, ROOT, SETUP_REFERENCE, build


def check():
    build(check=True)
    marketplace = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
    plugin = marketplace["plugins"][0]
    folder = (ROOT / plugin["source"]["path"]).resolve()
    assert ROOT in folder.parents and plugin["source"]["source"] == "local"
    manifest = json.loads((folder / "plugin.json").read_text())
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert manifest["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    assert manifest["name"] == plugin["name"]
    assert manifest["version"] == project["project"]["version"]
    config = tomllib.loads((ROOT / ".codex/config.toml").read_text())
    assert config["plugins"][manifest["name"] + "@" + marketplace["name"]]["enabled"] is True
    assert {p.name for p in (folder / "skills").iterdir() if p.is_dir()} == set(NAMES)
    setup = (ROOT / 'DOT_START_HERE.md').read_bytes()
    assert (ROOT / SETUP_REFERENCE).read_bytes() == setup
    assert (folder / 'skills/squad-onboard/references/SETUP.md').read_bytes() == setup
    for name in NAMES:
        text = (folder / "skills" / name / "SKILL.md").read_text()
        frontmatter = re.match(r"\A---\nname: ([a-z0-9-]+)\ndescription: ([^\n]+)\n---\n", text)
        assert frontmatter and frontmatter.group(1) == name and len(frontmatter.group(2)) <= 1024
    workflows = json.loads((ROOT / "workflows.json").read_text())["tasks"]
    assert len({w["key"] for w in workflows}) == len(workflows)
    assert {w["key"] for w in workflows} == {"monitor", "research", "reconcile"}
    assert all(w["skill"] in NAMES for w in workflows)
    print("Native package contracts and generated skills: passed")


if __name__ == "__main__":
    check()
