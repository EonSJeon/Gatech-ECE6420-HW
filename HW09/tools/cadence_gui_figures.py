"""Bind and verify already captured native ViVA images; never render plots.

The operator must inspect the actual capture/export and supply its evidence.
Metadata cannot establish an unobserved GUI action or prove image content.
"""
from __future__ import annotations
from datetime import datetime
import hashlib
import json
from pathlib import Path

KINDS={'active','passive'}
ROLES={'transient','spectrum','twotone_spectrum','compression','iip3','noise'}
STAGES={'transient':{'single_tone'},'spectrum':{'single_tone'},
        'twotone_spectrum':{'tight_two_tone'},'compression':{'compression'},
        'iip3':{'two_tone'},'noise':{'pnoise'}}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inside(root,relative):
    path=(Path(root).resolve()/relative).resolve()
    if not path.is_relative_to(Path(root).resolve()) or not path.is_file():
        raise ValueError('Missing or out-of-project GUI figure source: '+str(relative))
    return path


def source_records(root,result,kind,role):
    if kind not in KINDS or role not in ROLES:raise ValueError('Unknown native plot kind/role')
    records=[r for r in result['circuits'][kind]['runs'] if r['stage'] in STAGES[role]
             and (role!='noise' or r.get('sidebands')==63)]
    expected=14 if role=='compression' else 7 if role=='iip3' else 1
    if len(records)!=expected:raise ValueError('Incomplete actual native sources for '+kind+'/'+role)
    sources=[]
    for r in records:
        row={k:r[k] for k in ('test_name','stage','psf','psf_sha256','native_psf',
                              'generated_netlist','generated_netlist_sha256')}
        for key in ('psf','generated_netlist'):
            if sha(inside(root,row[key]))!=row[key+'_sha256']:
                raise ValueError('Actual GUI numerical/source hash changed: '+row[key])
        row['native_psf_sha256']=sha(inside(root,row['native_psf']))
        conversion_path=inside(root,row['psf']+'.conversion.json')
        conversion=json.loads(conversion_path.read_text())
        if (row['native_psf_sha256']!=conversion['source_sha256']
                or row['psf_sha256']!=conversion['ascii_sha256']):
            raise ValueError('Native/converted numerical hashes disagree for GUI plot source')
        row['conversion_evidence']=str(conversion_path.relative_to(Path(root).resolve()))
        row['conversion_evidence_sha256']=sha(conversion_path)
        if 'pin_dbm' in r:row['pin_dbm']=r['pin_dbm']
        if 'sidebands' in r:row['sidebands']=r['sidebands']
        sources.append(row)
    return sources


def bind(root,result,kind,role,image,capture_utc,capture_app,capture_attachment,
         expression,x_axis,y_axis,description,export_method,export_receipt=None,calculator_audit=None):
    root=Path(root).resolve();image=inside(root,image)
    observed=datetime.fromisoformat(capture_utc.replace('Z','+00:00'))
    if observed.tzinfo is None or observed.utcoffset().total_seconds()!=0:
        raise ValueError('Actual capture time must explicitly use UTC')
    for field,value in {'capture_app':capture_app,'capture_attachment':capture_attachment,
                        'expression':expression,'x_axis':x_axis,'y_axis':y_axis,
                        'rendering_description':description,'export_method':export_method}.items():
        if not isinstance(value,str) or not value.strip():raise ValueError('Actual GUI plot evidence required: '+field)
    if image.suffix.lower()!='.png' or not image.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Already captured portable PNG required; this helper does not create images')
    if export_method!='saveGraphImage':
        raise ValueError('Numerical GUI export mode requires the actual native saveGraphImage method')
    metadata={'schema_version':1,'origin':'cadence_gui_export','kind':kind,'role':role,
            'image_path':str(image.relative_to(root)),'image_sha256':sha(image),
            'capture_utc':capture_utc,'capture_app':capture_app,'capture_attachment':capture_attachment,
            'export_method':export_method,'source_run_id':result['run_id'],
            'source_records':source_records(root,result,kind,role),'expression':expression,
            'x_axis':x_axis,'y_axis':y_axis,'rendering_description':description}
    if not export_receipt or not calculator_audit:
        raise ValueError('Native saveGraphImage exports require original export and calculator receipts')
    for field,value in (('export_receipt',export_receipt),('calculator_audit',calculator_audit)):
        if value:
            path=inside(root,value);metadata[field]=str(path.relative_to(root));metadata[field+'_sha256']=sha(path)
    if export_receipt:
        rows=[line.split('\t') for line in inside(root,export_receipt).read_text().splitlines()]
        if not any(x[:2]==['SOURCE_RUN',result['run_id']] for x in rows):
            raise ValueError('Native export receipt identifies another numerical campaign')
        exports=[x for x in rows if len(x)>=7 and x[0]=='EXPORT' and x[3:5]==[kind,role]]
        if not exports:raise ValueError('Native export receipt does not contain this actual plot role')
        actual=exports[-1]
        if Path(actual[5]).name!=image.name or '\t'.join(actual[6:])!=expression:
            raise ValueError('Actual native export receipt image/expression differs from supplied metadata')
        metadata['native_export_time_raw']=actual[1];metadata['native_window']=actual[2]
        directories=[x[3].rstrip('/') for x in rows if len(x)>=4 and x[:3]==['SOURCE',kind,role]]
        for record in metadata['source_records']:
            suffix='/'+str(Path(record['native_psf']).parent)
            if not any(x.endswith(suffix) for x in directories):
                raise ValueError('Native export receipt is missing an actual numerical source directory')
    return metadata


