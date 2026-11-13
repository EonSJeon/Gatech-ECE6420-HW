# Editable HW09 Overleaf source

This folder is the local work tree for [the HW09 Overleaf project](https://www.overleaf.com/project/6af68c3c1b2af4608fb66bfd). The report compares active and passive single-balanced mixers using Cadence Spectre results from native Virtuoso schematics and ADE.

Open `main.tex` as the main document in Overleaf and select **pdfLaTeX**. Keep the folder structure so section and figure references resolve. Standard LaTeX fonts and packages are used.

Edit `main.tex`, `macros.tex`, `references.bib`, and `sections/user_discussion.tex` freely. These files are preserved on regeneration. The data-derived `sections/generated_*.tex`, figure files, and `build_manifest.json` are refreshed by `../tools/build_cadence_tex.py`. Put persistent discussion and formatting changes in the preserved files.

The report uses twelve native ViVA GUI plot exports and two full-testbench schematic exports from native `hiExportImage`. All fourteen figures use day mode for readability. A footnote in the report explains that the default night-mode exports were difficult to read. The two full schematic figures use landscape pages. Exact device dimensions, component values, connections, source settings, and measurement conventions are listed in the report.

Figure generation and binding are documented in `../cadence/README.md` and `../cadence/VIVA_README.md`. The current images are the original native day-mode exports restored byte for byte from source history; their original export receipts and electrical snapshots are retained. `exportnight.il` is a historical alternate appearance and is not used for the report. Figure hashes and native export evidence are recorded in `build_manifest.json`.

Git synchronization is manual in both directions through `../tools/overleaf_sync.py`, as documented in `../README.md`. Pull before editing or regeneration, then review and push the source changes. Pull accepts a clean fast-forward; push checks for newer Overleaf edits and uses an ordinary non-force push. Existing macOS Keychain authentication is reused. No password or token is saved in this project.

The separate Git metadata is in ignored `HW09/.local/overleaf-git`; there is no `.git` file or directory here. The parent repository tracks these source files independently. Compiled PDFs and LaTeX scratch files are ignored.

Connection verification: this line was added in the Overleaf web editor to verify that a Git pull receives online edits in HW09/overleaf.
