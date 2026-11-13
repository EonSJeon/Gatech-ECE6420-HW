"""Local Python API -> school Spectre worker -> numerical data -> local plots.

Only the maintained HW09 source tree is mirrored with deletion. Results,
simulation output, generated netlists, private configuration, and environments
are protected. No remote notebook output or plot is imported.
"""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROTECTED_SOURCE_PATHS = (
    ".venv/", ".local/", ".cache/", ".remote.env", "__pycache__/",
    ".ipynb_checkpoints/", "/simulation/", "/results/",
    "/netlists/generated/", "/output/", "/tmp/", "/cadence/", "/.cadence/", "/cds.lib", "/lib.defs", "/.cdsinit", "/.cdsenv",
    "/CDS.log*", "/libManager.log", "*.cdslck*", "*.key", "*.pem",
    "/.tmp_*/", "/logs_*/", ".nfs*",
)
NONNUMERICAL_OUTPUTS = (
    "python_baseline.json", "python_baseline.sha256",
    "figures/", "local-executed/", "matplotlib/", "ipython/", "executed/",
    "*.png", "*.jpg", "*.jpeg", "*.svg", "*.pdf", "*.ipynb", "*.html",
)


@dataclass
class RemoteConfig:
    host: str = "gt-ece"
    directory: str = "/nethome/sjeon84/Gatech-ECE6420/HW09"
    python: str = ".venv/bin/python"
    hostname: str = ""

    def __post_init__(self):
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.@-]*", self.host):
            raise ValueError("Invalid SSH host alias")
        # The deletion scope cannot be redirected to another homework or home.
        if not re.fullmatch(r"/nethome/[A-Za-z0-9_.-]+/Gatech-ECE6420/HW09", self.directory):
            raise ValueError("Remote source directory must be /nethome/USER/Gatech-ECE6420/HW09")
        if not re.fullmatch(r"[A-Za-z0-9_./-]+", self.python) or self.python.startswith("-"):
            raise ValueError("Invalid remote Python executable path")
        if self.hostname and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", self.hostname):
            raise ValueError("Invalid optional SSH hostname")

    @classmethod
    def load(cls):
        values = {}
        path = ROOT / ".remote.env"
        if path.is_file():
            for line in path.read_text().splitlines():
                fields = shlex.split(line, comments=True)
                if not fields:
                    continue
                if len(fields) != 1 or "=" not in fields[0]:
                    raise ValueError(".remote.env accepts KEY=value lines only")
                key, value = fields[0].split("=", 1)
                if key not in {"HW09_REMOTE_HOST", "HW09_REMOTE_DIR", "HW09_REMOTE_PYTHON", "HW09_SSH_HOSTNAME"}:
                    raise ValueError("Unknown .remote.env key: " + key)
                values[key] = value
        values.update(os.environ)
        return cls(values.get("HW09_REMOTE_HOST", cls.host),
                   values.get("HW09_REMOTE_DIR", cls.directory),
                   values.get("HW09_REMOTE_PYTHON", cls.python),
                   values.get("HW09_SSH_HOSTNAME", ""))

    def ssh(self):
        args = ["ssh", "-4", "-o", "LogLevel=ERROR", "-o", "ControlMaster=no",
                "-o", "ControlPath=none", "-o", "BatchMode=yes", "-o",
                "ConnectTimeout=15", "-o", "ServerAliveInterval=30"]
        if self.hostname:
            args += ["-o", "HostName=" + self.hostname]
        return args

    def command(self, script):
        # The remote login shell may be tcsh. Shell syntax runs in explicit Bash.
        return self.ssh() + [self.host, "bash -c " + shlex.quote(script)]


