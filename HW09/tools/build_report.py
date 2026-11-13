#!/usr/bin/env python3
"""Build the local English HW09 circuit-rebuild and simulation report.

The report consumes real result metadata and locally rendered figures. It never
runs Spectre, edits remote files, or substitutes missing measurements.
"""
from __future__ import annotations
import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import sys
from xml.sax.saxutils import escape

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"lib"))
from plots import load_results,plot_results
from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate,PageTemplate,Frame,Flowable,
    Paragraph,Spacer,PageBreak,Image,Table,TableStyle,KeepTogether)
import matplotlib.font_manager as fm

NAVY=colors.HexColor("#17384A");TEAL=colors.HexColor("#126578")
RUST=colors.HexColor("#B7642E");INK=colors.HexColor("#263741")
GRAY=colors.HexColor("#61737C");PALE=colors.HexColor("#F0F5F6")
LINE=colors.HexColor("#CFDADD");WARN=colors.HexColor("#9B4231")
W,H=A4;M=44;CW=W-2*M


def fonts():
    for name,bold in [("Body",False),("Bold",True)]:
        path=fm.findfont(fm.FontProperties(family="DejaVu Sans",weight="bold" if bold else "normal"))
        if name not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont(name,path))
    pdfmetrics.registerFontFamily("Body",normal="Body",bold="Bold",italic="Body",boldItalic="Bold")


def p(text,kind="body"):
    return Paragraph(text,STYLES[kind])


def safe(value):
    return escape(str(value)).replace("\n","<br/>")


def display(value,unit="",digits=4):
    if value is None:return "Not recorded"
    if isinstance(value,bool):return "Yes" if value else "No"
    if isinstance(value,(float,int)):
        if abs(value)>0 and (abs(value)<1e-3 or abs(value)>=1e7):text=f"{value:.{digits}g}"
        else:text=f"{value:.{digits}f}".rstrip("0").rstrip(".") if isinstance(value,float) else str(value)
    elif isinstance(value,(list,tuple)):text="["+", ".join(display(item,digits=digits) for item in value)+"]"
    elif isinstance(value,dict):text="; ".join(str(key)+": "+display(item,digits=digits) for key,item in value.items())
    else:text=str(value)
    return text+(" "+unit if unit else "")


def source_voltage(value,unit="V peak"):
    return "Not recorded" if value is None else f"{value:.10g} {unit}"


def pick(data,*names):
    for name in names:
        if name in data and data[name] is not None:return data[name]
    return None


def params(result,name):
    return {**result.get("config",{}).get(name,{}),**result.get("circuits",{}).get(name,{}).get("parameters",{})}


def table(headers,rows,widths=None,small=False,padding=5):
    content=[[p(safe(x),"table_head") for x in headers]]
    content.extend([[p(safe(display(x)),"small" if small else "table") for x in row] for row in rows])
    t=Table(content,colWidths=widths or [CW/len(headers)]*len(headers),repeatRows=1,hAlign="LEFT")
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),NAVY),
        ("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),7),
        ("RIGHTPADDING",(0,0),(-1,-1),7),("TOPPADDING",(0,0),(-1,-1),padding),
        ("BOTTOMPADDING",(0,0),(-1,-1),padding),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,PALE]),
        ("LINEBELOW",(0,0),(-1,0),.6,NAVY),
        ("LINEBELOW",(0,-1),(-1,-1),.5,LINE)]))
    return t


def heading(title,kicker=None):
    out=[]
    if kicker:out.append(p(safe(kicker.upper()),"kicker"))
    out += [p(safe(title),"h1"),Spacer(1,9)]
    return out


class Circuit(Flowable):
    """Native PDF vector schematic with explicit terminal/node labels."""
    def __init__(self,kind,load_cap_f=0):super().__init__();self.kind=kind;self.load_cap_f=load_cap_f;self.width=CW;self.height=236
    def draw(self):
        c=self.canv;c.saveState();c.setLineWidth(1.15);c.setStrokeColor(INK);c.setFillColor(INK)
        c.setFont("Body",8.4)
        def wire(points):
            path=c.beginPath();path.moveTo(*points[0])
            for pt in points[1:]:path.lineTo(*pt)
            c.drawPath(path)
        def dot(x,y):c.circle(x,y,2,stroke=0,fill=1)
        def ground(x,y):
            c.line(x,y,x,y-5)
            for width,dy in [(14,5),(9,8),(4,11)]:c.line(x-width/2,y-dy,x+width/2,y-dy)
        def resistor(x,y1,y2,label):
            mid=(y1+y2)/2;wire([(x,y1),(x,mid+12)])
            wire([(x,mid+12),(x-4,mid+9),(x+4,mid+5),(x-4,mid+1),(x+4,mid-3),(x-4,mid-7),(x,mid-12),(x,y2)])
            c.drawString(x+10,mid-2,label)
        def capacitor(x,top,label,side="right"):
            c.line(x,top,x,top-12);c.line(x-7,top-12,x+7,top-12)
            c.line(x-7,top-17,x+7,top-17);c.line(x,top-17,x,top-29)
            ground(x,top-29);c.setFont("Body",7)
            value=display(self.load_cap_f*1e15,"fF")
            if side=="left":
                c.drawRightString(x-10,top-14,label);c.drawRightString(x-10,top-24,value)
            else:
                c.drawString(x+11,top-14,label);c.drawString(x+11,top-24,value)
            c.setFont("Body",8.4)
        def mos(x,y,label,side="left"):
            sign=-1 if side=="left" else 1
            c.line(x,y-13,x,y+13);c.line(x,y+13,x,y+26);c.line(x,y-13,x,y-26)
            c.line(x+sign*10,y-11,x+sign*10,y+11);c.line(x+sign*10,y,x+sign*29,y)
            # Body contact is explicit in the wiring table; all bulks are zero.
            c.setFont("Bold",9);c.drawString(x+(17 if side=="left" else -31),y+2,label)
            c.setFont("Body",7);c.drawString(x+(17 if side=="left" else -38),y-10,"B = 0")
            c.setFont("Body",8.4)
        if self.kind=="active":
            xl,xr,xc=143,352,247.5
            wire([(xl,217),(xr,217)]);c.setFont("Bold",9);c.drawCentredString(xc,224,"VDD");c.setFont("Body",8.4)
            resistor(xl,217,164,"R1 = RD");resistor(xr,217,164,"R2 = RD")
            wire([(xl,164),(xl,145)]);wire([(xr,164),(xr,145)])
            wire([(xl,159),(xl-47,159)]);wire([(xr,159),(xr+47,159)])
            dot(xl,159);dot(xr,159)
            c.drawRightString(xl-50,156,"outp (X)");c.drawString(xr+50,156,"outn (Y)")
            if self.load_cap_f:
                wire([(xl,159),(203,159)]);capacitor(203,159,"CLP","left")
                wire([(xr,159),(294,159)]);capacitor(294,159,"CLN")
            mos(xl,119,"M2");mos(xr,119,"M3","right")
            c.drawRightString(xl-34,116,"LO+");c.drawString(xr+34,116,"LO-")
            wire([(xl,93),(xl,82),(xr,82),(xr,93)]);dot(xc,82)
            c.drawString(xc+9,83,"tail")
            mos(xc,51,"M1");wire([(xc,77),(xc,82)])
            c.drawRightString(xc-34,48,"RF + gate bias")
            ground(xc,25)
            c.setFont("Body",8);c.setFillColor(GRAY)
            c.drawCentredString(CW/2,1,"Differential output: VIF = V(outp) - V(outn). No additional tail current source.")
        else:
            xleft,xswitch,xout=99,235,365;ytop,ybottom=170,73
            wire([(xleft,ytop),(xleft,ybottom)]);dot(xleft,121)
            wire([(xleft-57,121),(xleft,121)])
            c.drawRightString(xleft-61,118,"RF node")
            for yy,label,lo,out in [(ytop,"M1","LO+","outp"),(ybottom,"M2","LO-","outn")]:
                # Horizontal source/drain channel; gate sits above it.
                wire([(xleft,yy),(xswitch-24,yy)]);wire([(xswitch+24,yy),(xout,yy)])
                c.line(xswitch-13,yy,xswitch+13,yy)
                c.line(xswitch-24,yy,xswitch-13,yy);c.line(xswitch+13,yy,xswitch+24,yy)
                c.line(xswitch-11,yy+10,xswitch+11,yy+10);c.line(xswitch,yy+10,xswitch,yy+31)
                c.drawCentredString(xswitch,yy+38,lo)
                c.setFont("Bold",9);c.drawCentredString(xswitch,yy-17,label);c.setFont("Body",8.4)
                c.drawCentredString(xswitch,yy-29,"B = 0")
                dot(xout,yy);wire([(xout,yy),(xout+45,yy)]);c.drawString(xout+50,yy+4,out)
                resistor(xout,yy,yy-43,"RL");ground(xout,yy-43)
                if self.load_cap_f:
                    wire([(xout,yy),(452,yy)]);capacitor(452,yy,"CLP" if out=="outp" else "CLN")
            c.setFont("Body",8);c.setFillColor(GRAY)
            c.drawCentredString(CW/2,7,"Drain = output, source = shared RF node; both RL resistors return to ground.")
        c.restoreState()


