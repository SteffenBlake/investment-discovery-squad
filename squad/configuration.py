"""One cloud deployment, configured only through individual native environment variables."""

import copy
import json
import os
import re
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from .util import ROOT, finite


_CONFIGURATION_TEMPLATE = {'schema_version': 2,
 'profile_id': None,
 'timezone': None,
 'jurisdiction': None,
 'base_currency': None,
 'starting_cash': None,
 'money_decimals': None,
 'max_trade_ideas_per_day': None,
 'max_candidates_per_day': None,
 'round_trip_cost_bps': None,
 'brokerage': {'name': None, 'execution_mode': 'human', 'constraints': None},
 'worker': {'model': None, 'reasoning_effort': None},
 'spending': {'additional_services_budget': None},
 'notification': {'destination': None},
 'instruments': [],
 'research_universe': [],
 'storage': {'backend': 'ladybug',
             'database_path': None,
             'backup_directory': None,
             'backup_interval_hours': None,
             'backup_retention_days': None,
             'runtime_id': None,
             'decision_accepted': False,
             'knowledge_path': None,
             'cloud_backup': {'provider': 'google_drive',
                              'folder_id': None,
                              'max_bytes': None,
                              'max_archive_bytes': None}},
 'schedules': {'monitor': {'enabled': None, 'rrule': None},
               'research': {'enabled': None, 'rrule': None},
               'reconcile': {'enabled': None, 'rrule': None}},
 'gitops': {'ref': None, 'update_policy': 'fast_forward'},
 'runtime': {'kind': 'dot_cloud'}}

# Architecture is fixed, not another onboarding choice.
_FIXED_FIELDS = {'schema_version', 'runtime.kind', 'storage.backend', 'storage.cloud_backup.provider',
                 'brokerage.execution_mode', 'gitops.update_policy'}


def configuration_template():
    return copy.deepcopy(_CONFIGURATION_TEMPLATE)


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Onboarding required: {label}")
    return value


def money(value):
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Invalid monetary value") from exc
    if not result.is_finite() or result < 0:
        raise ValueError("Monetary value must be finite and nonnegative")
    return result


def absolute_path(value, label):
    value = _text(value, label)
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{label} must be absolute, outside the checkout")
    path = path.resolve()
    if path == ROOT or ROOT in path.parents or any((parent / '.git').exists() for parent in (path, *path.parents)):
        raise ValueError(f"{label} must live outside every Git checkout/worktree")
    return path


