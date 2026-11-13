#!/usr/bin/env python3
"""Independently check actual exported OA connectivity and CDF values."""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
import re
from render_native_schematic import load_audit

SCALES={"":1.,"f":1e-15,"p":1e-12,"n":1e-9,"u":1e-6,"m":1e-3,"k":1e3,"M":1e6,"G":1e9}


def number(text,variables=None):
    text=str(text).strip()
    match=re.fullmatch(r"([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)([fpnumkMG]?)",text)
    if match:return float(match[1])*SCALES[match[2]]
    variables=variables or {}
    def evaluate(node):
        if isinstance(node,ast.Expression):return evaluate(node.body)
        if isinstance(node,ast.Constant) and isinstance(node.value,(float,int)):return node.value
        if isinstance(node,ast.Name) and node.id in variables:return variables[node.id]
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.USub,ast.UAdd)):
            value=evaluate(node.operand);return -value if isinstance(node.op,ast.USub) else value
        if isinstance(node,ast.BinOp):
            left,right=evaluate(node.left),evaluate(node.right)
            if isinstance(node.op,ast.Add):return left+right
            if isinstance(node.op,ast.Sub):return left-right
            if isinstance(node.op,ast.Mult):return left*right
            if isinstance(node.op,ast.Div):return left/right
            if isinstance(node.op,ast.Pow):return left**right
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=="sqrt" and len(node.args)==1:
            return math.sqrt(evaluate(node.args[0]))
        raise ValueError("Unsupported native CDF expression: "+text)
    result=float(evaluate(ast.parse(text,mode="eval")))
    if not math.isfinite(result):raise ValueError("Nonfinite actual CDF expression")
    return result


