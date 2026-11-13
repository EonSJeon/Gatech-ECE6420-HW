#!/usr/bin/env python3
"""Independent numerical and native-source audit for actual GUI measurements.

Reuses established pure numerical checks from validate_results.py without
calling its CLI, global baseline checks, or writer. The only output is the
separate results/cadence_gui_validation.json file.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
import numpy as np


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate(project):
    root=Path(project).resolve();sys.path.insert(0,str(root/'tools'))
    import cadence_import as gui
    from audit_native_schematic import audit as audit_native,number
    spec=importlib.util.spec_from_file_location('hw09_independent_numerics',root/'tools/validate_results.py')
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    result_path=root/'results/cadence_gui_results.json';result=json.loads(result_path.read_text())
    cfg=result['config'];fp=old.fingerprint(cfg);audit=old.Audit()
    def global_gui():
        old.require(result.get('origin')=='cadence_ade_gui' and result.get('status')=='complete',
                    'Actual GUI campaign must be complete; no baseline substitution')
        old.require(set(result['circuits'])=={'active','passive'},'Both GUI circuits required')
        old.require(sha(root/result['source_manifest'])==result['source_manifest_sha256'],'Actual GUI manifest changed')
        old.require(sha(root/result['baseline']['path'])==result['baseline']['sha256'],'Immutable baseline changed')
        old.require(fp in result['run_id'] or fp[:12] in result['run_id'],'GUI configuration fingerprint mismatch')
        return {'origin':result['origin'],'run_id':result['run_id'],'baseline_preserved':True}
    audit.check('gui_campaign.provenance',global_gui)
    if result.get('plot_figure_mode')=='cadence_gui_export':
        from cadence_gui_figures import validate as validate_gui_figures
        audit.check('gui_campaign.native_ViVA_export_figures',lambda:validate_gui_figures(root,result))
    elif result.get('plot_figure_mode') or result.get('numerical_plot_figures'):
        audit.check('gui_campaign.figure_mode',lambda:old.require(False,'Unknown or missing explicit GUI plot mode'))
    def native_deck(run):
        text=(root/run['generated_netlist']).read_text().replace('\\\n',' ')
        elements=old.read_deck(text);kind=run['kind'];p,c=cfg[kind],cfg['common']
        params={}
        for line in text.splitlines():
            if line.startswith('parameters '):params.update({k:number(v) for k,v in old.PARAMETER.findall(line)})
        wanted=({'M1':['tail','rf','0','0'],'M2':['outp','lop','tail','0'],'M3':['outn','lon','tail','0']}
                if kind=='active' else {'M1':['outp','lop','rf','0'],'M2':['outn','lon','rf','0']})
        old.require({n for n in elements if n.startswith('M')}==set(wanted),'Generated native MOS count changed')
        for name,nodes in wanted.items():
            e=elements[name];old.require(e['nodes']==nodes and e['model']=='NMOS_VTH','Generated native D/G/S/B/model differs')
            w=(p['gm_width_um'] if kind=='active' and name=='M1' else p['switch_width_um'])*1e-6
            for key,value in {'w':w,'l':p['length_nm']*1e-9,'m':1.,'ls':105e-9,'ld':105e-9,
                              'as':w*105e-9,'ad':w*105e-9,'ps':w+210e-9,'pd':w+210e-9}.items():
                old.close(number(e['params'][key]),value,name+'.'+key,atol=1e-22)
        for name,node in (('R1','outp'),('R2','outn')):
            old.require(elements[name]['nodes']==(['vdd',node] if kind=='active' else [node,'0']),'Native branch load connectivity changed')
            old.close(number(elements[name]['params']['r']),p['rd_ohm' if kind=='active' else 'rl_ohm'],'Native branch resistance')
        for name,node in (('CLP','outp'),('CLN','outn')):
            old.require(elements[name]['nodes']==[node,'0'],'Native CL terminal changed')
            old.close(number(elements[name]['params']['c']),c['load_cap_f'],'Native output capacitance',atol=1e-22)
        rf,second=elements['RFPORT'],elements['RFSECOND']
        old.require(rf['nodes']==['rfdrive','0'] and second['nodes']==['rf','rfdrive'],'Native RF source chain changed')
        old.close(number(rf['params']['r']),c['rs_ohm'],'Native RF source resistance')
        bias=p['rf_bias_v' if kind=='active' else 'rf_common_mode_v']
        old.close(number(rf['params']['dc'])*2,bias,'Native matched-port source DC')
        old.close(number(rf['params']['pacmag']),.5,'Native matched PAC magnitude')
        old.close(number(rf['params']['noisetemp']),16.85,'Native RF noise temperature')
        for name,node,phase in (('LOP','lop',0),('LON','lon',180)):
            e=elements[name];old.require(e['nodes']==[node,'0'],'Native LO terminal changed')
            for key,value in {'dc':p['lo_common_mode_v'],'freq':c['lo_hz'],
                              'ampl':p['lo_vpp_per_leg']/2,'sinephase':phase}.items():
                old.close(number(e['params'][key]),value,'Native LO '+key)
        if 'pin_dbm' in run:
            old.close(params['pinDbm'],run['pin_dbm'],'Native actual Pin design variable')
        periodic=run['stage'] in {'pnoise','pac_usb','pac_image'}
        two=run['stage'] in {'two_tone','tight_two_tone'}
        old.close(params['rfScale'],0 if periodic else 1,'Native rfScale')
        old.close(params['tone2Scale'],1 if two else 0,'Native second-tone scale')
        openpk=math.sqrt(8*c['rs_ohm']*.001*10**(params['pinDbm']/10))
        old.close(number(rf['params']['ampl'],params),0 if periodic else openpk/2,'Native source amplitude',atol=1e-14)
        old.close(number(second['params']['ampl'],params),openpk if two else 0,'Native second-tone amplitude',atol=1e-14)
        frequencies=cfg['analysis']['rf_tones_hz'] if two else [c['rf_hz'],c['rf_hz']]
        old.close([number(rf['params']['freq'],params),number(second['params']['freq'],params)],frequencies,'Native RF frequency variables')
        return {'native_DGSB_and_values_checked':True,'actual_design_variables':params}
    def source_run(run):
        hashes=gui.verify_gui_record(root,run)
        for key,value in hashes.items():old.require(run[key]==value,'GUI source/PSF hash changed: '+key)
        old.require(run.get('gui_action_utc') and run.get('gui_action_description'),'Observed GUI action missing')
        if run.get('native_psf'):
            conversion=json.loads((root/(run['psf']+'.conversion.json')).read_text())
            old.require(sha(root/run['native_psf'])==conversion['source_sha256'],'Original binary native PSF changed')
            old.require(sha(root/run['psf'])==conversion['ascii_sha256'],'Converted actual PSF changed')
        return native_deck(run)
    def run_projection(run):
        m=run['measurement'];x,data=gui.read_psf_gui(root/run['psf'])
        step=m['strobe_s'];n=m['sample_count'];target=(round(m['settle_s']/step)+np.arange(n))*step
        index=np.clip(np.searchsorted(x,target),0,len(x)-1);left=np.maximum(index-1,0)
        index=np.where(abs(x[left]-target)<abs(x[index]-target),left,index)
        old.require(len(set(index.tolist()))==n and max(abs(x[index]-target))<step*1e-4,'Actual raw PSF grid missing')
        alias={'outp':'outp','outn':'outn','rf':'rf','supply_current':'VDD:p'};alias.update(run.get('trace_names',{}))
        out=data[alias['outp']][index]-data[alias['outn']][index]
        fund=[old.project(target,out,f) for f in m['if_frequencies_hz']]
        im3=[old.project(target,out,f) for f in m['im3_frequencies_hz']]
        old.close(m['fund_vpk'],fund,'Independent raw-PSF fundamental',atol=1e-14)
        old.close(m['im3_vpk'],im3,'Independent raw-PSF IM3',atol=1e-16)
        if run['kind']=='active':
            power=-float(data[alias['supply_current']][index].mean())*cfg['common']['vdd_v']*1e3
            old.close(m['power_mw'],power,'Independent raw-PSF core power')
        old.require(m['settings_match_intended_limits'],'Effective numerical setting mismatch')
        text=(root/run['psf']).read_text().split('\nVALUE\n',1)[0]
        for key in ('reltol','maxstep'):
            hit=re.search(r'^"'+key+r'"\s+('+gui.NUMBER.pattern+r')\s*$',text,re.M)
            old.require(hit is not None,'Actual effective '+key+' missing')
            old.close(m['psf_header_'+key],float(hit[1]),'Actual effective '+key)
        return {'sample_count':n,'fundamental_from_actual_PSF':fund,'IM3_from_actual_PSF':im3}
    def raw_noise(kind,row,arrays):
        runs=row['runs'];c=cfg['common'];freq=np.asarray(cfg['analysis']['noise_frequency_hz'])
        def one(stage):
            values=[r for r in runs if r['stage']==stage];old.require(len(values)==1,'Exactly one '+stage+' required');return values[0]
        u=one('pac_usb');i=one('pac_image')
        for run in (u,i):
            header=(root/run['psf']).read_text().split('\nVALUE\n',1)[0]
            old.require(re.search(r'^"harmonic"\s+-1\s*$',header,re.M) is not None,
                        'Actual PAC result must explicitly identify harmonic -1')
            old.require(re.search(r'^"freqaxis"\s+"in"\s*$',header,re.M) is not None,
                        'Actual PAC result must use the input-frequency axis')
        fu,du=gui.read_psf_gui(root/u['psf'],axis='freq',names=['outp','outn'],complex_values=True)
        fi,di=gui.read_psf_gui(root/i['psf'],axis='freq',names=['outp','outn'],complex_values=True)
        usb=du['outp']-du['outn'];image=(di['outp']-di['outn'])[::-1]
        old.close(fu,c['lo_hz']+freq,'Actual USB PAC frequency',atol=.01)
        old.close(fi,c['lo_hz']-freq[::-1],'Actual image PAC frequency',atol=.01)
        d=arrays['noise'];old.close(d['gain_open_usb_complex'],usb,'Raw desired PAC complex gain',atol=1e-13)
        old.close(d['gain_open_image_complex'],image,'Raw image PAC complex gain',atol=1e-13)
        ref=4*old.K_B*c['source_noise_temp_k']*c['rs_ohm'];ssb=[];dsb=[]
        for run in sorted((r for r in runs if r['stage']=='pnoise'),key=lambda r:r['sidebands']):
            f,v=gui.read_psf_gui(root/run['psf'],axis='freq',names=['out','NF','NFdsb'])
            old.close(f,freq,'Raw PNOISE frequency',atol=.01)
            header=(root/run['psf']).read_text().split('\nVALUE\n',1)[0]
            for field,value in {'positive output signal':'outp','negative output signal':'outn',
                                'input probe':'RFPORT'}.items():
                old.require(re.search(r'^"'+re.escape(field)+r'"\s+"'+value+r'"\s*$',header,re.M) is not None,
                            'Actual PNOISE '+field+' differs from native measurement topology')
            units=re.search(r'^"out"\s+"([^\"]+)"',header,re.M)
            old.require(units is not None,'Actual noise units missing')
            if units[1]=='V/sqrt(Hz)':psd=v['out']**2
            elif units[1]=='V^2/Hz':psd=v['out']
            else:raise ValueError('Unsupported actual native noise units')
            a=10*np.log10(psd/(ref*abs(usb)**2));b=10*np.log10(psd/(ref*(abs(usb)**2+abs(image)**2)))
            old.require(max(abs(a-v['NF']))<.12 and max(abs(b-v['NFdsb']))<.12,'Raw native/manual NF mismatch')
            ssb.append(a);dsb.append(b)
            if run['sidebands']==63:
                old.close(d['onoise_v_per_rt_hz'],np.sqrt(psd),'Raw total output noise',atol=1e-19)
                old.close(d['native_ssb_nf_db'],v['NF'],'Raw native SSB NF')
                old.close(d['native_dsb_nf_db'],v['NFdsb'],'Raw native DSB NF')
        old.close(d['ssb_nf_by_sidebands_db'],ssb,'Raw sideband SSB matrix')
        old.close(d['dsb_nf_by_sidebands_db'],dsb,'Raw sideband DSB matrix')
        return {'raw_PAC_and_PNOISE_recomputed':True}
    for kind,row in result['circuits'].items():
        native_file=root/'cadence'/(kind+'_tb_audit.tsv')
        audit.check(kind+'.native_OA_source',lambda kind=kind:audit_native(native_file,kind,cfg,True))
        arrays={}
        for label,relative in row['curves'].items():
            def curve(relative=relative,label=label):
                file,data=old.load_npz(root,relative,fp);old.require(sha(file)==row['curve_sha256'][label],'GUI curve hash changed')
                arrays[label]=data;return {'path':relative,'sha256':sha(file)}
            audit.check(kind+'.curve.'+label,curve)
        audit.check(kind+'.metrics_and_reference',lambda kind=kind:old.metric_checks(kind,result))
        for label,spectrum,two in (('transient','spectrum',False),('twotone','twotone_spectrum',True)):
            audit.check(kind+'.'+label+'.grid_fft_lo',lambda kind=kind,label=label,spectrum=spectrum,two=two:
                        old.trace_checks(kind,label,cfg,arrays[label],arrays[spectrum],two))
        for label,function in (('single_projection',old.single_checks),('compression',old.compression_checks),
                               ('iip3_fits',old.iip3_checks),('noise_normalization',old.noise_checks)):
            audit.check(kind+'.'+label,lambda kind=kind,function=function:function(kind,result,arrays))
        audit.check(kind+'.window_convergence',lambda kind=kind:old.window_checks(kind,result))
        for run in row['runs']:
            name=run.get('test_name',run['stage'])+'.'+run['stage']
            audit.check(kind+'.actual_source.'+name,lambda run=run:source_run(run))
            if run.get('measurement'):audit.check(kind+'.raw_projection.'+name,lambda run=run:run_projection(run))
        audit.check(kind+'.raw_periodic_noise',lambda kind=kind,row=row:raw_noise(kind,row,arrays))
    failures=[c for c in audit.checks if not c['passed']]
    report={'schema_version':1,'status':'passed' if not failures else 'failed','origin':'independent_actual_GUI_audit',
            'run_id':result['run_id'],'config_fingerprint':fp,'campaign_json_sha256':sha(result_path),
            'completed_utc':datetime.now(timezone.utc).isoformat(),'checks_count':len(audit.checks),
            'failures_count':len(failures),'checks':audit.checks,'validator_sha256':sha(__file__),
            'reused_pure_validator_sha256':sha(root/'tools/validate_results.py'),
            'baseline_not_modified':True}
    (root/'results/cadence_gui_validation.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True,type=Path)
    a=p.parse_args();r=validate(a.root)
    print(json.dumps({k:r[k] for k in ('status','checks_count','failures_count','run_id')}))
    for c in r['checks']:
        if not c['passed']:print('FAIL',c['check'],c['reason'])
    raise SystemExit(0 if r['status']=='passed' else 1)
