import argparse
import json
import sqlite3
import sys
from pathlib import Path

from . import __version__
from .engine import Engine
from .portfolio import Portfolio
from .runner import run
from .configuration import absolute_path, load_configuration, configuration_template, build_runtime_settings, environment_fields, has_configuration, redact, reject_secrets
from .provisioning import open_store, storage_plan, adopt, check_initialization_target
from .runtime import owner_lock
from .knowledge import Knowledge
from . import backups


def read_json(path):
    value = json.loads(Path(path).read_text())
    reject_secrets(value)
    return value



def parser():
    p = argparse.ArgumentParser(description="Dot-ready investment discovery; recommendations only")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("init", "doctor", "status", "portfolio", "alerts", "storage-plan", "onboarding", "backup-due", "setup-runtime"):
        sub.add_parser(name)
    for name in ("run", "research"):
        q = sub.add_parser(name)
        q.add_argument("--offline", action="store_true")
        q.add_argument("--continue-work", action="store_true", help="Resume remaining work after handling delivery")
        q.add_argument("--preflight", action="store_true", help="Initial collection on an empty forecast ledger")
    sub.add_parser("export").add_argument("--output")
    q = sub.add_parser("backup")
    q.add_argument("action", nargs="?", choices=["cloud", "snapshot", "list", "verify", "restore"], default="cloud")
    q.add_argument("--output")
    q.add_argument("--file-id")
    q.add_argument("--expected-identity")
    q.add_argument("--force", action="store_true")
    q = sub.add_parser("knowledge")
    q.add_argument("action", choices=["status", "ingest", "search", "show", "context"])
    q.add_argument("--file")
    q.add_argument("--query")
    q.add_argument("--id")
    q.add_argument("--type", choices=["Claim", "Entity", "Source", "Batch"], default="Claim")
    q.add_argument("--symbols", help="Comma-separated symbols")
    q.add_argument("--portfolio", help="Save supplied portfolio snapshot and return related research")
    q.add_argument("--limit", type=int, default=15)
    q.add_argument("--hops", type=int, default=2)
    for name in ("discover", "forecast", "fill", "prices"):
        sub.add_parser(name).add_argument("--file", required=True)
    sub.add_parser('prepare-test').add_argument('--file', required=True)
    q = sub.add_parser('trial')
    q.add_argument('action', choices=['status', 'review'])
    q.add_argument('--file', help='Private JSON containing performance review and user decision')
    q = sub.add_parser("backtest")
    q.add_argument("--signal", required=True)
    q.add_argument("--dataset", required=True)
    sub.add_parser("report").add_argument("--signal", required=True)
    q = sub.add_parser("idea")
    q.add_argument("--prediction", required=True)
    q.add_argument("--portfolio", required=True, help="Actual user-supplied cash, currency and holdings snapshot")
    q = sub.add_parser("state")
    q.add_argument("--signal", required=True)
    q.add_argument("--to", choices=["REJECTED", "DEGRADED", "INVALIDATED"], required=True)
    q.add_argument("--reason", required=True)
    sub.add_parser("claim").add_argument("--alert", required=True)
    for name in ("ack", "release"):
        q = sub.add_parser(name)
        q.add_argument("--alert", required=True)
        q.add_argument("--token", required=True)
        q.add_argument("--receipt" if name == "ack" else "--confirmed-not-sent", required=True)
    q = sub.add_parser("adopt")
    q.add_argument("--confirm-currency", required=True)
    q.add_argument("--confirm-starting-cash", required=True)
    q = sub.add_parser("deployment")
    q.add_argument("action", choices=["sync"])
    return p


def execute(args):
    if args.command in {"onboarding", "setup-runtime"} or args.command == "doctor" and not has_configuration():
        return _execute(args)
    installation = load_configuration(require_storage_acceptance=args.command != "storage-plan")
    args._configuration = installation
    if args.command == "storage-plan" or args.command == "doctor" and not Path(installation["storage"]["database_path"]).exists():
        return _execute(args)
    if args.command == "backup" and args.action in {"restore", "list", "verify"}:
        return _execute(args)
    with owner_lock(installation, create=args.command == "init"):
        return _execute(args)


