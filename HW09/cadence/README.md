# HW09 native Cadence schematic and GUI experiment state

The editable OpenAccess library is `HW09_Mixers` in this directory. The flat testbenches are `active_tb/schematic` and `passive_tb/schematic`. Their checked native instances use `NCSU_Devices_FreePDK45/NMOS_VTH`, analogLib sources, resistors and capacitors. The actual experiment state is `HW09_Mixers/mixer_campaign/maestro`.

| Setting | Active | Passive |
| --- | --- | --- |
| Device M1 | W=15 um, L=50 nm, m=1 | W=20 um, L=50 nm, m=1 |
| LO switch MOS | M2/M3, W=20 um, L=50 nm, m=1 | M1/M2, W=20 um, L=50 nm, m=1 |
| Source/drain diffusion length | 105 nm each | 105 nm each |
| Supply | 1 V | No core supply |
| RF source common mode | 0.65 V open-circuit; port DC field 0.325 V | 0 V |
| LO common mode | 0.8 V | 0.5 V |
| LO sine amplitude per leg | 0.2 Vpk | 0.2 Vpk |
| LO sine phases | 0 / 180 degrees | 0 / 180 degrees |
| LO swing | 0.4 Vpp per leg, 0.8 Vpp differential | Same |
| Branch resistors | 500 ohm each to VDD | 500 ohm each to ground |
| CLP / CLN | 10 fF each to ground | Same |
| RF Thevenin resistance | 50 ohm, included once in RFPORT | Same |

Every bulk connects to ground. The installed symbol has no finger-count CDF field; each device is one unfingered instance. Its callbacks set AD/AS/PD/PS from W and LS/LD. Intrinsic Cgs/Cgd are already inside the BSIM4 model; the explicit CLP/CLN loads are additional testbench components.

## Open and run the saved GUI state

1. Connect to the existing school FastX session and start Virtuoso with the installed NCSU PDK initialization. Open Library Manager, choose `HW09_Mixers`, `mixer_campaign`, `maestro`. This opens the actual graphical ADE Assembler matrix.
2. Inspect either schematic and the test variables. `pinDbm` is available source power per RF tone; `fRF/fRF2`, `tone2Scale`, and `rfScale` configure single-tone, two-tone, and LO-only operation. At -55 dBm, Vopen,pk is 1.12468265038 mV; the RFPORT amplitude field is half that value.
3. Use ordinary **Spectre** in High Performance Simulation, with error preset override **Do not override**. The individual analyses request conservative accuracy. The initial default Spectre X MX mode ignored/redefined the intended maxstep and tolerance values, so its diagnostic smoke history is excluded from the final verified campaign.
4. For a fresh generated setup, only `active_single_tone` and `passive_single_tone` are enabled. Click the actual ADE **Run All** button and accept **Update and Run** when prompted. Inspect the emitted `input.scs`, real Spectre log and numerical traces before continuing.
5. Load `enable_all.il` in the same GUI process, then click the actual ADE **Run All** button again. The helper enables 56 configured tests and excludes the metadata-only `active_probe`. It does not start a simulator. Maximum simultaneous simulation jobs is two.
6. Wait until all enabled tests finish. Load `export_paths.il` to write `HW09/ade_native_paths.tsv` with the selected native history and actual point-1 directories. This fixed campaign gives each named test one constant-valued point. The exporter checks real files and rejects additional sweep points rather than returning a template path.
7. Fetch numerical data, model/netlist/log provenance and native OA/state into the matching local HW09 paths. For the primary report, export the plots in the visible native ViVA GUI and transfer their actual PNGs/receipts explicitly. Local notebook review uses **ECE6420 (Local)** to check/import data, verify the native images and prepare editable TeX; it does not substitute Matplotlib images. The earlier local-render common-prompt workflow remains only as the standalone baseline.

## Native GUI presentation and image helpers

Load these lowercase source files through the existing visible Virtuoso/ViVA GUI, using CIW or the SKILL IDE. They reuse completed experiment data and do not invoke simulator-run APIs. Review CIW status and image receipts after each operation; helper definitions are not proof of an export.

| GUI-loaded file | Purpose |
| --- | --- |
| `presentation.il` | Adds larger display labels from actual instance properties, checks identical instance/value/terminal/orientation/wire snapshots, then saves and uses documented `hiExportImage` for native schematic PNGs. |
| `plotactive.il` | Loads `plots.il` definitions and opens native active-circuit ViVA plot views from the actual campaign data. |
| `plotpassive.il` | Opens passive-circuit views using the loaded native plot definitions. |
| `plotall.il` | Alternative that loads definitions and creates all twelve native plot views. Use this path instead of the active/passive sequence; reloading definitions resets the plot registry. |
| `exportplots.il` | Calls the native image exporter for the complete registered plot set after calculator/source checks. |

