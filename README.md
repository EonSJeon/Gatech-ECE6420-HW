# ECE6420 - Wireless IC Design

Georgia Tech ECE6420 circuit-simulation homework and projects. The course covers RF nonlinearity/noise, receivers, LNAs, mixers, VCOs and PLLs. See the [course syllabus](course/ECE6420_Syllabus_2026%20Fall.pdf).

The current assignment is [HW05: Common-gate LNA](HW05/README.md).

Open [HW05/notebooks/00_overview.ipynb](HW05/notebooks/00_overview.ipynb), select **ECE6420 (Local)**, connect GlobalProtect, and choose **Run All**. Computation runs through SSH on the school server; received numerical data is plotted in the local kernel. FFT plots use stems. No remote notebook kernel or Remote SSH extension is required.

```text
course/                 Course syllabus
HW05/
  references/           Assignment and solution PDFs
  netlists/reference/   Immutable reference netlists
  netlists/generated/   Generated netlists
  notebooks/            Current notebook source
  lib/                  Shared computation, transfer and plotting functions
  results/              Numerical results and locally rendered figures
  simulation/           PSF, logs and worker status
  tools/                Execution and synchronization tools
```

The local and remote homework roots correspond directly:

```text
Local:  Gatech-ECE6420/HW05
Remote: /nethome/sjeon84/Gatech-ECE6420/HW05
```

The named local kernel is already registered on this Mac. See [HW05 setup and execution](HW05/README.md) for registration commands, parameter editing and offline review mode. The [common prompt](prompt/Common%20Prompt%20%E2%80%94%20ECE%20Circuit%20Simulation%20Homework%20with%20Cadence_Spectre.md) records conventions for later assignments.

## Zotero reading library

The [ECE6420 Zotero collection](docs/zotero/papers/README.md) mirrors the collection under Favorites, including native annotations. Run `./tools/open-vscode.sh` to start the background mirror. See [connection, commands, and publishing limits](docs/zotero/ZOTERO_VSCODE_SETUP.md). Reviews follow [Zotero Paper Review Common Prompt](prompt/Zotero%20Paper%20Review%20Common%20Prompt.md).


## HW09 - Single-balanced mixers

[HW09](HW09/README.md) contains native Virtuoso active/passive mixer schematics, the ADE simulation campaign, measured results, and a schematic rebuild guide. The [editable report source](HW09/overleaf/main.tex) is synchronized with [Overleaf](https://www.overleaf.com/project/6af68c3c1b2af4608fb66bfd) and uses native Cadence day-mode figures. Open [the GUI results review notebook](HW09/notebooks/01_cadence_gui_review.ipynb) with the **ECE6420 (Local)** kernel to inspect existing results and exported images.
