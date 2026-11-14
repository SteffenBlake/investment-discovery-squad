#!/bin/sh
set -eu
exec "${SQUAD_PYTHON:-python3}" "$(dirname -- "$0")/check.py"
