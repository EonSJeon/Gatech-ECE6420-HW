#!/usr/bin/env python3
"""Locally author the full HW09 native-schematic/ADE mixer design report.

Run only after the required PDF artifact-operation marker. This consumes the
separate GUI campaign, actual native-source figures, and the retained Python
baseline; it does not launch simulation or generate remote numerical plots.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,PageBreak,Spacer,Image
import matplotlib.font_manager as fm


def build(project, output=None, allow_partial=False):
    root=Path(project).resolve()
    sys.path.insert(0,str(root/"lib"))
    import plots
    result_path=root/"results/cadence_gui_results.json"
    result=json.loads(result_path.read_text())
    if result.get("origin")!="cadence_ade_gui":
        raise ValueError("Report requires an actual separate Cadence GUI campaign")
    if result.get("status")!="complete" and not allow_partial:
        raise ValueError("Complete all GUI measurements before authoring the final report")
    source_manifest=root/result["source_manifest"]
    if hashlib.sha256(source_manifest.read_bytes()).hexdigest()!=result["source_manifest_sha256"]:
        raise ValueError("GUI source manifest changed after import")
    for row in result["circuits"].values():
        for run in row.get("runs",[]):
            for field in ("spectre_log","generated_netlist","schematic_export","psf"):
                if hashlib.sha256((root/run[field]).read_bytes()).hexdigest()!=run[field+"_sha256"]:
                    raise ValueError("Actual GUI source/result changed after import: "+run[field])
        for label,path in row.get("curves",{}).items():
            if hashlib.sha256((root/path).read_bytes()).hexdigest()!=row.get("curve_sha256",{}).get(label):
                raise ValueError("GUI numerical curve changed after import: "+path)
    baseline_path=root/result["baseline"]["path"]
    if hashlib.sha256(baseline_path.read_bytes()).hexdigest()!=result["baseline"]["sha256"]:
        raise ValueError("The retained Python baseline changed after GUI comparison")
    baseline=json.loads(baseline_path.read_text())
    config=result["config"]
    if baseline["config"]!=config:
        raise ValueError("Baseline and GUI configuration differ")
    fp=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
    figures={}
    figure_dir=root/"results/cadence_gui/figures"
    for kind,row in result["circuits"].items():
        plots._plots_one(kind,row,config["common"],figures,show=False,root=root,
            figures=figure_dir,config_fingerprint=fp,allow_partial=allow_partial)
    for name,bold in (("CBody",False),("CBold",True)):
        font=fm.findfont(fm.FontProperties(family="DejaVu Sans",weight="bold" if bold else "normal"))
        if name not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont(name,font))
    pdfmetrics.registerFontFamily("CBody",normal="CBody",bold="CBold",italic="CBody",boldItalic="CBold")
    ink=colors.HexColor("#17384A");teal=colors.HexColor("#126578")
    style={
        "body":ParagraphStyle("body",fontName="CBody",fontSize=9,leading=12.5,spaceAfter=7),
        "title":ParagraphStyle("title",fontName="CBold",fontSize=21,leading=25,textColor=ink,spaceAfter=11),
        "h2":ParagraphStyle("h2",fontName="CBold",fontSize=12,leading=16,textColor=teal,spaceAfter=7,spaceBefore=9),
        "small":ParagraphStyle("small",fontName="CBody",fontSize=7.4,leading=9.8,spaceAfter=5,splitLongWords=True),
        "th":ParagraphStyle("th",fontName="CBold",fontSize=8,leading=10,textColor=colors.white),
    }
    page_width,page_height=A4; margin=43; usable=page_width-2*margin
    def p(text,kind="body"):
        return Paragraph(escape(str(text)).replace("\n","<br/>"),style[kind])
    def value(x):
        if x is None:return "Not measured in GUI"
        if isinstance(x,bool):return "Yes" if x else "No"
        if isinstance(x,(float,int)):return f"{x:.4g}"
        if isinstance(x,(list,tuple)):return "["+", ".join(value(v) for v in x)+"]"
        if isinstance(x,dict):return "; ".join(str(k)+": "+value(v) for k,v in x.items())
        return str(x)
    def table(head,rows,widths=None):
        data=[[Paragraph(escape(str(v)),style["th"]) for v in head]]
        data.extend([[p(value(v),"small") for v in row] for row in rows])
        t=Table(data,colWidths=widths or [usable/len(head)]*len(head),repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),ink),
            ("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),6),
            ("RIGHTPADDING",(0,0),(-1,-1),6),("TOPPADDING",(0,0),(-1,-1),4),
            ("BOTTOMPADDING",(0,0),(-1,-1),4),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F0F5F6")])]))
        return t
    story=[]
    def title(text):story.append(p(text,"title"))
    def figure(path,height=265):
        from reportlab.lib.utils import ImageReader
        w,h=ImageReader(str(path)).getSize();scale=min(usable/w,height/h)
        story.append(Image(str(path),width=w*scale,height=h*scale))
    def measured(data,kind,key):
        metrics=data.get("circuits",{}).get(kind,{}).get("metrics",{})
        if key in metrics:return metrics[key]
        gain_key={"conversion_loss_db":"voltage_gain_db","power_conversion_loss_db":"power_gain_db"}.get(key)
        return -metrics[gain_key] if gain_key and metrics.get(gain_key) is not None else None
    def quantity(kind,key,unit=""):
        found=measured(result,kind,key)
        return value(found)+(str(" "+unit) if found is not None and unit else "")
    def native_figure(spec,height):
        source=root/spec["source_audit"]
        if hashlib.sha256(source.read_bytes()).hexdigest()!=spec["source_sha256"]:
            raise ValueError("Native schematic audit changed after local source rendering")
        for auxiliary in spec.get("auxiliary_source_audits",[]):
            if hashlib.sha256((root/auxiliary["source"]).read_bytes()).hexdigest()!=auxiliary["sha256"]:
                raise ValueError("Native arc/source metadata changed after local rendering")
        figure(root/spec["image_path"],height=height)
        story.append(p(spec["rendering_description"],"small"))

    common=config["common"]
    title("HW09: Single-balanced mixer design")
    story.append(p("Active and passive single-balanced downconversion mixers at 5.8 GHz RF, 5.6 GHz LO, and 200 MHz IF. The primary measurements in this report come from native Virtuoso schematic testbenches launched through the ADE GUI. The earlier Python-generated-netlist campaign is retained separately as a comparison baseline."))
    lo_legs=[config[k]["lo_vpp_per_leg"] for k in ("active","passive")]
    compliance=all(0<v<1 and 2*v<1 for v in lo_legs) and common["vdd_v"]==1
    story.append(table(["Assignment constraint","Implemented schematic condition"],[
        ["Technology / supply","NCSU 45 nm CMOS; VDD="+value(common["vdd_v"])+" V; installed minimum L=50 nm"],
        ["RF / LO / IF",value(common["rf_hz"]/1e9)+" / "+value(common["lo_hz"]/1e9)+" GHz / "+value(common["if_hz"]/1e6)+" MHz"],
        ["LO swing strictly below 1 Vpp","Per leg active/passive="+value(lo_legs)+" Vpp; differential="+value([2*v for v in lo_legs])+" Vpp; "+("compliant" if compliance else "check required")],
        ["Loading / source",value(config["active"]["rd_ohm"])+" ohm active and "+value(config["passive"]["rl_ohm"])+" ohm passive per branch; CL="+value(common["load_cap_f"]*1e15)+" fF each; Rs="+value(common["rs_ohm"])+" ohm"],
        ["GUI campaign",result["status"]+"; HW09_Mixers native schematics; figures rendered locally"],
    ],[usable*.32,usable*.68]))
    if result["status"]!="complete":
        story.append(p("DIAGNOSTIC REPORT: incomplete GUI stages remain explicitly marked. Baseline measurements do not substitute for absent GUI measurements.","h2"))
    metrics=[("voltage_gain_db","Source-open differential voltage gain (dB)"),
        ("conversion_loss_db","Voltage conversion loss (dB)"),
        ("power_gain_db","Transducer power gain (dB)"),
        ("power_conversion_loss_db","Transducer power conversion loss (dB)"),("ssb_nf_db","Loaded SSB NF (dB)"),
        ("dsb_nf_db","Loaded DSB NF (dB)"),("iip3_dbm","Input IIP3, worst product (dBm/tone)"),
        ("p1db_dbm","Input P1dB bracket midpoint (dBm)"),("power_mw","Core DC power (mW)")]
    story.append(p("Measured comparison","h2"))
    rows=[]
    for key,label in metrics:
        rows.append([label]+[value(measured(data,kind,key))
            for kind in ("active","passive") for data in (result,baseline)])
    story.append(table(["Metric","Active GUI","Active Python","Passive GUI","Passive Python"],rows,
                 [usable*.38]+[usable*.155]*4))
    story.append(p("Voltage gain uses the 50-ohm source open-circuit voltage. Power gain uses the total signal power in both physical 500-ohm branch resistors. Loaded NF includes those branch resistors; no extra output termination is introduced. Passive zero core DC power excludes the external ideal LO driver.","small"))
    tradeoff=("The active GUI circuit gives "+quantity("active","voltage_gain_db","dB")+
        " voltage gain and "+quantity("active","power_gain_db","dB")+" power gain at "+quantity("active","power_mw","mW")+
        " core power. The passive GUI circuit has "+quantity("passive","conversion_loss_db","dB")+
        " voltage conversion loss and "+quantity("passive","power_conversion_loss_db","dB")+
        " transducer power loss; its reported core DC power excludes the LO generator. Loaded SSB NF is "+
        quantity("active","ssb_nf_db","dB")+" active versus "+quantity("passive","ssb_nf_db","dB")+" passive.")
    for key,label in (("iip3_dbm","IIP3"),("p1db_dbm","input P1dB")):
        av=measured(result,"active",key);pv=measured(result,"passive",key)
        if av is not None and pv is not None:
            winner="active" if av>pv else "passive" if pv>av else "neither"
            tradeoff+=" Measured "+label+" is "+value(av)+" / "+value(pv)+" dBm (active/passive); "+winner+" has the higher value."
    story.append(p(tradeoff,"small"))
    screen=baseline.get("design_selection",{})
    candidates=screen.get("rows",[]) if isinstance(screen,dict) else []
    if candidates:
        story.append(PageBreak());title("Bias choice and bounded design screening")
        story.append(p("The fixed schematic values were chosen using the earlier standalone Python-netlist screen below. These rows explain the design choice; they are not new GUI measurements. The final schematic/ADE results are reported separately in the measured comparison."))
        if screen.get("scope"):story.append(p(screen["scope"],"small"))
        compact=[]
        selected=([r for r in candidates if r.get("selected")]+[r for r in candidates if not r.get("selected")])[:4]
        for candidate in selected:
            label=candidate["circuit"].capitalize()+"; "+("selected" if candidate.get("selected") else "comparison")
            if candidate["circuit"]=="active":label+="; Wgm/Wsw="+value(candidate.get("gm_width_um"))+"/"+value(candidate.get("switch_width_um"))+" um; RF bias="+value(candidate.get("rf_bias_v"))+" V"
            else:label+="; Wsw="+value(candidate.get("switch_width_um"))+" um"
            compact.append([label,value(candidate.get("lo_common_mode_v")),value(candidate.get("voltage_gain_db")),value(candidate.get("power_mw")),value(candidate["ssb_nf_db"]) if candidate.get("ssb_nf_db") is not None else "Not screened",value(candidate["iip3_dbm"]) if candidate.get("iip3_dbm") is not None else "Not screened"])
        story.append(table(["Earlier screening candidate","LO CM (V)","Voltage gain (dB)","Pdc (mW)","SSB NF (dB)","IIP3 (dBm)"],compact,
                           [usable*.36,usable*.12,usable*.13,usable*.12,usable*.13,usable*.14]))
        for candidate in selected:
            if candidate.get("selected") and candidate.get("reason"):
                story.append(p(candidate["circuit"].capitalize()+" choice: "+candidate["reason"],"small"))
        story.append(p("The active choice balances transconductor gm, core current and switching headroom. Increasing RF gate bias or width can increase gm and current but reduce voltage margin across the stacked devices. Passive LO common mode trades switch conduction against simultaneous conduction and parasitic feedthrough. This bounded screen establishes a reproducible candidate, not a global optimum."))
    source_figures=result.get("native_schematic_figures",[])
    for kind in ("active","passive"):
        row=result["circuits"][kind];params=config[kind]
        story.append(PageBreak());title(kind.capitalize()+" native schematic")
        images=[s for s in source_figures if s["kind"]==kind]
        if not images and not allow_partial:
            raise ValueError("Missing actual native schematic source figure for "+kind)
        topology=("M1 converts the single-ended RF gate voltage into current. M2 and M3 steer that shared current with complementary LO phases, and R1/R2 return to the 1 V supply to convert IF current into differential voltage. There is no additional tail current source below M1."
                  if kind=="active" else "Two NMOS switches share the single-ended RF source node. Complementary LO gates commutate the input to separate outp/outn drains. Each RL resistor returns to ground, providing a differential IF output without a core DC supply.")
        story.append(p(topology))
        core=next((spec for spec in images if "core" in Path(spec["image_path"]).stem),images[0] if images else None)
        if core:native_figure(core,240)
        devs=([("M1",params["gm_width_um"],"tail / rf / 0 / 0"),
               ("M2",params["switch_width_um"],"outp / lop / tail / 0"),
               ("M3",params["switch_width_um"],"outn / lon / tail / 0")]
              if kind=="active" else [("M1",params["switch_width_um"],"outp / lop / rf / 0"),
                                        ("M2",params["switch_width_um"],"outn / lon / rf / 0")])
        story.append(table(["MOS","W (um)","L (nm)","m","Drain / gate / source / body"],
             [[name,width,params["length_nm"],1,nets] for name,width,nets in devs],
             [usable*.10,usable*.13,usable*.13,usable*.08,usable*.56]))
        story.append(table(["Testbench value","Value"],[
            ["MOS cell","NCSU_Devices_FreePDK45 / NMOS_VTH / symbol"],
            ["Bodies","Ground for every NMOS; schematic gnd! netlists as node 0"],
            ["Each R1/R2 branch resistor",value(params["rd_ohm" if kind=="active" else "rl_ohm"])+" ohm to "+("VDD" if kind=="active" else "ground")],
            ["Each CLP/CLN output capacitor",value(common["load_cap_f"]*1e15)+" fF to ground"],
            ["RF source bias",str(params["rf_bias_v" if kind=="active" else "rf_common_mode_v"])+" V"],
            ["LO common mode",str(params["lo_common_mode_v"])+" V"],
            ["Each LO sine amplitude","0.2 Vpk; 0.4 Vpp; opposite sine phases 0/180 degrees"],
            ["Differential LO swing","0.8 Vpp"],
        ],[usable*.36,usable*.64]))
        story.append(p("CGS/CGD are intrinsic BSIM4 parasitics. The separate CLP/CLN loads are explicit schematic elements. The installed PDK minimum L is 50 nm; multiplier is 1 and no finger-count CDF field is required.","small"))
        others=[spec for spec in images if spec is not core]
        for spec in others:
            story.append(PageBreak());title(kind.capitalize()+" complete native testbench")
            native_figure(spec,370)
            story.append(p("All source and load instances shown here belong to the actual saved native testbench. RFPORT includes the only 50-ohm source resistance. RFSECOND is the series second-tone voltage source and becomes a zero-volt connection in the single-tone/noise configurations. The exact source fields and amplitude convention are listed later in this report."))
            story.append(table(["Native instance","Settable CDF fields / values"],[
                ["RFPORT","r=50; num=1; srcType=sine; vdc="+value(params["rf_bias_v" if kind=="active" else "rf_common_mode_v"]/2)+" V; pacm=0.5; noisetemp=16.85 C"],
                ["LOP / LON","srcType=sine; vdc="+value(params["lo_common_mode_v"])+" V; va=0.2 Vpk; freq=5.6G; sinephase=0 / 180"],
                ["RF controls","pinDbm is available input power per tone; fRF/fRF2 set frequency; rfScale/tone2Scale enable the two RF sinusoids"],
            ],[usable*.23,usable*.77]))
        story.append(PageBreak());title(kind.capitalize()+" GUI transient and spectra")
        for suffix in ("transient","spectrum"):
            key=kind+"_"+suffix
            if key in figures:figure(figures[key],height=270)
        story.append(p("Raw differential output includes LO feedthrough. The separately labeled 200 MHz component is a coherent Fourier reconstruction from the actual GUI-run samples. FFT amplitudes do not establish a stochastic noise floor.","small"))
        story.append(PageBreak());title(kind.capitalize()+" measured bias and headroom")
        single=row.get("single_tone",{});window=row.get("window_convergence",{});reference=window.get("reference",{})
        headroom=[("Mean RF node (V)",single.get("mean_rf_v")),
                  ("Mean outp / outn (V)",[single.get("mean_outp_v"),single.get("mean_outn_v")]),
                  ("Output minimum / maximum (V)",[single.get("min_output_v"),single.get("max_output_v")]),
                  ("Measured differential LO swing (Vpp)",single.get("lo_diff_vpp")),
                  ("Mean core power (mW)",single.get("power_mw"))]
        if kind=="active":headroom.append(("Tail minimum / mean / maximum (V)",[single.get("tail_min_v"),single.get("tail_mean_v"),single.get("tail_max_v")]))
        story.append(table(["Settled GUI transient quantity","Measured value"],headroom,[usable*.55,usable*.45]))
        story.append(p("These values are measured over the settled LO-driven trace. A static DC operating point does not establish transistor region throughout commutation. Inspect the measured tail/output extrema rather than assuming every device remains in saturation. Capacitive feedthrough can briefly move an output beyond its supply rail.","small"))
        story.append(p("Coherent-window cross-check","h2"))
        story.append(table(["Window check","GUI evidence"],[
            ["Status",window.get("status")],
            ["Short settle / window / sample count",[single.get("settle_s"),single.get("window_s"),single.get("sample_count")]],
            ["Reference settle / window / sample count",[reference.get("settle_s"),reference.get("window_s"),reference.get("sample_count")]],
            ["Reference-minus-short gain (dB)",window.get("gain_delta_db")],
            ["Allowed gain difference (dB)",window.get("tolerance_db")],
            ["Effective reltol / maxstep, single run",[single.get("psf_header_reltol"),single.get("psf_header_maxstep")]],
        ],[usable*.55,usable*.45]))
        story.append(PageBreak());title(kind.capitalize()+" GUI linearity")
        for suffix in ("compression","iip3"):
            key=kind+"_"+suffix
            if key in figures:figure(figures[key],height=210)
        lin=row.get("linearity",{});cube=lin.get("cubic_region",{})
        convergence=lin.get("convergence") or {}
        story.append(table(["Check","GUI evidence"],[
            ["Linearity status",lin.get("status")],["Measured P1dB bracket",lin.get("p1db_bracket_dbm")],
            ["Accepted input powers",cube.get("pins_dbm")],
            ["Fundamental slopes",cube.get("fundamental_slopes")],
            ["IM3 slopes",cube.get("im3_slopes")],
            ["Minimum IM3 / empty-bin margin (dB)",cube.get("minimum_im3_to_empty_bin_margin_db")],
            ["Tighter-repeat IIP3 change (dB)",convergence.get("delta_db")],
            ["Effective reltol, normal / repeat",[convergence.get("effective_reltol_normal"),convergence.get("effective_reltol_tight")]],
            ["Effective maxstep (s), normal / repeat",[convergence.get("effective_maxstep_normal_s"),convergence.get("effective_maxstep_tight_s")]],
            ["Convergence check passed",convergence.get("passed")],
        ],[usable*.38,usable*.62]))
        story.append(PageBreak());title(kind.capitalize()+" GUI periodic noise")
        if kind+"_noise" in figures:figure(figures[kind+"_noise"],height=285)
        noise=row.get("noise",{})
        noise_native=noise.get("native_checks",{});noise_convergence=noise.get("convergence",{})
        story.append(table(["Check","GUI evidence"],[
            ["Noise status",noise.get("status")],["Source / circuit temperature","290 K / 27 C"],
            ["PSS reference setup","LO only, 5.6 GHz, 5 ns tstab, shooting, conservative, gear2only"],
            ["PAC","Matched-port magnitude 0.5 V = 1 V open circuit; output sideband -1"],
            ["PNOISE output / source","outp-outn; RFPORT; no external output probe"],
            ["SSB reference sideband","+1; desired RF=LO+IF"],
            ["Native SSB / DSB agreement (dB)",[noise_native.get("max_ssb_delta_db"),noise_native.get("max_dsb_delta_db")]],
            ["Noise sideband counts",noise_convergence.get("sidebands")],
            ["Last SSB sideband change (dB)",noise_convergence.get("last_ssb_delta_db")],
            ["Last DSB sideband change (dB)",noise_convergence.get("last_dsb_delta_db")],
            ["Noise convergence passed",noise_convergence.get("passed")],
        ],[usable*.38,usable*.62]))
    story.append(PageBreak());title("Exact source and measurement conventions")
    story.append(table(["Property","RF port","Ideal vsource + one 50-ohm resistor"],[
        ["RF amplitude at -55 dBm","0.000562341325190349 Vpk","0.001124682650380698 Vpk"],
        ["Active source DC","0.325 V entered","0.65 V entered"],
        ["Passive source DC","0 V","0 V"],["PAC source","0.5 V entered","1 V entered"],
        ["Noise source","Port noise at 16.85 C","Resistor thermal noise at 290 K"],
    ],[usable*.32,usable*.34,usable*.34]))
    story.append(p("At each sweep point use Vopen,pk = sqrt(8 Rs x 0.001 x 10^(Pin/10)), per tone. Single-tone RF is 5.8 GHz. Equal two-tone inputs are 5.79 and 5.81 GHz, yielding IF fundamentals 190/210 MHz and IM3 170/230 MHz. Keep exactly one 50-ohm source resistance."))
    story.append(p("The normal single-tone window is 5 ns settling plus 20 ns measurement at 5 ps strobes (4000 samples); compare with a 20 ns / 100 ns reference. Two-tone tests use 20 ns settling plus 100 ns measurement (20000 samples). Declared global settings are maxstep=2 ps and reltol=1e-5; the repeat halves maxstep and declares reltol=1e-6. The conservative analysis preset can override the global relative tolerance. Actual effective relative tolerances and maximum steps are read from each PSF header and reported with the convergence evidence; do not infer tenfold effective tolerance tightening from the global option alone."))
    story.append(table(["Output IF (MHz)","Desired RF (GHz)","Image RF (GHz)"],
        [[100,5.7,5.5],[200,5.8,5.4],[300,5.9,5.3]]))
    story.append(PageBreak());title("Source and run provenance")
    provenance=[
        ["Native library / views","HW09_Mixers / active_tb and passive_tb / schematic"],
        ["Actual-run manifest",result["source_manifest"]],
        ["Configuration SHA-256",fp],
        ["Actual manifest SHA-256",result["source_manifest_sha256"]],
        ["Immutable Python baseline SHA-256",result["baseline"]["sha256"]],
        ["GUI result JSON SHA-256",hashlib.sha256(result_path.read_bytes()).hexdigest()],
    ]
    for kind,row in result["circuits"].items():
        records=row.get("runs",[])
        counts=Counter(run["stage"] for run in records)
        inventory=", ".join(stage+"="+str(count) for stage,count in sorted(counts.items()))
        provenance.append([kind.capitalize()+" measurement records",inventory or "No actual records"])
        observed=sorted({run["gui_action_utc"] for run in records})
        if observed:
            provenance.append([kind.capitalize()+" observed GUI Run UTC",observed[0] if len(observed)==1 else observed[0]+" to "+observed[-1]])
        exports={run["schematic_export_sha256"] for run in records}
        if exports:provenance.append([kind.capitalize()+" native audit SHA-256","\n".join(sorted(exports))])
    story.append(table(["Evidence","Recorded value"],provenance,[usable*.36,usable*.64]))
    story.append(p("Every imported record retains its actual Spectre log, ADE-generated input.scs, raw PSF hash, native OA audit, and observed GUI launch record in results/cadence_gui_results.json. Several analyses may share one physical native job; the inventory counts measurement records, not automatically distinct simulator launches. Native source geometry and exact arc audits are retained under cadence/. Full paths and per-file hashes remain machine-readable there, keeping this appendix compact.","small"))
    story.append(p("The GUI action was observed and recorded by the operator. A manifest label alone cannot prove an action that was not observed. All numerical plots are regenerated locally; no remote plot images are imported.","small"))
    story.append(p("Scope: nominal schematic-level NCSU 45 nm devices with ideal external LO/bias sources. Layout parasitics, corners, Monte Carlo, and LO-driver noise/power are outside this comparison. Static bias does not establish device region over the complete LO cycle.","small"))
    story.append(p("Sources: HW9_Mixer_design.pdf; B. Razavi, RF Microelectronics, second edition, Chapter 6, Figures 6.15(b) and 6.42; the actual native OA schematic audits, saved ADE state, generated netlists and simulation logs in this HW09 project. The earlier standalone screen is explicitly labeled and never substitutes for absent GUI results.","small"))
    destination=Path(output or root/"output/pdf/HW09_mixer_design_report.pdf")
    destination.parent.mkdir(parents=True,exist_ok=True)
    def page(canvas,doc):
        canvas.setFont("CBody",7);canvas.setFillColor(colors.HexColor("#61737C"))
        canvas.drawString(margin,page_height-26,"ECE6420 / HW09 - Native schematic and ADE GUI verification")
        canvas.drawString(margin,25,"Numerical figures rendered locally from actual schematic-run data")
        canvas.drawRightString(page_width-margin,25,str(doc.page))
    doc=SimpleDocTemplate(str(destination),pagesize=A4,leftMargin=margin,rightMargin=margin,
                         topMargin=45,bottomMargin=43,title="HW09 - Single-balanced mixer design with native ADE results")
    doc.build(story,onFirstPage=page,onLaterPages=page)
    return destination


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",required=True,type=Path)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--allow-partial",action="store_true",help="Explicit diagnostic report only")
    args=parser.parse_args()
    print(build(args.root,args.output,args.allow_partial))
