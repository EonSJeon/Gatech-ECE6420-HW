#!/usr/bin/env python3
"""Convert an actual native ADE PSF file to 17-digit ASCII using Cadence psf.

Run on the school server. Original binary data remains untouched. Conversion
metadata records both hashes and the exact official-tool invocation. No plot
is generated or imported.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess

PSF_TOOL="/tools/software/cadence/ic/latest/tools/dfII/bin/psf"


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def convert(source,destination,tool=PSF_TOOL):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if not source.is_file():raise FileNotFoundError(source)
    if source==destination:raise ValueError("Do not overwrite the native ADE PSF")
    destination.parent.mkdir(parents=True,exist_ok=True)
    command=[str(tool),"-f","%.17g","-i",str(source),"-o",str(destination)]
    proc=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=120)
    if proc.returncode:raise RuntimeError("Official PSF conversion failed: "+proc.stderr+proc.stdout)
    text=destination.read_text()
    if "\nVALUE\n" not in text or not text.startswith("HEADER\n"):
        raise ValueError("PSF converter did not create a readable HEADER/VALUE result")
    evidence={"status":"complete","origin":"actual_ADE_PSF_lossless_text_conversion",
        "source":str(source),"source_sha256":sha(source),
        "ascii":str(destination),"ascii_sha256":sha(destination),
        "double_precision_format":"%.17g","command":command,
        "completed_utc":datetime.now(timezone.utc).isoformat(),
        "stdout":proc.stdout,"stderr":proc.stderr}
    destination.with_suffix(destination.suffix+".conversion.json").write_text(json.dumps(evidence,indent=2)+"\n")
    return evidence


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("source",type=Path);p.add_argument("destination",type=Path)
    p.add_argument("--tool",default=PSF_TOOL)
    a=p.parse_args();print(json.dumps(convert(a.source,a.destination,a.tool),indent=2))
