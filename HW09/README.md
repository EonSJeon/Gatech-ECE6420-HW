# HW09 - Single-balanced passive and active downconversion mixers

The primary report uses **FastX / Virtuoso / ADE** experiments, **native ViVA GUI plot exports**, and two full-testbench schematic images exported by native **`hiExportImage`**. The six plot roles per circuit are transient, spectrum, two-tone spectrum, compression, IIP3 and noise. [01_cadence_gui_review.ipynb](notebooks/01_cadence_gui_review.ipynb), using **ECE6420 (Local)**, fetches existing numerical data, imports/checks provenance, displays the actual GUI-exported images and prepares editable **Overleaf LaTeX source** at `overleaf/main.tex`. It requires `plot_figure_mode=cadence_gui_export` and all twelve validated plot images; there is no Python rendering fallback. Run changed experiments and export new images in Cadence first, then record their actual paths in `cadence/gui_run_manifest.json`. See [native GUI helper instructions](cadence/README.md) and [Overleaf source instructions](overleaf/README.md).

`00_overview.ipynb`, `run_all.sh`, and the earlier PDF builders retain the original common-prompt standalone Python/Matplotlib workflow as a baseline only. No baseline rerun is requested. `results/python_baseline.json` is the immutable comparison snapshot; its checksum is retained separately. Native OA/state backups, numerical data and actual GUI images stay in this same HW09 project. Generic fetches exclude live locks and image files; actual native GUI PNGs are transferred explicitly with their export receipts. Primary review never starts a simulator, creates replacement plots, compiles a local PDF or pushes to Overleaf.

```bash
HW09/.venv/bin/python HW09/tools/execute_cadence_review.py --mode fetch --no-tex
HW09/.venv/bin/python HW09/tools/execute_cadence_review.py --mode review
```

From the repository root, the first command fetches/imports/checks existing GUI results and displays already transferred native GUI images; the second reviews the same local evidence and prepares editable LaTeX using those images. Complete actual GUI-image metadata is required in both modes. `--no-report` remains a compatibility alias for `--no-tex`. The notebook parameter `BUILD_TEX` controls source generation. Open `main.tex` in Overleaf with pdfLaTeX when recompilation is desired there. No Remote SSH extension or remote notebook kernel is required.

`HW09/overleaf` is also the work tree for [the HW09 Overleaf project](https://www.overleaf.com/project/6af68c3c1b2af4608fb66bfd). Run `HW09/.venv/bin/python HW09/tools/overleaf_sync.py pull` before editing or regenerating, and explicitly run `push --message "Update HW09 source"` after review. `status` is local-only; `status --refresh` checks the remote. Git metadata stays in ignored `HW09/.local/overleaf-git`, so the parent repository keeps tracking ordinary source files. Pull is fast-forward only, and push refuses new remote commits or divergence. See the source-folder README for commands and conflict behavior; notebook Run All never pushes automatically.

The maintained report uses the supplied IEEE conference template, starts directly with circuit and measurement sections, and includes the simulation results in two columns. It has no abstract, introduction, conclusion, or bibliography. The TeX comments answer the output-load and finger-count questions; report composition is maintained in `tools/ieee_report.py`.

## Legacy standalone Python baseline

This project implements the two supplied circuit topologies as parameterized Spectre netlists. Run the Python API or notebook locally; the school server runs Spectre and numerical analysis. Numerical traces, generated netlists, and logs return to this same workspace. Figures and the PDF are created locally. FFT plots use stems.

## Run the maintained notebook

1. Connect GlobalProtect and verify `ssh gt-ece`.
2. Open `notebooks/00_overview.ipynb` locally and select **ECE6420 (Local)**.
3. Run the setup and parameter cells. The setup prints the actual local interpreter.
4. Edit `CONFIG` in the parameter cell, then use **Run All**. Its current Python values are sent explicitly, including edits that have not yet been saved in the notebook file.

Save edits to Python source before a remote run: source synchronization transfers files from disk. No Remote SSH extension or remote Jupyter kernel is required. Normal local Jupyter notebook support is sufficient.

The notebook defaults to `EXECUTION_MODE = "remote"`. Use `EXECUTION_MODE = "review"` to redraw the saved numerical data and rebuild the local report without SSH. Review mode does not rerun Spectre; changing circuit parameters requires a remote run.

The notebook rejects missing, mismatched, or incomplete result metadata before plotting or building a final report. Selected-stage runs can legitimately return `partial`; run the missing phases before treating the work as complete. Set `ALLOW_PARTIAL = True` only for an explicitly labeled diagnostic report, which passes `--allow-partial` to the local report builder.

```bash
cd HW09
./run_all.sh
python3 tools/execute_notebooks.py --mode review --in-place
```

The launcher reuses `HW09/.venv/bin/python` when available. Set `HW09_LOCAL_PYTHON` to select another installed local interpreter. If **ECE6420 (Local)** is already registered, reuse it. If it is absent, install the listed requirements in the intended local environment, then explicitly run `python3 tools/setup_local_kernel.py` and refresh the notebook kernel list.

## Python API

Run this from `HW09/` or add its absolute `lib/` path:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "lib"))
from mixer import default_config
from remote_bridge import run_remote
from plots import plot_results

