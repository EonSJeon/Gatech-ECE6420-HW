#!/usr/bin/env python3
"""Bind observed GUI actions to actual completed ADE files, never planned paths."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import sys


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_figures(root):
    """Prefer a complete real-capture pair; never mix partial captures with renders."""
    base=root/'results/cadence_gui/schematics'
    exports=[base/(kind+'_gui_export.json') for kind in ('active','passive')]
    captures=[base/(kind+'_gui_screenshot.json') for kind in ('active','passive')]
    if any(p.is_file() for p in exports):
        if not all(p.is_file() for p in exports):
            raise ValueError('Both actual native schematic export metadata files are required')
        paths=exports
    elif any(p.is_file() for p in captures):
        if not all(p.is_file() for p in captures):
            raise ValueError('Both actual native schematic screenshot metadata files are required')
        paths=captures
    else:
        paths=[base/(kind+'_'+view+'.json') for kind in ('active','passive')
               for view in ('testbench','core') if (base/(kind+'_'+view+'.json')).is_file()]
    figures=[]
    for meta_path in paths:
        meta=json.loads(meta_path.read_text());source=Path(meta['source_audit'])
        png=Path(meta.get('png') or meta['image_path'])
        if not source.is_absolute():source=root/source
        if not png.is_absolute():png=root/png
        source=source.resolve();png=png.resolve()
        if not source.is_relative_to(root) or not png.is_relative_to(root):
            raise ValueError('Native schematic figure provenance escapes project')
        if sha(source)!=meta['source_sha256']:raise ValueError('Actual native source audit changed')
        if meta.get('image_sha256') and sha(png)!=meta['image_sha256']:
            raise ValueError('Actual native schematic image changed after capture')
        figure={k:v for k,v in meta.items() if k not in ('png','source_audit','auxiliary_source_audits')}
        figure.update(image_path=str(png.relative_to(root)),source_audit=str(source.relative_to(root)),
                      image_sha256=sha(png),auxiliary_source_audits=[])
        figure.setdefault('kind',meta_path.name.split('_',1)[0])
        figure.setdefault('origin','native_oa_geometry_local_render')
        for aux in meta.get('auxiliary_source_audits',[]):
            actual=Path(aux['source']);actual=actual if actual.is_absolute() else root/actual
            if sha(actual)!=aux['sha256']:raise ValueError('Actual native arc audit changed')
            figure['auxiliary_source_audits'].append({'source':str(actual.relative_to(root)),'sha256':aux['sha256']})
        figures.append(figure)
    return figures


def bind(project,history,action_utc,description,output=None,allow_partial=False,plot_metadata_dir=None,comparison_path=None):
    root=Path(project).resolve();sys.path.insert(0,str(root/'tools'))
    import cadence_import as gui
    if not re.fullmatch(r'Interactive\.\d+',history):raise ValueError('Invalid actual GUI history')
    planning_path=root/'cadence/cadence_gui_manifest.json';plan=json.loads(planning_path.read_text())
    base=root/'simulation/cadence_gui/HW09_Mixers/mixer_campaign/maestro/results/maestro'/history/'1'
    result={'schema_version':1,'origin':'cadence_ade_gui','history':history,'config':plan['config'],
            'simulation_trigger':'Observed ADE Assembler GUI Run; no scripted simulation start',
            'gui_action_utc':action_utc,'gui_action_description':description,
            'planning_manifest':'cadence/cadence_gui_manifest.json','planning_manifest_sha256':sha(planning_path),
            'max_concurrent_jobs':2,'runs':[],'pending':[],'native_schematic_figures':[],
            'excluded_diagnostic_histories':['Interactive.0'],
            'bound_utc':datetime.now(timezone.utc).isoformat()}
    for planned in plan['runs']:
        test=base/planned['test_name'];log=test/'psf/spectre.out';ascii_dir=test/'ascii'
        try:
            if not log.is_file() or not re.search(r'spectre completes with\s+0 errors',log.read_text(errors='replace'),re.I):
                raise ValueError('Actual native zero-error completion log not available')
            stage=planned['stage']
            suffix='.pac' if stage in {'pac_usb','pac_image'} else '.pnoise' if stage=='pnoise' else '.tran'
            candidates=list(ascii_dir.glob('*'+suffix))
            if suffix=='.pac':
                candidates=[p for p in candidates if re.search(r'^"harmonic"\s+-1\s*$',
                    p.read_text().split('\nVALUE\n',1)[0],re.M)]
            if len(candidates)!=1:raise ValueError('Expected one actual '+suffix+' result (PAC requires explicit harmonic−1), found '+str(len(candidates)))
            psf=candidates[0];conversion_path=Path(str(psf)+'.conversion.json')
            conversion=json.loads(conversion_path.read_text())
            native=root/conversion['source']
            if sha(native)!=conversion['source_sha256'] or sha(psf)!=conversion['ascii_sha256']:
                raise ValueError('Native/converted result hash changed')
            record={**planned,'origin':'cadence_ade_gui','gui_action_utc':action_utc,
                    'gui_action_description':description,'psf':str(psf.relative_to(root)),
                    'native_psf':str(native.relative_to(root)),
                    'generated_netlist':str((test/'netlist/input.scs').relative_to(root)),
                    'spectre_log':str(log.relative_to(root)),
                    'schematic_export':'cadence/'+planned['kind']+'_tb_audit.tsv'}
            record.update(gui.verify_gui_record(root,record));result['runs'].append(record)
        except (ValueError,FileNotFoundError,KeyError) as exc:
            result['pending'].append({'test_name':planned['test_name'],'stage':planned['stage'],'reason':str(exc)})
    result['native_schematic_figures']=source_figures(root)
    result['test_count']=len({r['test_name'] for r in result['runs']})
    result['run_record_count']=len(result['runs'])
    result['status']='bound_complete' if not result['pending'] and result['test_count']==56 and result['run_record_count']==58 else 'partial'
    if result['status']!='bound_complete' and not allow_partial:
        raise ValueError('Actual GUI manifest incomplete: '+json.dumps(result['pending'][:5])+
                         '; '+str(result['test_count'])+' tests / '+str(result['run_record_count'])+' records')
    destination=Path(output or root/'cadence/gui_run_manifest.json')
    if not destination.is_absolute():destination=root/destination
    if plot_metadata_dir is not None:
        from cadence_gui_figures import KINDS,ROLES
        directory=Path(plot_metadata_dir);directory=directory if directory.is_absolute() else root/directory
        result['plot_figure_mode']='cadence_gui_export'
        result['numerical_plot_figures']=[json.loads((directory/(kind+'_'+role+'.json')).read_text())
                                         for kind in sorted(KINDS) for role in sorted(ROLES)]
    elif destination.is_file():
        previous=json.loads(destination.read_text())
        if previous.get('plot_figure_mode')=='cadence_gui_export':
            result['plot_figure_mode']='cadence_gui_export'
            result['numerical_plot_figures']=previous.get('numerical_plot_figures',[])
    if comparison_path is not None:
        path=Path(comparison_path);path=path if path.is_absolute() else root/path;path=path.resolve()
        if not path.is_relative_to(root):raise ValueError('Native comparison evidence must be inside HW09')
        result['native_plot_comparison']={'path':str(path.relative_to(root)),'sha256':sha(path)}
    elif destination.is_file():
        previous=json.loads(destination.read_text())
        if previous.get('native_plot_comparison'):result['native_plot_comparison']=previous['native_plot_comparison']
    if result.get('plot_figure_mode')=='cadence_gui_export':
        from cadence_gui_figures import validate as validate_gui_figures
        mixer,_=gui.baseline_modules(root)
        source_view={**result,'run_id':'cadence_gui_'+mixer.fingerprint(plan['config'])[:12],
                     'circuits':{kind:{'runs':[r for r in result['runs'] if r['kind']==kind]}
                                 for kind in ('active','passive')}}
        validate_gui_figures(root,source_view)
    destination.write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True,type=Path)
    p.add_argument('--history',required=True);p.add_argument('--action-utc',required=True)
    p.add_argument('--description',required=True);p.add_argument('--output',type=Path)
    p.add_argument('--gui-plot-metadata-dir',type=Path,help='Directory with all12 actual kind_role.json ViVA export metadata files')
    p.add_argument('--native-plot-comparison',type=Path,help='Optional independent native calculator comparison JSON')
    p.add_argument('--allow-partial',action='store_true');a=p.parse_args()
    r=bind(a.root,a.history,a.action_utc,a.description,a.output,a.allow_partial,a.gui_plot_metadata_dir,a.native_plot_comparison)
    print(json.dumps({k:r[k] for k in ('status','test_count','run_record_count','pending')}))
