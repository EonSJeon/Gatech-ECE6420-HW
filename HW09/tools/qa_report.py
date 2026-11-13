#!/usr/bin/env python3
"""Render an already-created HW09 PDF and check structural layout bounds.

This reads PDF pages and writes only PNG previews plus a JSON audit. Visual
inspection remains necessary for text inside rasterized scientific figures.
"""
from __future__ import annotations
import argparse
import json
import math
import shutil
import subprocess
from pathlib import Path
import pymupdf as fitz
from PIL import Image,ImageOps,ImageDraw


def inspect(pdf,output_dir,dpi=135):
    pdf=Path(pdf).resolve();output_dir=Path(output_dir).resolve()
    output_dir.mkdir(parents=True,exist_ok=True)
    audit={"source_pdf":str(pdf),"render_dpi":dpi,"pages":[],"out_of_page_spans":[],"body_empty_pages":[]}
    thumbs=[]
    with fitz.open(pdf) as doc:
        audit["page_count"]=len(doc)
        renderer=shutil.which("pdftoppm")
        if renderer is None:
            raise RuntimeError("Poppler pdftoppm is required for report rendering.")
        audit["renderer"]="Poppler pdftoppm"
        subprocess.run([renderer,"-r",str(dpi),"-png",str(pdf),str(output_dir/"poppler-page")],
                       check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        page_digits=len(str(len(doc)))
        for i,page in enumerate(doc):
            spans=[s for b in page.get_text("dict")["blocks"] for l in b.get("lines",[]) for s in l["spans"] if s["text"].strip()]
            body=[s for s in spans if 44<s["bbox"][1]<page.rect.height-44]
            for s in spans:
                r=fitz.Rect(s["bbox"])
                if r.x0<-.5 or r.y0<-.5 or r.x1>page.rect.width+.5 or r.y1>page.rect.height+.5:
                    audit["out_of_page_spans"].append({"page":i+1,"text":s["text"],"bbox":list(r)})
            image_path=output_dir/f"page-{i+1:02d}.png"
            rendered_path=output_dir/f"poppler-page-{i+1:0{page_digits}d}.png"
            rendered_path.replace(image_path)
            text=" ".join(s["text"] for s in body)
            if len(text.strip())<40:audit["body_empty_pages"].append(i+1)
            audit["pages"].append({"page":i+1,"body_text_characters":len(text),
                "min_body_font_pt":min((s["size"] for s in body),default=None),
                "raster_images":len(page.get_images()),"render":str(image_path),
                "opening_text":text[:180]})
            with Image.open(image_path) as im:
                image=im.convert("RGB");image.thumbnail((300,425))
                tile=Image.new("RGB",(316,456),"#E8ECEE")
                tile.paste(image,((316-image.width)//2,10))
                ImageDraw.Draw(tile).text((12,436),f"Page {i+1}",fill="#17384A")
                thumbs.append(tile)
    columns=4;rows=math.ceil(len(thumbs)/columns)
    sheet=Image.new("RGB",(columns*316,rows*456),"white")
    for i,thumb in enumerate(thumbs):sheet.paste(thumb,((i%columns)*316,(i//columns)*456))
    sheet.save(output_dir/"contact-sheet.png")
    audit["contact_sheet"]=str(output_dir/"contact-sheet.png")
    audit["structural_layout_passed"]=not audit["out_of_page_spans"] and not audit["body_empty_pages"]
    (output_dir/"qa.json").write_text(json.dumps(audit,indent=2)+"\n")
    return audit


if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("pdf",type=Path)
    ap.add_argument("--output-dir",type=Path,required=True);ap.add_argument("--dpi",type=int,default=135)
    args=ap.parse_args();result=inspect(args.pdf,args.output_dir,args.dpi)
    print(json.dumps({k:result[k] for k in ("page_count","out_of_page_spans","body_empty_pages","structural_layout_passed","contact_sheet")},indent=2))
