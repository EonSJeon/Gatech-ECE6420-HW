#!/usr/bin/env python3
"""Bind an already captured, actual GUI PNG to its saved native schematic audit.

This records supplied capture evidence; it does not capture, edit, synthesize,
or render an image, run simulation, regenerate TeX, compile PDF, or sync Git.
The screenshot itself must have been captured and inspected by the operator.
"""
from __future__ import annotations
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bind(root,kind,image,capture_utc,capture_app,capture_attachment,role="testbench",origin="cadence_gui_screenshot",export_method=None,export_receipt=None,presentation_audit=None):
    root=Path(root).resolve();image=Path(image).resolve()
    if kind not in {"active","passive"} or role not in {"core","testbench"}:raise ValueError("Unknown schematic kind/role")
    if not image.is_relative_to(root) or not image.is_file() or image.suffix.lower()!=".png":
        raise ValueError("Supply the inspected actual PNG already saved within HW09")
    if not image.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):raise ValueError("Actual PNG file required")
    capture=datetime.fromisoformat(capture_utc.replace("Z","+00:00"))
    if capture.tzinfo is None or capture.utcoffset().total_seconds()!=0:raise ValueError("Record the actual capture time in UTC")
    if not capture_app.strip() or not capture_attachment.strip():raise ValueError("Actual app and attachment evidence required")
    if origin not in {"cadence_gui_screenshot","cadence_gui_export"}:raise ValueError("Actual GUI capture/export origin required")
    if origin=="cadence_gui_export" and not export_method:raise ValueError("Record the actual native export method")
    audit=root/"cadence"/(kind+"_tb_audit.tsv")
    metadata={"origin":origin,"kind":kind,"role":role,
              "view":"actual GUI "+role,"source_audit":str(audit),"source_sha256":sha(audit),
              "png":str(image),"image_sha256":sha(image),"capture_utc":capture_utc,
              "capture_app":capture_app,"capture_attachment":capture_attachment,
              "rendering_description":"Actual Virtuoso GUI "+("native image export" if origin=="cadence_gui_export" else "screenshot")+" of the saved "+kind+" mixer "+role+". Exact device values and D/G/S/B connections are listed in the accompanying tables."}
    if export_method:metadata["export_method"]=export_method
    metadata["auxiliary_source_audits"]=[]
    if export_receipt:
        receipt=(root/export_receipt).resolve()
        if not receipt.is_relative_to(root) or not receipt.is_file():raise ValueError("Missing native export receipt")
        rows=[line.split("\t") for line in receipt.read_text().splitlines()]
        rows=[r for r in rows if len(r)==8 and r[:5]==["export",kind,role,"cadence_gui_export",export_method]
              and Path(r[5]).name==image.name]
        if len(rows)!=1:raise ValueError("Native export receipt does not identify this image exactly once")
        metadata["native_export_record"]=rows[0]
        metadata["auxiliary_source_audits"].append({"source":str(receipt),"sha256":sha(receipt)})
    elif origin=="cadence_gui_export" and export_method=="hiExportImage":
        raise ValueError("hiExportImage requires its actual GUI export receipt")
    if presentation_audit:
        proof=(root/presentation_audit).resolve()
        if not proof.is_relative_to(root) or not proof.is_file():raise ValueError("Missing electrical presentation proof")
        rows=[line.split("\t") for line in proof.read_text().splitlines()]
        before=[r[2] for r in rows if r[:2]==["before",kind]]
        after=[r[2] for r in rows if r[:2]==["after",kind]]
        if len(before)!=1 or before!=after or not any(r[:3]==["unchanged",kind,"t"] for r in rows):
            raise ValueError("Electrical values/connections changed during presentation")
        metadata["presentation_electrical_unchanged"]=True
        metadata["auxiliary_source_audits"].append({"source":str(proof),"sha256":sha(proof)})
    suffix="gui_export" if origin=="cadence_gui_export" else "gui_screenshot"
    output=root/"results/cadence_gui/schematics"/(kind+"_"+suffix+".json")
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(metadata,indent=2)+"\n")
    return output


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind",choices=("active","passive"));parser.add_argument("image",type=Path)
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--role",choices=("core","testbench"),default="testbench")
    parser.add_argument("--origin",choices=("cadence_gui_screenshot","cadence_gui_export"),default="cadence_gui_screenshot")
    parser.add_argument("--export-method")
    parser.add_argument("--export-receipt",type=Path)
    parser.add_argument("--presentation-audit",type=Path)
    parser.add_argument("--capture-utc",required=True);parser.add_argument("--capture-app",required=True)
    parser.add_argument("--capture-attachment",required=True)
    args=parser.parse_args()
    print(bind(args.root,args.kind,args.image,args.capture_utc,args.capture_app,args.capture_attachment,args.role,args.origin,args.export_method,args.export_receipt,args.presentation_audit))