def validate_profile(profile, *, require_storage_acceptance=True):
    allowed = {"schema_version", "profile_id", "timezone", "jurisdiction", "base_currency", "starting_cash",
               "money_decimals", "max_trade_ideas_per_day", "max_candidates_per_day", "round_trip_cost_bps",
               "brokerage", "worker", "spending", "notification", "instruments", "research_universe",
               "storage", "schedules", "gitops", "runtime"}
    if set(profile) - allowed:
        raise ValueError("Unknown profile fields; shared validation rules cannot be overridden by a profile")
    reject_secrets(profile)
    if profile.get("schema_version") != 2:
        raise ValueError("Configuration schema 2 required; run onboarding for the required native variables. Existing state is preserved")
    template = configuration_template()
    def check_objects(value, expected, prefix=''):
        for key, shape in expected.items():
            if isinstance(shape, dict) and key in value:
                child = value[key]
                if not isinstance(child, dict) or set(child) - set(shape):
                    raise ValueError('Unknown or invalid profile object fields: ' + prefix + key)
                check_objects(child, shape, prefix + key + '.')
    check_objects(profile, template)
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", _text(profile.get("profile_id"), "profile_id")):
        raise ValueError("profile_id must be a lowercase identifier")
    ZoneInfo(_text(profile.get("timezone"), "timezone"))
    _text(profile.get("jurisdiction"), "jurisdiction (user-supplied, never inferred)")
    if not re.fullmatch(r"[A-Z]{3}", _text(profile.get("base_currency"), "base_currency")):
        raise ValueError("base_currency must be a three-letter currency code")
    if profile.get("starting_cash") is None or money(profile["starting_cash"]) <= 0:
        raise ValueError("Onboarding required: positive starting_cash")
    for key in ("max_trade_ideas_per_day", "max_candidates_per_day"):
        if type(profile.get(key)) is not int or profile[key] < 1:
            raise ValueError(f"Onboarding required: positive integer {key}")
    if type(profile.get("money_decimals")) is not int or not 0 <= profile["money_decimals"] <= 6:
        raise ValueError("Onboarding required: money_decimals from 0 to 6")
    if profile.get("round_trip_cost_bps") is None or not 0 <= finite(profile["round_trip_cost_bps"]) < 10000:
        raise ValueError("Onboarding required: realistic round_trip_cost_bps")
    brokerage = profile.get("brokerage", {})
    _text(brokerage.get("name"), "brokerage.name or description of investing mechanism")
    if brokerage.get("execution_mode") != "human":
        raise ValueError("Human-executed recommendations are the required trading workflow")
    _text(brokerage.get("constraints"), "brokerage.constraints (use 'none known' only after review)")
    worker = profile.get("worker", {})
    for key in ("model", "reasoning_effort"):
        if key not in worker or worker[key] is not None and not isinstance(worker[key], str):
            raise ValueError(f"worker.{key} must be a supported preference or null for host default")
    if profile.get("spending", {}).get("additional_services_budget") is None:
        raise ValueError("Onboarding required: spending.additional_services_budget (zero is valid)")
    money(profile["spending"]["additional_services_budget"])
    _text(profile.get("notification", {}).get("destination"), "notification.destination")
    instruments = profile.get("instruments")
    if not isinstance(instruments, list) or not instruments:
        raise ValueError("Onboarding required: at least one allowed instrument")
    seen = set()
    for item in instruments:
        symbol = _text(item.get("symbol"), "instrument.symbol")
        if symbol in seen:
            raise ValueError("Duplicate instrument")
        seen.add(symbol)
        if item.get("currency") != profile["base_currency"]:
            raise ValueError("Automatic FX accounting unsupported: instrument currency must match base_currency")
        ZoneInfo(_text(item.get("exchange_timezone"), "instrument.exchange_timezone"))
        if not re.fullmatch(r"\d{2}:\d{2}", _text(item.get("close_time"), "instrument.close_time")):
            raise ValueError("close_time must be HH:MM")
        hour, minute = map(int, item["close_time"].split(":"))
        if hour > 23 or minute > 59:
            raise ValueError("Invalid close_time")
        if not item.get("weekdays") or any(type(day) is not int or not 0 <= day <= 6 for day in item["weekdays"]):
            raise ValueError("instrument.weekdays needs integers 0 (Monday) to 6")
        for key in ("lot_size", "price_tick"):
            if money(item.get(key)) <= 0:
                raise ValueError(f"instrument.{key} must be positive")
    if not isinstance(profile.get("research_universe"), list):
        raise ValueError("research_universe must be a list, which may start empty")
    storage = profile.get("storage", {})
    if storage.get("backend") != "ladybug":
        raise ValueError("Research knowledge backend must be LadybugDB; SQLite is the separate accounting/prediction ledger")
    runtime = profile.get("runtime", {})
    if runtime.get("kind") != "dot_cloud":
        raise ValueError("Dot cloud is the required central owner runtime")
    if require_storage_acceptance and storage.get("decision_accepted") is not True:
        raise ValueError("Database discussion/decision required: storage.decision_accepted must be true")
    if type(storage.get("decision_accepted")) is not bool:
        raise ValueError("storage.decision_accepted must explicitly be true or false")
    database = absolute_path(storage.get("database_path"), "storage.database_path")
    backup = absolute_path(storage.get("backup_directory"), "storage.backup_directory")
    graph = absolute_path(storage.get("knowledge_path"), "storage.knowledge_path")
    if graph == database or graph.parent != database.parent:
        raise ValueError("Graph and ledger need distinct files in one private data directory")
    if backup == database.parent or database.parent in backup.parents:
        raise ValueError("Backup staging must be outside the live data directory")
    cloud = storage.get("cloud_backup", {})
    if cloud.get("provider") != "google_drive":
        raise ValueError("Configure google_drive for independent cloud backup")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", _text(cloud.get("folder_id"), "storage.cloud_backup.folder_id")):
        raise ValueError("Invalid Drive folder identifier")
    for key in ("max_bytes", "max_archive_bytes"):
        if type(cloud.get(key)) is not int or cloud[key] < 1024:
            raise ValueError(f"Explicit positive byte budget required: storage.cloud_backup.{key}")
    if not cloud["max_archive_bytes"] <= min(cloud["max_bytes"], 1024**3):
        raise ValueError("Archive limit must fit backup budget and be at most 1 GiB")
    if database == backup or database in backup.parents:
        raise ValueError("Backup directory cannot be the database file")
    _text(storage.get("runtime_id"), "storage.runtime_id")
    if type(storage.get("backup_interval_hours")) is not int or storage["backup_interval_hours"] < 1:
        raise ValueError("Onboarding required: positive backup_interval_hours")
    if type(storage.get("backup_retention_days")) is not int or storage["backup_retention_days"] < 1:
        raise ValueError("Onboarding required: positive backup_retention_days")
    for key in ("monitor", "research", "reconcile"):
        schedule = profile.get("schedules", {}).get(key, {})
        if type(schedule.get("enabled")) is not bool:
            raise ValueError(f"Onboarding required: schedules.{key}.enabled")
        if schedule["enabled"] and not _text(schedule.get("rrule"), f"schedules.{key}.rrule").startswith("RRULE:"):
            raise ValueError("Use a native RFC 5545 RRULE")
    gitops = profile.get("gitops", {})
    _text(gitops.get("ref"), "gitops.ref")
    if gitops.get("update_policy") != "fast_forward":
        raise ValueError("Approved-ref fast-forward reconciliation is required")
    for spec in profile.get("research_universe", []):
        if spec.get("symbol") not in seen:
            raise ValueError("Research hypothesis uses an instrument outside the configured universe")
    return profile


