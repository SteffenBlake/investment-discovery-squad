"""Investment discovery: research evidence, immutable forecasts, human execution."""

import json
from pathlib import Path

__version__ = json.loads((Path(__file__).resolve().parents[4] / 'plugin.json').read_text(encoding='utf-8'))['version']
