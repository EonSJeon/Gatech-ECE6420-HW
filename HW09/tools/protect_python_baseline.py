#!/usr/bin/env python3
"""Preserve the standalone baseline and keep its report separate from ADE GUI."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from cadence_review_bridge import preserve_python_baseline

REPORT_CELL = """if BUILD_REPORT:
    baseline_report = ROOT / 'output/pdf/HW09_python_baseline_report.pdf'
    command = [sys.executable, str(ROOT / 'tools/build_report.py'), '--output', str(baseline_report)]
    if ALLOW_PARTIAL:
        command.append('--allow-partial')
    subprocess.run(command, cwd=ROOT, check=True)
    from IPython.display import FileLink, display
    display(FileLink(str(baseline_report)))
else:
    print('Standalone Python-baseline report skipped by BUILD_REPORT=False.')"""


def protect(root=ROOT, dry_run=False):
    root = Path(root).resolve()
    changes = []
    if not dry_run:
        print(preserve_python_baseline(root))
    notebook_path = root / "notebooks/00_overview.ipynb"
    if notebook_path.exists():
        notebook = json.loads(notebook_path.read_text())
        for cell in notebook["cells"]:
            if cell.get("id") == "hw09-local-report":
                if "".join(cell["source"]) != REPORT_CELL:
                    cell["source"] = REPORT_CELL.splitlines(keepends=True)
                    cell["outputs"], cell["execution_count"] = [], None
                    changes.append(str(notebook_path.relative_to(root)) + " report cell")
            if cell.get("id") == "hw09-title":
                source = "".join(cell["source"])
                if "Standalone Python baseline" not in source:
                    source += "\n\n**Standalone Python baseline:** this notebook runs the earlier Python-generated-netlist campaign. Native schematic experiments must be run in ADE; use `01_cadence_gui_review.ipynb` to fetch and review their actual GUI results. This notebook writes only the separately named Python-baseline PDF."
                    cell["source"] = source.splitlines(keepends=True)
        if not dry_run:
            notebook_path.write_text(json.dumps(notebook, indent=1) + "\n")
    generator = root / "tools/create_notebook.py"
    if generator.exists():
        source = generator.read_text()
        old = "command = [sys.executable, str(ROOT / 'tools/build_report.py')]"
        new = "command = [sys.executable, str(ROOT / 'tools/build_report.py'), '--output', str(ROOT / 'output/pdf/HW09_python_baseline_report.pdf')]"
        patched = source.replace(old, new)
        marker = '    by_id["hw09-local-report"]["source"] = """'
        if marker in patched:
            start = patched.index(marker) + len(marker)
            stop = patched.index('"""', start)
            patched = patched[:start] + REPORT_CELL + patched[stop:]
        patched = patched.replace("# HW09 - Single-balanced mixer comparison",
                                  "# HW09 - Standalone Python-netlist baseline")
        if patched != source:
            changes.append(str(generator.relative_to(root)))
            if not dry_run:
                generator.write_text(patched)
    builder = root / "tools/build_report.py"
    if builder.exists():
        source = builder.read_text()
        patched = source.replace('base/"output/pdf/HW09_mixer_design_report.pdf"',
                                 'base/"output/pdf/HW09_python_baseline_report.pdf"')
        if patched != source:
            changes.append(str(builder.relative_to(root)) + " default output")
            if not dry_run:
                builder.write_text(patched)
    bridge = root / "lib/remote_bridge.py"
    if bridge.exists():
        source = bridge.read_text()
        patched = source
        if '"/cds.lib"' not in source:
            patched = patched.replace('"/.cadence/",',
                                      '"/.cadence/", "/cds.lib", "/lib.defs", "/.cdsinit", "/.cdsenv",')
        patched = patched.replace('"*.cdslck",', '"*.cdslck*",')
        if '"python_baseline.json"' not in patched:
            patched = patched.replace('NONNUMERICAL_OUTPUTS = (',
                                      'NONNUMERICAL_OUTPUTS = (\n    "python_baseline.json", "python_baseline.sha256",')
        if patched != source:
            changes.append(str(bridge.relative_to(root)) + " native control-file/lock protection")
            if not dry_run:
                bridge.write_text(patched)
    print(json.dumps({"dry_run": dry_run, "changes": changes}, indent=2))
    return changes


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    protect(args.root, args.dry_run)
