import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

UTC = timezone.utc
ROOT = Path(os.environ.get("SQUAD_REPO", Path(__file__).resolve().parent.parent)).expanduser().resolve()


def now_utc():
    return datetime.now(UTC)


def instant(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("Timestamp must include timezone")
    return value.astimezone(UTC)


def stamp(value):
    return instant(value).isoformat(timespec="microseconds")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def finite(value, *, positive=False):
    value = float(value)
    if not math.isfinite(value) or (positive and value <= 0):
        raise ValueError("Expected finite " + ("positive number" if positive else "number"))
    return value


def config(path=None):
    return json.loads(Path(path or ROOT / "settings.json").read_text())


def wilson(successes, attempts):
    if not attempts:
        return [0.0, 1.0]
    z = 1.959963984540054
    p = successes / attempts
    d = 1 + z * z / attempts
    center = (p + z * z / (2 * attempts)) / d
    radius = z * math.sqrt(p * (1 - p) / attempts + z * z / (4 * attempts**2)) / d
    return [max(0, center - radius), min(1, center + radius)]
