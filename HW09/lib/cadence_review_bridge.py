"""Fetch and review existing native ADE GUI results; never start a simulator.

Native OA/state and GUI numerical output are received into the same HW09 tree.
The operator's actual-run manifest remains local and is never overwritten by
this transfer. No source push, remote plotting, or delete operation is used.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys

from remote_bridge import RemoteConfig

ROOT = Path(__file__).resolve().parents[1]
TRANSFER_EXCLUDES = (
    "*.cdslck*", "*.lck", "*.lock", "*.lock.*", ".DS_Store", "__pycache__/",
    ".tmp_*/", "logs_*/", ".nfs*", ".tmpADEDir_*/", ".skillide.*",
    "*.key", "*.pem", ".remote.env", "*.png", "*.jpg", "*.jpeg", "*.svg",
    "*.pdf", "*.eps", "*.ps", "*.html", "*.ipynb", "figures/", "probe_runtime/",
    "*manifest.json", "*manifest.json.part",
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def project_path(root, relative):
    root = Path(root).resolve()
    relative = Path(relative)
    if relative.is_absolute():
        raise ValueError("Use a project-relative path")
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Path escapes the HW09 project: " + str(relative))
    return path


def preserve_python_baseline(root=ROOT):
    """Create once, retain exact original bytes, and detect later modification."""
    root = Path(root).resolve()
    snapshot = project_path(root, "results/python_baseline.json")
    proof = project_path(root, "results/python_baseline.sha256")
    if not snapshot.exists():
        source = project_path(root, "results/hw9_results.json")
        raw = source.read_bytes()
        result = json.loads(raw)
        if result.get("status") != "complete" or result.get("origin") == "cadence_ade_gui":
            raise ValueError("A complete standalone Python campaign is required for the baseline snapshot")
        if set(result.get("circuits", {})) != {"active", "passive"}:
            raise ValueError("The comparison baseline must contain both circuits")
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        try:
            with snapshot.open("xb") as stream:
                stream.write(raw)
        except FileExistsError:
            # Another local caller already created the immutable snapshot.
            pass
    result = json.loads(snapshot.read_text())
    if result.get("status") != "complete" or result.get("origin") == "cadence_ade_gui":
        raise ValueError("Invalid immutable standalone baseline")
    digest = sha(snapshot)
    if proof.exists():
        if proof.read_text().split()[0] != digest:
            raise ValueError("The immutable Python baseline was modified; preserve it and investigate")
    else:
        try:
            with proof.open("x") as stream:
                stream.write(digest + "  python_baseline.json\n")
        except FileExistsError:
            if proof.read_text().split()[0] != digest:
                raise ValueError("Conflicting immutable baseline checksum")
    return {"path": str(snapshot), "sha256": digest, "run_id": result.get("run_id")}


def fetch_gui_artifacts(root=ROOT, remote=None):
    """Receive actual native CAD source and already-run GUI data over SSH.

    Keep the GUI Run action in ADE. Files still being written may fail later
    provenance checks; finish the ADE history and rerun this fetch if necessary.
    Unsafe symlinks are skipped rather than following targets outside the tree.
    """
    root = Path(root).resolve()
    remote = remote or RemoteConfig.load()
    remote.__post_init__()
    required = ("cadence", "simulation/cadence_gui")
    optional = ("cds.lib", "lib.defs", "ade_native_paths.tsv")
    checks = ["set -e"]
    checks += ["test -d " + shlex.quote(remote.directory + "/" + name) for name in required]
    checks += ["printf '%s\\n' " + shlex.quote(name) for name in required]
    for name in optional:
        checks.append("if test -f " + shlex.quote(remote.directory + "/" + name) +
                      "; then printf '%s\\n' " + shlex.quote(name) + "; fi")
    observed = subprocess.run(remote.command("\n".join(checks)), check=True,
                              capture_output=True, text=True)
    paths = observed.stdout.splitlines()
    if not set(required).issubset(paths) or not set(paths).issubset((*required, *optional)):
        raise ValueError("Unexpected native GUI source/data inventory from the server")
    for name in paths:
        destination = project_path(root, name)
        is_directory = name in required
        destination.parent.mkdir(parents=True, exist_ok=True)
        if is_directory:
            destination.mkdir(parents=True, exist_ok=True)
        source = remote.host + ":" + remote.directory + "/" + name
        command = ["rsync", "-az", "--safe-links", "-e", shlex.join(remote.ssh())]
        command += ["--exclude=" + pattern for pattern in TRANSFER_EXCLUDES]
        command += [source + ("/" if is_directory else ""),
                    str(destination) + ("/" if is_directory else "")]
        subprocess.run(command, check=True)
    record = {"fetched_utc": datetime.now(timezone.utc).isoformat(),
              "remote_host": remote.host, "remote_directory": remote.directory,
              "paths": paths, "source_push": False, "simulator_invoked": False,
              "remote_visual_outputs_imported": False, "delete_used": False,
              "lock_pattern_excluded": "*.cdslck*"}
    target = project_path(root, "results/cadence_gui_fetch.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, indent=2) + "\n")
    print("Fetched native OA/state/audits and actual GUI data. ADE Run remains a GUI action.")
    return record


def import_actual_gui_results(root, manifest_relative):
    root = Path(root).resolve()
    manifest = project_path(root, manifest_relative)
    record = json.loads(manifest.read_text())
    if record.get("origin") != "cadence_ade_gui" or not record.get("runs"):
        raise ValueError("Select the operator's actual-run manifest, not a planning manifest")
    subprocess.run([sys.executable, str(root / "tools/cadence_import.py"),
                    "--root", str(root), "--manifest", str(manifest.relative_to(root))],
                   cwd=root, check=True)
    result = json.loads((root / "results/cadence_gui_results.json").read_text())
    if result.get("origin") != "cadence_ade_gui":
        raise ValueError("Importer did not produce a native GUI campaign")
    return result


def render_gui_figures(root, *, show=True, allow_partial=False):
    root = Path(root).resolve()
    result = json.loads((root / "results/cadence_gui_results.json").read_text())
    if result.get("origin") != "cadence_ade_gui":
        raise ValueError("Expected native GUI result metadata")
    if result.get("status") != "complete" and not allow_partial:
        raise ValueError("Complete missing GUI measurements before final review")
    if result.get("plot_figure_mode")=="cadence_gui_export":
        sys.path.insert(0,str(root/"tools"))
        from cadence_gui_figures import validate
        validate(root,result)
        figures={spec["kind"]+"_"+spec["role"]:project_path(root,spec["image_path"])
                 for spec in result["numerical_plot_figures"]}
        if show:
            from IPython.display import Image,display
            for key,path in figures.items():
                print(key+": actual native GUI export")
                display(Image(filename=str(path)))
        return figures
    raise ValueError("Primary review requires all twelve cadence_gui_export images; Python rendering remains only in the standalone baseline")


def render_gui_tex(root=ROOT):
    """Prepare editable Overleaf source and PNGs; never compile or upload."""
    root=Path(root).resolve()
    subprocess.run([sys.executable,str(root/"tools/build_cadence_tex.py"),
                    "--root",str(root)],cwd=root,check=True)
    source=root/"overleaf/main.tex"
    if not source.is_file():raise RuntimeError("Expected editable LaTeX source was not produced")
    return source


def render_gui_report(root=ROOT):
    """Compatibility alias: returns editable .tex source, never a PDF."""
    return render_gui_tex(root)
