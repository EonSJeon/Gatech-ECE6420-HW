#!/usr/bin/env python3
"""Generate editable Overleaf LaTeX and local PNG figures from actual ADE data.

This tool never compiles a PDF, invokes a simulator, or uploads files. Complete
GUI results and unchanged provenance files are required before any output write.
Generated sections/figures are refreshed; main.tex, macros.tex, references.bib,
and sections/user_discussion.tex are preserved unless --refresh-template is used.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inside(root,relative):
    path=(root/relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("Missing or out-of-project source: "+str(relative))
    return path


def tex(value):
    replacements={"\\":r"\textbackslash{}","&":r"\&","%":r"\%","$":r"\$",
                  "#":r"\#","_":r"\_","{":r"\{","}":r"\}",
                  "~":r"\textasciitilde{}","^":r"\textasciicircum{}",
                  "µ":r"\ensuremath{\mu}","μ":r"\ensuremath{\mu}","Ω":r"\ensuremath{\Omega}",
                  "°":r"\ensuremath{^\circ}","−":"-","–":"--","—":"---",
                  "→":r"\ensuremath{\to}","≤":r"\ensuremath{\le}","≥":r"\ensuremath{\ge}"}
    return "".join(replacements.get(c,c) for c in str(value))


def number(value,digits=4):
    if value is None:return r"\emph{Not saved}"
    if isinstance(value,bool):return "Yes" if value else "No"
    if isinstance(value,(list,tuple)):
        return ", ".join(number(x,digits) for x in value)
    if isinstance(value,str):return tex(value)
    if not math.isfinite(float(value)):raise ValueError("Nonfinite report value")
    text=format(value,"."+str(digits)+"g")
    if "e" in text:
        mantissa,exponent=text.split("e")
        text=mantissa+r"\times10^{"+str(int(exponent))+"}"
    return r"\ensuremath{"+text+"}"


def table(headers,rows,spec=None):
    spec=spec or ("X"*len(headers))
    environment="tabularx" if "X" in spec else "tabular"
    opening=(r"\begin{tabularx}{\linewidth}{"+spec+"}" if environment=="tabularx" else r"\begin{tabular}{"+spec+"}")
    lines=[r"\begin{center}\small",opening,r"\toprule",
           " & ".join(tex(x) for x in headers)+r" \\",r"\midrule"]
    lines += [" & ".join(str(x) for x in row)+r" \\" for row in rows]
    lines += [r"\bottomrule",r"\end{"+environment+"}",r"\end{center}"]
    return "\n".join(lines)+"\n"


def figure(filename,caption,label):
    return (r"\reportfigure{"+filename+"}{"+caption+"}{"+label+"}\n")


def native_figure(filename,caption,label,role):
    macro="nativecorefigure" if role=="core" else "nativetestbenchfigure"
    return "\\"+macro+"{"+filename+"}{"+caption+"}{"+label+"}\n"


def schematic_role(spec):
    role=spec.get("role") or ("core" if "core" in Path(spec["image_path"]).stem else "testbench")
    if role not in {"core","testbench"}:raise ValueError("Unknown schematic figure role")
    return role


def validate_schematic_figures(root,native):
    for kind in ("active","passive"):
        if not any(spec.get("kind")==kind for spec in native):raise ValueError("Missing actual native figure: "+kind)
    native_roles=set()
    for spec in native:
        if spec.get("kind") not in {"active","passive"}:raise ValueError("Unknown native figure kind")
        role=(spec["kind"],schematic_role(spec))
        if role in native_roles:raise ValueError("Duplicate native schematic figure role")
        native_roles.add(role)
        origin=spec.get("origin","native_oa_geometry_local_render")
        if origin not in {"native_oa_geometry_local_render","cadence_gui_screenshot","cadence_gui_export"}:
            raise ValueError("Unknown schematic image origin")
        image=inside(root,spec["image_path"])
        if image.suffix.lower()!=".png" or not image.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Portable PNG schematic figure required")
        if "image_sha256" in spec and sha(image)!=spec["image_sha256"]:
            raise ValueError("Schematic image changed after provenance binding")
        if origin in {"cadence_gui_screenshot","cadence_gui_export"}:
            for field in ("image_sha256","capture_utc","capture_app","capture_attachment","role"):
                if not isinstance(spec.get(field),str) or not spec[field].strip():
                    raise ValueError("Actual screenshot requires capture evidence: "+field)
            observed=datetime.fromisoformat(spec["capture_utc"].replace("Z","+00:00"))
            if observed.tzinfo is None or observed.utcoffset().total_seconds()!=0:
                raise ValueError("Screenshot capture time must include UTC timezone")
            if origin=="cadence_gui_export" and not spec.get("export_method"):
                raise ValueError("Native GUI export requires the actual export method")
        if sha(inside(root,spec["source_audit"]))!=spec["source_sha256"]:
            raise ValueError("Native schematic audit changed")
        for extra in spec.get("auxiliary_source_audits",[]):
            if sha(inside(root,extra["source"]))!=extra["sha256"]:raise ValueError("Native symbol geometry changed")


def validate(root):
    path=inside(root,"results/cadence_gui_results.json")
    result=json.loads(path.read_text())
    if result.get("origin")!="cadence_ade_gui" or result.get("status")!="complete":
        raise ValueError("Complete actual native-schematic/ADE GUI measurements are required; no LaTeX is generated from missing or planned data")
    if result.get("plot_figure_mode")!="cadence_gui_export":
        raise ValueError("The primary report requires all twelve actual native ViVA GUI exports; Python plotting remains only in the standalone baseline")
    if set(result.get("circuits",{}))!={"active","passive"}:
        raise ValueError("Both native GUI circuits are required")
    if sha(inside(root,result["source_manifest"]))!=result["source_manifest_sha256"]:
        raise ValueError("Actual-run manifest changed after import")
    baseline_path=inside(root,result["baseline"]["path"])
    if baseline_path.name!="python_baseline.json" or sha(baseline_path)!=result["baseline"]["sha256"]:
        raise ValueError("An unchanged immutable Python baseline snapshot is required")
    baseline=json.loads(baseline_path.read_text())
    if baseline.get("config")!=result["config"]:raise ValueError("GUI/baseline configuration mismatch")
    needed=("voltage_gain_db","power_gain_db","ssb_nf_db","dsb_nf_db","iip3_dbm","p1db_dbm","power_mw")
    for kind,row in result["circuits"].items():
        if row.get("status")!="complete":raise ValueError("Incomplete GUI circuit: "+kind)
        for stage in ("single_tone","linearity","noise","window_convergence"):
            if row.get(stage,{}).get("status")!="complete":raise ValueError("Incomplete GUI stage: "+kind+"/"+stage)
        for key in needed:
            found=row.get("metrics",{}).get(key)
            if isinstance(found,bool) or not isinstance(found,(float,int)) or not math.isfinite(found):
                raise ValueError("Missing/nonfinite measured GUI metric: "+kind+"/"+key)
        single=row["single_tone"]
        fields=["mean_rf_v","mean_outp_v","mean_outn_v","min_output_v","max_output_v",
                "lo_diff_vpp","power_mw","settle_s","window_s","sample_count"]
        if kind=="active":fields += ["tail_min_v","tail_mean_v","tail_max_v"]
        for key in fields:
            if key not in single or single[key] is None:raise ValueError("Missing GUI transient evidence: "+kind+"/"+key)
        if single.get("settings_match_intended_limits") is not True:
            raise ValueError("Actual GUI single-tone solver settings exceed intended limits: "+kind)
        win=row["window_convergence"]
        for key in ("reference","gain_delta_db","tolerance_db"):
            if key not in win:raise ValueError("Missing GUI window evidence: "+kind+"/"+key)
        for key in ("settle_s","window_s","sample_count"):
            if key not in win["reference"]:raise ValueError("Missing GUI reference-window evidence")
        if win["reference"].get("settings_match_intended_limits") is not True:
            raise ValueError("Actual GUI reference-window solver settings exceed intended limits: "+kind)
        lin=row["linearity"]
        if len(lin.get("compression",[]))<4 or len(lin.get("two_tone",[]))<3:
            raise ValueError("Missing actual GUI linearity sweep records: "+kind)
        for key in ("p1db_bracket_dbm","p1db_dbm","p1db_resolution_db","cubic_region","convergence"):
            if key not in lin or lin[key] is None:raise ValueError("Missing GUI linearity evidence: "+kind+"/"+key)
        for key in ("delta_db","effective_reltol_normal","effective_reltol_tight",
                    "effective_maxstep_normal_s","effective_maxstep_tight_s","passed"):
            if key not in lin["convergence"] or lin["convergence"][key] is None:
                raise ValueError("Missing actual numerical-convergence evidence: "+kind+"/"+key)
        if lin["convergence"].get("passed") is not True or lin["convergence"].get("actual_numerical_settings_passed") is not True:
            raise ValueError("Actual GUI IIP3 convergence/solver evidence failed: "+kind)
        for run in lin.get("compression",[])+lin.get("two_tone",[]):
            if run.get("settings_match_intended_limits") is not True:
                raise ValueError("Actual GUI linearity sweep has invalid solver settings: "+kind)
        if row["noise"].get("convergence",{}).get("passed") is not True or row["noise"].get("native_checks",{}).get("passed") is not True:
            raise ValueError("Actual GUI periodic-noise convergence/normalization failed: "+kind)
        if not row.get("runs"):raise ValueError("Missing actual GUI run evidence")
        for run in row["runs"]:
            if not run.get("gui_action_utc") or run.get("view")!="schematic":
                raise ValueError("Missing observed native GUI launch evidence")
            for field in ("spectre_log","generated_netlist","schematic_export","psf"):
                if sha(inside(root,run[field]))!=run[field+"_sha256"]:
                    raise ValueError("Actual GUI source/data changed: "+run[field])
        required_curves={"transient","spectrum","compression","iip3","twotone","twotone_spectrum","noise"}
        if not required_curves.issubset(row.get("curves",{})):
            raise ValueError("Missing required actual GUI numerical curves: "+kind)
        for label,relative in row.get("curves",{}).items():
            if sha(inside(root,relative))!=row.get("curve_sha256",{}).get(label):
                raise ValueError("GUI numerical curve changed: "+relative)
    native=result.get("native_schematic_figures",[])
    validate_schematic_figures(root,native)
    if len(native)!=2 or any(schematic_role(spec)!="testbench" or spec.get("origin") not in {"cadence_gui_export","cadence_gui_screenshot"} for spec in native):
        raise ValueError("The primary report requires exactly two actual full-testbench GUI schematic images; optional core crops and reconstructed diagrams are excluded")
    if result.get("plot_figure_mode")=="cadence_gui_export":
        from cadence_gui_figures import validate as validate_gui_plots
        validate_gui_plots(root,result)
    return result,baseline,path


MAIN=r"""\documentclass[10pt,a4paper]{article}
\input{macros}
\title{Single-Balanced Mixer Design\\\large ECE6420: Native Virtuoso and ADE Results}
\author{}
\date{}
\begin{document}
\maketitle
\input{sections/generated_design}
\input{sections/generated_active}
\input{sections/generated_passive}
\input{sections/generated_methods}
\input{sections/user_discussion}
\input{sections/generated_provenance}
\bibliographystyle{ieeetr}
\bibliography{references}
\end{document}
"""

MACROS=r"""\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage[a4paper,margin=20mm]{geometry}
\usepackage{amsmath,amssymb,graphicx,booktabs,tabularx,array}
\usepackage{caption,placeins,seqsplit,pdflscape}
\usepackage[hidelinks]{hyperref}
\graphicspath{{figures/}}
\setlength{\parindent}{0pt}
\setlength{\parskip}{5pt}
\newcommand{\hash}[1]{{\ttfamily\scriptsize\seqsplit{#1}}}
\newcommand{\reportfigure}[3]{%
  \begin{figure}[htbp]\centering
  \includegraphics[width=\linewidth,height=.40\textheight,keepaspectratio]{#1}
  \caption{#2}\label{#3}\end{figure}}
\newcommand{\nativecorefigure}[3]{%
  \begin{figure}[p]\centering
  \includegraphics[width=\linewidth,height=.74\textheight,keepaspectratio]{#1}
  \caption{#2}\label{#3}\end{figure}}
\newcommand{\nativetestbenchfigure}[3]{%
  \clearpage\begin{landscape}\thispagestyle{plain}
  \begin{figure}[p]\centering
  \includegraphics[width=.95\linewidth,height=.72\paperwidth,keepaspectratio]{#1}
  \caption{#2}\label{#3}\end{figure}
  \clearpage\end{landscape}\clearpage}
"""

BIB=r"""@book{razavi2012,
 author={Behzad Razavi}, title={{RF Microelectronics}}, edition={2},
 publisher={Prentice Hall}, year={2012},
 note={Chapter 6; Figures 6.15(b) and 6.42}
}
@misc{hw09,
 author={{Georgia Institute of Technology}},
 title={{ECE6420 HW9: Mixer Design}}, howpublished={Course assignment},
 note={Assignment supplied in the maintained HW09 project}
}
"""


def build(root,refresh_template=False):
    root=Path(root).resolve()
    result,_,result_path=validate(root)
    config=result["config"];common=config["common"]
    lo=[config[k]["lo_vpp_per_leg"] for k in ("active","passive")]
    if not (common["vdd_v"]==1 and all(0<x<1 and 2*x<1 for x in lo)):
        raise ValueError("Supply/strict LO-swing assignment constraint is not met")
    figures={};fp=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
    gui_plot_mode=result.get("plot_figure_mode")=="cadence_gui_export"
    gui_plot_specs={}
    if gui_plot_mode:
        for spec in result["numerical_plot_figures"]:
            key=spec["kind"]+"_"+spec["role"]
            figures[key]=inside(root,spec["image_path"])
            gui_plot_specs[key]=spec
    else:
        raise ValueError("Actual native ViVA GUI exports are required; no Python-render fallback")
    def plot_caption(kind,role,default):
        if not gui_plot_mode:return default
        caption=gui_plot_specs[kind+"_"+role]["rendering_description"]
        if role=="transient":
            caption="Native ViVA transient view of the "+kind+" mixer: RF node after DC-bias subtraction and raw V(outp)-V(outn), including LO/RF feedthrough, in separate panels."
        if role=="noise":caption+=" Curves show native Spectre NF/NFdsb; the metric table retains independently audited manual normalization."
        return tex(caption)
    output=root/"overleaf"
    previous_manifest=output/"build_manifest.json"
    previous=json.loads(previous_manifest.read_text()) if previous_manifest.is_file() else {}
    for directory in (output,output/"sections",output/"figures"):directory.mkdir(parents=True,exist_ok=True)
    copied={};native={"active":[],"passive":[]}
    def copy_image(source,name):
        source=Path(source).resolve()
        if not source.is_relative_to(root) or source.suffix.lower()!=".png":raise ValueError("Unexpected local figure")
        destination=output/"figures"/name
        shutil.copy2(source,destination)
        copied[name]={"source":str(source.relative_to(root)),"sha256":sha(destination)}
        return name
    plot_names={key:copy_image(path,key+".png") for key,path in figures.items()}
    native_names=set()
    for spec in result["native_schematic_figures"]:
        kind=spec["kind"];role=schematic_role(spec)
        source_type="gui" if spec.get("origin") in {"cadence_gui_screenshot","cadence_gui_export"} else "native"
        target=kind+"_"+source_type+"_"+role+".png"
        if target in native_names:raise ValueError("Duplicate native figure role: "+target)
        native_names.add(target)
        name=copy_image(inside(root,spec["image_path"]),target)
        native[kind].append((role,name,spec["rendering_description"]))
    def metric(data,kind,key):
        row=data["circuits"][kind].get("metrics",{})
        gain={"conversion_loss_db":"voltage_gain_db","power_conversion_loss_db":"power_gain_db"}.get(key)
        return row[key] if key in row else -row[gain] if gain and gain in row else None
    d=[r"\section{Design requirements and measured comparison}",
       r"The two circuits implement single-balanced downconversion at the assignment RF/LO/IF frequencies. The results below compare an active current-switching mixer and a passive switching mixer simulated in Cadence Spectre from native Virtuoso schematics through ADE.\cite{hw09,razavi2012}\footnote{All figures were exported from the native Cadence GUI in day mode because the default night-mode exports were difficult to read.}"]
    d.append(table(["Constraint","Implemented condition"],[
        ["Technology / supply",r"NCSU 45 nm CMOS; $V_{DD}="+str(common["vdd_v"])+r"\,\mathrm{V}$; installed minimum $L=50\,\mathrm{nm}$"],
        ["RF / LO / IF",number(common["rf_hz"]/1e9)+" / "+number(common["lo_hz"]/1e9)+r" GHz / "+number(common["if_hz"]/1e6)+" MHz"],
        ["LO constraint",r"Each leg: "+number(lo)+r" Vpp (active/passive); differential: "+number([2*x for x in lo])+r" Vpp. Both are strictly below 1 Vpp."],
        ["Source / load",r"$R_s="+str(common["rs_ohm"])+r"\,\Omega$; equal branch loads; $C_L="+str(common["load_cap_f"]*1e15)+r"\,\mathrm{fF}$ per output."],
    ],"lX"))
    keys=[("voltage_gain_db","Differential voltage gain (dB)"),("conversion_loss_db","Voltage conversion loss (dB)"),
          ("power_gain_db","Transducer power gain (dB)"),("power_conversion_loss_db","Transducer power loss (dB)"),
          ("ssb_nf_db","Loaded SSB NF (dB)"),("dsb_nf_db","Loaded DSB NF (dB)"),
          ("iip3_dbm","Input IIP3 (dBm/tone)"),("p1db_dbm","Input P1dB midpoint (dBm)"),("power_mw","Core DC power (mW)")]
    d.append(table(["Metric","Active","Passive"],
        [[tex(label)]+[number(metric(result,kind,key)) for kind in ("active","passive")] for key,label in keys],"Xrr"))
    a=result["circuits"]["active"]["metrics"];p=result["circuits"]["passive"]["metrics"]
    d.append("The active circuit provides "+number(a["voltage_gain_db"])+" dB voltage gain and "+number(a["power_gain_db"])+" dB power gain at "+number(a["power_mw"])+" mW core power. The passive circuit has "+number(-p["voltage_gain_db"])+" dB voltage loss and "+number(-p["power_gain_db"])+" dB transducer power loss. Its zero core DC power excludes the ideal external LO driver. Loaded SSB NF is "+number(a["ssb_nf_db"])+" / "+number(p["ssb_nf_db"])+" dB (active/passive).")
    for key,label in (("iip3_dbm","IIP3"),("p1db_dbm","input P1dB")):
        winner="active" if a[key]>p[key] else "passive" if p[key]>a[key] else "neither"
        d.append("The measured "+label+" values are "+number(a[key])+" / "+number(p[key])+" dBm; "+winner+" has the higher measured value. Compression and intermodulation are evaluated separately, with the uncertainty/brackets shown below.")
    sections={"generated_design.tex":"\n\n".join(d)}
    for kind in ("active","passive"):
        row=result["circuits"][kind];q=config[kind];single=row["single_tone"];win=row["window_convergence"];ref=win["reference"]
        content=[r"\FloatBarrier\section{"+kind.capitalize()+r" native schematic and GUI results}"]
        content.append("M1 converts RF gate voltage into current; M2/M3 steer the shared current with complementary LO phases. R1/R2 return to VDD and convert IF current to differential voltage. No additional tail current source is placed below M1." if kind=="active" else "Two NMOS switches share the RF source node, have complementary LO gates, and drive separate outp/outn drains. Each branch resistor returns to ground. The desired output is differential even though the RF input is single-ended.")
        for role,name,description in sorted(native[kind],key=lambda item:item[0]!="core"):
            content.append(native_figure(name,tex(description),"fig:"+kind+"-"+role,role))
        devices=[("M1",q["gm_width_um"],"tail / rf / 0 / 0"),("M2",q["switch_width_um"],"outp / lop / tail / 0"),("M3",q["switch_width_um"],"outn / lon / tail / 0")] if kind=="active" else [("M1",q["switch_width_um"],"outp / lop / rf / 0"),("M2",q["switch_width_um"],"outn / lon / rf / 0")]
        content.append(table(["MOS","W (um)","L (nm)","m","Drain / gate / source / body"],[[name,number(width),number(q["length_nm"]),"1",tex(nets)] for name,width,nets in devices],"lrrrX"))
        content.append(table(["Schematic property","Exact value / connection"],[
            ["MOS library/cell/view",tex("NCSU_Devices_FreePDK45 / NMOS_VTH / symbol")],
            ["Bodies / diffusion",r"All bodies to ground; $L_S=L_D=105\,\mathrm{nm}$; CDF callbacks compute AS/AD/PS/PD."],
            ["R1/R2",number(q["rd_ohm" if kind=="active" else "rl_ohm"])+r" $\Omega$ each to "+("VDD" if kind=="active" else "ground")],
            ["CLP/CLN",number(common["load_cap_f"]*1e15)+" fF each, output to ground"],
            ["RF source DC",number(q["rf_bias_v" if kind=="active" else "rf_common_mode_v"])+" V open circuit; RFPORT vdc is half"],
            ["LO DC / amplitude",number(q["lo_common_mode_v"])+r" V common mode; "+number(q["lo_vpp_per_leg"]/2)+r" Vpk each; $0^\circ/180^\circ$ sinusoidal phase"],
        ],"lX"))
        content.append(r"$C_{GS}$ and $C_{GD}$ are intrinsic BSIM4 parasitics; do not add them as discrete parts. CLP/CLN are explicit output loads. The installed symbol has no separate finger-count CDF field; each device uses multiplier 1.")
        content.append(r"\subsection{Settled waveforms, spectra and headroom}")
        for suffix in ("transient","spectrum"):
            key=kind+"_"+suffix
            if key not in plot_names:raise ValueError("Missing complete GUI plot: "+key)
            content.append(figure(plot_names[key],plot_caption(kind,suffix,"Actual "+kind+" GUI-run "+suffix+"; raw differential output includes LO/RF feedthrough."),"fig:"+key))
        head=[("Mean RF node (V)",single.get("mean_rf_v")),("Mean outp / outn (V)",[single.get("mean_outp_v"),single.get("mean_outn_v")]),("Output min / max (V)",[single.get("min_output_v"),single.get("max_output_v")]),("Differential LO (Vpp)",single.get("lo_diff_vpp")),("Core power (mW)",single.get("power_mw"))]
        if kind=="active":head.append(("Tail min / mean / max (V)",[single.get("tail_min_v"),single.get("tail_mean_v"),single.get("tail_max_v")]))
        head += [("Short settle / window (ns)",[single["settle_s"]*1e9,single["window_s"]*1e9]),("Reference settle / window (ns)",[ref["settle_s"]*1e9,ref["window_s"]*1e9]),("Short / reference samples",[single["sample_count"],ref["sample_count"]]),("Reference-minus-short gain (dB)",win["gain_delta_db"]),("Allowed difference (dB)",win["tolerance_db"])]
        content.append(table(["Measured GUI evidence","Value"],[[tex(label),number(found)] for label,found in head],"Xr"))
        content.append("The static bias solution does not establish transistor region throughout LO commutation. Use the settled measured extrema to assess headroom. Capacitive LO feedthrough can briefly push an active output beyond VDD. FFT bin amplitudes do not measure a stochastic noise floor.")
        lin=row["linearity"];cube=lin["cubic_region"];conv=lin.get("convergence") or {}
        content.append(r"\FloatBarrier\subsection{GUI linearity}")
        for suffix in ("compression","iip3","twotone_spectrum"):
            key=kind+"_"+suffix
            if key not in plot_names:raise ValueError("Missing complete GUI plot: "+key)
            content.append(figure(plot_names[key],plot_caption(kind,suffix,"Actual "+kind+" GUI "+suffix.replace("_"," ")+" measurement; input powers are available power per tone."),"fig:"+key))
        checks=[("Input P1dB bracket (dBm)",lin["p1db_bracket_dbm"]),("P1dB midpoint / half-bracket (dBm)",[lin["p1db_dbm"],lin.get("p1db_resolution_db")]),("Accepted powers (dBm/tone)",cube["pins_dbm"]),("Fundamental slopes",cube["fundamental_slopes"]),("IM3 slopes",cube["im3_slopes"]),("Minimum IM3/empty-bin margin (dB)",cube["minimum_im3_to_empty_bin_margin_db"]),("Tighter-repeat IIP3 change (dB)",conv.get("delta_db")),("Effective reltol normal / repeat",[conv.get("effective_reltol_normal"),conv.get("effective_reltol_tight")]),("Effective maxstep normal / repeat (s)",[conv.get("effective_maxstep_normal_s"),conv.get("effective_maxstep_tight_s")]),("Convergence passed",conv.get("passed"))]
        content.append(table(["Linearity check","Actual GUI evidence"],[[tex(label),number(found)] for label,found in checks],"Xr"))
        noise=row["noise"];nc=noise["convergence"];native_check=noise["native_checks"]
        content.append(r"\FloatBarrier\subsection{GUI periodic noise}")
        content.append(figure(plot_names[kind+"_noise"],plot_caption(kind,"noise","Loaded SSB and DSB noise figure from the actual "+kind+" GUI periodic-noise data; intrinsic branch-load noise is included."),"fig:"+kind+"-noise"))
        checks=[("Source / circuit temperature",str(common["source_noise_temp_k"])+" K / "+str(common["temp_c"])+" C"),("Native SSB / DSB agreement (dB)",[native_check["max_ssb_delta_db"],native_check["max_dsb_delta_db"]]),("Sideband counts",nc["sidebands"]),("Last SSB sideband change (dB)",nc["last_ssb_delta_db"]),("Last DSB sideband change (dB)",nc["last_dsb_delta_db"]),("Convergence passed",nc["passed"])]
        content.append(table(["Noise check","Actual GUI evidence"],[[tex(label),number(found)] for label,found in checks],"Xr"))
        sections["generated_"+kind+".tex"]="\n\n".join(content)
    pin=config["analysis"]["small_signal_pin_dbm"]
    openpk=math.sqrt(8*common["rs_ohm"]*.001*10**(pin/10))
    methods=[r"\FloatBarrier\section{Exact source and measurement conventions}",
        r"Use native library \texttt{NCSU\_Devices\_FreePDK45}, cell \texttt{NMOS\_VTH}, view \texttt{symbol}. Check the terminal labels before wiring. Source/drain diffusion lengths are 105 nm; the installed callbacks give $A_S=WL_S$, $A_D=WL_D$, $P_S=W+2L_S$, and $P_D=W+2L_D$. Enter W, L and multiplier, then let the native property-form callbacks compute the read-only geometry fields.",
        r"\subsection{RF/LO source setup}",
        r"The Spectre/analogLib port uses matched-load voltage entries: its internal open-circuit DC, sine peak and PAC voltage are twice the entered fields. An ideal voltage source followed by exactly one source resistor uses the full open-circuit values directly. Do not add a second $R_s$ when using the port.",
        table(["Property","Native RF port","Ideal vsource plus one source resistor"],[
            ["Reference available input power",number(pin)+" dBm per tone",number(pin)+" dBm per tone"],
            ["Reference sine peak",number(openpk/2,10)+" V entered",number(openpk,10)+" V entered"],
            ["Active RF DC",number(config["active"]["rf_bias_v"]/2)+" V entered",number(config["active"]["rf_bias_v"])+" V entered"],
            ["Passive RF DC",number(config["passive"]["rf_common_mode_v"]/2)+" V entered",number(config["passive"]["rf_common_mode_v"])+" V entered"],
            ["PAC magnitude",r"0.5 V entered $\rightarrow$ 1 V open",r"1 V entered $\rightarrow$ 1 V open"],
            ["Source noise",number(common["source_noise_temp_k"]-273.15)+" C port noise temperature",number(common["source_noise_temp_k"])+" K resistor thermal noise"],
        ],"lXX"),
        r"The source CDF fields are \texttt{srcType}, \texttt{vdc}, \texttt{va}, \texttt{freq}, \texttt{sinephase}, and \texttt{pacm}. Set the LO source type to sine and use \emph{Phase for Sinusoid 1}, not the separate AC phase field, for $0^\circ/180^\circ$. The LO/bias generators are ideal; their driver power and noise are outside this core comparison.",
        r"\begin{align}P_{\mathrm{in,av}}&=\frac{V_{\mathrm{open,pk}}^2}{8R_s}, & V_{\mathrm{open,pk}}&=\sqrt{8R_s(10^{-3})10^{P_{\mathrm{in,dBm}}/10}},\\ G_V&=20\log_{10}\!\left(\frac{V_{\mathrm{IF,pk}}}{V_{\mathrm{open,pk}}}\right), & P_{\mathrm{load}}&=\frac{V_{\mathrm{IF,pk}}^2}{4R_L},\\ G_T&=10\log_{10}\!\left(\frac{P_{\mathrm{load}}}{P_{\mathrm{in,av}}}\right), & \mathrm{CL}_V&=-G_V,\quad \mathrm{CL}_P=-G_T.\end{align}",
        r"Here $V_{\mathrm{IF}}=V(\mathrm{outp})-V(\mathrm{outn})$ and $R_L$ is one physical branch resistor. Voltage gain and transducer power gain differ because the input/output references differ; a negative conversion loss denotes gain.",
        r"\subsection{Coherent transient and linearity extraction}",
        r"Single-tone RF is 5.8 GHz. Two equal available-power inputs at 5.79/5.81 GHz produce IF fundamentals at 190/210 MHz and IM3 products at 170/230 MHz. The measured settling, windows and exact sample counts are reported for each circuit. Coherent frequency bins are set by the settled observation window.",
        r"Frequency-domain amplitudes are extracted from the settled differential output. The spectra use native ViVA DFT analysis of the saved waveforms. Solver convergence is checked with a tighter tolerance repeat.",
        r"\begin{equation}P_{\mathrm{IIP3,dBm}}=P_{\mathrm{in,dBm/tone}}+10\log_{10}\!\left(\frac{A_{\mathrm{IF}}}{A_{\mathrm{IM3}}}\right).\end{equation}",
        r"The intercept is an extrapolation accepted only over a resolved three-point region with fundamental slope near 1 and IM3 slope near 3. The IM3/empty-bin margin is a numerical residual check, not a stochastic noise floor. A tighter repeat at the accepted region's middle power checks numerical stability. Compare the \emph{effective} reltol/maxstep values read from PSF headers: an analysis accuracy preset can override a declared global tolerance.",
        r"Input P1dB is the first 1 dB drop below the low-power, source-referenced gain. The reported value is the midpoint of adjacent measured crossing bounds; the half-bracket is its resolution. Do not normalize away gain compression by changing the input voltage reference at each drive level.",
        r"\subsection{Periodic noise normalization}",
        r"Use the LO-only periodic solution, with both RF transient scales set to zero while retaining RF DC bias, the noisy source resistance, and the PAC excitation. The actual saved ADE state and generated netlists retain the solver/analysis controls. Desired and image PAC gains are evaluated explicitly; DSB NF is not obtained by blindly subtracting 3 dB.",
        r"\begin{align}F_{\mathrm{SSB}}&=\frac{S_{v,\mathrm{out}}}{4kT_0R_s\lvert G_{\mathrm{open,USB}}\rvert^2},\\ F_{\mathrm{DSB}}&=\frac{S_{v,\mathrm{out}}}{4kT_0R_s(\lvert G_{\mathrm{open,USB}}\rvert^2+\lvert G_{\mathrm{open,image}}\rvert^2)}.\end{align}",
        r"$S_{v,\mathrm{out}}$ is the total output voltage-noise PSD; a PSF amplitude spectral density must be squared before this normalization. Both physical branch-resistor noise contributions are included. No external output load/probe resistor is added or subtracted. SSB refsideband is $+1$; the PAC output sideband is $-1$ for the specified input-axis runs.",
        table(["Output IF (MHz)","Desired RF (GHz)","Image RF (GHz)"],
              [[number(f/1e6),number((common["lo_hz"]+f)/1e9),number(abs(common["lo_hz"]-f)/1e9)]
               for f in config["analysis"]["noise_frequency_hz"]],"rrr"),
    ]
    sections["generated_methods.tex"]="\n\n".join(methods)
    screenshots=[spec for spec in result["native_schematic_figures"] if spec.get("origin") in {"cadence_gui_screenshot","cadence_gui_export"}]
    figure_provenance=("Schematic figures are actual Cadence GUI captures/exports; saved OA audits retain electrical connectivity and exact values." if len(screenshots)==len(result["native_schematic_figures"]) else "Schematic figures are identified individually as actual GUI captures/exports or local renderings from audited saved OA geometry.")
    numerical_provenance=("Numerical figures are native ViVA GUI exports tied to unchanged actual PSF data." if gui_plot_mode else "Numerical plots are rendered locally from unchanged actual PSF data.")
    provenance=[r"\FloatBarrier\section{Source and run provenance}",
        "The actual ADE GUI Run action was observed and recorded by the operator. A manifest label alone does not establish an action that was not observed. "+numerical_provenance+" "+figure_provenance]
    rows=[["Native designs",tex("HW09_Mixers / active_tb and passive_tb / schematic")],
          ["Actual manifest",tex(result["source_manifest"])],
          ["Configuration SHA-256",r"\hash{"+fp+"}"],
          ["Manifest SHA-256",r"\hash{"+result["source_manifest_sha256"]+"}"],
          ["GUI result SHA-256",r"\hash{"+sha(result_path)+"}"]]
    for kind,row in result["circuits"].items():
        counts=Counter(run["stage"] for run in row["runs"])
        rows.append([kind.capitalize()+" measurement records",tex(", ".join(key+"="+str(count) for key,count in sorted(counts.items())))])
        observed=sorted({run["gui_action_utc"] for run in row["runs"]})
        rows.append([kind.capitalize()+" observed Run UTC",tex(observed[0]+(" to "+observed[-1] if len(observed)>1 else ""))])
        exports=sorted({run["schematic_export_sha256"] for run in row["runs"]})
        rows.append([kind.capitalize()+" native audit SHA-256",r"\newline ".join(r"\hash{"+digest+"}" for digest in exports)])
        captures=[spec for spec in screenshots if spec["kind"]==kind]
        if captures:rows.append([kind.capitalize()+" screenshot capture",tex("; ".join(spec["capture_app"]+", "+spec["capture_utc"] for spec in captures))])
    provenance.append(table(["Evidence","Recorded source"],[[tex(label),found] for label,found in rows],"lX"))
    provenance.append("Several measurement analyses can share one physical native job. All actual netlist/log/PSF paths and per-file hashes remain in the machine-readable GUI results JSON. This source project also includes a build manifest recording the local figure hashes.")
    provenance.append(r"Scope: nominal schematic-level NCSU devices and ideal external sources. Layout parasitics, process corners, Monte Carlo, and LO-driver noise/power are outside this comparison. The assignment and textbook topologies are cited in \cite{hw09,razavi2012}.")
    sections["generated_provenance.tex"]="\n\n".join(provenance)
    for name,body in sections.items():
        (output/"sections"/name).write_text("% Generated from verified actual GUI data; regenerated by build_cadence_tex.py.\n"+body+"\n")
    templates={"main.tex":MAIN,"macros.tex":MACROS,"references.bib":BIB,
               "sections/user_discussion.tex":"% Editable discussion: preserved on later generation.\n% Add your interpretation, edits, or course-specific formatting here.\n"}
    for name,content in templates.items():
        path=output/name
        if refresh_template or not path.exists():path.write_text(content)
    archived=[]
    archive_id=previous.get("gui_results_sha256","")
    if not isinstance(archive_id,str) or len(archive_id)!=64 or any(c not in "0123456789abcdef" for c in archive_id):archive_id="previous"
    for name,evidence in previous.get("figures",{}).items():
        if name in copied:continue
        path=output/"figures"/name
        if Path(name).name!=name or path.suffix.lower()!=".png" or not path.is_file():continue
        if path.is_symlink():raise ValueError("Preserve/review former generated image symbolic link: "+name)
        if sha(path)!=evidence.get("sha256"):
            print("Preserved user-modified former generated image: "+name)
            continue
        archive=root/"results/cadence_gui/archived_source_figures"/archive_id[:12]/name
        if archive.is_symlink() or not archive.resolve().is_relative_to(root):raise ValueError("Unsafe generated-image archive path")
        archive.parent.mkdir(parents=True,exist_ok=True)
        if archive.exists() and sha(archive)!=sha(path):raise ValueError("Conflicting archived generated figure: "+name)
        shutil.copy2(path,archive);path.unlink()
        archived.append({"filename":name,"archive":str(archive.relative_to(root)),"sha256":sha(archive)})
    record={"generated_utc":datetime.now(timezone.utc).isoformat(),"origin":"verified_cadence_ade_gui_tex_source",
            "run_id":result["run_id"],"gui_results_sha256":sha(result_path),
            "actual_manifest_sha256":result["source_manifest_sha256"],
            "builder_sha256":sha(Path(__file__)),"figures":copied,
            "schematic_figure_evidence":result["native_schematic_figures"],
            "plot_figure_mode":result["plot_figure_mode"],
            "numerical_plot_evidence":result.get("numerical_plot_figures",[]),
            "native_plot_comparison":result.get("native_plot_comparison"),
            "archived_former_generated_figures":archived,
            "compiled_pdf":False,"external_upload":False,
            "generated_sections":sorted(sections),"preserved_template_files":sorted(templates)}
    (output/"build_manifest.json").write_text(json.dumps(record,indent=2)+"\n")
    print("Editable LaTeX and local PNG figures prepared: "+str(output/"main.tex"))
    print("No PDF compiled, simulator launched, or external upload performed.")
    return output/"main.tex"


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--check-only",action="store_true",help="Validate provenance without writing LaTeX/figures")
    parser.add_argument("--refresh-template",action="store_true",help="Explicitly replace editable template files with defaults")
    args=parser.parse_args()
    if args.check_only:
        result,_,_=validate(args.root.resolve())
        print("Complete actual GUI source validated: "+result["run_id"])
    else:build(args.root,args.refresh_template)
