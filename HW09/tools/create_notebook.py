#!/usr/bin/env python3
"""Create the single HW09 overview notebook; never replace it silently."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def markdown(identifier, source):
    return {"cell_type": "markdown", "id": identifier, "metadata": {}, "source": source}


def code(identifier, source, tags=None):
    return {"cell_type": "code", "id": identifier,
            "metadata": {"tags": tags or ["local-only"]},
            "source": source, "outputs": [], "execution_count": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replace", action="store_true", help="Explicitly regenerate the maintained notebook source")
    args = parser.parse_args()
    path = ROOT / "notebooks/00_overview.ipynb"
    if path.exists() and not args.replace:
        raise SystemExit("Notebook already exists; preserve its source edits and saved local outputs.")
    cells = [
        markdown("hw09-title", "# HW09 - Standalone Python-netlist baseline\n\nSelect **ECE6420 (Local)** and connect GlobalProtect for a fresh simulation. **Run All** sends the current parameter dictionary to the school Spectre worker, receives numerical traces, and renders figures here. The notebook kernel and PDF generation run locally.\n\nThe two circuits follow the supplied active 3-NMOS current-commutating topology and passive 2-NMOS switching topology. See the final report for exact device values, terminal connections, bias conditions, measurement conventions, and schematic reconstruction steps."),
        code("hw09-setup", "import json\nimport os\nfrom pathlib import Path\nimport subprocess\nimport sys\n\n_cwd = Path.cwd().resolve()\n_candidates = [_cwd, _cwd / 'HW09', *_cwd.parents]\nROOT = next((p for p in _candidates if (p / 'lib/remote_bridge.py').is_file()), None)\nif ROOT is None:\n    raise RuntimeError('Open this notebook from the HW09 project directory.')\nif str(ROOT / 'lib') not in sys.path:\n    sys.path.insert(0, str(ROOT / 'lib'))\nos.environ.setdefault('MPLCONFIGDIR', str(ROOT / 'simulation/matplotlib'))\nfrom mixer import default_config\nfrom remote_bridge import run_remote\n\nEXECUTION_MODE = os.environ.get('HW09_EXECUTION_MODE', 'remote')\nprint('Local interpreter:', sys.executable)\nprint('Project:', ROOT)\nprint('Execution mode:', EXECUTION_MODE)\nprint('Kernel: ECE6420 (Local); Spectre runs over SSH independently of this kernel.')\n%matplotlib inline"),
        markdown("hw09-parameter-help", "## Parameters\n\nStart from the complete maintained configuration. Edit the dictionary below before running the next cell. Current Python values, including unsaved notebook edits, are serialized as JSON and sent to the server. Save changes to external Python source files before running, because source transfer reads those files from disk.\n\n`STAGES = None` requests the full campaign. Individual worker stages are `design`, `single_tone`, `linearity`, and `noise`; their dependencies and cache matching are validated by the worker. For offline review, set `EXECUTION_MODE = 'review'` and keep the configuration consistent with the saved results."),
        code("hw09-parameters", "CONFIG = default_config()\nSTAGES = None\nBUILD_REPORT = True\n\n# Examples of explicit edits (uncomment and choose values intentionally):\n# CONFIG['active']['rd_ohm'] = 300.0\n# CONFIG['active']['rf_bias_v'] = 0.65\n# CONFIG['active']['lo_common_mode_v'] = 0.80\n# CONFIG['active']['lo_vpp_per_leg'] = 0.40\n# CONFIG['passive']['rl_ohm'] = 1000.0\n# CONFIG['passive']['lo_vpp_per_leg'] = 0.40\n# EXECUTION_MODE = 'review'\nCONFIG", ["parameters", "local-only"]),
        code("hw09-remote-run", "print('Requested configuration:')\nprint(json.dumps(CONFIG, indent=2, allow_nan=False))\nif EXECUTION_MODE == 'remote':\n    REMOTE_STATUS = run_remote(CONFIG, stages=STAGES)\n    print(REMOTE_STATUS)\nelif EXECUTION_MODE == 'review':\n    print('Offline review: using saved numerical results; no SSH or Spectre run.')\nelse:\n    raise ValueError('EXECUTION_MODE must be remote or review')", ["remote-bridge", "local-only"]),
        markdown("hw09-plot-help", "## Locally rendered measurements\n\nThe next cell uses the returned numerical data. FFT figures use stems. Missing, failed, or stale simulations must be reported explicitly rather than replaced by a synthetic curve or an assumed noise floor."),
        code("hw09-local-plots", "from plots import plot_results\nimport matplotlib.pyplot as plt\nPLOT_STATUS = plot_results(CONFIG)\nplt.show()", ["local-only"]),
        markdown("hw09-report-help", "## PDF and schematic handoff\n\nThe report is authored locally from verified numerical results. It records the actual device values, RF/LO definitions, differential IF output, loads, operating points, measurement settings, and comparison results. Generated Spectre netlists and raw logs remain available for checking a later Virtuoso schematic run."),
        code("hw09-local-report", "if BUILD_REPORT:\n    subprocess.run([sys.executable, str(ROOT / 'tools/build_report.py')], cwd=ROOT, check=True)\n    from IPython.display import FileLink, display\n    for report in sorted((ROOT / 'output/pdf').glob('*.pdf')):\n        display(FileLink(str(report)))\nelse:\n    print('Report generation skipped by BUILD_REPORT=False.')", ["local-only"]),
    ]
    by_id = {cell["id"]: cell for cell in cells}
    by_id["hw09-parameters"]["source"] = by_id["hw09-parameters"]["source"].replace(
        "BUILD_REPORT = True\n", "BUILD_REPORT = True\nALLOW_PARTIAL = False\n")
    by_id["hw09-local-plots"]["source"] = by_id["hw09-local-plots"]["source"].replace(
        "plot_results(CONFIG)", "plot_results(CONFIG, allow_partial=ALLOW_PARTIAL)")
    by_id["hw09-local-report"]["source"] = """if BUILD_REPORT:
    baseline_report = ROOT / 'output/pdf/HW09_python_baseline_report.pdf'
    command = [sys.executable, str(ROOT / 'tools/build_report.py'), '--output', str(baseline_report)]
    if ALLOW_PARTIAL:
        command.append('--allow-partial')
    subprocess.run(command, cwd=ROOT, check=True)
    from IPython.display import FileLink, display
    display(FileLink(str(baseline_report)))
