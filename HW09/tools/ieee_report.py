"""Compose the concise conference report from the verified mixer measurements."""
from __future__ import annotations
import math

MAIN = r"""\documentclass[conference]{IEEEtran}
\input{macros}
\title{HW09: Single-Balanced Mixer Design}
\author{\IEEEauthorblockN{Sangeon Jeon}
\IEEEauthorblockA{ECE6420 Wireless IC Design\\Georgia Institute of Technology}}
\date{\today}
\begin{document}
\maketitle
\input{sections/generated_design}
\input{sections/generated_active}
\input{sections/generated_passive}
\input{sections/generated_methods}
\input{sections/generated_results}
\input{sections/user_discussion}
\end{document}
"""

MACROS = r"""\usepackage{amsmath,amssymb,graphicx,booktabs,tabularx,array}
\usepackage[hidelinks]{hyperref}
\graphicspath{{figures/}}
\newcommand{\reportfigure}[3]{%
  \begin{figure}[!tb]\centering
  \includegraphics[width=.94\columnwidth]{#1}
  \caption{#2}\label{#3}
  \end{figure}}
\newcommand{\schematicfigure}[3]{%
  \begin{figure*}[!t]\centering
  \includegraphics[width=.84\textwidth]{#1}
  \caption{#2}\label{#3}
  \end{figure*}}
"""


def num(value, digits=3):
    if not math.isfinite(float(value)):
        raise ValueError("Nonfinite conference-report value")
    return format(float(value), f'.{digits}f')


def sci(value, digits=2):
    mantissa, exponent = f'{float(value):.{digits}e}'.split('e')
    return mantissa + r'\times10^{' + str(int(exponent)) + '}'


def table(caption, label, rows):
    placement = '!b' if label == 'tab:design' else '!t'
    body = [r'\begin{table}[' + placement + ']', r'\caption{' + caption + '}',
            r'\label{' + label + '}', r'\centering\footnotesize',
            r'\setlength{\tabcolsep}{4pt}',
            r'\begin{tabularx}{\columnwidth}{@{}Xrr@{}}',
            r'\toprule', r'Parameter & Active & Passive \\', r'\midrule']
    body += [' & '.join(row) + r' \\' for row in rows]
    body += [r'\bottomrule', r'\end{tabularx}', r'\end{table}']
    return '\n'.join(body)


def plot(kind, role, caption):
    return (r'\reportfigure{' + kind + '_' + role + '.png}{' + caption +
            '}{fig:' + kind + '-' + role + '}')