def header_footer(canvas,doc):
    canvas.saveState();canvas.setStrokeColor(LINE);canvas.setLineWidth(.6)
    canvas.line(M,H-36,W-M,H-36);canvas.line(M,36,W-M,36)
    canvas.setFillColor(GRAY);canvas.setFont("Bold",8)
    canvas.drawString(M,H-27,"ECE6420  /  HW09")
    canvas.setFont("Body",7.7);canvas.drawRightString(W-M,H-27,"Single-balanced downconversion mixers")
    canvas.drawString(M,24,"Spectre netlist study and Virtuoso rebuild guide")
    canvas.drawRightString(W-M,24,str(doc.page));canvas.restoreState()


def add_image(story,path,caption,max_height=290):
    if not path:return
    reader=ImageReader(path);iw,ih=reader.getSize();scale=min(CW/iw,max_height/ih)
    story += [Image(path,width=iw*scale,height=ih*scale,hAlign="CENTER"),Spacer(1,4),p(safe(caption),"caption"),Spacer(1,9)]


def device_rows(result,name):
    q=params(result,name)
    length=pick(q,"length_nm","l_nm","mos_length_nm")
    nf=pick(q,"nf","fingers");mult=pick(q,"m","multiplier")
    if name=="active":
        wg=pick(q,"gm_width_um","gm_w_um","w_gm_um","w1_um")
        ws=pick(q,"switch_width_um","switch_w_um","w_switch_um","ws_um")
        return [["M1",display(wg,"um"),display(length,"nm"),nf if nf is not None else 1,mult if mult is not None else 1,"tail / rf / 0 / 0"],
                ["M2",display(ws,"um"),display(length,"nm"),nf if nf is not None else 1,mult if mult is not None else 1,"outp / lop / tail / 0"],
                ["M3",display(ws,"um"),display(length,"nm"),nf if nf is not None else 1,mult if mult is not None else 1,"outn / lon / tail / 0"]]
    ws=pick(q,"switch_width_um","switch_w_um","w_switch_um","ws_um")
    return [["M1",display(ws,"um"),display(length,"nm"),nf if nf is not None else 1,mult if mult is not None else 1,"outp / lop / rf / 0"],
            ["M2",display(ws,"um"),display(length,"nm"),nf if nf is not None else 1,mult if mult is not None else 1,"outn / lon / rf / 0"]]


def noise_summary(evidence):
    conv=evidence.get("convergence",{});checks=evidence.get("native_checks",{})
    def largest(key):
        value=conv.get(key)
        return max(abs(float(x)) for x in value) if value else None
    return [
      ("Stage status",evidence.get("status")),
      ("Output probe / loading",str(evidence.get("output_probe","Not recorded"))+"; intrinsic load resistors included, no external output load"),
      ("SSB / DSB definition",evidence.get("definition")),
      ("Source temperature / circuit temperature",display(evidence.get("source_temperature_k"),"K")+" / "+display(evidence.get("circuit_temperature_c"),"C")),
      ("Source resistance / open-circuit PAC",display(evidence.get("source_resistance_ohm"),"ohm")+" / "+display(evidence.get("port_open_ac_v"),"V")),
      ("PNOISE reference sideband",evidence.get("refsideband")),
      ("Desired / image input frequency (Hz)",display(evidence.get("signal_input_frequency_hz"))+" / "+display(evidence.get("image_input_frequency_hz"))),
      ("Noise sideband counts",conv.get("sidebands")),
      ("Last SSB / DSB sideband change (dB)",display(largest("last_ssb_delta_db"))+" / "+display(largest("last_dsb_delta_db"))),
      ("Sideband tolerance / passed",display(conv.get("tolerance_db"),"dB")+" / "+display(conv.get("passed"))),
      ("Native SSB / DSB cross-check difference (dB)",display(checks.get("max_ssb_delta_db"))+" / "+display(checks.get("max_dsb_delta_db"))),
      ("PSS maximum small-signal frequency (Hz)",conv.get("pss_maxacfreq_hz")),
    ]


