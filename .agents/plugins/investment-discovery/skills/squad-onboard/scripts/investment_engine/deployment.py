"""Approved-ref, clean-tree, fast-forward Git updates."""

import subprocess

from .util import ROOT


def git(*args):
    result = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)
    if result.returncode:
        raise ValueError("Git operation failed: " + result.stderr.strip())
    return result.stdout.strip()


def deployment_command(args, settings):
    if settings["gitops"]["update_policy"] != "fast_forward":
        raise ValueError("Approved-ref fast-forward reconciliation is required")
    if git("status", "--porcelain", "--untracked-files=normal"):
        raise ValueError("Working tree not clean; refusing to update")
    ref = settings["gitops"]["ref"]
    import re
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}", ref) or ".." in ref:
        raise ValueError("Unsupported Git ref")
    before = git("rev-parse", "HEAD")
    git("fetch", "origin", ref)
    git("merge", "--ff-only", "FETCH_HEAD")
    return {"changed": before != git("rev-parse", "HEAD"), "revision": git("rev-parse", "HEAD"),
            "next": "Start a fresh command invocation; refresh loaded skills and reconcile native tasks through Dot tools"}
