"""Reproducible native-task plans and drift checks; platform tools perform actual mutations."""

import json
import subprocess
from datetime import timedelta
from pathlib import Path

from .storage import open_store
from .knowledge import Knowledge
from .util import ROOT, canonical, digest, instant, now_utc, stamp


def git(*args):
    result = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)
    if result.returncode:
        raise ValueError("Git operation failed: " + result.stderr.strip())
    return result.stdout.strip()


def source_state():
    revision = git("rev-parse", "HEAD")
    dirty = bool(git("status", "--porcelain", "--untracked-files=normal"))
    files = git("ls-files", "-z").split("\0")
    content = {name: (ROOT / name).read_bytes().hex() for name in files if name and (ROOT / name).is_file()}
    skills = {str(p.relative_to(ROOT / ".agents" / "skills")): p.read_text()
              for folder in (ROOT / ".agents" / "skills").glob("squad-*") for p in folder.rglob("*") if p.is_file()}
    return {"revision": revision, "digest": digest(content), "dirty": dirty, "skills_digest": digest(skills)}


def desired(settings):
    source = source_state()
    store = open_store(settings)
    try:
        identity = store.identity
        with Knowledge(settings, identity) as graph:
            graph_identity = graph.status()["setup_identity"]
    finally:
        store.close()
    tasks = []
    for workflow in json.loads((ROOT / "workflows.json").read_text())["tasks"]:
        schedule = settings["schedules"][workflow["key"]]
        key = "squad/" + settings["profile_id"] + "/" + workflow["key"]
        # Deliberately thin: method stays in the installed/versioned skill, not a stale prompt copy.
        binding = "Configuration: required individual native SQUAD_* variables on the owner runtime.\n"
        prompt = (f"Use ${workflow['skill']}. SQUAD_TASK_KEY={key}\n"
                  f"SQUAD_REPO={ROOT}\n" + binding +
                  f"Central owner: {settings['storage']['runtime_id']} ({settings['runtime']['kind']}). Keep graph, ledger and sources outside worktrees.\n"
                  "Use the same owner for knowledge reads/writes. Delegated researchers return structured batches; never initialize a separate worker copy. "
                  "Read the current skill and injected configuration. Check deployment drift before financial work; "
                  "reconciliation must compare current Git source and actual saved task state. "
                  "Never infer execution or notification delivery from worker output alone.")
        tasks.append({"key": key, "title": workflow["title"] + " [" + settings["profile_id"] + "]",
                      "prompt": prompt, "rrule": schedule.get("rrule") if schedule["enabled"] else None,
                      "timezone": settings["timezone"], "is_enabled": schedule["enabled"],
                      "model": settings["worker"]["model"], "reasoning_effort": settings["worker"]["reasoning_effort"],
                      "runtime_id": settings["storage"]["runtime_id"]})
    profile_digest = digest(settings)
    signature = digest({"tasks": tasks, "source": source["digest"], "profile": profile_digest, "setup_identity": identity})
    return {"source": source, "profile_id": settings["profile_id"], "setup_identity": identity,
            "database_path": settings["storage"]["database_path"], "knowledge_path": settings["storage"]["knowledge_path"],
            "runtime_kind": settings["runtime"]["kind"], "graph_setup_identity": graph_identity, "signature": signature, "profile_digest": profile_digest,
            "ready_to_apply": not source["dirty"], "tasks": tasks,
            "note": "Use actual native schedule tools to apply; this JSON is not a platform schedule manifest"}


def compare(plan, observed):
    actions, seen = [], {}
    prefix = "squad/" + plan["profile_id"] + "/"
    for task in observed.get("tasks", []):
        key = task.get("key", "")
        if not key.startswith(prefix):
            continue
        if key in seen:
            actions.append({"action": "duplicate", "key": key, "ids": [seen[key].get("id"), task.get("id")]})
        seen[key] = task
    expected_keys = {t["key"] for t in plan["tasks"]}
    for task in plan["tasks"]:
        current = seen.get(task["key"])
        if current is None:
            if task["is_enabled"]:
                actions.append({"action": "create", "key": task["key"], "desired": task})
            continue
        if not current.get("id"):
            actions.append({"action": "invalid_receipt", "key": task["key"]})
            continue
        if not task["is_enabled"]:
            if current.get("is_enabled"):
                actions.append({"action": "disable", "key": task["key"], "id": current["id"]})
            continue
        changes = {k: v for k, v in task.items() if k != "key" and v is not None and current.get(k) != v}
        if changes:
            actions.append({"action": "update", "key": task["key"], "id": current["id"], "changes": changes})
    for key, task in seen.items():
        if key not in expected_keys and task.get("is_enabled"):
            actions.append({"action": "disable_obsolete", "key": key, "id": task.get("id")})
    return actions


def _fresh(value):
    try:
        delta = now_utc() - instant(value)
    except (ValueError, TypeError, AttributeError):
        return False
    return timedelta(0) <= delta <= timedelta(minutes=15)


