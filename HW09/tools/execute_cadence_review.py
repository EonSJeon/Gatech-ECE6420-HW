#!/usr/bin/env python3
"""Execute only the local GUI-results review; this never invokes simulation."""
import argparse
import copy
import json
import os
from pathlib import Path
import sys

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]


def execute(mode="fetch", manifest=None, build_tex=True):
    path = ROOT / "notebooks/01_cadence_gui_review.ipynb"
    original = nbformat.read(path, as_version=4)
    notebook = copy.deepcopy(original)
    for cell in notebook.cells:
        if cell.cell_type == "code":
            cell.outputs, cell.execution_count = [], None
    parameters = next(i for i, c in enumerate(notebook.cells) if "parameters" in c.metadata.get("tags", []))
    overrides = "FETCH_FROM_SERVER = " + repr(mode == "fetch") + "\nBUILD_TEX = " + repr(build_tex) + "\n"
    if manifest:
        overrides += "MANIFEST_RELATIVE = " + json.dumps(manifest) + "\n"
    notebook.cells.insert(parameters + 1, nbformat.v4.new_code_cell(overrides))
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "simulation/matplotlib"))
    os.environ.setdefault("IPYTHONDIR", str(ROOT / "simulation/ipython"))
    client = NotebookClient(notebook, timeout=1200, kernel_name="ece6420-local",
                            resources={"metadata": {"path": str(ROOT)}})
    manager = client.create_kernel_manager()
    manager.kernel_spec.argv = [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"]
    print("Local native-GUI result review (%s); no simulator is launched." % mode, flush=True)
    try:
        client.execute()
    finally:
        executed = {c.id: c for c in notebook.cells if c.cell_type == "code"}
        for cell in original.cells:
            if cell.cell_type == "code" and cell.id in executed:
                cell.outputs = executed[cell.id].outputs
                cell.execution_count = executed[cell.id].execution_count
        if "language_info" in notebook.metadata:
            original.metadata["language_info"] = notebook.metadata["language_info"]
        nbformat.write(original, path)
    print("Completed local fetch/review/figures/LaTeX source workflow; ADE Run remains in the GUI.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("fetch", "review"), default="fetch")
    parser.add_argument("--manifest", help="Project-relative operator-authored actual-run manifest")
    parser.add_argument("--no-tex", "--no-report", dest="no_tex", action="store_true", help="Skip LaTeX generation; --no-report is a compatibility alias")
    args = parser.parse_args()
    execute(args.mode, args.manifest, not args.no_tex)
