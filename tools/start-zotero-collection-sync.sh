#!/bin/bash
set -euo pipefail
export TZ=America/New_York
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
export TMPDIR="$project_root/.local/tmp/"
export XDG_CACHE_HOME="$project_root/.local/cache"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUNBUFFERED=1
export XDG_CONFIG_HOME="$project_root/.local/config"
local_dir="$project_root/.local/zotero"
python="$project_root/.local/venvs/zotero-mcp/bin/python"
server="$project_root/tools/zotero-collection-sync.py"
pid_file="$local_dir/collection-sync.pid"
log_file="$local_dir/collection-sync.log"
control_lock="$local_dir/collection-sync-control.lock"
mkdir -p "$TMPDIR" "$XDG_CACHE_HOME" "$XDG_CONFIG_HOME" "$local_dir"
cd -- "$project_root"
case "${1:-}" in
    --start|--stop|--status)
        if ! ps -p "$$" -o pid= >/dev/null 2>&1; then
            echo 'Process inspection is unavailable. Run this lifecycle command from the project terminal with host process access.' >&2
            exit 2
        fi
        ;;
esac

# A numeric PID alone is insufficient: guard against stale files and PID reuse.
read_pid() {
    daemon_pid=''
    if [[ -f "$pid_file" ]]; then
        IFS= read -r daemon_pid < "$pid_file" || true
    fi
    case "$daemon_pid" in ''|*[!0-9]*) return 1 ;; esac
    [[ "$daemon_pid" -gt 1 ]] || return 1
}

is_our_daemon() {
    local candidate="$1" command_line process_uid
    command_line="$(ps -ww -p "$candidate" -o command= 2>/dev/null)" || return 1
    process_uid="$(ps -p "$candidate" -o uid= 2>/dev/null)" || return 1
    process_uid="${process_uid//[[:space:]]/}"
    [[ "$process_uid" == "$(id -u)" ]] || return 1
    case "$command_line" in *"$server"*) return 0 ;; *) return 1 ;; esac
}

running() {
    read_pid && is_our_daemon "$daemon_pid"
}

held_control=false
cleanup() {
    if [[ "$held_control" == true ]]; then
        rm -f -- "$control_lock/owner"
        rmdir "$control_lock" 2>/dev/null || true
    fi
}

acquire_control() {
    local owner=''
    if ! mkdir "$control_lock" 2>/dev/null; then
        if [[ -f "$control_lock/owner" ]]; then
            IFS= read -r owner < "$control_lock/owner" || true
        fi
        case "$owner" in ''|*[!0-9]*) owner='' ;; esac
        if [[ -n "$owner" ]] && ! kill -0 "$owner" 2>/dev/null; then
            rm -f -- "$control_lock/owner"
            rmdir "$control_lock" 2>/dev/null || true
        fi
        if ! mkdir "$control_lock" 2>/dev/null; then
            echo 'Collection sync lifecycle operation already in progress; retry shortly.' >&2
            return 1
        fi
    fi
    held_control=true
    printf '%s\n' "$$" > "$control_lock/owner"
    trap cleanup EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    trap 'exit 129' HUP
}

case "${1:-}" in
    --status)
        if running; then
            echo "Collection sync running (PID $daemon_pid)."
            echo "Log: $log_file"
        elif [[ -f "$pid_file" ]]; then
            echo 'Collection sync not running; PID file is stale or belongs to another command.'
        else
            echo 'Collection sync stopped.'
        fi
        if [[ -x "$python" && -f "$server" ]]; then
            "$python" - "$server" <<'PYSTATUS'
import json
import subprocess
import sys
result = subprocess.run([sys.executable, sys.argv[1], '--status'], capture_output=True, text=True, check=True)
status = json.loads(result.stdout)
compact = {key: value for key, value in status.items() if key not in ('unavailable', 'conflicts')}
for name in ('unavailable', 'conflicts'):
    rows = status.get(name, [])
    compact[name + '_count'] = len(rows)
    compact[name + '_keys'] = [row.get('key') for row in rows]
print(json.dumps(compact, ensure_ascii=False, indent=2))
PYSTATUS
        fi
        ;;
    --start)
        acquire_control
        if running; then
            echo "Collection sync already running (PID $daemon_pid)."
            exit 0
        fi
        if [[ ! -x "$python" || ! -f "$server" ]]; then
            echo 'Project-local collection-sync Python environment or server is missing.' >&2
            exit 1
        fi
        # Old metadata may name an unrelated process. Leave that process untouched.
        rm -f -- "$pid_file"
        # A new session/process group survives the launching terminal/tool job.
        # All standard streams and other descriptors are detached from that job.
        daemon_pid="$("$python" - "$python" "$server" "$project_root" "$log_file" <<'PYLAUNCH'
import subprocess
import sys
executable, server, workspace, log = sys.argv[1:]
with open(log, 'ab', buffering=0) as output:
    process = subprocess.Popen(
        [executable, '-u', server, '--watch'], cwd=workspace,
        stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
        start_new_session=True, close_fds=True)
print(process.pid, flush=True)
PYLAUNCH
)"
        printf '%s\n' "$daemon_pid" > "$pid_file.part"
        mv -f -- "$pid_file.part" "$pid_file"
        sleep 0.25
        if ! is_our_daemon "$daemon_pid"; then
            rm -f -- "$pid_file"
            echo "Collection sync failed to stay running; inspect $log_file" >&2
            exit 1
        fi
        echo "Collection sync started (PID $daemon_pid)."
        echo "Log: $log_file"
        ;;
    --stop)
        acquire_control
        if ! running; then
            if [[ -f "$pid_file" ]]; then
                rm -f -- "$pid_file"
                echo 'Collection sync not running; unrelated processes were left untouched.'
            else
                echo 'Collection sync already stopped.'
            fi
            exit 0
        fi
        # The watcher handles SIGTERM by finishing its current cycle. This releases
        # its flock and the shared PDF publish lock without an interrupted write.
        # Re-check command identity immediately before sending the signal.
        if is_our_daemon "$daemon_pid"; then
            kill -TERM "$daemon_pid"
        fi
        attempts=0
        while is_our_daemon "$daemon_pid"; do
            attempts=$((attempts + 1))
            if [[ "$attempts" -ge 450 ]]; then
                echo 'Collection sync did not stop after SIGTERM; PID metadata was preserved.' >&2
                exit 1
            fi
            sleep 0.1
        done
        rm -f -- "$pid_file"
        echo 'Collection sync stopped.'
        ;;
    *)
        # Run one foreground synchronization by default; other CLI flags pass through.
        exec "$python" "$server" "$@"
        ;;
esac