def load_configuration(*, require_storage_acceptance=True):
    fields = environment_fields()
    unknown = {key for key in os.environ if key.startswith("SQUAD_")} - set(fields) - set(SECRET_ENV) - {"SQUAD_REPO", "SQUAD_PYTHON", "SQUAD_TASK_KEY"}
    if unknown:
        raise ValueError("Unsupported SQUAD configuration keys: " + ", ".join(sorted(unknown)) + "; use documented individual native variables")
    if not any(name in os.environ for name in fields):
        raise ValueError("Onboarding required: bind the documented individual SQUAD_* variables on Dot's cloud owner")
    missing = sorted(set(fields) - set(os.environ))
    if missing:
        raise ValueError("Missing required native configuration: " + ", ".join(missing))
    profile = configuration_template()
    for name, (path, kind) in fields.items():
        value = os.environ[name]
        try:
            parsed = json.loads(value) if kind != "string" or value == "null" else value
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON for {name}; expected {kind}") from exc
        node = profile
        for part in path[:-1]:
            node = node[part]
        node[path[-1]] = parsed
    validate_profile(profile, require_storage_acceptance=require_storage_acceptance)
    return profile


SECRET_ENV = ("SQUAD_GOOGLE_REFRESH_TOKEN", "SQUAD_GOOGLE_CLIENT_ID", "SQUAD_GOOGLE_CLIENT_SECRET")


def reject_secrets(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if re.search(r"(^|_)(token|secret|password|credential|api_key|private_key)($|_)", key, re.I):
                raise ValueError("Credentials belong in runtime secret variables, never profile/evidence JSON")
            reject_secrets(child)
    elif isinstance(value, list):
        for child in value:
            reject_secrets(child)
    elif isinstance(value, str):
        if any(os.environ.get(key) and os.environ[key] in value for key in SECRET_ENV):
            raise ValueError('Runtime credentials cannot be copied into profile/evidence text')


def environment_fields():
    template = configuration_template()
    integers = {"schema_version", "money_decimals", "max_trade_ideas_per_day", "max_candidates_per_day",
                "backup_interval_hours", "backup_retention_days", "max_bytes", "max_archive_bytes"}
    booleans = {"decision_accepted", "enabled"}
    numbers = {"round_trip_cost_bps"}
    result = {}
    def walk(node, path=()):
        for key, value in node.items():
            parts = (*path, key)
            if isinstance(value, dict):
                walk(value, parts)
            elif ".".join(parts) not in _FIXED_FIELDS:
                kind = "JSON array" if isinstance(value, list) else "integer" if key in integers else "boolean" if key in booleans else "number" if key in numbers else "string"
                result["SQUAD_" + "_".join(parts).upper()] = (parts, kind)
    walk(template)
    return result


def has_configuration():
    return any(key.startswith("SQUAD_") and key not in {"SQUAD_REPO", "SQUAD_PYTHON", "SQUAD_TASK_KEY", *SECRET_ENV} for key in os.environ)


def redact(message):
    message = str(message)
    for key in SECRET_ENV:
        value = os.environ.get(key)
        if value:
            message = message.replace(value, "[REDACTED]")
    return message


def settings(profile=None):
    shared = json.loads((ROOT / "settings.json").read_text())
    if profile is None:
        return shared
    validate_profile(profile)
    return {**shared, **profile}


def instrument(settings, symbol):
    for item in settings["instruments"]:
        if item["symbol"] == symbol:
            return item
    raise ValueError(f"Instrument not configured: {symbol}")


def write_private_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=".squad-", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(json.dumps(value, indent=2, allow_nan=False) + "\n")
    try:
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
