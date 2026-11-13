#!/usr/bin/env python3
"""Execute the local HW09 notebook through its real SSH/data/local-plot path."""
import argparse
import copy
import json
import os
from pathlib import Path
import sys

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]


def execute_path(path=None, mode="remote", parameters=None, in_place=True):
    if mode not in {"remote", "review"}:
        raise ValueError("Notebook execution is local; select remote or review mode")
    path = Path(path or ROOT / "notebooks/00_overview.ipynb").resolve()
    original = nbformat.read(path, as_version=4)
    notebook = copy.deepcopy(original)
    for cell in notebook.cells:
        if cell.cell_type == "code":
            cell.outputs, cell.execution_count = [], None
    parameters_cell = next(i for i, c in enumerate(notebook.cells)
                           if "parameters" in c.metadata.get("tags", []))
    overrides = "EXECUTION_MODE = " + repr(mode) + "\n"
    if parameters is not None:
        if not isinstance(parameters, dict):
            raise TypeError("Parameter overrides must be the complete CONFIG dictionary")
        encoded = json.dumps(parameters, allow_nan=False)
        overrides += "import json as _override_json\nCONFIG = _override_json.loads(" + repr(encoded) + ")\n"
    notebook.cells.insert(parameters_cell + 1, nbformat.v4.new_code_cell(overrides))
    os.environ["HW09_EXECUTION_MODE"] = mode
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "simulation/matplotlib"))
    os.environ.setdefault("IPYTHONDIR", str(ROOT / "simulation/ipython"))
    print("Executing %s locally (%s); interpreter: %s" % (path.name, mode, sys.executable), flush=True)
    client = NotebookClient(notebook, timeout=7200, kernel_name="ece6420-local",
                            resources={"metadata": {"path": str(ROOT)}})
    # Keep the local interpreter selected by this launcher; SSH independently
    # chooses the server worker interpreter through RemoteConfig.
    manager = client.create_kernel_manager()
    manager.kernel_spec.argv = [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"]
    try:
        client.execute()
    finally:
        results = {c.id: c for c in notebook.cells if c.cell_type == "code"}
        for cell in original.cells:
            if cell.cell_type == "code" and cell.id in results:
                cell.outputs = results[cell.id].outputs
                cell.execution_count = results[cell.id].execution_count
        if "language_info" in notebook.metadata:
            original.metadata["language_info"] = notebook.metadata["language_info"]
        target = path if in_place else ROOT / "simulation/local-executed" / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        nbformat.write(original, target)
    print("Completed. Spectre computed remotely; all plots and PDF authoring were local.", flush=True)
    return notebook


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("remote", "review"), default="remote")
    parser.add_argument("--config", type=Path, help="JSON file containing the complete CONFIG dictionary")
    parser.add_argument("--in-place", action="store_true", help="Save locally generated outputs in the maintained notebook")
    args = parser.parse_args()
    config = json.loads(args.config.read_text()) if args.config else None
    execute_path(mode=args.mode, parameters=config, in_place=args.in_place)


if __name__ == "__main__":
    main()