def sections(result):
    config = result['config']; common = config['common']
    a = result['circuits']['active']; p = result['circuits']['passive']
    am = a['metrics']; pm = p['metrics']
    design = r"""\section{Circuits and Simulation Conditions}
The active mixer follows the single-balanced topology in Fig.~6.42, and the
passive mixer follows the NMOS implementation in Fig.~6.15(b), reproduced in
Fig.~\ref{fig:topologies}. Both cores retain these circuit structures.
They downconvert a 5.8~GHz RF input with a 5.6~GHz local oscillator (LO) to a
200~MHz intermediate frequency (IF). The supply is 1~V. Figures use day mode
because the night-mode exports were difficult to read.

\begin{figure*}[!t]\centering
\begin{minipage}[c]{.52\textwidth}\centering
\includegraphics[width=\linewidth]{Fig6.15.png}
\end{minipage}\hspace{.04\textwidth}
\begin{minipage}[c]{.30\textwidth}\centering
\includegraphics[width=\linewidth]{Fig6.42.png}
\end{minipage}
\caption{Implemented core topologies: passive mixer (left, Fig.~6.15) and active
mixer (right, Fig.~6.42).}
\label{fig:topologies}\end{figure*}

The transistors use library \texttt{NCSU\_Devices\_FreePDK45} and cell \texttt{NMOS\_VTH}.
The installed process uses a minimum channel length of 50~nm; all bodies are
connected to ground. Each RF source has a 50~$\Omega$ resistance. Complementary
LO sinusoids have 0.4~V peak-to-peak per leg and 0.8~V differential
peak-to-peak, satisfying the specified limit under either interpretation.
Table~\ref{tab:design} gives the selected device sizes and biases.

% Response to the load-capacitance questions in the annotated source:
% 10 fF is an explicit testbench assumption, not a universal convention and
% not a capacitance specified by the assignment or the supplied core drawings.
% CLP and CLN load the two outputs equally in both circuits; every reported
% measurement includes these capacitors. These are loaded-circuit results.
% The assignment leaves output loading unspecified, so this is a disclosed
% design condition, not an assertion that an unloaded circuit was simulated.
% With a 500-ohm branch resistor alone, the 10-fF load gives an RC pole near
% 31.83 GHz and about 0.00017 dB attenuation at 200 MHz. This simple RC estimate
% excludes transistor parasitics and is not a simulated load-sensitivity study.
% Removing the capacitors would require a new simulation campaign.
A 10~fF capacitor from each output to ground is an explicit testbench load,
additional to the core drawings. This load is a design assumption rather than
an assignment requirement, and is applied identically to both mixers.
The shown $C_{GS}$ and $C_{GD}$ are included in the transistor model; they are
not added as separate capacitors.

% Review response: omit a separate drain/gate/source/body connection table.
% The labeled schematics already show those connections.
% Review response: do not repeat the numerical performance table in prose.
"""
    design += '\n' + table('Selected circuit parameters', 'tab:design', [
        [r'Transconductor width ($\mu$m)', num(config['active']['gm_width_um'], 0), '--'],
        [r'Switch width ($\mu$m)', num(config['active']['switch_width_um'], 0), num(config['passive']['switch_width_um'], 0)],
        [r'Channel length (nm)', '50', '50'],
        [r'Branch load ($\Omega$)', '500', '500'],
        [r'RF source DC (V, open circuit)', num(config['active']['rf_bias_v'], 2), num(config['passive']['rf_common_mode_v'], 2)],
        [r'LO common mode (V)', num(config['active']['lo_common_mode_v'], 2), num(config['passive']['lo_common_mode_v'], 2)],
    ])

    active = r"""\subsection{Active Mixer}
The RF transistor M1 converts input voltage into current. The differential
pair M2--M3 steers this current between the two 500~$\Omega$ loads, which
return to $V_{DD}$. The output is $v_{\mathrm{IF}}=v_{\mathrm{outp}}-v_{\mathrm{outn}}$.
The LO pair operates as a current switch; the RF transconductor is
single-ended. The 1~V supply makes transconductor bias and
switch headroom competing design constraints.

% Response to the CLP/CLN question: these are the explicit 10-fF output loads
% disclosed in the preceding section, not the transistor's Cgs/Cgd parasitics.
% They are included in both circuits and retained in all existing results.
%
% Response to the finger-count/multiplier question:
% Finger count describes a multifinger layout/model segmentation. The device
% multiplier m represents complete parallel device multiplicity. They are
% different parameters; m=1 alone does not establish the number of fingers.
% The installed symbol does not expose a separate finger-count property.
% These simulations use the selected W/L and m=1; no additional finger-count
% property was entered. This implementation detail is omitted from the prose.
% The redundant terminal-connection table remains omitted as requested.
\schematicfigure{active_schematic.png}{Active mixer testbench with device
values, output loads and source settings.}{fig:active-schematic}
"""
    passive = r"""\subsection{Passive Mixer}
Two NMOS switches share the RF source node, receive complementary LO phases,
and drive separate outputs loaded by 500~$\Omega$ resistors to ground.
The RF source DC level is zero. The 0.5~V LO common mode provides gate drive
without an RF transconductance stage. Finite switch resistance and source/load
interaction cause conversion loss. Zero core DC power excludes the energy
supplied by the ideal external LO driver.

\schematicfigure{passive_schematic.png}{Passive mixer testbench with device
values, output loads and source settings.}{fig:passive-schematic}
"""

    methods = r"""\section{Measurement Definitions}
\subsection{Source Reference and Conversion Gain}
All results use the same available input power reference and differential IF
output. For a source resistance $R_s$, an open-circuit sinusoidal peak voltage
$V_{\mathrm{open,pk}}$ gives
\begin{equation}
P_{\mathrm{in,av}}=\frac{V_{\mathrm{open,pk}}^2}{8R_s}.
\label{eq:pin}\end{equation}
At the small-signal test power of $-55$~dBm, the open-circuit peak is
1.12468~mV. The analogLib port uses matched-load voltage entries: enter half
this value (0.56234~mV), with $R_s=50~\Omega$ inside the port. The active
port's DC entry is 0.325~V to obtain 0.65~V open circuit; the passive entry is
zero. Its PAC magnitude is 0.5~V for a 1~V open-circuit reference. Do not add a
second source resistor. LO legs use 0.2~V sine peaks and phases of
$0^\circ$ and $180^\circ$.

For differential IF peak amplitude $V_{\mathrm{IF,pk}}$ and one physical
branch resistor $R_L$, the reported gain and load power are
\begin{align}
G_V &=20\log_{10}\!\left(\frac{V_{\mathrm{IF,pk}}}{V_{\mathrm{open,pk}}}\right),
\label{eq:gv}\\
P_{\mathrm{IF,load}}&=\frac{V_{\mathrm{IF,pk}}^2}{4R_L},
\label{eq:pout}\\
G_T&=10\log_{10}\!\left(\frac{P_{\mathrm{IF,load}}}{P_{\mathrm{in,av}}}\right).
\label{eq:gt}\end{align}
Voltage conversion loss is $-G_V$ and transducer power loss is $-G_T$.
The different source/load impedances mean that voltage gain and power gain
must not be interchanged.

\subsection{Transient and Linearity Measurements}
Single-tone measurements use 5~ns settling followed by a 20~ns observation
window at a 5~ps strobe interval (4000 samples). A 20~ns settling plus 100~ns
window checks steady-state convergence. Spectra use a rectangular DFT on the
settled differential output. The time-domain plots retain the full waveform,
including LO/RF feedthrough, rather than an extracted IF sinusoid.

The input 1~dB compression point is the first crossing of the low-power gain
minus 1~dB in a fourteen-point input-power campaign. The reported midpoint
has a half-bracket resolution of 0.078125~dB. This is sweep resolution, not a
statistical confidence interval.

Equal tones at 5.79 and 5.81~GHz produce IF fundamentals at 190 and 210~MHz,
and third-order products at 170 and 230~MHz. Two-tone measurements use a
20~ns settling time and 100~ns window (20000 samples; 10~MHz bins).
For each resolved product,
\begin{equation}
P_{\mathrm{IIP3}}=P_{\mathrm{in,tone}}
+10\log_{10}\!\left(\frac{A_{\mathrm{IF}}}{A_{\mathrm{IM3}}}\right),
\label{eq:iip3}\end{equation}
where the powers are in dBm and the amplitudes use the same peak-voltage
reference. The accepted interval is $-40$, $-35$ and $-30$~dBm per tone;
fundamental and IM3 slopes must approach one and three, respectively.
The lower of the two product intercepts is reported. A repeat at $-35$~dBm
uses effective reltol $10^{-7}$ and a 1~ps maximum step, versus $10^{-6}$ and
2~ps for the main campaign. Empty-bin margins test numerical resolution,
not a stochastic noise floor.

\subsection{Periodic Noise}
Shooting periodic steady-state analysis uses the 5.6~GHz LO, 63 harmonics,
and 5~ns stabilization. RF transient amplitudes are zero; RF DC bias, source
resistance noise and PAC excitation remain enabled. Source noise temperature
is 290~K and circuit temperature is $27^\circ$C. Periodic noise is evaluated
at 100, 200 and 300~MHz while checking 15, 31 and 63 folded sidebands.

Let $S_{v,\mathrm{out}}$ be total differential output voltage-noise PSD and
$G_{\mathrm{USB}}$, $G_{\mathrm{image}}$ the desired and image voltage gains
referenced to the open-circuit source. The noise factors are
\begin{align}
F_{\mathrm{SSB}}&=\frac{S_{v,\mathrm{out}}}{4kT_0R_s|G_{\mathrm{USB}}|^2},
\label{eq:ssb}\\
F_{\mathrm{DSB}}&=\frac{S_{v,\mathrm{out}}}
{4kT_0R_s\bigl(|G_{\mathrm{USB}}|^2+|G_{\mathrm{image}}|^2\bigr)}.
\label{eq:dsb}\end{align}
Noise figure is $10\log_{10}F$. At 200~MHz IF, the desired and image RF
frequencies are 5.8 and 5.4~GHz. The DSB result uses both measured gains;
it is not defined by subtracting 3~dB from SSB NF. Both branch-resistor noise
contributions are included. Ideal LO-driver noise and power are excluded.
"""

    results = r"""\section{Simulation Results}
Table~\ref{tab:performance} compares the circuits at 200~MHz IF. The passive
conversion loss is the negative of the signed gain entry. The active mixer
trades DC power for conversion gain and lower loaded noise figure. The
passive mixer avoids a DC transconductance bias, but its finite switch
conductance and limited LO swing reduce signal transfer. Its small
compression advantage does not imply a higher third-order intercept;
compression and intermodulation characterize different nonlinear behavior.
"""
    results += '\n' + table('Performance at 200 MHz IF', 'tab:performance', [
        [r'Voltage gain $G_V$ (dB)', num(am['voltage_gain_db'], 2), num(pm['voltage_gain_db'], 2)],
        [r'Transducer gain $G_T$ (dB)', num(am['power_gain_db'], 2), num(pm['power_gain_db'], 2)],
        [r'Loaded SSB NF (dB)', num(am['ssb_nf_db'], 2), num(pm['ssb_nf_db'], 2)],
        [r'Loaded DSB NF (dB)', num(am['dsb_nf_db'], 2), num(pm['dsb_nf_db'], 2)],
        [r'IIP3 (dBm/tone)', num(am['iip3_dbm'], 2), num(pm['iip3_dbm'], 2)],
        [r'Input P1dB (dBm)', '$'+num(am['p1db_dbm'], 2)+r'\pm0.08$', '$'+num(pm['p1db_dbm'], 2)+r'\pm0.08$'],
        [r'Core DC power (mW)', num(am['power_mw'], 3), num(pm['power_mw'], 0)],
    ])
    results += r"""

\subsection{Waveforms and Spectra}
The active output extrema are 0.622 and 1.010~V; capacitive LO feedthrough
can briefly push an output above the DC supply. The shared source node of
the LO pair spans 0.196--0.305~V. These settled extrema are more informative
for headroom than the static bias solution alone. The passive outputs span
approximately $-22.9$ to 22.2~mV. The differential output spectra show the
200~MHz IF together with out-of-band feedthrough.
"""
    for kind in ('active', 'passive'):
        cap = kind.capitalize()
        results += '\n\n' + plot(kind, 'transient', cap + ' mixer: settled RF input and differential output, including feedthrough.')
        results += '\n\n' + plot(kind, 'spectrum', cap + ' mixer: differential output spectrum at $-55$~dBm input; full-band and IF views, with 50~MHz DFT bins.')
    results += r"""

\subsection{Compression, Intermodulation and Convergence}
The compression sweeps and two-tone plots use available source power per
tone. The horizontal compression reference is the mean of the first three
low-power gains minus 1~dB. The accepted cubic interval resolves both IM3
products above numerical residuals. Table~\ref{tab:checks} summarizes slope
and convergence checks; the dominant numerical sensitivity in this campaign
is the active mixer's tighter-repeat IIP3 change.
"""
    ac = a['linearity']['cubic_region']; pc = p['linearity']['cubic_region']
    max_delta = lambda row: max(abs(v) for v in row['linearity']['convergence']['delta_db'])
    results += '\n' + table('Extraction and convergence checks', 'tab:checks', [
        ['Fundamental slope (mean)', num(sum(ac['fundamental_slopes'])/2, 3), num(sum(pc['fundamental_slopes'])/2, 3)],
        ['IM3 slope (mean)', num(sum(ac['im3_slopes'])/2, 3), num(sum(pc['im3_slopes'])/2, 3)],
        ['IM3/residual margin (dB)', num(ac['minimum_im3_to_empty_bin_margin_db'], 1), num(pc['minimum_im3_to_empty_bin_margin_db'], 1)],
        [r'Tighter-repeat $|\Delta\mathrm{IIP3}|$ (dB)', num(max_delta(a), 3), num(max_delta(p), 4)],
        [r'Longer-window $|\Delta G_V|$ (dB)', '$'+sci(abs(a['window_convergence']['gain_delta_db']))+'$', '$'+sci(abs(p['window_convergence']['gain_delta_db']))+'$'],
        [r'Last sideband $|\Delta\mathrm{NF}|$ (dB)', '$'+sci(max(abs(v) for v in a['noise']['convergence']['last_ssb_delta_db']))+'$', '$'+sci(max(abs(v) for v in p['noise']['convergence']['last_ssb_delta_db']))+'$'],
    ])
    for kind in ('active', 'passive'):
        cap = kind.capitalize()
        results += '\n\n' + plot(kind, 'compression', cap + ' mixer: conversion gain versus input power and the 1~dB compression threshold.')
        results += '\n\n' + plot(kind, 'iip3', cap + ' mixer: IF fundamentals and IM3 products versus input power per tone. Slopes are checked over $-40$ to $-30$~dBm.')
        results += '\n\n' + plot(kind, 'twotone_spectrum', cap + ' mixer: two-tone spectrum at $-35$~dBm per tone, with 190/210~MHz fundamentals and 170/230~MHz IM3 products.')
    for kind in ('active', 'passive'):
        results += '\n\n' + plot(kind, 'noise', kind.capitalize() + ' mixer: loaded SSB and DSB noise figure with 63 folded sidebands; transistor and branch-load noise are included.')
    results += r"""

\subsection{Loaded Noise Figure}
The noise plots show the 63-sideband Spectre SSB and DSB results. Explicit
source-noise normalization agrees within $8.31\times10^{-5}$~dB. The last
sideband changes are negligible compared with the reported precision.
The passive circuit's lack of core DC power does not eliminate the noise
penalty of conversion loss and branch loading.

The comparison is for the stated nominal schematic models, common output
loads and ideal external sources. Layout parasitics, process variation and
LO-driver circuitry are outside the simulated circuit boundary.
"""
    return {'generated_design.tex': design, 'generated_active.tex': active,
            'generated_passive.tex': passive, 'generated_methods.tex': methods,
            'generated_results.tex': results}