Canonical order is `plotactive.il` then `plotpassive.il`, or `plotall.il` alone, followed by GUI inspection and `exportplots.il`. The exported PNGs and `native_export_receipt.tsv` are under `cadence/gui_exports`. `plots.il` contains definitions only. `plotdiagnostics.il` is retained as a specific earlier-session weak-IM3 diagnostic/recovery; the final plotting definitions include the corrected comparison and do not require that recovery. `focusplots.il` is a session-specific window-focus aid, not a reusable campaign entry point.

The primary schematic pair is `active_gui_testbench.png` and `passive_gui_testbench.png`, presented on landscape pages. Their `presentation_exports.tsv` receipt records actual `hiExportImage` calls, file paths, native times and windows; `presentation_electrical.tsv` records equal electrical snapshots before/after annotation. `presentation_before.json` and `presentation_after.json` retain pre/post OA byte hashes. Optional `*_gui_core.png` crops and the earlier local OA-primitive renderings are excluded from the report.

Primary plot metadata requires twelve real native GUI images: transient, spectrum, two-tone spectrum, compression, IIP3 and noise for each circuit. `plot_figure_mode=cadence_gui_export` prevents Python-render fallback. Native PSF paths, hashes, calculator audits and image-export receipts remain the source evidence. Native noise plots show Spectre NF/NFdsb; audited manual normalization remains the numerical-table reference. Native ViVA DFT interpolation and the table's saved-strobe projection are cross-checked separately, retaining the native plotted values. Inspect the actual GUI/exported images before binding their metadata.

Numerical result data is under `HW09/simulation/cadence_gui`. Cadence also creates current-session ICRP runtime/log folders such as `HW09/.tmp_sjeon84` and `HW09/logs_sjeon84`; keep them protected while workers are active. Native waveform storage uses supported double-precision PSF. The installed lossless converter is `/tools/software/cadence/ic/latest/tools/dfII/bin/psf`: `psf -f %.17g -i native_file -o ascii_file`. The native top-level `.../psf/test/...` paths can be templates; the verified campaign uses actual `.../Interactive.N/1/test/...` point files.

## Rebuild the native state from maintained source

`build.il` is the separately maintained native schematic builder. It creates real editable symbols, wires, nets and instance properties, then checks and saves both schematics. Do not run it over unsaved manual edits.

Run `python3 tools/generate_cadence_ade.py` locally to regenerate `cadence/ade.il` and `cadence/ade_plan.json` from `references/final_config.json`. Transfer source to the matching remote project, then load `ade.il` through native SKILL IDE or CIW. Configuration creates/saves the native maestro tests and opens the actual maestro GUI if needed. No helper calls a simulation-run API; the user/operator starts every experiment from the visible GUI Run command.

Transient tests request maxstep 2 ps, strobe 5 ps, and global reltol 1e-5; the conservative preset made the corrected smoke's effective reltol 1e-6. Tight IIP3 checks request maxstep 1 ps and global reltol 1e-6, also conservative. Use actual generated netlists and effective headers/logs to document precision. Single-tone windows are 5 ns settling plus 20 ns measurement, with an independent 20+100 ns reference; two-tone windows are 20+100 ns.

Periodic tests keep RF DC bias and source noise while setting RF sine amplitudes to zero. Shooting PSS uses 5.6 GHz, 63 harmonics, 5 ns stabilization and maxacfreq 381.348 GHz. Desired PAC covers 5.7/5.8/5.9 GHz and image PAC 5.3/5.4/5.5 GHz; select the harmonic -1 child. PNOISE covers 100/200/300 MHz, uses RFPORT as input probe, differential outp/outn, reference sideband +1, and checks 15/31/63 folded sidebands. No external output probe/load is added. The reported loaded NF includes the physical branch-resistor noise and excludes ideal LO-driver noise/power.

The planning JSON records requested tests. Only the actual GUI history, emitted native schematic netlists, completion logs, converted numerical files and observed GUI-run timestamps establish a measured result.

### Native day-mode report figures

The current report uses the fourteen original native day-mode exports restored byte for byte from Overleaf source commit `b0015389bd5176fc9d8a2aab88dbfbecb2c8fefa`. Their original native export receipts and electrical snapshot proof are retained. `results/cadence_gui/day_mode_rollback.json` records the restored image hashes. Day mode was selected because the default night-mode exports were difficult to read; the report states this in a footnote. Simulation data and the Native Calculator audit are unchanged.

`plots.il` uses white graph and image backgrounds for future native plot exports. `presentation.il` exports the current schematic layer colors with `hiExportImage`; choose the native day appearance before replacing the approved schematic images. `exportnight.il` and `presentation_night_electrical.tsv` retain the earlier alternate appearance and its electrical proof. See `VIVA_README.md` for the reconstruction workflow.
