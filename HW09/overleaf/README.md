# HW09 IEEE conference source

This folder is synchronized with [the HW09 Overleaf project](https://www.overleaf.com/project/6af68c3c1b2af4608fb66bfd). Open `main.tex` with pdfLaTeX. The supplied `conference-latex-template_10-17-19.zip` provides the unchanged `IEEEtran.cls`; the report uses its `conference` defaults for paper size, margins, fonts and two columns.

The paper begins directly with circuit configuration, measurement definitions and simulation results. It has no abstract, introduction, conclusion, citations or bibliography. Schematics span both columns when needed for labels; plots and the three compact comparison tables use one column. All fourteen measured schematic/plot images remain the original day-mode exports. The two supplied topology images are preserved unchanged.

The comments in `sections/generated_design.tex` and `sections/generated_active.tex` answer the output-capacitance and finger-count questions. The 10-fF output capacitors are an explicit, shared testbench load assumption. The connection tables and repeated metric prose were removed. Full run records and hashes stay in the machine-readable build and result records.

`main.tex`, `macros.tex`, and `sections/user_discussion.tex` are preserved on later regeneration. Data-derived sections are composed by `../tools/ieee_report.py` through `../tools/build_cadence_tex.py`. Update the composition template for editorial changes that must survive regeneration. The build manifest records the class, image and measurement hashes. Source packaging includes the verified class file.

Pull before editing or regeneration with `../tools/overleaf_sync.py`; review and explicitly push the result. Existing macOS Keychain authentication is reused. Git metadata is kept separately in ignored `HW09/.local/overleaf-git`, and the parent repository tracks ordinary source files.

Connection verification: this line was added in the Overleaf web editor to verify that a Git pull receives online edits in HW09/overleaf.