def build(root=None,output=None,render=True,allow_partial=False):
    base=Path(root or ROOT).resolve();result=load_results(base,allow_partial=allow_partial)
    fonts();global STYLES
    STYLES={
      "body":ParagraphStyle("body",fontName="Body",fontSize=9.5,leading=13.4,textColor=INK,spaceAfter=7),
      "h1":ParagraphStyle("h1",fontName="Bold",fontSize=22,leading=27,textColor=NAVY,spaceAfter=5),
      "h2":ParagraphStyle("h2",fontName="Bold",fontSize=12.2,leading=16,textColor=TEAL,spaceBefore=11,spaceAfter=6,keepWithNext=True),
      "kicker":ParagraphStyle("kicker",fontName="Bold",fontSize=8,leading=11,textColor=TEAL,spaceAfter=5),
      "small":ParagraphStyle("small",fontName="Body",fontSize=7.4,leading=10.2,textColor=INK,wordWrap="CJK"),
      "table":ParagraphStyle("table",fontName="Body",fontSize=8,leading=10.8,textColor=INK,wordWrap="CJK"),
      "table_head":ParagraphStyle("table_head",fontName="Bold",fontSize=8,leading=10.5,textColor=colors.white),
      "caption":ParagraphStyle("caption",fontName="Body",fontSize=7.7,leading=10.4,textColor=GRAY,spaceAfter=5),
      "callout":ParagraphStyle("callout",fontName="Bold",fontSize=10,leading=14,textColor=NAVY,backColor=PALE,borderPadding=10,spaceBefore=8,spaceAfter=13),
    }
    if render:
        figures=plot_results(root=base,show=False,allow_partial=allow_partial)
    else:
        manifest=json.loads((base/"results/figures/manifest.json").read_text())
        expected_fp=hashlib.sha256(json.dumps(result["config"],sort_keys=True).encode()).hexdigest()
        if manifest.get("run_id")!=result.get("run_id") or manifest.get("completed_utc")!=result.get("completed_utc") or manifest.get("config_fingerprint")!=expected_fp:
            raise ValueError("The saved figure manifest belongs to a different result revision. Regenerate local figures.")
        figures=manifest["figures"]
    report_path=Path(output or base/"output/pdf/HW09_python_baseline_report.pdf").resolve();report_path.parent.mkdir(parents=True,exist_ok=True)
    common=result.get("config",{}).get("common",{})
    circuits=result.get("circuits",{})
    status=result.get("status","not recorded")
    story=[]
    story += heading("Single-balanced mixer design","Python-driven Spectre study / schematic rebuild guide")
    story.append(p("Active and passive downconversion at 5.8 GHz RF, 5.6 GHz LO, and 200 MHz IF. The two circuits follow the user-selected textbook topologies. All plotted traces come from the recorded Spectre run; schematic drawings below are native vector diagrams.","body"))
    story.append(p("Run status: "+safe(status.upper())+". "+("Measured values below are simulation results, not hand-calculation targets." if status=="complete" else "Inspect pending or failed analyses before treating this report as a completed assignment."),"callout"))
    story += [table(["Specification / convention","Value"],[
        ["Supply",display(common.get("vdd_v"),"V")],
        ["RF / LO / nominal IF",f"{display(common.get('rf_hz',0)/1e9,'GHz')} / {display(common.get('lo_hz',0)/1e9,'GHz')} / {display(common.get('if_hz',0)/1e6,'MHz')}"],
        ["RF Thevenin resistance",display(common.get("rs_ohm"),"ohm")],
        ["Temperature",display(common.get("temp_c"),"C")],
        ["Source noise temperature",display(common.get("source_noise_temp_k"),"K")],
        ["Capacitance from each output to ground",display(common.get("load_cap_f",0)*1e15,"fF")]],widths=[CW*.43,CW*.57]),Spacer(1,12)]
    metric_rows=[]
    labels=[("voltage_gain_db","Source-referenced conversion gain","dB"),
        ("rf_node_gain_db","RF-node-referenced conversion gain","dB"),
        ("conversion_loss_db","Voltage conversion loss","dB"),
        ("power_gain_db","Transducer power conversion gain","dB"),
        ("power_conversion_loss_db","Transducer power conversion loss","dB"),
        ("ssb_nf_db","Single-sideband noise figure","dB"),
        ("dsb_nf_db","Double-sideband noise figure","dB"),
        ("iip3_dbm","Input IP3, per tone","dBm"),
        ("p1db_dbm","Input 1-dB compression point","dBm"),
        ("power_mw","Core DC power","mW")]
    for key,label,unit in labels:
        metric_rows.append([label]+[display(circuits.get(name,{}).get("metrics",{}).get(key),unit) for name in ("active","passive")])
    story += [p("Measured comparison","h2"),table(["Metric","Active","Passive"],metric_rows,widths=[CW*.54,CW*.23,CW*.23]),
              p("A missing value is labeled Not recorded. DSB NF is shown only when the image-sideband gain was evaluated with a matching definition. Passive core DC power excludes the external LO generator; LO-driver power is not implied to be zero.","caption")]
    screening=result.get("design_selection")
    if screening:
        candidate_rows=screening.get("rows",[]) if isinstance(screening,dict) else screening
        if candidate_rows:
            # Keep the selected designs visible even if many preliminary points
            # were retained in the machine-readable screening record.
            candidate_rows=([row for row in candidate_rows if row.get("selected")]+
                            [row for row in candidate_rows if not row.get("selected")])[:4]
            story.append(PageBreak());story += heading("Bounded design selection","Recorded candidate screening")
            story.append(p("The following table compares up to four recorded candidates under the stated source, load, frequency, and LO constraints. Candidate screening guided the choice of the two final circuits. The final selected circuits are characterized separately by the complete measurement campaign on the following pages."))
            if isinstance(screening,dict) and screening.get("method"):
                story.append(p(safe(screening["method"])))
            if isinstance(screening,dict) and screening.get("scope"):
                story.append(p(safe(screening["scope"]),"caption"))
            if isinstance(screening,dict):
                sw=screening.get("candidate_gain_window_s");tw=screening.get("candidate_iip3_window_s")
                story.append(p("Recorded screening: gain window = "+display(sw*1e9 if sw is not None else None,"ns")+"; IIP3 window = "+display(tw*1e9 if tw is not None else None,"ns")+"; gain-reference input = "+display(screening.get("input_power_dbm_per_tone"),"dBm per tone")+". N/S means not screened: that metric was not measured in the candidate screen.","caption"))
            selection=[]
            for row in candidate_rows:
                passive=str(row.get("circuit","")).lower()=="passive"
                selection.append([row.get("circuit","Not recorded"),("N/A" if passive else display(row.get("gm_width_um")))+" / "+display(row.get("switch_width_um")),
                    ("N/A" if passive else display(row.get("rf_bias_v")))+" / "+display(row.get("lo_common_mode_v")),
                    display(row.get("voltage_gain_db"),digits=3),display(row.get("power_mw"),digits=3),display(row["ssb_nf_db"],digits=3) if row.get("ssb_nf_db") is not None else "N/S",display(row["iip3_dbm"],digits=3) if row.get("iip3_dbm") is not None else "N/S",
                    display(row.get("selected",False)),row.get("reason","")])
            story.append(table(["Circuit","Wgm / Wsw (um)","RF bias / LO CM (V)","Gain (dB)","Pdc (mW)","SSB NF (dB)","IIP3 (dBm)","Use?","Reason"],selection,
                widths=[70,55,70,45,45,45,45,40,CW-415],small=True))
            story.append(p("Gain is source-referenced differential voltage conversion gain. Read the recorded candidate method and scope before comparing screening values with the final full-campaign metrics. The exact values to draw in Virtuoso are on the final circuit pages.","caption"))
            ma=circuits.get("active",{}).get("metrics",{});mp=circuits.get("passive",{}).get("metrics",{})
            if all(ma.get(k) is not None for k in ("voltage_gain_db","power_gain_db","power_mw","ssb_nf_db","iip3_dbm","p1db_dbm")) and all(mp.get(k) is not None for k in ("conversion_loss_db","power_conversion_loss_db","ssb_nf_db","iip3_dbm","p1db_dbm")):
                story.append(p("Measured comparison and tradeoffs","h2"))
                story.append(p("Active gain is "+display(ma["voltage_gain_db"],"dB")+" in voltage and "+display(ma["power_gain_db"],"dB")+" in power at "+display(ma["power_mw"],"mW")+" core power. Passive power conversion loss is "+display(mp["power_conversion_loss_db"],"dB")+"; its zero core DC power excludes the LO driver. Active/passive SSB NF is "+display(ma["ssb_nf_db"],"dB")+" / "+display(mp["ssb_nf_db"],"dB")+", and IIP3 is "+display(ma["iip3_dbm"],"dBm")+" / "+display(mp["iip3_dbm"],"dBm")+". P1dB is "+display(ma["p1db_dbm"],"dBm")+" / "+display(mp["p1db_dbm"],"dBm")+", so compression and intermodulation merit separate checks. The bounded active choice improves gain, power, NF and IIP3; the lower passive LO common mode reduces unwanted simultaneous conduction in the recorded screen."))
    for name in ("active","passive"):
        entry=circuits.get(name,{});q=params(result,name)
        story.append(PageBreak());story += heading(name.capitalize()+" circuit and exact values","Build this circuit in Virtuoso")
        model=pick(q,"device_model","model_name") or pick(result.get("environment",{}),"device_model","model_name","device") or "NMOS_VTH"
        story += [p("MOS model: <b>"+safe(model)+"</b>. Use one unfingered instance. Set Width (w), Length (l), and Multiplier (m); the nf = 1 column is an assumption, not a separate GUI field.","caption"),
                  Circuit(name,common.get("load_cap_f",0)),Spacer(1,7),table(["MOS","W","L","nf","m","Drain / gate / source / bulk"],device_rows(result,name),widths=[35,48,45,25,25,CW-178],small=True),Spacer(1,10)]
        if name=="active":
            notes="M1 converts RF voltage to current and sets the branch bias through its gate DC voltage. M2 and M3 steer the shared current. Use the model's four-terminal NMOS symbol; do not add a separate tail current source below M1. R1 and R2 connect to VDD."
            selected=[("Load resistance, each",pick(q,"rd_ohm","load_ohm"),"ohm"),("M1 RF gate bias",pick(q,"rf_bias_v","gate_bias_v"),"V")]
        else:
            notes="The two sources share the RF node. Drain nodes are separate differential IF outputs, each terminated by RL to ground. LO+ and LO- drive opposite gates. The reference drawing's CGS and CGD labels represent intrinsic MOS parasitics already included in the NCSU BSIM4 model; do not place additional CGS/CGD capacitors. CLP and CLN are different: they are explicit output testbench loads from outp/outn to ground and must be reproduced."
            selected=[("Load resistance, each",pick(q,"rl_ohm","load_ohm"),"ohm"),("RF common-mode voltage",pick(q,"rf_common_mode_v","rf_bias_v"),"V")]
        selected += [("LO common-mode voltage",pick(q,"lo_common_mode_v","lo_cm_v"),"V"),
                     ("LO swing, per leg",pick(q,"lo_vpp_per_leg","lo_per_leg_vpp","lo_vpp_leg"),"Vpp"),
                     ("LO differential swing",pick(q,"lo_differential_vpp","lo_diff_vpp") if pick(q,"lo_differential_vpp","lo_diff_vpp") is not None else (2*q['lo_vpp_per_leg'] if q.get('lo_vpp_per_leg') is not None else None),"Vpp")]
        lo_amplitude=q["lo_vpp_per_leg"]/2 if q.get("lo_vpp_per_leg") is not None else None
        selected += [("LO sinusoidal frequency",common.get("lo_hz"),"Hz"),
                     ("LO+ sine amplitude / sine phase",display(lo_amplitude,"V peak")+" / 0 degrees",""),
                     ("LO- sine amplitude / sine phase",display(lo_amplitude,"V peak")+" / 180 degrees","")]
        selected.append(("Explicit CLP / CLN load, each",common.get("load_cap_f")*1e15 if common.get("load_cap_f") is not None else None,"fF"))
        story += [p(notes),table(["Bias / passive element","Value"],[[label,display(value,unit)] for label,value,unit in selected],widths=[CW*.64,CW*.36]),Spacer(1,7)]
        extras={k:v for k,v in q.items() if k not in {"gm_width_um","switch_width_um","length_nm","nf","m","rd_ohm","rl_ohm","rf_bias_v","rf_common_mode_v","lo_common_mode_v","lo_vpp_per_leg","lo_differential_vpp"}}
        if extras:story += [p("Additional recorded parameters","h2"),table(["Parameter","Value"],list(extras.items()),widths=[CW*.5,CW*.5],small=True)]
        single=entry.get("single_tone",{})
        raw_dc=dict(entry.get("dc",{}));operating_points=raw_dc.pop("operating_points",{})
        omitted_fields=raw_dc.pop("omitted_nonfinite_op_fields",[])
        raw_dc.pop("static_op_note",None)
        dc={**{key:value for key,value in raw_dc.items() if isinstance(value,(float,int)) and not isinstance(value,bool) and math.isfinite(value)},
            **{key:single[key] for key in ("tail_min_v","tail_max_v","tail_mean_v","lo_diff_vpp","power_mw") if key in single}}
        if dc or operating_points:
            story.append(PageBreak());story += heading(name.capitalize()+" operating-point evidence","Static bias and LO-driven voltage headroom")
            if operating_points:
                op_rows=[]
                for device,op in operating_points.items():
                    op_rows.append([device,display(op.get("id")*1e3 if op.get("id") is not None else None),
                        display(op.get("gm")*1e3 if op.get("gm") is not None else None),
                        display(op.get("gds")*1e3 if op.get("gds") is not None else None),
                        *[display(op.get(key)) for key in ("vgs","vds","vth","vdsat","region")]])
                story += [p("Static DC solution","h2"),p("For the static operating point, both sinusoidal LO sources are at their DC common-mode values. This table is a bias check at that condition. It does not replace the minimum/maximum checks over a complete LO cycle; region is the raw Spectre region code.","caption"),
                          table(["MOS","Id (mA)","gm (mS)","gds (mS)","VGS (V)","VDS (V)","VTH (V)","VDSAT (V)","Region"],op_rows,
                                widths=[CW*f for f in (.09,.11,.11,.11,.115,.115,.115,.13,.105)],small=True,padding=3.5)]
                if omitted_fields:story.append(p("Only finite operating-point values are shown. The raw simulator output contains additional nonfinite model fields; the omitted-field audit remains in the result JSON.","caption"))
                if name=="active":story.append(p("The static switching-device region code 3 indicates weak inversion at the LO common-mode bias. It does not establish the region of either switch throughout the LO cycle; the periodic waveform and headroom checks remain the relevant evidence during commutation.","caption"))
            if dc:story += [p("Settled LO-driven transient","h2"),p("Means and extrema below come from the saved, settled LO-driven transient. Raw differential output contains LO feedthrough as well as the desired IF signal. Confirm headroom with these periodic traces, rather than assuming the static DC solution persists while the LO switches.","caption"),table(["Recorded quantity","Value"],list(dc.items()),widths=[CW*.52,CW*.48],small=True,padding=3.5)]
            if name=="active" and dc.get("max_output_v",0)>common.get("vdd_v",1):
                story.append(p("The measured output peak is "+display(dc["max_output_v"],"V")+", slightly above the "+display(common.get("vdd_v"),"V")+" supply because of LO feedthrough and capacitive kick. The raw output is therefore not confined to the supply rails.","caption"))
            window_check=entry.get("window_convergence",{})
            reference=window_check.get("reference",{})
            compact_check=[]
            if window_check:
                def ns(value):return display(value*1e9 if value is not None else None)
                compact_check=[("Status",window_check.get("status")),
                    ("Short settle / window / samples (ns / ns / count)",ns(window_check.get("short_settle_s"))+" / "+ns(window_check.get("short_window_s"))+" / "+display(single.get("sample_count"))),
                    ("Reference settle / window / samples (ns / ns / count)",ns(reference.get("settle_s"))+" / "+ns(reference.get("window_s"))+" / "+display(reference.get("sample_count"))),
                    ("Reference-minus-short voltage gain (dB)",window_check.get("gain_delta_db")),
                    ("Allowed gain difference (dB)",window_check.get("tolerance_db"))]
            if compact_check:story += [p("Single-tone window cross-check","h2"),table(["Window-convergence check","Recorded value"],compact_check,widths=[CW*.54,CW*.46],small=True,padding=3.5)]
    story.append(PageBreak());story += heading("Measurement definitions","Use the same references when rebuilding")
    method=[
      ("RF input and available power","The source is a Thevenin voltage generator with series Rs. Pin = Vopen,pk squared / (8 Rs), per tone. A source amplitude, a loaded RF-node voltage, and the available input power are different quantities; retain all three references when comparing plots."),
      ("Differential voltage conversion gain","Gain = 20 log10(VIF,pk / Vopen,pk), with VIF = V(outp) - V(outn). RF-node gain uses the measured RF-gate/shared-input node instead. No additional 50-ohm output termination is inserted merely to calculate gain."),
      ("Transducer power gain and conversion loss","For equal output resistors R and a symmetric differential sinusoidal component, total load signal power is VIF,pk squared / (4 R). Transducer power gain is 10 log10(Pload / Pin,available), and power conversion loss is its negative. This power result differs from voltage conversion gain when input and output reference impedances differ."),
      ("Single-tone and two-tone runs","Single-tone RF is 5.8 GHz, producing the 200 MHz IF. Two RF tones at 5.79 and 5.81 GHz produce IF tones at 190 and 210 MHz; their third-order products are at 170 and 230 MHz. Input powers for IIP3 are per tone."),
      ("IIP3","For a resolved fundamental and its corresponding IM3, IIP3 = Pin + [20 log10(Afund/Aim3)]/2. Accept an intercept only in a drive interval where the fundamental slope is approximately one and the IM3 slope approximately three in voltage-amplitude coordinates. Numerical spurs and compressed points do not establish cubic behavior."),
      ("Input P1dB","Measure source-referenced conversion gain during a single-tone input sweep. Input P1dB is where that gain first falls 1 dB below its low-drive reference. This run refines a measured crossing by bisection and reports the final bracket midpoint; the neighboring measured bounds establish its resolution."),
      ("Periodic noise figure","The LO creates a periodically time-varying circuit. Use converged periodic steady state followed by periodic noise analysis. SSB NF refers desired-sideband signal gain to the total output noise, including noise folded from the image and other included sidebands. DSB NF requires the gains of both desired and image sidebands; do not subtract 3 dB without checking that assumption."),
      ("Coherent spectrum and transient","Raw V(outp)-V(outn) includes LO feedthrough, RF feedthrough, and mixing products; it is not an IF-filtered waveform. The report shows a 2 ns zoom of that raw trace and a separately labeled 200 MHz Fourier component reconstructed from the actual coherent projection. FFT plots use the full recorded waveform on an exact uniform measurement grid. An FFT amplitude bin is not a stochastic noise-floor measurement."),
      ("DC power and load convention","Active core power is the average current drawn from the 1 V supply times that supply voltage. Report passive core power separately from the power used to generate the external LO. Output loading remains the pair of resistors shown in each topology.")]
    for index,(title,text) in enumerate(method):
        if index==5:
            story.append(PageBreak());story += heading("Compression and noise methods","Match these measurements in Virtuoso")
        story += [p(title,"h2"),p(text)]
    timing=[]
    for name in ("active","passive"):
        row=circuits.get(name,{})
        for mode,measurement in [("Single tone",row.get("single_tone",{})),("Two tone",next(iter(row.get("linearity",{}).get("two_tone",[])),{}))]:
            if measurement:
                window=measurement.get("window_s")
                start=pick(measurement,"settle_s","measurement_start_s")
                step=measurement.get("strobe_s",result.get("config",{}).get("analysis",{}).get("strobe_s"))
                timing.append([name.capitalize()+" / "+mode,display(start*1e9 if start is not None else None),
                    display(window*1e9 if window is not None else None),measurement.get("sample_count"),
                    display(step*1e12 if step is not None else None),display(1/window/1e6 if window else None)])
    if timing:story += [p("Recorded coherent sampling grids","h2"),table(["Circuit / analysis","Settle (ns)","Window (ns)","Samples","Strobe (ps)","FFT bins (MHz)"],timing,
        widths=[CW*.3,CW*.14,CW*.15,CW*.12,CW*.14,CW*.15],small=True),p("The FFT-bin spacing is 1 / window. Single-tone and two-tone windows can differ while each remains coherent with its own RF/LO/IF tones.","caption")]
    for name in ("active","passive"):
        available=[k for k in (f"{name}_transient",f"{name}_spectrum") if k in figures]
        if available:
            story.append(PageBreak());story += heading(name.capitalize()+" waveforms and spectra","Actual locally rendered Spectre traces")
            for key in available:add_image(story,figures[key],"Source: saved numerical curves for "+name+". Raw output contains LO feedthrough; the extracted IF curve is a labeled Fourier reconstruction. No remote image output was imported.",max_height=275)
        available=[k for k in (f"{name}_compression",f"{name}_iip3") if k in figures]
        if available:
            story.append(PageBreak());story += heading(name.capitalize()+" linearity","Measured drive sweeps")
            for key in available:add_image(story,figures[key],"Available input power is per RF tone. Intercepts are valid only in the verified cubic region.",max_height=255)
            evidence=circuits.get(name,{}).get("linearity",{})
            if evidence:
                story.append(PageBreak());story += heading(name.capitalize()+" linearity validation","Accepted measurement region and convergence")
                summary=[("Stage status",evidence.get("status")),("Small-signal compression reference (dB)",evidence.get("baseline_gain_db")),
                         ("Input P1dB (dBm)",evidence.get("p1db_dbm")),("Final P1dB bracket (dBm)",evidence.get("p1db_bracket_dbm")),
                         ("Compression samples",len(evidence.get("compression",[]))),
                         ("Two-tone samples",len(evidence.get("two_tone",[]))),
                         ("IIP3, lower / upper products (dBm)",evidence.get("iip3_each_side_dbm"))]
                selected=evidence.get("cubic_region") or {};conv=evidence.get("convergence") or {}
                summary += [("Accepted input powers (dBm per tone)",selected.get("pins_dbm")),
                            ("Fundamental slopes, lower / upper",selected.get("fundamental_slopes")),
                            ("IM3 slopes, lower / upper",selected.get("im3_slopes")),
                            ("Minimum IM3 / empty-bin margin (dB)",selected.get("minimum_im3_to_empty_bin_margin_db")),
                            ("Tighter-solver IIP3 change (dB)",conv.get("delta_db")),
                            ("Tighter-solver check passed",conv.get("passed"))]
                story += [table(["Linearity evidence","Recorded value"],summary,widths=[CW*.58,CW*.42],small=True)]
                if f"{name}_twotone_spectrum" in figures:
                    add_image(story,figures[f"{name}_twotone_spectrum"],"Actual spectrum from the tighter-solver check at the accepted cubic region's middle input power. The IF detail focuses its axis range on the measured fundamentals and IM3 products; it does not represent a stochastic noise floor.",max_height=315)
    periodic={name:circuits.get(name,{}).get("noise",{}).get("analysis_settings",{}) for name in ("active","passive")}
    if any(periodic.values()):
        story.append(PageBreak());story += heading("Exact periodic-analysis setup","PSS, PAC, and PNOISE schematic handoff")
        story.append(p("Use the LO-driven periodic solution with RF sine amplitudes set to zero for PSS and noise analysis. Keep the RF source resistance and source noise enabled. The PAC magnitude uses the matched-source port convention discussed in the source setup table; 0.5 V at the port represents 1 V open circuit."))
        setting_labels={"pss_fund_hz":"PSS fundamental frequency (Hz)","pss_tstab_s":"PSS stabilization time (s)",
            "pss_harmonics":"PSS harmonics","pss_solver":"PSS solver","pss_errpreset":"PSS accuracy preset",
            "pss_method":"PSS integration method","pss_maxacfreq_hz":"PSS maxacfreq (Hz)",
            "pnoise_output_frequencies_hz":"PNOISE output frequencies (Hz)","pnoise_sweeptype":"PNOISE sweep type",
            "pnoise_noisetype":"PNOISE noise type","pnoise_refsideband":"PNOISE reference sideband",
            "pnoise_sideband_checks":"PNOISE sideband checks","pnoise_final_maxsideband":"Final PNOISE maximum sideband",
            "pnoise_input_probe":"PNOISE input source","pnoise_output_nodes":"Differential output nodes",
            "pnoise_output_probe":"External output-probe element","pac_output_sideband":"PAC output sideband",
            "pac_freqaxis":"PAC frequency axis","pac_source_matched_v":"PAC source magnitude, matched convention (V)"}
        settings_keys=list(dict.fromkeys([*periodic["active"],*periodic["passive"]]))
        story.append(table(["Analysis property","Active","Passive"],[[setting_labels.get(key,key.replace("_"," ")),periodic["active"].get(key),periodic["passive"].get(key)] for key in settings_keys],
                           widths=[CW*.42,CW*.29,CW*.29],small=True))
        pac_pairs={}
        for name in ("active","passive"):
            noise=circuits.get(name,{}).get("noise",{})
            noise_output_frequencies=noise.get("analysis_settings",{}).get("pnoise_output_frequencies_hz",[]);desired=noise.get("signal_input_frequency_hz",[]);image=noise.get("image_input_frequency_hz",[])
            if isinstance(noise_output_frequencies,(int,float)):noise_output_frequencies=[noise_output_frequencies]
            if isinstance(desired,(int,float)):desired=[desired]
            if isinstance(image,(int,float)):image=[image]
            for fo,fd,fi in zip(noise_output_frequencies,desired,image):pac_pairs.setdefault((fo,fd,fi),[]).append(name.capitalize())
        pac_rows=[["Both" if len(names)==2 else names[0],display(fo/1e6),display(fd/1e9),display(fi/1e9)] for (fo,fd,fi),names in pac_pairs.items()]
        if pac_rows:story += [p("PAC input frequencies paired to the PNOISE output axis","h2"),table(["Circuit","Output IF (MHz)","Desired RF input (GHz)","Image RF input (GHz)"],pac_rows,widths=[CW*.2,CW*.22,CW*.29,CW*.29],small=True)]
    for name in ("active","passive"):
        key=name+"_noise";evidence=circuits.get(name,{}).get("noise",{})
        if key in figures or evidence:
            story.append(PageBreak());story += heading(name.capitalize()+" noise figure and folding","Periodic steady-state / periodic noise results")
            if key in figures:add_image(story,figures[key],"Loaded differential-output noise figure includes the intrinsic load resistors. No external output load is added.",max_height=230)
            if evidence:story += [p("Noise settings and independent checks","h2"),table(["Setting / check","Recorded value"],noise_summary(evidence),widths=[CW*.47,CW*.53],small=True)]
    story.append(PageBreak());story += heading("Rebuild and rerun in Virtuoso","A direct mapping from the verified netlists")
    steps=[
      "Create two separate schematic cells for the active and passive mixer, plus separate testbench cells. Choose library NCSU_Devices_FreePDK45, cell NMOS_VTH (uppercase), view symbol. Set Width (w), Length (l), and Multiplier (m) as listed. This symbol has no nf/finger-count CDF field: each MOS is one unfingered instance.",
      "Name the nets rf, lop, lon, outp, and outn. Add tail only in the active cell; this is the common-source switching node, not an added current source. Connect every NMOS bulk to ground. Verify each D/G/S/B row against the symbol's terminal labels before connecting the testbench.",
      "Place the two equal load resistors. Active: each output resistor returns to VDD. Passive: each output resistor returns to ground. Add the explicit CLP and CLN output testbench capacitors, each from its output to ground, at the recorded value (10 fF in this run). The CGS/CGD labels in the passive reference figure are intrinsic transistor parasitics already inside the PDK model; do not add separate capacitors for those labels.",
      "Generate LO+ and LO- as 5.6 GHz sinusoids with the same DC common mode and equal amplitudes. In analogLib/vsource, choose Source type = sine and set Phase for Sinusoid 1 (sinephase) to 0 degrees for LO+ and 180 degrees for LO-. The AC phase field is separate. Frequency 1 sets 5.6 GHz, and Amplitude 1 is the per-leg peak voltage. With opposite phases, differential Vpp is twice the per-leg Vpp.",
      "Use an RF source with the recorded DC bias/common mode and series Rs. For the two-tone test, combine the two source voltages without adding a second unintended source termination. Keep available input power per tone consistent with the numerical study.",
      "Run the DC operating point first. Confirm active M1 has sufficient drain-source voltage and that both switching devices and load drops fit within the 1 V supply. Check the actual gate and drain waveforms during an LO cycle; the DC solution alone does not prove correct commutation.",
      "For transient analysis, use the stop time, maximum step, strobe interval, and coherent measurement window recorded in the analysis settings below. Plot V(outp)-V(outn), not just one output. Verify the 200 MHz IF and inspect LO/RF feedthrough separately.",
      "Repeat single-tone compression and two-tone IIP3 sweeps using the saved source-amplitude grid. Then run PSS with LO only and the matching PNOISE setup. Use the same RF source-noise reference, output differential probe, sideband count, and SSB/DSB convention as the recorded run.",
      "Compare your schematic-generated netlist with netlists/generated before comparing final metrics. Differences in source DC bias, phase, loading, model corner, device geometry, or power reference can change the result even when the circuit picture looks identical."]
    for index,text in enumerate(steps,1):story.append(p(f"<b>{index}.</b> "+safe(text)))
    story.append(PageBreak());story += heading("Source setup and MOS geometry","Exact translation to schematic properties")
    analysis=result.get("config",{}).get("analysis",{})
    pin=analysis.get("small_signal_pin_dbm");rs=common.get("rs_ohm")
    vopen=math.sqrt(8*rs*1e-3*10**(pin/10)) if rs is not None and pin is not None else None
    story += [p("Spectre's <b>port</b> uses a matched-load amplitude convention. Its open-circuit DC, sine amplitude, and PAC voltage are twice the entered voltage values. A normal ideal <b>vsource</b> followed by an explicit series resistor uses the full open-circuit values directly. Mixing these conventions causes a 6.02 dB voltage-reference error.","callout")]
    story.append(p("The numerical amplitudes in the tables use the recorded small-signal reference input power. During compression and IIP3 sweeps, recompute Vopen,pk = sqrt(8 Rs x 0.001 x 10^(Pin/10)) at each input-power point; keep the DC bias unchanged. Each RF tone uses that point's per-tone amplitude."))
    story.append(p("LO+ and LO- are ideal sinusoidal voltage sources with no extra series resistance. Their driver noise and driver power are outside this core comparison. The RF source alone uses the recorded Thevenin resistance and source thermal-noise temperature."))
    for name in ("active","passive"):
        q=params(result,name);bias=pick(q,"rf_bias_v","rf_common_mode_v")
        source_rows=[
          ["Series source resistance",display(rs,"ohm"),display(rs,"ohm")],
          ["RF DC / common-mode",display(bias/2 if bias is not None else None,"V entered as port dc"),display(bias,"V entered as vsource dc")],
          ["Single-tone sine amplitude",source_voltage(vopen/2 if vopen is not None else None,"V peak entered as port ampl"),source_voltage(vopen,"V peak entered as vsource ampl")],
          ["PAC source magnitude","0.5 V entered -> 1 V open circuit","1 V entered -> 1 V open circuit"],
          ["Source thermal noise",("isnoisy = yes; noisetemp = "+display(common.get("source_noise_temp_k")-273.15 if common.get("source_noise_temp_k") is not None else None,"C")),("Noiseless ideal voltage source; Rs thermal noise at "+display(common.get("source_noise_temp_k"),"K"))],
          ["RF sine frequency",display(common.get("rf_hz"),"Hz"),display(common.get("rf_hz"),"Hz")],
          ["RF transient sine phase","0 degrees","0 degrees"],
          ["Second series source, single-tone","RFSECOND dc = 0 V, ampl = 0 V","Omit or use a 0 V series source"],
          ["Second series source, two-tone",source_voltage(vopen,"V peak (ordinary vsource) at second RF tone"),source_voltage(vopen,"V peak at second RF tone; do not duplicate Rs")],
          ["Available RF power",display(pin,"dBm per tone"),display(pin,"dBm per tone")]]
        story += [p(name.capitalize()+" RF source","h2"),table(["Property","Spectre port + RFSECOND","Ideal vsource + series Rs"],source_rows,widths=[CW*.28,CW*.36,CW*.36],small=True)]
    story += [p("Verified single-device diffusion geometry","h2"),p("The installed NCSU PDK callback code was checked: for Multiplier = 1, as = W x ls, ad = W x ld, ps = W + 2 ls, and pd = W + 2 ld. Use ls = ld = 105 nm. Set Width, Length, and Multiplier in the symbol form, check the source/drain diffusion lengths, and let the callbacks compute AS/AD/PS/PD; those derived CDF fields are read-only. Compare the generated netlist with the values below. The diffusion extension is not additional channel length or extra gate width."),
              p("The installed PDK minimum channel length is 50 nm, although its technology-node name is 45 nm. The recorded L = 50 nm follows that PDK limit. No nf/finger-count field is declared for this symbol; each listed device is one unfingered instance.","caption")]
    geometry=[]
    for name in ("active","passive"):
        q=params(result,name);widths=[("M1",q.get("gm_width_um")),("M2 / M3",q.get("switch_width_um"))] if name=="active" else [("M1 / M2",q.get("switch_width_um"))]
        for device,width in widths:
            geometry.append([name.capitalize()+" "+device,display(width,"um"),display(width*.105 if width is not None else None,"um2"),display(width+.210 if width is not None else None,"um"),"105 nm"])
    story.append(table(["Device","W","as = ad","ps = pd","ls = ld"],geometry,widths=[CW*.28,CW*.15,CW*.2,CW*.2,CW*.17],small=True))
    story += [p("Python API and local notebook","h2"),p("Open notebooks/00_overview.ipynb and select <b>ECE6420 (Local)</b>. The local Run All action sends the current parameter cell to the school server, runs Spectre through Python, pulls numerical traces and logs, and renders figures locally. Review mode redraws the saved data without rerunning Spectre. No remote Jupyter kernel or Remote SSH extension is required.")]
    story.append(PageBreak());story += heading("Run provenance and verification","Reproducibility record")
    env=result.get("environment",{})
    provenance=[["Run ID",result.get("run_id","Not recorded")],["Completed UTC",result.get("completed_utc","Not recorded")],
        ["Result JSON SHA-256",hashlib.sha256((base/"results/hw9_results.json").read_bytes()).hexdigest()],
        ["Rendered by","Local Python / matplotlib / ReportLab"],["Maintained project","Gatech-ECE6420/HW09 (one local/remote source tree)"]]
    provenance+=list(env.items())
    story.append(table(["Provenance","Recorded value"],provenance,widths=[CW*.32,CW*.68],small=True))
    audit_path=base/"results/validation.json"
    if audit_path.exists():
        audit=json.loads(audit_path.read_text());result_sha=hashlib.sha256((base/"results/hw9_results.json").read_bytes()).hexdigest()
        expected_fp=hashlib.sha256(json.dumps(result["config"],sort_keys=True).encode()).hexdigest()
        if audit.get("campaign_json_sha256")!=result_sha or audit.get("run_id")!=result.get("run_id") or audit.get("config_fingerprint")!=expected_fp:
            raise ValueError("Independent validation audit is stale or belongs to a different campaign. Rerun tools/validate_results.py before building the report.")
        if (audit.get("status")!="passed" or audit.get("failures_count")!=0) and not allow_partial:
            raise ValueError("Independent numerical validation has not passed; a final report cannot be built.")
        story += [p("Independent numerical audit","h2"),table(["Audit evidence","Recorded value"],[
            ["Status",audit.get("status")],["Checks / failures",display(audit.get("checks_count"))+" / "+display(audit.get("failures_count"))],
            ["Matching run ID",audit.get("run_id")],["Matching source result SHA-256",audit.get("campaign_json_sha256")],
            ["Audit completed UTC",audit.get("completed_utc")]],widths=[CW*.38,CW*.62],small=True)]
    validation=result.get("validation",{})
    if validation:story += [p("Validation evidence","h2"),table(["Check","Recorded result"],list(validation.items()),widths=[CW*.36,CW*.64],small=True)]
    settings=result.get("analysis_settings",result.get("config",{}).get("analysis",{}))
    if settings:story += [p("Analysis settings","h2"),table(["Setting","Value"],list(settings.items()),widths=[CW*.4,CW*.6],small=True)]
    notes=list(result.get("notes",[]))
    for name in ("active","passive"):
        notes += [name.capitalize()+": "+str(x) for x in circuits.get(name,{}).get("notes",[])]
    if notes:
        story.append(p("Recorded limitations and notes","h2"))
        for note in notes:story.append(p("- "+safe(note)))
    story += [p("Reference basis","h2"),p("[1] HW09 assignment: HW9_Mixer_design.pdf, project source. [2] B. Razavi, RF Microelectronics, second edition, Chapter 6: Fig. 6.15(b), single-balanced passive mixer; Fig. 6.42, single-balanced active mixer; Section 6.3.1, conversion gain. [3] The actual Spectre logs and generated analysis netlists retained under this project's simulation/ and netlists/generated/ folders.","caption")]
    doc=BaseDocTemplate(str(report_path),pagesize=A4,leftMargin=M,rightMargin=M,topMargin=49,bottomMargin=48,
        title="ECE6420 HW09 - Single-balanced mixer design",author="ECE6420 simulation study",pageCompression=1)
    doc.addPageTemplates([PageTemplate(id="body",frames=[Frame(M,48,CW,H-97,leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)],onPage=header_footer)])
    doc.build(story)
    return report_path


if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("--root",type=Path,default=ROOT)
    ap.add_argument("--output",type=Path);ap.add_argument("--reuse-figures",action="store_true")
    ap.add_argument("--allow-partial",action="store_true",help="Explicit diagnostic report only; incomplete runs are otherwise rejected.")
    args=ap.parse_args();print(build(args.root,args.output,render=not args.reuse_figures,allow_partial=args.allow_partial))