def audit(path,kind,config,require_intended_names=False):
    path=Path(path);text=path.read_text();instances,shapes,pins,connections,props=load_audit(path)
    checks=[];aliases={}
    def check(label,condition):
        checks.append({"check":label,"passed":bool(condition)})
        if not condition:raise ValueError("Native OA audit failed: "+label)
    def close(label,actual,expected):
        check(label,math.isclose(number(actual),expected,rel_tol=1e-9,abs_tol=1e-22))
    check("schCheck errors/warnings",bool(re.search(r"^check_errors\t\(0 0\)$",text,re.M)))
    def normalize(net):return "0" if net in {"gnd!","0"} else net
    terms={name:{} for name in instances}
    for c in connections:terms[c["instance"]][c["terminal"]]=normalize(c["net"])
    def find(cell,wanted,label):
        matching=[name for name,inst in instances.items() if inst["cell"]==cell and terms[name]==wanted]
        check(label+" unique actual native instance",len(matching)==1)
        aliases[label]=matching[0]
        return matching[0]
    p,c=config[kind],config["common"]
    mos_expected=([("M1",{"D":"tail","G":"rf","S":"0","B":"0"},p["gm_width_um"]),
        ("M2",{"D":"outp","G":"lop","S":"tail","B":"0"},p["switch_width_um"]),
        ("M3",{"D":"outn","G":"lon","S":"tail","B":"0"},p["switch_width_um"]) ]
        if kind=="active" else [
        ("M1",{"D":"outp","G":"lop","S":"rf","B":"0"},p["switch_width_um"]),
        ("M2",{"D":"outn","G":"lon","S":"rf","B":"0"},p["switch_width_um"])])
    check("MOS count",sum(i["cell"]=="NMOS_VTH" for i in instances.values())==len(mos_expected))
    for role,nodes,width in mos_expected:
        name=find("NMOS_VTH",nodes,role);v=props[name];w=width*1e-6
        check(role+" library",instances[name]["lib"]=="NCSU_Devices_FreePDK45")
        check(role+" model",v["model"]=="NMOS_VTH")
        for key,expected in {"w":w,"l":p["length_nm"]*1e-9,"m":1,"ls":105e-9,"ld":105e-9,
            "as":w*105e-9,"ad":w*105e-9,"ps":w+210e-9,"pd":w+210e-9}.items():
            close(role+" "+key,v[key],expected)
    check("Resistor count",sum(i["cell"]=="res" for i in instances.values())==2)
    check("Capacitor count",sum(i["cell"]=="cap" for i in instances.values())==2)
    for role,node in (("R1","outp"),("R2","outn")):
        name=find("res",{"PLUS":"vdd" if kind=="active" else node,
                          "MINUS":node if kind=="active" else "0"},role)
        close(role+" resistance",props[name]["r"],p["rd_ohm" if kind=="active" else "rl_ohm"])
    for role,node in (("CLP","outp"),("CLN","outn")):
        name=find("cap",{"PLUS":node,"MINUS":"0"},role)
        close(role+" capacitance",props[name]["c"],c["load_cap_f"])
    rf=find("port",{"PLUS":"rfdrive","MINUS":"0"},"RFPORT")
    v=props[rf]
    for key,expected in {"r":c["rs_ohm"],"vdc":p["rf_bias_v" if kind=="active" else "rf_common_mode_v"]/2,
                         "pacm":.5,"noisetemp":16.85,"num":1,"sinephase":0}.items():close("RFPORT "+key,v[key],expected)
    check("RFPORT is noisy",v["isnoisyNoiseModel"]=="yes")
    check("RFPORT sine type",v["srcType"]=="sine")
    second=find("vsource",{"PLUS":"rf","MINUS":"rfdrive"},"RFSECOND")
    close("RFSECOND DC",props[second]["vdc"],0)
    check("RFSECOND sine type",props[second]["srcType"]=="sine")
    for pin in (-60,-55,-35):
        env={"pinDbm":pin,"rfScale":1,"tone2Scale":1,"fRF":c["rf_hz"],"fRF2":c["rf_hz"]}
        openpk=math.sqrt(8*c["rs_ohm"]*.001*10**(pin/10))
        check(f"RFPORT matched amplitude at {pin} dBm",math.isclose(number(v["va"],env),openpk/2,rel_tol=1e-12))
        check(f"RFSECOND amplitude at {pin} dBm",math.isclose(number(props[second]["va"],env),openpk,rel_tol=1e-12))
        env.update(rfScale=0,tone2Scale=0)
        check(f"LO-only RF amplitudes at {pin} dBm",number(v["va"],env)==number(props[second]["va"],env)==0)
    for role,node,phase in (("LOP","lop",0),("LON","lon",180)):
        name=find("vsource",{"PLUS":node,"MINUS":"0"},role)
        check(role+" sine type",props[name]["srcType"]=="sine")
        for key,expected in {"freq":c["lo_hz"],"va":p["lo_vpp_per_leg"]/2,
                             "vdc":p["lo_common_mode_v"],"sinephase":phase}.items():close(role+" "+key,props[name][key],expected)
    if kind=="active":
        name=find("vsource",{"PLUS":"vdd","MINUS":"0"},"VDD")
        close("VDD",props[name]["vdc"],c["vdd_v"])
        check("VDD DC type",props[name]["srcType"]=="dc")
    for first,second_hz in ((c["rf_hz"],c["rf_hz"]),tuple(config["analysis"]["rf_tones_hz"])):
        env={"fRF":first,"fRF2":second_hz}
        check("RFPORT frequency design-variable mapping",number(props[rf]["freq"],env)==first)
        check("RFSECOND frequency design-variable mapping",number(props[second]["freq"],env)==second_hz)
    non_ground={name for name,inst in instances.items() if inst["cell"]!="gnd"}
    check("No unreviewed extra device",set(aliases.values())==non_ground)
    check("Analog primitive libraries",all(inst["lib"]=="analogLib" for inst in instances.values()
                                          if inst["cell"]!="NMOS_VTH"))
    if require_intended_names:
        check("Intended readable native instance names",all(k==v for k,v in aliases.items()))
    return {"status":"passed","kind":kind,"source_audit":str(path.resolve()),
            "source_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
            "checks_count":len(checks),"checks":checks,"actual_native_role_names":aliases,
            "instance_count":len(instances),"connection_count":len(connections)}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("audit",type=Path);p.add_argument("--kind",choices=("active","passive"),required=True)
    p.add_argument("--config",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    p.add_argument("--require-intended-names",action="store_true")
    a=p.parse_args();result=audit(a.audit,a.kind,json.loads(a.config.read_text()),a.require_intended_names)
    a.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:result[k] for k in ("status","kind","checks_count","actual_native_role_names")},indent=2))
