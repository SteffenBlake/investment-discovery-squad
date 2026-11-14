"""One cloud deployment, configured only through explicitly loaded environment variables."""

import copy
import json
import os
import re
import subprocess
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from .util import ROOT, finite, load_method_settings


_CONFIGURATION_TEMPLATE = {'schema_version': 2,
 'profile_id': None,
 'timezone': None,
 'jurisdiction': None,
 'base_currency': None,
 'risk_preferences': None,
 'max_candidates_per_day': None,
 'round_trip_cost_bps': None,
 'brokerage': {'name': None, 'execution_mode': 'human', 'constraints': None,
               'entry_fee_fixed': None, 'entry_fee_per_unit': None},
 'worker': {'model': None, 'reasoning_effort': None},
 'spending': {'additional_services_budget': None},
 'notification': {'destination': None},
 'instruments': [],
 'research_universe': [],
 'storage': {'backend': 'ladybug',
             'database_path': None,
             'backup_directory': None,
             'backup_interval_hours': None,
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
RUNTIME_ENV = {"SQUAD_REPO", "SQUAD_PYTHON", "SQUAD_LADYBUG_HOME"}


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
    directory = path
    while not directory.is_dir():
        directory = directory.parent
    checkout = subprocess.run(['git', '-C', str(directory), 'rev-parse', '--is-inside-work-tree'],
                              capture_output=True, text=True, check=False)
    if path == ROOT or ROOT in path.parents or (checkout.returncode == 0 and checkout.stdout.strip() == 'true'):
        raise ValueError(f"{label} must live outside every Git checkout/worktree")
    return path


def validate_installation(installation, *, require_storage_acceptance=True):
    allowed = {"schema_version", "profile_id", "timezone", "jurisdiction", "base_currency", "risk_preferences",
               "max_candidates_per_day", "round_trip_cost_bps",
               "brokerage", "worker", "spending", "notification", "instruments", "research_universe",
               "storage", "schedules", "gitops", "runtime"}
    if set(installation) - allowed:
        raise ValueError("Unknown installation fields; shared validation rules belong in method settings")
    reject_secrets(installation)
    if installation.get("schema_version") != 2:
        raise ValueError("Configuration schema 2 required; run onboarding for the required environment variables. Existing state is preserved")
    template = configuration_template()
    def check_objects(value, expected, prefix=''):
        for key, shape in expected.items():
            if isinstance(shape, dict) and key in value:
                child = value[key]
                if not isinstance(child, dict) or set(child) - set(shape):
                    raise ValueError('Unknown or invalid installation object fields: ' + prefix + key)
                check_objects(child, shape, prefix + key + '.')
    check_objects(installation, template)
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", _text(installation.get("profile_id"), "profile_id")):
        raise ValueError("profile_id must be a lowercase identifier")
    ZoneInfo(_text(installation.get("timezone"), "timezone"))
    _text(installation.get("jurisdiction"), "jurisdiction (user-supplied, never inferred)")
    _text(installation.get('risk_preferences'), 'risk_preferences (user-reviewed loss tolerance and restrictions)')
    if not re.fullmatch(r"[A-Z]{3}", _text(installation.get("base_currency"), "base_currency")):
        raise ValueError("base_currency must be a three-letter currency code")
    if type(installation.get("max_candidates_per_day")) is not int or installation["max_candidates_per_day"] < 1:
        raise ValueError("Onboarding required: positive integer max_candidates_per_day")
    if installation.get("round_trip_cost_bps") is None or not 0 <= finite(installation["round_trip_cost_bps"]) < 10000:
        raise ValueError("Onboarding required: realistic round_trip_cost_bps")
    brokerage = installation.get("brokerage", {})
    _text(brokerage.get("name"), "brokerage.name or description of investing mechanism")
    if brokerage.get("execution_mode") != "human":
        raise ValueError("Human-executed recommendations are the required trading workflow")
    _text(brokerage.get("constraints"), "brokerage.constraints (use 'none known' only after review)")
    for key in ("entry_fee_fixed", "entry_fee_per_unit"):
        if brokerage.get(key) is None:
            raise ValueError("Onboarding required: brokerage." + key)
        money(brokerage[key])
    worker = installation.get("worker", {})
    for key in ("model", "reasoning_effort"):
        if key not in worker or worker[key] is not None and not isinstance(worker[key], str):
            raise ValueError(f"worker.{key} must be a supported preference or null for host default")
    if installation.get("spending", {}).get("additional_services_budget") is None:
        raise ValueError("Onboarding required: spending.additional_services_budget (zero is valid)")
    money(installation["spending"]["additional_services_budget"])
    _text(installation.get("notification", {}).get("destination"), "notification.destination")
    instruments = installation.get("instruments")
    if not isinstance(instruments, list) or not instruments:
        raise ValueError("Onboarding required: at least one allowed instrument")
    seen = set()
    for item in instruments:
        symbol = _text(item.get("symbol"), "instrument.symbol")
        if symbol in seen:
            raise ValueError("Duplicate instrument")
        seen.add(symbol)
        if item.get("currency") != installation["base_currency"]:
            raise ValueError("Automatic FX accounting unsupported: instrument currency must match base_currency")
        ZoneInfo(_text(item.get("exchange_timezone"), "instrument.exchange_timezone"))
        import exchange_calendars
        if item.get("exchange_calendar") not in exchange_calendars.get_calendar_names():
            raise ValueError("instrument.exchange_calendar must name a supported exchange calendar")
        for key in ("lot_size", "price_tick"):
            if money(item.get(key)) <= 0:
                raise ValueError(f"instrument.{key} must be positive")
    if not isinstance(installation.get("research_universe"), list):
        raise ValueError("research_universe must be a list, which may start empty")
    storage = installation.get("storage", {})
    if storage.get("backend") != "ladybug":
        raise ValueError("Research knowledge backend must be LadybugDB; SQLite is the separate accounting/prediction ledger")
    runtime = installation.get("runtime", {})
    if runtime.get("kind") != "dot_cloud":
        raise ValueError("Runtime must run on This Dot’s cloud computer")
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
    for key in ("monitor", "research", "reconcile"):
        schedule = installation.get("schedules", {}).get(key, {})
        if type(schedule.get("enabled")) is not bool:
            raise ValueError(f"Onboarding required: schedules.{key}.enabled")
        if schedule["enabled"] and not _text(schedule.get("rrule"), f"schedules.{key}.rrule").startswith("RRULE:"):
            raise ValueError("Use an RFC 5545 recurrence rule")
    gitops = installation.get("gitops", {})
    _text(gitops.get("ref"), "gitops.ref")
    if gitops.get("update_policy") != "fast_forward":
        raise ValueError("Approved-ref fast-forward reconciliation is required")
    for spec in installation.get("research_universe", []):
        if spec.get("symbol") not in seen:
            raise ValueError("Research hypothesis uses an instrument outside the configured universe")
    return installation


def load_configuration(*, require_storage_acceptance=True):
    fields = environment_fields()
    unknown = {key for key in os.environ if key.startswith("SQUAD_")} - set(fields) - RUNTIME_ENV
    if unknown:
        raise ValueError("Unsupported SQUAD configuration keys: " + ", ".join(sorted(unknown)) + "; use documented individual environment variables")
    if not any(name in os.environ for name in fields):
        raise ValueError("Onboarding required: load documented SQUAD_* variables from project .env")
    missing = sorted(set(fields) - set(os.environ))
    if missing:
        raise ValueError("Missing required environment configuration: " + ", ".join(missing))
    installation = configuration_template()
    for name, (path, kind) in fields.items():
        value = os.environ[name]
        try:
            parsed = json.loads(value) if kind != "string" or value == "null" else value
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON for {name}; expected {kind}") from exc
        node = installation
        for part in path[:-1]:
            node = node[part]
        node[path[-1]] = parsed
    validate_installation(installation, require_storage_acceptance=require_storage_acceptance)
    return installation


def secret_values():
    return [value for key, value in os.environ.items() if len(value) >= 8
            and re.search(r'(^|_)(TOKEN|SECRET|PASSWORD|API_KEY|PRIVATE_KEY)($|_)', key, re.I)]


def reject_secrets(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if re.search(r"(^|_)(token|secret|password|credential|api_key|private_key)($|_)", key, re.I):
                raise ValueError("Credentials belong in runtime secret variables, never installation/evidence JSON")
            reject_secrets(child)
    elif isinstance(value, list):
        for child in value:
            reject_secrets(child)
    elif isinstance(value, str):
        if any(secret in value for secret in secret_values()):
            raise ValueError('Runtime credentials cannot be copied into installation/evidence text')


def environment_fields():
    template = configuration_template()
    integers = {"schema_version", "max_candidates_per_day",
                "backup_interval_hours", "max_bytes", "max_archive_bytes"}
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
    return any(key.startswith("SQUAD_") and key not in RUNTIME_ENV for key in os.environ)


def redact(message):
    message = str(message)
    for value in secret_values():
        message = message.replace(value, "[REDACTED]")
    return message


def build_runtime_settings(installation=None):
    shared = load_method_settings()
    if installation is None:
        return shared
    validate_installation(installation)
    return {**shared, **installation}


def instrument(settings, symbol):
    for item in settings["instruments"]:
        if item["symbol"] == symbol:
            return item
    raise ValueError(f"Instrument not configured: {symbol}")


def write_private_json(path, value):
    path = Path(path)
    private_directory(path.parent)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=".squad-", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(json.dumps(value, indent=2, allow_nan=False) + "\n")
    try:
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def private_directory(path):
    """Create each missing directory privately; preserve existing ancestors."""
    path = Path(path)
    if not path.exists():
        private_directory(path.parent)
        path.mkdir(mode=0o700, exist_ok=True)
