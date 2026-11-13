#!/usr/bin/env python3
"""Package only the verified editable Overleaf source for browser import.

No project-wide archive, CAD data, credentials, PDF compilation, or upload.
The default temporary ZIP is under HW09/tmp/. It is created only on explicit run.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

from build_cadence_tex import validate

ROOT=Path(__file__).resolve().parents[1]
INPUT=re.compile(r"\\(?:input|include)\s*\{([^{}]+)\}")
FIGURE=re.compile(r"\\(?:reportfigure|nativecorefigure|nativetestbenchfigure)\s*\{([^{}]+)\}|\\includegraphics(?:\[[^\]]*\])?\s*\{([^{}]+)\}")
BIB=re.compile(r"\\bibliography\s*\{([^{}]+)\}")
SECRET=re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\b(?:sk-proj-|sk-)[A-Za-z0-9_-]{20,}|\bgh[pousr]_[A-Za-z0-9]{30,}|\bAKIA[A-Z0-9]{16}\b|\bxox[baprs]-[A-Za-z0-9-]{20,}")


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def collect_source(source):
    """Resolve literal TeX includes and referenced PNGs within a strict whitelist."""
    source=Path(source).resolve()
    def checked(relative):
        if not re.fullmatch(r"[A-Za-z0-9_./-]+",relative):raise ValueError("Nonportable source filename")
        relative=Path(relative)
        if relative.is_absolute() or ".." in relative.parts:raise ValueError("Source reference escapes project")
        candidate=source/relative
        if candidate.is_symlink() or not candidate.resolve().is_relative_to(source) or not candidate.is_file():
            raise ValueError("Missing/unsafe source reference: "+str(relative))
        return candidate
    for path in source.rglob("*"):
        if path.is_symlink():raise ValueError("Source tree contains a symbolic link: "+str(path.relative_to(source)))
        if path.name in {".env",".remote.env","id_rsa","id_ed25519"} or path.suffix in {".key",".pem"}:
            raise ValueError("Credential-like file found in source tree")
    selected={checked(name) for name in ("main.tex","macros.tex","references.bib","README.md","build_manifest.json")}
    pending=[source/"main.tex",source/"macros.tex"];seen=set()
    while pending:
        path=pending.pop()
        if path in seen:continue
        seen.add(path);text=path.read_text()
        # Ignore comments, including commented-out optional figures/inputs.
        text="\n".join(re.split(r"(?<!\\)%",line,maxsplit=1)[0] for line in text.splitlines())
        for relative in INPUT.findall(text):
            if not relative.endswith(".tex"):relative+=".tex"
            ref=checked(relative)
            if ref.name not in {"main.tex","macros.tex"} and not ref.relative_to(source).as_posix().startswith("sections/"):
                raise ValueError("Only maintained section includes may be packaged")
            selected.add(ref);pending.append(ref)
        for first,second in FIGURE.findall(text):
            relative=first or second
            if "#" in relative:continue  # Parameterized include inside the maintained reportfigure macro.
            if not relative.startswith("figures/"):relative="figures/"+relative
            ref=checked(relative)
            if ref.suffix.lower()!=".png" or not ref.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("Only local PNG figures may be packaged")
            selected.add(ref)
        for names in BIB.findall(text):
            if names!="references":raise ValueError("Put bibliography entries in the maintained references.bib")
    manifest=json.loads((source/"build_manifest.json").read_text())
    if manifest.get("origin")!="verified_cadence_ade_gui_tex_source" or manifest.get("compiled_pdf") is not False:
        raise ValueError("Expected verified source-only build manifest")
    for path in selected:
        relative=path.relative_to(source).as_posix()
        if path.suffix.lower()==".png":
            evidence=manifest.get("figures",{}).get(path.name)
            if not evidence or digest(path)!=evidence.get("sha256"):raise ValueError("Figure differs from the generated data-derived source")
        elif SECRET.search(path.read_text()):raise ValueError("Credential-like content found in source text; nothing packaged")
        if relative not in {"main.tex","macros.tex","references.bib","README.md","build_manifest.json"} and not (relative.startswith("sections/") and path.suffix==".tex") and not (relative.startswith("figures/") and path.suffix.lower()==".png"):
            raise ValueError("File outside source whitelist")
    return sorted(selected)


def package(root=ROOT,output=None,replace=False):
    root=Path(root).resolve();source=root/"overleaf"
    if source.is_symlink():raise ValueError("Overleaf source directory must be inside HW09")
    result,_,result_path=validate(root)
    files=collect_source(source)
    manifest=json.loads((source/"build_manifest.json").read_text())
    if manifest.get("gui_results_sha256")!=digest(result_path) or manifest.get("run_id")!=result["run_id"]:
        raise ValueError("Regenerate TeX from the current completed GUI campaign before packaging")
    target=Path(output).resolve() if output else root/"tmp/overleaf_hw09_source.zip"
    allowed=(root/"tmp").resolve()
    if not allowed.is_relative_to(root) or (root/"tmp").is_symlink():
        raise ValueError("Temporary source directory must stay inside HW09 without a symbolic link")
    if not target.is_relative_to(allowed) or target.suffix.lower()!=".zip":
        raise ValueError("Temporary source ZIP must be under HW09/tmp/")
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists() and not replace:raise FileExistsError("Source ZIP exists; use --replace explicitly")
    with zipfile.ZipFile(target,"w" if replace else "x",compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:archive.write(path,path.relative_to(source).as_posix())
    print("Source-only browser-import ZIP: "+str(target))
    print("Included %d source/PNG files; no CAD/raw logs/credentials/PDF/upload." % len(files))
    return target


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--replace",action="store_true")
    args=parser.parse_args()
    package(args.root,args.output,args.replace)