def validate(root,result,figures=None):
    figures=result.get('numerical_plot_figures',[]) if figures is None else figures
    found=set()
    for spec in figures:
        kind,role=spec.get('kind'),spec.get('role')
        if (kind,role) in found:raise ValueError('Duplicate actual GUI plot role')
        found.add((kind,role))
        if spec.get('origin')!='cadence_gui_export':raise ValueError('Actual native GUI-export origin required')
        if spec.get('source_run_id')!=result['run_id']:raise ValueError('GUI image belongs to another campaign')
        checked=bind(root,result,kind,role,spec['image_path'],spec['capture_utc'],spec['capture_app'],
                     spec['capture_attachment'],spec['expression'],spec['x_axis'],spec['y_axis'],
                     spec['rendering_description'],spec['export_method'],spec.get('export_receipt'),
                     spec.get('calculator_audit'))
        for field in ('image_sha256','source_records'):
            if spec.get(field)!=checked[field]:raise ValueError('Actual GUI figure evidence changed: '+field)
        for field in ('export_receipt','calculator_audit'):
            if spec.get(field) and spec.get(field+'_sha256')!=checked[field+'_sha256']:
                raise ValueError('Native GUI export receipt changed: '+field)
    wanted={(kind,role) for kind in KINDS for role in ROLES}
    if found!=wanted:raise ValueError('Complete12 native GUI plot roles required; missing='+str(sorted(wanted-found)))
    proof=result.get('native_plot_comparison')
    if proof:
        path=inside(root,proof['path'])
        if sha(path)!=proof['sha256']:raise ValueError('Independent native plot comparison changed')
        comparison=json.loads(path.read_text())
        if (comparison.get('origin')!='independent_native_Cadence_calculator_comparison'
                or comparison.get('source_run_id')!=result['run_id']
                or comparison.get('unique_measurement_count')!=88
                or comparison.get('comparison_tolerance',{}).get('passed') is not True
                or comparison.get('amplitudes_modified') is not False
                or comparison.get('metric_tables_modified') is not False):
            raise ValueError('Invalid independent native calculator comparison evidence')
        source=inside(root,comparison['source_audit'])
        if sha(source)!=comparison['source_audit_sha256']:
            raise ValueError('Native calculator source audit changed after independent comparison')
        if comparison.get('expected_check_input'):
            frozen=inside(root,comparison['expected_check_input'])
            if sha(frozen)!=comparison.get('expected_check_input_sha256'):
                raise ValueError('Frozen native calculator comparison-input JSON changed')
            original=json.loads(frozen.read_text())
            if original.get('origin')!='cadence_ade_gui' or original.get('run_id')!=result['run_id']:
                raise ValueError('Native calculator comparison input must be the actual GUI campaign')
        if any(spec.get('calculator_audit')!=comparison['source_audit'] for spec in figures):
            raise ValueError('Figure and independent comparison identify different native calculator audits')
    return {'origin':'cadence_gui_export','figure_count':len(figures),'roles':sorted(found)}
