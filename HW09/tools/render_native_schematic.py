#!/usr/bin/env python3
"""Render an actual Virtuoso OA geometry audit locally, never a GUI screenshot.

Consumes the hw09Audit TSV exported from the live native schematic database.
Symbol primitives and top-level wires are real exported geometry. Dynamic
Cadence label expressions are replaced with actual exported instance captions.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle,Polygon,Ellipse
import numpy as np

NUMBER=re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")


def points(text):
    values=[float(x) for x in NUMBER.findall(text)]
    if len(values)%2:raise ValueError("Odd coordinate count in actual OA geometry: "+text)
    return np.asarray(values,dtype=float).reshape((-1,2))


def string(text):
    text=text.strip()
    if text=="nil":return ""
    if text.startswith('"') and text.endswith('"'):
        return text[1:-1].replace('\\"','"').replace('\\n','\n')
    return text


MATRICES={"R0":((1,0),(0,1)),"R90":((0,-1),(1,0)),
          "R180":((-1,0),(0,-1)),"R270":((0,1),(-1,0)),
          "MX":((1,0),(0,-1)),"MY":((-1,0),(0,1)),
          "MXR90":((0,1),(1,0)),"MYR90":((0,-1),(-1,0))}


def load_audit(path):
    instances={};shapes=[];pins=[];connections=[];properties={}
    for number,line in enumerate(Path(path).read_text().splitlines(),1):
        row=line.split("\t")
        if not row or not row[0] or row[0].startswith("#"):continue
        kind=row[0]
        try:
            if kind=="instance":
                origin=points(row[4])
                if origin.shape!=(1,2):raise ValueError("Invalid instance origin")
                orient=string(row[5])
                if orient not in MATRICES:raise ValueError("Unsupported actual OA orientation: "+orient)
                instances[row[1]]={"name":row[1],"lib":row[2],"cell":row[3],"origin":origin[0],"orient":orient}
            elif kind=="connection":connections.append({"instance":row[1],"terminal":row[2],"net":row[3]})
            elif kind=="pin":pins.append({"instance":row[1],"terminal":row[2],"position":points(row[3])[0]})
            elif kind=="property":properties.setdefault(row[1],{})[row[2]]=string(row[3])
            elif kind=="mastershape":
                shapes.append({"instance":row[1],"kind":row[2],"bbox":points(row[3]),"points":points(row[4]),"label":string(row[5]),"lpp":row[6] if len(row)>6 else ""})
            elif kind=="shape":
                shapes.append({"instance":None,"kind":row[1],"bbox":points(row[2]),"points":points(row[3]),"label":string(row[4]),"lpp":row[5] if len(row)>5 else ""})
        except (ValueError,IndexError) as exc:
            raise ValueError(f"Malformed OA audit row {number}: {exc}") from exc
    if not instances or not shapes or not connections:
        raise ValueError("Actual OA instance, shape and connection exports are required")
    return instances,shapes,pins,connections,properties


def load_arcs(path):
    arcs=[]
    if not Path(path).is_file():return arcs
    for line in Path(path).read_text().splitlines():
        row=line.split("\t")
        if row[0]!="arc":continue
        arcs.append({"lib":row[1],"cell":row[2],"bbox":points(row[3]),
                     "ellipse":points(row[4]),"start":float(row[5]),"stop":float(row[6])})
    return arcs


def render(audit,output_prefix,kind=None,core_only=False):
    audit=Path(audit).resolve();prefix=Path(output_prefix).resolve()
    instances,shapes,pins,connections,properties=load_audit(audit)
    arc_audit=audit.parent/"symbol_arcs.tsv"
    arcs=load_arcs(arc_audit)
    fig,ax=plt.subplots(figsize=(13,8.5))
    label_font=(10.6 if kind=="passive" else 9.5) if core_only else 11.5
    color="#17384A";extent=[];core_extent=[];skipped=set();pending_labels=[]
    signal_names={c["net"] for c in connections}
    core_instances={name for name,inst in instances.items() if inst["cell"] in {"NMOS_VTH","res","cap"}}
    core_min_x=min(instances[name]["origin"][0] for name in core_instances)
    core_instances.update(name for name,inst in instances.items() if inst["cell"]=="gnd" and inst["origin"][0]>=core_min_x-1)
    def transform(coords,instance):
        if not len(coords):return coords
        if instance is None:return coords
        inst=instances[instance]
        return coords@np.asarray(MATRICES[inst["orient"]]).T+inst["origin"]
    for shape in shapes:
        if core_only and shape["instance"] is not None and shape["instance"] not in core_instances:
            continue
        if '"instance"' in shape["lpp"] or '"pin"' in shape["lpp"]:
            continue
        coords=transform(shape["points"],shape["instance"])
        box=transform(shape["bbox"],shape["instance"])
        category=shape["kind"]
        if category not in {"label","text","textDisplay"}:
            if len(box):extent.extend(box.tolist())
            if len(coords):extent.extend(coords.tolist())
            if shape["instance"] in core_instances:
                if len(box):core_extent.extend(box.tolist())
                if len(coords):core_extent.extend(coords.tolist())
            elif shape["instance"] is None and len(coords) and min(coords[:,0])>=core_min_x-2:
                core_extent.extend(coords.tolist())
        if category in {"line","path","pathSeg"} and len(coords)>1:
            ax.plot(coords[:,0],coords[:,1],color=color,lw=1.25)
        elif category in {"rect","rectangle"} and len(box)==2:
            lo=np.min(box,axis=0);hi=np.max(box,axis=0)
            ax.add_patch(Rectangle(lo,*(hi-lo),fill=False,edgecolor=color,lw=.9))
        elif category in {"polygon","poly"} and len(coords)>2:
            ax.add_patch(Polygon(coords,closed=True,fill=False,edgecolor=color,lw=1))
        elif category in {"ellipse","circle"} and len(box)==2:
            lo=np.min(box,axis=0);hi=np.max(box,axis=0)
            ax.add_patch(Ellipse((hi+lo)/2,*(hi-lo),fill=False,edgecolor=color,lw=1))
        elif category=="arc" and shape["instance"]:
            inst=instances[shape["instance"]]
            matching=[arc for arc in arcs if arc["lib"]==inst["lib"] and arc["cell"]==inst["cell"]
                      and arc["bbox"].shape==shape["bbox"].shape and np.allclose(arc["bbox"],shape["bbox"],atol=1e-12,rtol=0)]
            if len(matching)==1:
                arc=matching[0];ellipse=arc["ellipse"]
                lo=ellipse.min(axis=0);hi=ellipse.max(axis=0)
                center=(hi+lo)/2;radius=(hi-lo)/2
                stop=arc["stop"]
                while stop<arc["start"]:stop+=2*np.pi
                angles=np.linspace(arc["start"],stop,97)
                local=center+np.column_stack((radius[0]*np.cos(angles),radius[1]*np.sin(angles)))
                curve=transform(local,shape["instance"])
                ax.plot(curve[:,0],curve[:,1],color=color,lw=1)
            else:skipped.add("arc")
        elif category in {"label","text","textDisplay"}:
            label=shape["label"]
            if not label or label.startswith("cds") or "cdsParam" in label or "[@" in label:continue
            if shape["instance"] and instances[shape["instance"]]["cell"] in {"gnd","vdd","vss","ground"}:continue
            if shape["instance"] and label in {"D","G","S","B","PLUS","MINUS"}:continue
            if len(box):
                origin=box[0]
                pending_labels.append((origin,label,shape["instance"]))
        elif category not in {"inst","instance"}:
            skipped.add(category)
    # Instance identifiers and values come from actual native properties, not
    # from a hand-entered copy of the intended configuration.
    for name,inst in instances.items():
        if inst["cell"] in {"gnd","vdd","vss","ground"}:continue
        if core_only and name not in core_instances:continue
        x,y=inst["origin"]; props=properties.get(name,{})
        caption=name
        if inst["cell"].startswith("NMOS"):
            keys=["w","l"]
        elif inst["cell"]=="res":keys=["r"]
        elif inst["cell"]=="cap":keys=["c"]
        else:keys=["srcType","r","vdc","va","freq","sinephase"]
        values=[]
        for key in keys:
            if key in props and props[key]:
                val=props[key]
                if key=="va" and len(val)>16:val="pinDbm expression"
                values.append(key+"="+val)
        source_instance=inst["cell"] in {"port","vsource"}
        if values:
            caption+="\n"+("\n".join(values) if source_instance else "\n".join(", ".join(values[i:i+2]) for i in range(0,len(values),2)))
        offset=(16,27) if inst["cell"].startswith("NMOS") else (18,16)
        vertical="bottom"
        if source_instance and name in {"RFPORT","LOP","LON"}:vertical="top"
        if name in {"LOP","LON"}:offset=(6,16)
        if name in {"RFPORT","VDD"}:offset=(36,0)
        if name=="RFSECOND":offset=(90,16)
        if kind=="active" and name=="M3":offset=(16,-40)
        if kind=="passive" and inst["cell"].startswith("NMOS"):offset=(32,25)
        ax.annotate(caption,(x,y),xytext=offset,textcoords="offset points",fontsize=label_font,
                    color="#126578",ha="left",va=vertical,bbox={"facecolor":"white","edgecolor":"none","alpha":.8,"pad":1})
    # Draw only connection anchors exported from the database. Native wire
    # geometry already determines topology; no new connection is inferred.
    if pins:
        pp=np.asarray([p["position"] for p in pins if not core_only or p["instance"] in core_instances])
        if len(pp):ax.scatter(pp[:,0],pp[:,1],s=3,color=color,zorder=2)
    bounds=np.asarray(core_extent if core_only else extent)
    if not len(bounds):raise ValueError("No visible native geometry")
    low=bounds.min(axis=0);high=bounds.max(axis=0);span=np.maximum(high-low,.1)
    for origin,label,instance in pending_labels:
        # Keep actual signal labels near electrical geometry; leave the
        # standalone instructional paragraphs to the report's readable text.
        if instance is None and label not in signal_names:
            continue
        offset=(0,-3) if label=="tail" else (0,3)
        ax.annotate(label,origin,xytext=offset,textcoords="offset points",fontsize=label_font,
                    color=color,ha="left",va="top" if label=="tail" else "bottom",clip_on=True)
    ax.set_xlim(low[0]-.07*span[0],high[0]+.18*span[0])
    upper=high[1]+.12*span[1]
    if not core_only and "RFSECOND" in instances:upper=max(upper,instances["RFSECOND"]["origin"][1]+2.4)
    ax.set_ylim(low[1]-.08*span[1],upper)
    ax.set_aspect("equal");ax.axis("off")
    ax.set_title((kind.capitalize()+" mixer "+("core" if core_only else "testbench") if kind else "Native Virtuoso schematic")+
                 "\nLocally rendered from exported native OA geometry",fontsize=12,fontweight="bold",color=color,pad=10)
    fig.tight_layout()
    prefix.parent.mkdir(parents=True,exist_ok=True)
    for extension in ("png","svg"):
        fig.savefig(prefix.with_suffix("."+extension),dpi=220,bbox_inches="tight",facecolor="white")
    plt.close(fig)
    metadata={"origin":"native_oa_geometry_local_render","source_audit":str(audit),
              "source_sha256":hashlib.sha256(audit.read_bytes()).hexdigest(),
              "instance_count":len(instances),"connection_count":len(connections),
              "rendered_instances":sorted(core_instances if core_only else instances),
              "label_font_pt":label_font,
              "shape_count":len(shapes),"unrendered_shape_types":sorted(skipped),
              "view":"core crop" if core_only else "complete testbench",
              "png":str(prefix.with_suffix(".png")),"svg":str(prefix.with_suffix(".svg")),
              "rendering_description":("Core crop of the actual native testbench; external source symbol primitives and pins are omitted while native core wires and net labels are retained. " if core_only else "Complete native testbench. Source symbols retain all exported master primitives; actual source type and settings are identified by their CDF captions. ")+"Rendered locally from exported OA symbol primitives, wires, signal labels, instance orientations and actual CDF properties. Nonprinting boundaries, unresolved dynamic labels and standalone instructional notes are omitted for readability. This is a source-geometry rendering, not a GUI screenshot."}
    if arcs:
        metadata["auxiliary_source_audits"]=[{"source":str(arc_audit),"sha256":hashlib.sha256(arc_audit.read_bytes()).hexdigest()}]
    prefix.with_suffix(".json").write_text(json.dumps(metadata,indent=2)+"\n")
    return metadata


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("audit",type=Path);p.add_argument("output_prefix",type=Path)
    p.add_argument("--kind",choices=("active","passive"))
    p.add_argument("--core-only",action="store_true")
    args=p.parse_args();print(json.dumps(render(args.audit,args.output_prefix,args.kind,args.core_only),indent=2))
