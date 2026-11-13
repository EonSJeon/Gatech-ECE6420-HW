#!/usr/bin/env bash
set -euo pipefail
HW09_ROOT="$(cd "$(dirname "$0")" && pwd)"
HW09_PYTHON="${HW09_LOCAL_PYTHON:-python3}"
if [[ -x "$HW09_ROOT/.venv/bin/python" && "$HW09_PYTHON" == python3 ]]; then
    HW09_PYTHON="$HW09_ROOT/.venv/bin/python"
fi
exec "$HW09_PYTHON" "$HW09_ROOT/tools/execute_notebooks.py" --mode remote --in-place "$@"
