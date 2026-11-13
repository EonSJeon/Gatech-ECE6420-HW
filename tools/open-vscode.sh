#!/bin/bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
"$project_root/tools/start-zotero-collection-sync.sh" --start
code_cli='/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code'
exec "$code_cli" "$project_root" "$project_root/docs/zotero/papers/README.md" "$@"
