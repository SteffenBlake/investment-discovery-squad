#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
exec "${SQUAD_PYTHON:-python3}" scripts/check.py