def _execute(args):
    if args.command == "setup-runtime":
        import importlib.metadata
        import tempfile
        with tempfile.TemporaryDirectory(prefix="squad-runtime-test-") as folder:
            cfg = {"profile_id": "runtime-probe", "storage": {"knowledge_path": str(Path(folder) / "probe.lbdb")}}
            with Knowledge(cfg, "synthetic-runtime-probe", create=True) as graph:
                graph.ensure_index()
        return {"ladybug_version": importlib.metadata.version("ladybug"), "fts_available": True, "production_database_created": False}
    if args.command == "onboarding":
        return {"configuration_template": configuration_template(),
                "guide": str(Path(__file__).resolve().parents[2] / "references/configuration.md"), "storage_guide": str(Path(__file__).resolve().parents[2] / "references/storage.md"),
                "database_created": False, "environment_variables": {key: {"path": ".".join(value[0]), "type": value[1]} for key, value in environment_fields().items()},
                "note": "Required cloud workflow: individual native variables, vault-bound Google refresh credentials, reviewed Ladybug/SQLite storage and verified Drive recovery"}
    if args.command == "doctor" and not has_configuration():
        return {"repo_ready": True, "operational_ready": False, "stage": "ONBOARDING_REQUIRED",
                "database_created": False, "guide": str(Path(__file__).resolve().parents[2] / "references/setup.md")}
    installation = getattr(args, "_configuration", None) or load_configuration(require_storage_acceptance=args.command != "storage-plan")
    if args.command == "storage-plan":
        return storage_plan(installation)
    settings = build_runtime_settings(installation)
    if args.command == "adopt":
        return adopt(settings, args.confirm_currency, args.confirm_starting_cash)
    if args.command == "backup" and args.action in {"list", "verify", "restore"}:
        from .drive import Drive
        drive = Drive(settings)
        if args.action == "list":
            return {"backups": drive.list()}
        if not args.file_id or not args.expected_identity:
            raise ValueError("Specify actual --file-id and --expected-identity; never select or relabel a ledger implicitly")
        if args.action == "restore":
            return backups.restore(settings, args.file_id, args.expected_identity, drive=drive)
        import tempfile
        import hashlib
        metadata, data = drive.download(args.file_id, expected_identity=args.expected_identity)
        with tempfile.TemporaryDirectory(prefix="squad-verify-") as folder:
            path = Path(folder) / "download.zip"
            path.write_bytes(data)
            manifest = backups.verify_archive(path, settings, args.expected_identity, Path(folder) / "state")
        return {"verified": True, "file_id": args.file_id, "sha256": hashlib.sha256(data).hexdigest(), "setup_identity": manifest["setup_identity"], "restore_tested": True}
    if args.command == "deployment":
        from .deployment import deployment_command
        return deployment_command(args, settings)
    if args.command == "doctor" and not Path(installation["storage"]["database_path"]).exists():
        return {"repo_ready": True, "operational_ready": False, "stage": "DATABASE_NOT_INITIALIZED",
                "database_created": False, "next": "Review storage-plan, then run init"}
    if args.command == 'init':
        check_initialization_target(settings)
    store = open_store(settings, initialize=args.command == "init")
    engine = Engine(store, settings)
    try:
        command = args.command
        if command == "init":
            with Knowledge(settings, store.identity, create=True) as graph:
                graph_status = graph.status()
            return {"initialized": str(store.path), "database_path": str(store.path.resolve()),
                    "setup_identity": store.identity, "mode": store.mode, "monitoring_active": False, "knowledge": graph_status,
                    "next": "Follow squad-onboard references/setup.md for cloud-thread checks, schedules and setup confirmation message"}
        if command == "knowledge":
            if args.action == "context":
                from .briefing import portfolio_context
                return portfolio_context(engine, read_json(args.portfolio) if args.portfolio else None,
                                         symbols=args.symbols.split(",") if args.symbols else None, query=args.query, limit=args.limit, hops=args.hops)
            with Knowledge(settings, store.identity) as graph:
                if args.action == "status":
                    return graph.status()
                if args.action == "ingest":
                    if not args.file:
                        raise ValueError("knowledge ingest requires --file")
                    result = graph.ingest(read_json(args.file))
                    with store.transaction():
                        if not store.db.execute("SELECT 1 FROM events WHERE kind='knowledge_batch_ingested' AND json_extract(data,'$.batch_id')=?", (result["batch_id"],)).fetchone():
                            store.event("knowledge_batch_ingested", batch_id=result["batch_id"], graph_revision=result["fingerprint"])
                    return result
                if args.action == "search":
                    return graph.search(args.query, limit=args.limit)
                if not args.id:
                    raise ValueError("knowledge show requires --id")
                record = graph.get(args.type, args.id)
                if record is None:
                    raise ValueError("Unknown knowledge record")
                return {"type": args.type, "record": record}
        if command == "doctor":
            with Knowledge(settings, store.identity) as graph:
                graph_status = graph.status()
            checks = {"python_3_11_or_newer": sys.version_info >= (3, 11),
                      "config_valid": True, "sqlite_integrity": store.db.execute("PRAGMA quick_check").fetchone()[0] == "ok",
                      "production_mode": store.mode == "production", "no_paid_api_dependency": True}
            return {"repo_ready": all(checks.values()), "checks": checks,
                    "knowledge": graph_status, "cloud_backup": backups.current_backup(settings, store),
                    "live_activation_verified": False, "operational_ready": False,
                    "note": "External Dot identity, saved schedules and notification delivery must be verified in Dot; this CLI cannot inspect them"}
        if command in {"run", "research"}:
            if args.preflight:
                if store.db.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]:
                    raise ValueError("Preflight cannot evaluate an existing live prediction ledger; reconcile deployment first")
            return run(engine, research=command == "research", offline=args.offline,
                       forecast_enabled=not args.preflight, continue_work=args.continue_work)
        if command == "discover":
            spec = read_json(args.file)
            return {"created": engine.discover(spec), "signal_id": spec["id"]}
        if command == 'prepare-test':
            plan = read_json(args.file)
            return engine.prepare_test(**plan)
        if command == 'trial':
            from .trial import trial_status, review_trial
            if args.action == 'review':
                if not args.file:
                    raise ValueError('trial review requires --file')
                return review_trial(engine, **read_json(args.file))
            return trial_status(engine)
        if command == "backtest":
            return engine.backtest(args.signal, read_json(args.dataset))
        if command == "forecast":
            forecast = read_json(args.file)
            signal_id, event_id = forecast.pop("signal_id"), forecast.pop("event_id")
            return {"prediction_id": engine.register(signal_id, event_id, **forecast)}
        if command == "prices":
            rows = read_json(args.file)
            return {"new_prices": sum(engine.record_price(**row) for row in rows)}
        if command == "report":
            return engine.report(args.signal)
        if command == "state":
            engine.change_state(args.signal, args.to, args.reason)
            return {"state": store.state(args.signal)}
        if command == "alerts":
            return [dict(r) for r in store.db.execute("SELECT id,signal_id,at,status,receipt FROM outbox ORDER BY at")]
        if command == "claim":
            return engine.claim(args.alert)
        if command == "ack":
            return {"acknowledged": engine.acknowledge(args.alert, args.token, args.receipt)}
        if command == "release":
            engine.release(args.alert, args.token, args.confirmed_not_sent)
            return {"released": True}
        if command == "portfolio":
            return Portfolio(engine).balance()
        if command == "fill":
            return {"recorded": Portfolio(engine).fill(**read_json(args.file))}
        if command == "idea":
            return Portfolio(engine).idea(args.prediction, read_json(args.portfolio))
        if command == "export":
            target = absolute_path(str(args.output or store.path.parent / "ledger-export.json"), "export destination")
            store.export(target)
            return {"exported": str(target)}
        if command == "backup":
            if args.output:
                target = absolute_path(args.output, "backup destination")
                if args.action == "snapshot":
                    return {"archive": str(target), "manifest": backups.snapshot(settings, store, target), "cloud_verified": False}
                raise ValueError("--output is only for backup snapshot; production recovery requires backup cloud")
            if args.action == "snapshot":
                raise ValueError("backup snapshot requires --output NEW_ABSOLUTE_PATH")
            return backups.cloud_backup(settings, store, force=args.force)
        if command == "backup-due":
            return backups.cloud_backup(settings, store)
        if command == "status":
            return {"mode": store.mode, "setup_identity": store.identity, "database_path": str(store.path.resolve()),
                    "signals": [dict(r) for r in store.db.execute("SELECT * FROM signals ORDER BY id")],
                    "predictions": store.db.execute("SELECT COUNT(*) FROM predictions").fetchone()[0],
                    "outcomes": store.db.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0],
                    "outbox": [dict(r) for r in store.db.execute("SELECT id,status FROM outbox")],
                    "last_run": next((dict(r) for r in store.db.execute("SELECT at,kind FROM events WHERE kind='run_completed' ORDER BY seq DESC LIMIT 1")), None),
                    "portfolio": Portfolio(engine).balance()}
        raise ValueError("Unknown command")
    finally:
        store.close()


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = execute(args)
        print(json.dumps(result, indent=2, allow_nan=False))
        if isinstance(result, dict) and result.get("errors"):
            return_code = 2
        else:
            return_code = 0
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, sqlite3.Error) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": redact(exc), "committed": "Inspect ledger before retrying any write"}), file=sys.stderr)
        return_code = 1
    if return_code:
        raise SystemExit(return_code)
