# HW09 native ViVA figures

For a fresh reconstruction of the graph windows, load **`printfinal.il`**
through the existing Virtuoso SKILL IDE. It calls `replotexport.il` and
`replot.il` to evaluate retained Interactive.2 PSF results in twelve visible
ViVA windows using definitions in `plots.il`. It then applies `finalstyle.il`
and the approved `layoutfinal.il` before native image export.

The current report restores the fourteen original native day-mode exports from Overleaf source commit `b0015389bd5176fc9d8a2aab88dbfbecb2c8fefa`, together with their original export receipts. No simulation or numerical reevaluation was required. The report footnote explains that the default night-mode exports were difficult to read. The rollback and exact image hashes are recorded in `results/cadence_gui/day_mode_rollback.json`.

For future exports of the existing twelve graph windows, load `exportfinal.il` after the maintained `plots.il` definitions. Native `saveGraphImage` uses a white export background and the approved layout. `exportnight.il` is retained as a historical alternate appearance; it is not the current report export path.
The local notebook does not render these graphs; the actual Cadence GUI
performs their creation and image export.
There are no simulation calls or external plotting/rendering programs.

The plot outputs are twelve 2400-by-1600 PNGs in `cadence/gui_exports`, plus
`native_calculator_audit.tsv` and `native_export_receipt.tsv`. Archive prior task
PNGs before repeating this operation to avoid native overwrite confirmations.
The wrapper returns focus to the CIW when finished.

Subwindows use a vertical layout, complete legends above each graph, and short
trace names. Custom axis names omit units so native units appear once.
Transient curves use solid lines. The single-tone spectrum includes a native
IF detail pane. Manual display bounds and fixed major-tick steps keep endpoint
labels inside the image; measurement windows remain unchanged. The final
layout sets positive 20/22-point font preferences, while existing graph objects
retain their inherited fonts. Readability and label visibility were verified
from the actual exported PNGs; preference values alone do not establish exact
rendered glyph sizes.

All conversion-gain and IIP3 points are evaluated inside native OCEAN from
actual binary PSF with dft, mag, value, and db20. A one-volt-peak cosine verifies
DFT normalization; transforms must retain N/2+1 bins. Expected values are used
only for consistency checks and never replace measured native amplitudes.
The mixed comparison tolerance is 1 nV plus 0.01% of the reference amplitude.
It is a numerical comparison threshold, not a guarantee from simulator abstol.

Native and independent nearest-strobe Fourier calculations differed by at most
0.497 nV active and 0.0618 nV passive. Maximum weak-tone differences were
0.003414 dB and 0.003086 dB outside the accepted cubic interval. Mean IIP3 over
the accepted interval differed by less than 0.000076 dB and 0.000030 dB.
Independent linear interpolation of actual PSF samples reproduced over 99% of
the difference. Native graph values remain unchanged.

Transient figures show RF voltage minus applied bias and raw differential
output, including feedthrough. Noise figures use native NF and NFdsb, including
branch-load noise; NFieee is excluded. The source campaign is
`cadence_gui_ab6a7104f23d`.

Do not call awvUpdateWindow on supplied-waveform graphs: its database refresh
tries to evaluate human-readable trace names as Calculator expressions.
Rebuild the graphs from retained PSF through replotexport.il instead.

Primary references are installed IC25.1 oceanref (dft, v, getData, value, mag,
db20, saveGraphImage), vivaxlskill (native graph, title, legend, HI-window APIs),
and the registered font settings in etc/tools/viva/.cdsenv.

The primary figures use native day mode for readability. Graph image export explicitly uses white. Schematic exports use `fullColor` and preserve the selected on-screen layer colors; select day appearance before replacing the approved white-background schematic exports. The earlier night-mode images remain in task archives and Overleaf Git history.