def record(plan, settings, receipt):
    if not plan["ready_to_apply"]:
        raise ValueError("Commit reviewed source before recording deployment; dirty/untracked source cannot be deployed")
    if not _fresh(receipt.get("observed_at", "")):
        raise ValueError("Need fresh timestamped native task readback")
    loaded = receipt.get("loaded_skills", {})
    if loaded.get("digest") != plan["source"]["skills_digest"] or loaded.get("source") not in {"repository", "installed_plugin"}:
        raise ValueError("Loaded skill contents do not match this revision; refresh the plugin or use matching repo skills")
    actions = compare(plan, receipt)
    if actions:
        raise ValueError("Native task drift remains: " + canonical(actions))
    probe = receipt.get("runtime_probe", {})
    for key in ("setup_identity", "database_path", "knowledge_path", "runtime_kind", "graph_setup_identity"):
        if probe.get(key) != plan[key]:
            raise ValueError("Independent runtime probe differs: " + key)
    if probe.get("runtime_id") != settings["storage"]["runtime_id"] or not probe.get("independent_run_receipt"):
        raise ValueError("Need actual independent worker execution/persistence receipt")
    if not _fresh(probe.get("observed_at", "")):
        raise ValueError("Runtime probe is stale")
    delivery = receipt.get("delivery", {})
    if delivery.get("destination") != settings["notification"]["destination"] or not delivery.get("receipt"):
        raise ValueError("Need actual delivery proof to the configured destination")
    from .backups import current_backup
    verification_store = open_store(settings)
    try:
        recovery = current_backup(settings, verification_store)
        if not recovery["current"] or not recovery.get("receipt", {}).get("restore_tested"):
            raise ValueError("Deployment requires a current uploaded, downloaded and restore-tested cloud backup")
    finally:
        verification_store.close()
    value = {"cloud_backup": recovery["receipt"], "signature": plan["signature"], "source": plan["source"], "setup_identity": plan["setup_identity"],
             "recorded_at": stamp(now_utc()), "observation": receipt,
             "verification_boundary": "Platform receipts are assertions supplied by the actual Dot tools, not authenticated by this CLI"}
    store = open_store(settings)
    try:
        with store.transaction():
            store.event("deployment_applied", **value)
    finally:
        store.close()
    path = Path(settings["storage"]["database_path"]).parent / "deployment.json"
    from .configuration import write_private_json
    write_private_json(path, value)
    return {"recorded": True, "signature": plan["signature"], "path": str(path)}


def check(plan, settings, observed=None):
    store = open_store(settings)
    try:
        row = store.db.execute("SELECT seq,data FROM events WHERE kind='deployment_applied' ORDER BY seq DESC LIMIT 1").fetchone()
        receipt = json.loads(row["data"]) if row else None
        last_restore = store.db.execute("SELECT COALESCE(MAX(seq),0) FROM events WHERE kind='restore_completed'").fetchone()[0]
        requires_recovery_review = bool(row and last_restore >= row["seq"])
    finally:
        store.close()
    drift = compare(plan, observed) if observed is not None else []
    if observed is not None and not _fresh(observed.get("observed_at")):
        drift.append({"action": "refresh_readback", "reason": "Native task readback is missing or stale"})
    current = bool(receipt and receipt.get("signature") == plan["signature"] and plan["ready_to_apply"] and not drift and not requires_recovery_review)
    return {"status": "CURRENT" if current else "DRIFT" if receipt else "NOT_APPLIED",
            "current": current, "signature": plan["signature"], "actions": drift,
            "native_state_readback_supplied": observed is not None, "restore_requires_reconciliation": requires_recovery_review,
            "note": "A cached receipt does not prove an external task remains enabled or that a phone received push"}


def deployment_command(args, settings):
    if args.action == "sync":
        if settings["gitops"]["update_policy"] != "fast_forward":
            raise ValueError("Approved-ref fast-forward reconciliation is required")
        if source_state()["dirty"]:
            raise ValueError("Working tree not clean; refusing to update")
        ref = settings["gitops"]["ref"]
        import re
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}", ref) or ".." in ref:
            raise ValueError("Unsupported Git ref")
        before = git("rev-parse", "HEAD")
        git("fetch", "origin", ref)
        git("merge", "--ff-only", "FETCH_HEAD")
        return {"changed": before != git("rev-parse", "HEAD"), "revision": git("rev-parse", "HEAD"),
                "next": "Start a fresh command invocation; regenerate plan and reconcile native schedules"}
    plan = desired(settings)
    if args.action == "plan":
        if args.observed:
            plan["actions"] = compare(plan, json.loads(Path(args.observed).read_text()))
        return plan
    if args.action == "record":
        if not args.file:
            raise ValueError("--file must contain actual native readback and receipts")
        return record(plan, settings, json.loads(Path(args.file).read_text()))
    observed = json.loads(Path(args.observed).read_text()) if args.observed else None
    return check(plan, settings, observed)
