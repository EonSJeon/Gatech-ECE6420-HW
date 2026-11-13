#!/usr/bin/env python3
"""Create the local review notebook for experiments already run in ADE."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def markdown(identifier, source):
    return {"cell_type": "markdown", "id": identifier, "metadata": {}, "source": source}


def code(identifier, source, parameters=False):
    return {"cell_type": "code", "id": identifier,
            "metadata": {"tags": ["local-only"] + (["parameters"] if parameters else [])},
            "source": source, "outputs": [], "execution_count": None}


def create(path):
    cells = [
        markdown("gui-title", "# HW09 - Native Cadence GUI result review\n\nSelect **ECE6420 (Local)**. This notebook receives existing native Virtuoso/ADE results, validates actual GUI-exported images and prepares editable LaTeX source locally. **Run All does not launch Spectre or press ADE Run.** Run changed schematic experiments from the native ADE GUI first. The earlier Python-generated-netlist experiment remains in `00_overview.ipynb` as a separate baseline."),
        code("gui-setup", "import json\nimport os\nfrom pathlib import Path\nimport subprocess\nimport sys\n\n_candidates = [Path.cwd().resolve(), Path.cwd().resolve() / 'HW09', *Path.cwd().resolve().parents]\nROOT = next((p for p in _candidates if (p / 'lib/cadence_review_bridge.py').is_file()), None)\nif ROOT is None:\n    raise RuntimeError('Open this notebook from the HW09 project.')\nsys.path.insert(0, str(ROOT / 'lib'))\nos.environ.setdefault('MPLCONFIGDIR', str(ROOT / 'simulation/matplotlib'))\nfrom cadence_review_bridge import preserve_python_baseline, fetch_gui_artifacts, import_actual_gui_results, render_gui_figures, render_gui_tex\nprint('Local interpreter:', sys.executable)\nprint('Kernel: ECE6420 (Local)')\nprint('Native experiments run from ADE; this notebook only fetches and reviews their data.')\n%matplotlib inline"),
        code("gui-parameters", "FETCH_FROM_SERVER = True\nMANIFEST_RELATIVE = 'cadence/gui_run_manifest.json'\nBUILD_TEX = True\nALLOW_PARTIAL_REVIEW = False\n# Set FETCH_FROM_SERVER=False to review the existing local native data without VPN.\n# MANIFEST_RELATIVE must identify the operator's actual-run record, not a planning file.", True),
        markdown("gui-provenance-help", "## Actual experiment record\n\nThe operator creates the manifest only after observing **ADE Run**, using the actual native history, generated netlist, log, and PSF paths. This notebook does not invent GUI launch timestamps or turn a planning file into run evidence. Fetching preserves the local manifest, copies the editable OA/state backup with `*.cdslck*` excluded, and never deletes files or pushes source to the server."),
        code("gui-fetch", "BASELINE = preserve_python_baseline(ROOT)\nprint('Immutable Python baseline:', BASELINE)\nif FETCH_FROM_SERVER:\n    FETCH_RECORD = fetch_gui_artifacts(ROOT)\n    print(FETCH_RECORD)\nelse:\n    print('Offline review: native source and GUI data are read from the local HW09 tree.')"),
        code("gui-import", "GUI_RESULTS = import_actual_gui_results(ROOT, MANIFEST_RELATIVE)\nprint('Actual GUI campaign:', GUI_RESULTS['run_id'])\nprint('Status:', GUI_RESULTS['status'])\nif GUI_RESULTS['status'] != 'complete' and not ALLOW_PARTIAL_REVIEW:\n    raise RuntimeError('Complete the missing native ADE measurements before final review/reporting.')\nfor kind, row in GUI_RESULTS['circuits'].items():\n    print(kind, json.dumps(row.get('metrics', {}), indent=2))"),
        markdown("gui-figures-help", "## Verified actual native GUI images\n\nWhen `plot_figure_mode=cadence_gui_export`, this cell verifies and displays the twelve already exported native ViVA images and their exact numerical-source records. It does not regenerate them with Matplotlib or substitute missing images. Capture/export new plots in Cadence first. Earlier local Python renderings remain only as archive/baseline material; the report's numerical tables retain independently audited measurements."),
        code("gui-figures", "GUI_FIGURES = render_gui_figures(ROOT, show=True, allow_partial=ALLOW_PARTIAL_REVIEW)\nprint('Verified review figures:', len(GUI_FIGURES))"),
        markdown("gui-report-help", '## Editable Overleaf source\n\nThe final step writes `overleaf/main.tex`, data-derived section includes, and local PNG figures from the complete actual GUI campaign. It does not compile a PDF or upload anything. Open `main.tex` in Overleaf and recompile there when desired. Editable `main.tex`, `macros.tex`, `references.bib`, and `sections/user_discussion.tex` are preserved on regeneration; generated sections and figures are refreshed. Missing or stale measurements are rejected.'),
        code("gui-report", "if BUILD_TEX:\n    if GUI_RESULTS['status'] != 'complete':\n        raise RuntimeError('Complete actual GUI measurements are required before generating the LaTeX source.')\n    source = render_gui_tex(ROOT)\n    from IPython.display import FileLink, display\n    display(FileLink(str(source)))\n    print('Editable source and local PNG figures prepared. No PDF compiled or files uploaded.')\nelse:\n    print('LaTeX generation skipped by BUILD_TEX=False.')"),
    ]
    notebook = {"nbformat": 4, "nbformat_minor": 5, "cells": cells,
                "metadata": {"kernelspec": {"display_name": "ECE6420 (Local)", "language": "python", "name": "ece6420-local"},
                             "language_info": {"name": "python", "version": "3.12"},
                             "hw09": {"workflow": "ADE GUI Run -> fetch actual native results -> local validation/figures/LaTeX source", "launches_simulator": False}}}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(notebook, indent=1) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    destination = ROOT / "notebooks/01_cadence_gui_review.ipynb"
    if destination.exists() and not args.replace:
        raise SystemExit("Review notebook already exists; preserve its edits and outputs.")
    create(destination)
    print("Created " + str(destination))