config = default_config()
# Edit the complete parameter dictionary here before requesting a run.
run_remote(config, stages=None)  # None requests the full measurement campaign.
plot_results(config)           # Figures are rendered on this local Python process.
```

Run selected stages with `stages=["design", "single_tone", "linearity", "noise"]`, or a subset supported by the worker. The worker validates dependencies and source/configuration provenance. Use the complete default parameter dictionary as the basis for overrides.

```bash
./tools/remote.sh status
./tools/remote.sh push --dry-run
./tools/remote.sh push
./tools/remote.sh pull
./tools/remote.sh run --config my_parameters.json --stages single_tone,linearity
python3 tools/build_report.py
```

## Workspace and synchronization

```text
Local:  /Users/jeonsang-eon/Gatech-ECE6420/HW09
Remote: /nethome/sjeon84/Gatech-ECE6420/HW09

references/              Assignment and circuit references
netlists/reference/      Maintained topology definitions
netlists/generated/      Actual analysis netlists returned by the server
notebooks/               One maintained local overview notebook
lib/                     Circuit, analysis, transfer, parser, and plotting code
tools/                   Local entry points and the headless remote worker
results/                 Numerical results and measurement metadata
results/figures/         Locally generated figures
simulation/              Real Spectre data and logs, worker audit, local runtime caches
output/pdf/              Locally authored report
```

The source push uses `rsync --delete` only within the validated remote HW09 directory. It protects existing `results/`, `simulation/`, generated netlists, `.venv/`, `.local/`, private `.remote.env`, and local deliverables. Data pull does not delete local files or replace notebooks/source code. It excludes remote figures, images, PDFs, HTML, and notebooks. No plots are generated on the school server.

The SSH alias is `gt-ece`; no SSH configuration or credentials are changed. Remote shell syntax runs in explicit Bash because the login shell can be tcsh. The worker interpreter defaults to the existing project runtime `.venv/bin/python`. To override the host, exact HW09 directory, interpreter, or hostname, use the keys in `tools/remote.env.example` in a private `HW09/.remote.env` file. Do not store passwords or private keys in this project.

## Recreating the circuit in Virtuoso

Use the final parameter tables, terminal-by-terminal connections, analysis settings, and amplitude/power conventions in the PDF. Recreate the same device model, body connections, RF source resistance, LO common mode and per-leg swing, output loads, and measured differential output. Copying only W/L while changing those conditions does not reproduce a mixer measurement.

The Python notebook exposes all parameter dictionaries. The generated netlists and Spectre logs retain the actual values used, and the measurement metadata ties numerical results to that configuration. Consult the report for the measured values and any remaining limitations; this README does not substitute assumed or fabricated performance numbers.


## Selected schematic values

Use **NCSU_Devices_FreePDK45 / NMOS_VTH / symbol** in Virtuoso. This installed PDK uses a minimum channel length of **50 nm** despite the process name FreePDK45. Set Width, Length, Multiplier=1, and source/drain diffusion lengths LS=LD=105 nm. Its callbacks compute AD/AS/PD/PS automatically. There is no finger-count CDF field for this symbol; the baseline uses one unfingered device (implicit model nf=1).

| Circuit | Devices | Width | Length | Bias / loads |
| --- | --- | --- | --- | --- |
| Active | M1 RF transconductor | 15 um | 50 nm | RF source DC bias 0.65 V |
| Active | M2/M3 LO switching pair | 20 um each | 50 nm | LO common mode 0.8 V |
| Passive | M1/M2 switches | 20 um each | 50 nm | RF source DC bias 0 V; LO common mode 0.5 V |
| Both | R1/R2 | 500 ohm each | - | Active returns to VDD=1 V; passive returns to ground |
| Both | CLP/CLN | 10 fF each | - | Explicit output-node testbench loads to ground |

All MOS bodies connect to ground. Active M1 is `(tail, rf, 0, 0)` in drain/gate/source/body order; M2/M3 are `(outp, lop, tail, 0)` / `(outn, lon, tail, 0)`. Do not place another tail current source below M1. Passive devices are `(outp, lop, rf, 0)` / `(outn, lon, rf, 0)`. Output is always `V(outp)-V(outn)`.

LO legs use analogLib/vsource: Source type=sine, Frequency 1=5.6G, Amplitude 1=0.2 Vpk, DC voltage=the common mode above. Set **Phase for Sinusoid 1** (`sinephase`) to 0/180 degrees. AC phase is a different field. Each leg is 0.4 Vpp and the differential LO is 0.8 Vpp, satisfying either interpretation of the less-than-1-Vpp requirement. LO driver power/noise are excluded; the drivers are ideal testbench sources.

## RF source and power convention

The input Thevenin resistance is 50 ohm. At per-tone available source power P, the open-circuit sine peak is `sqrt(8*50*P)` with P in watts. Spectre/analogLib port DC and amplitude describe the matched-load voltage; the internal open-circuit values are twice those fields. Set RFPORT DC to half the desired RF source bias, transient amplitude to half Vopen, and PAC magnitude=0.5 to obtain a 1 V open-circuit PAC source. An equivalent analogLib/vsource uses the full source bias and Vopen, followed by one explicit 50-ohm resistor; do not add that resistor again when using port r=50.

The normal small-signal run uses -55 dBm available input power. Single-tone RF is 5.8 GHz. The two-tone test uses 5.79/5.81 GHz with equal available power per tone; IF fundamentals are 190/210 MHz and IM3 products are 170/230 MHz. Conversion voltage gain is reported relative to the open-circuit source and separately to the actual RF node. Transducer power gain uses the two physical output load resistors and is a separate quantity.

Single-tone sweeps use 5 ns settling plus a 20 ns coherent window (4000 samples at 5 ps; 50 MHz FFT bins). A separate 20 ns settling / 100 ns window reference checks this shorter window. Two-tone sweeps use 20 ns settling plus a 100 ns coherent window (20000 samples; 10 MHz bins). FFT spectra use stems. The displayed reconstructed IF component is calculated from the actual simulated trace; the raw LO-containing differential output remains available separately.

Noise uses LO-only shooting PSS followed by PAC and PNOISE with a noisy 50-ohm RF port at 290 K. Circuit temperature is 27 C. The primary SSB NF includes the intrinsic branch-resistor noise and all retained folded sidebands; no external output load is added/subtracted. Native Spectre NF is cross-checked using total output noise and explicit desired/image PAC gains. Counts 15/31/63 verify noise-sideband convergence.

[Exact component CSV](references/component_values.csv), [final Python configuration](references/final_config.json), [active reference deck](netlists/reference/active_reference.scs), and [passive reference deck](netlists/reference/passive_reference.scs) support manual schematic reconstruction. Final generated analysis decks and simulator logs are in `netlists/generated/` and `simulation/`.

The two `netlists/reference/*_reference.scs` decks are runnable single-tone baselines with the normal -55 dBm RF excitation. The Cgs/Cgd labels in the textbook passive-mixer figure are intrinsic MOS capacitances already included by the BSIM4 model; do not place extra Cgs/Cgd components. CLP/CLN=10 fF are separate chosen testbench loads.


## Verified baseline results

The complete Python/Spectre campaign passed the independent numerical audit (91 checks, no failures). The maintained local notebook completed its real SSH/data/plot/PDF workflow without cell errors; all 20 parser, transfer-safety, and numerical-audit tests pass. Results are schematic-level, nominal-corner simulations with ideal external LO/bias sources, rather than post-layout or statistical guarantees.

| Metric | Active | Passive |
| --- | ---: | ---: |
| Source-referenced differential voltage gain | +8.573 dB | -5.975 dB |
| Transducer power gain | +1.584 dB | -12.965 dB |
| Loaded SSB noise figure at 200 MHz | 11.146 dB | 16.694 dB |
| Loaded DSB noise figure at 200 MHz | 8.124 dB | 13.708 dB |
| Input IIP3, worst product, per tone | -2.718 dBm | -5.472 dBm |
| Input P1dB, final bracket midpoint | -15.547 dBm | -15.078 dBm |
| Core DC power | 0.685 mW | 0 mW |

P1dB brackets are [-15.625, -15.46875] dBm (active) and [-15.15625, -15] dBm (passive). Passive zero core DC power excludes the external LO driver. Both noise figures include the actual 500-ohm branch-load noise. See `results/hw9_results.json` for full precision and measurement definitions, and `results/validation.json` for the independent audit.
