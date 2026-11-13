#!/usr/bin/env python3
"""Record actual operator-inspected native ViVA PNG export evidence only."""
from pathlib import Path
import argparse,json
from cadence_gui_figures import bind,ROLES

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',required=True,type=Path);p.add_argument('--kind',required=True,choices=('active','passive'))
    p.add_argument('--role',required=True,choices=sorted(ROLES));p.add_argument('--image',required=True)
    for flag in ('capture-utc','capture-app','capture-attachment','expression','x-axis','y-axis','description','export-method'):
        p.add_argument('--'+flag,required=True)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--export-receipt');p.add_argument('--calculator-audit')
    a=p.parse_args();root=a.root.resolve()
    result=json.loads((root/'results/cadence_gui_results.json').read_text())
    spec=bind(root,result,a.kind,a.role,a.image,a.capture_utc,a.capture_app,a.capture_attachment,
              a.expression,a.x_axis,a.y_axis,a.description,a.export_method,a.export_receipt,a.calculator_audit)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(spec,indent=2)+'\n')
    print(str(a.output))

if __name__=='__main__':main()
