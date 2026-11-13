#!/usr/bin/env python3
"""Manage the one-to-one HW09 source tree and numerical-data transfer."""
import argparse
import json
from pathlib import Path
import shlex
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from remote_bridge import RemoteConfig, push_sources, pull_data, run_remote, run_command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("status", "push", "pull", "run"), default="status", nargs="?")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--config", type=Path, help="JSON parameter dictionary; otherwise use mixer.default_config()")
    parser.add_argument("--stages", help="Comma-separated measurement stages; omitted runs the complete campaign")
    args = parser.parse_args()
    remote = RemoteConfig.load()
    if args.operation == "status":
        run_command(remote.command("hostname; if test -d %s; then ls -ld %s; else printf 'HW09 remote directory has not been created yet.\\n'; fi" %
                                  (shlex.quote(remote.directory), shlex.quote(remote.directory))))
    elif args.operation == "push":
        push_sources(remote, args.dry_run)
    elif args.operation == "pull":
        pull_data(remote, args.dry_run)
    else:
        if args.dry_run:
            parser.error("Use push --dry-run or pull --dry-run to preview transfers")
        if args.config:
            config = json.loads(args.config.read_text())
        else:
            from mixer import default_config
            config = default_config()
        run_remote(config, args.stages, remote)


if __name__ == "__main__":
    main()
