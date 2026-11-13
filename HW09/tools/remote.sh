#!/usr/bin/env bash
set -euo pipefail
HW09_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "${HW09_LOCAL_PYTHON:-python3}" "$HW09_ROOT/tools/manage_remote.py" "$@"