else:
    print('Standalone Python-baseline report skipped by BUILD_REPORT=False.')"""
    check = code("hw09-result-validation", """RESULT_PATH = ROOT / 'results/hw9_results.json'
if not RESULT_PATH.is_file():
    raise FileNotFoundError('No simulation result metadata was received: ' + str(RESULT_PATH))
RESULT_METADATA = json.loads(RESULT_PATH.read_text())
if RESULT_METADATA.get('config') != CONFIG:
    raise ValueError('Saved results do not match CONFIG. Run the campaign or restore the saved configuration.')
if RESULT_METADATA.get('status') != 'complete' and not ALLOW_PARTIAL:
    raise RuntimeError('Campaign status is ' + str(RESULT_METADATA.get('status')) +
                       '. Complete and validate missing stages before rendering a final report.')
print('Verified result status:', RESULT_METADATA.get('status'))
print('Recorded run ID:', RESULT_METADATA.get('run_id'))
if RESULT_METADATA.get('status') == 'complete':
    subprocess.run([sys.executable, str(ROOT / 'tools/validate_results.py')], cwd=ROOT, check=True)
""")
    cells.insert(next(i for i, cell in enumerate(cells) if cell["id"] == "hw09-plot-help"), check)
    notebook = {"nbformat": 4, "nbformat_minor": 5, "cells": cells,
                "metadata": {"kernelspec": {"display_name": "ECE6420 (Local)", "language": "python", "name": "ece6420-local"},
                             "language_info": {"name": "python", "version": "3.12"},
                             "hw09": {"workflow": "local Python -> SSH Spectre -> numerical data -> local figures/PDF", "configuration": "CONFIG", "remote_plots": False}}}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(notebook, indent=1) + "\n")
    print("Created " + str(path))


if __name__ == "__main__":
    main()
