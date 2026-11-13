#!/bin/bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
source "$project_root/tools/zotero-env.sh"
cd -- "$project_root"
exec "$project_root/.local/venvs/zotero-mcp/bin/python" "$project_root/tools/zotero-project.py" "$@"