def run_command(command, payload=None):
    """Stream real remote progress into the local notebook/API caller."""
    with subprocess.Popen(command, stdin=subprocess.PIPE if payload is not None else subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, bufsize=1) as process:
        if payload is not None:
            process.stdin.write(payload)
            process.stdin.close()
        try:
            for line in process.stdout:
                print(line, end="", flush=True)
            code = process.wait()
        except BaseException:
            process.terminate()
            process.wait()
            raise
    if code:
        raise RuntimeError("Remote command failed (exit %s). Inspect the log above and verify GlobalProtect / ssh gt-ece." % code)


def rsync(remote, source, destination, *, excludes=(), delete=False, dry_run=False):
    command = ["rsync", "-az", "--exclude=.DS_Store"]
    if delete:
        command.append("--delete")
    if dry_run:
        command += ["--dry-run", "--itemize-changes"]
    command += ["--exclude=" + p for p in excludes]
    command += ["-e", shlex.join(remote.ssh()), str(source), str(destination)]
    run_command(command)


def push_sources(remote=None, dry_run=False):
    remote = remote or RemoteConfig.load()
    remote.__post_init__()
    if not dry_run:
        run_command(remote.command("mkdir -p " + " ".join(shlex.quote(remote.directory + p)
                    for p in ("", "/results", "/simulation", "/netlists/generated"))))
    rsync(remote, str(ROOT) + "/", remote.host + ":" + remote.directory + "/",
          excludes=PROTECTED_SOURCE_PATHS, delete=True, dry_run=dry_run)


def pull_data(remote=None, dry_run=False):
    remote = remote or RemoteConfig.load()
    for folder in ("results", "netlists/generated", "simulation"):
        destination = ROOT / folder
        if not dry_run:
            destination.mkdir(parents=True, exist_ok=True)
        rsync(remote, remote.host + ":" + remote.directory + "/" + folder + "/",
              str(destination) + "/", excludes=NONNUMERICAL_OUTPUTS, dry_run=dry_run)


def normalize_stages(stages):
    if stages is None:
        return None
    if isinstance(stages, str):
        stages = stages.split(",")
    result = list(stages)
    if not result or any(not isinstance(s, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", s) for s in result):
        raise ValueError("Stages must be nonempty measurement names")
    return result


def run_remote(config, stages=None, remote=None):
    """Run the current Python parameter values remotely and fetch real data.

    Parameters are transported as JSON on stdin, including edits in an unsaved
    notebook parameter cell. No parameter value is interpolated into shell code.
    """
    if not isinstance(config, dict):
        raise TypeError("config must be a dictionary")
    stages = normalize_stages(stages)
    payload = json.dumps({"config": config, "stages": stages}, allow_nan=False)
    remote = remote or RemoteConfig.load()
    print("Local Python -> %s:%s -> Spectre" % (remote.host, remote.directory), flush=True)
    push_sources(remote)
    script = "cd %s && %s tools/remote_worker.py" % (shlex.quote(remote.directory), shlex.quote(remote.python))
    try:
        run_command(remote.command(script), payload)
    except BaseException:
        try:
            pull_data(remote)
        except Exception as exc:
            print("Data fetch after failure: " + str(exc), flush=True)
        raise
    pull_data(remote)
    results_path = ROOT / "results/hw9_results.json"
    if not results_path.is_file():
        raise FileNotFoundError("Remote run returned no HW09 result metadata: " + str(results_path))
    results = json.loads(results_path.read_text())
    if results.get("config") != config:
        raise ValueError("Pulled results do not match the current Python configuration; preserve them and inspect the worker audit.")
    status = results.get("status")
    if status not in {"complete", "partial", "failed", "running"}:
        raise ValueError("Pulled results contain an unknown or missing campaign status")
    print("Numerical data received. Render figures and build the report locally.", flush=True)
    print("Recorded campaign status: " + status, flush=True)
    return {"status": status, "results_path": str(results_path),
            "run_id": results.get("run_id"), "completed_utc": results.get("completed_utc"),
            "remote_host": remote.host, "remote_directory": remote.directory,
            "stages": stages}
