"""Python API for reproducible HW09 Spectre simulations (server, no plotting)."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
MODEL=os.environ.get('HW09_MODEL','/tools/designkits/NCSU/FreePDK4514/ncsu_basekit/models/hspice/tran_models/models_nom/NMOS_VTH.inc')
SPECTRE=os.environ.get('SPECTRE_BIN','/tools/software/cadence/spectre/latest/tools.lnx86/bin/spectre')
LICENSE=os.environ.get('HW09_LICENSE','5280@ece-winlic.ece.gatech.edu:1055@ansyslic.ecs.gatech.edu')
SIM=ROOT/'simulation';GEN=ROOT/'netlists/generated';CURVES=ROOT/'results/curves';RESULT=ROOT/'results/hw9_results.json'
VERSION='hw09-mixer-1.0'

def default_config():
    return {'common':{'rf_hz':5.8e9,'lo_hz':5.6e9,'if_hz':2e8,'vdd_v':1.,'rs_ohm':50.,'temp_c':27.,'source_noise_temp_k':290.,'load_cap_f':10e-15},
      'active':{'gm_width_um':15.,'switch_width_um':20.,'length_nm':50.,'nf':1,'m':1,'rd_ohm':500.,'rf_bias_v':.65,'lo_common_mode_v':.8,'lo_vpp_per_leg':.4},
      'passive':{'switch_width_um':20.,'length_nm':50.,'nf':1,'m':1,'rl_ohm':500.,'rf_common_mode_v':0.,'lo_common_mode_v':.5,'lo_vpp_per_leg':.4},
      'analysis':{'small_signal_pin_dbm':-55.,'transient_settle_s':20e-9,'window_s':100e-9,'strobe_s':5e-12,'maxstep_s':2e-12,'reltol':1e-5,
        'single_tone_window_s':20e-9,'single_tone_settle_s':5e-9,'parallel_jobs':2,
        'compression_pin_dbm':[-60,-50,-40,-35,-30,-25,-20,-15,-10,-5,0,5],
        'iip3_pin_dbm':[-50,-45,-40,-35,-30,-25,-20],
        'rf_tones_hz':[5.79e9,5.81e9],'noise_sidebands':[15,31,63],'noise_frequency_hz':[1e8,2e8,3e8],'force':False}}

def now():return datetime.now(timezone.utc).isoformat()
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def fingerprint(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True).encode()).hexdigest()
def save_json(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.part')
    tmp.write_text(json.dumps(obj,indent=2,sort_keys=True,allow_nan=False)+'\n');tmp.replace(path)

def validate_config(config):
    required=default_config()
    if not isinstance(config,dict) or set(config)!=set(required):raise ValueError('Use the complete default_config() structure.')
    c=config['common'];a=config['analysis']
    assert c['vdd_v']==1 and c['rs_ohm']>0 and c['load_cap_f']>=0
    assert abs(abs(c['rf_hz']-c['lo_hz'])-c['if_hz'])<1
    for kind in ('active','passive'):
        p=config[kind]
        assert p['nf']==p['m']==1,'This baseline uses one finger and multiplicity one; geometry must be re-derived for other values.'
        assert p['length_nm']>=45 and p['switch_width_um']>0
        assert 0<p['lo_vpp_per_leg']<.5,'Both per-leg and differential LO Vpp must remain below 1V.'
        assert p['lo_common_mode_v']-p['lo_vpp_per_leg']/2>=0
        assert p['lo_common_mode_v']+p['lo_vpp_per_leg']/2<=1
    assert a['window_s']>0 and a['strobe_s']>0
    for span in (a['window_s'],a['transient_settle_s'],a['single_tone_window_s'],a['single_tone_settle_s']):
        assert abs(span/a['strobe_s']-round(span/a['strobe_s']))<1e-6,'Window and settling time must be exact strobe-grid multiples.'
    for key in ('compression_pin_dbm','iip3_pin_dbm'):
        grid=np.asarray(a[key],dtype=float)
        assert len(grid)>=3 and np.all(np.isfinite(grid)) and np.all(np.diff(grid)>0),'Input-power grids must be finite and strictly increasing.'
    assert int(a['parallel_jobs'])==a['parallel_jobs'] and 1<=a['parallel_jobs']<=2,'Use one or two bounded independent Spectre jobs.'
    for freq in [c['rf_hz'],c['lo_hz'],c['if_hz'],*a['rf_tones_hz']]:
        assert abs(freq*a['window_s']-round(freq*a['window_s']))<1e-6,'Use an exact coherent measurement window.'
    for freq in (c['rf_hz'],c['lo_hz'],c['if_hz']):
        assert abs(freq*a['single_tone_window_s']-round(freq*a['single_tone_window_s']))<1e-6,'Single-tone measurement window is not coherent.'
    return deepcopy(config)

def mos_line(name,nodes,width_um,length_nm):
    # NCSU single-finger diffusion extension: area W*105nm, exposed perimeter W+210nm.
    w=width_um*1e-6;l=length_nm*1e-9;extension=105e-9
    return f'{name} ({" ".join(nodes)}) NMOS_VTH w={w:.12g} l={l:.12g} as={w*extension:.12g} ad={w*extension:.12g} ps={w+2*extension:.12g} pd={w+2*extension:.12g} ls={extension:.12g} ld={extension:.12g} m=1'

def deck(kind,config,pin_dbm=-55,two_tone=False,extra='',lo_only=False,maxstep=None,reltol=None,stop=None):
    c=config['common'];p=config[kind];a=config['analysis'];rs=c['rs_ohm']
    open_peak=math.sqrt(8*rs*.001*10**(pin_dbm/10)) if pin_dbm is not None else 0.
    tones=a['rf_tones_hz'] if two_tone else [c['rf_hz'],c['rf_hz']]
    bias=p['rf_bias_v'] if kind=='active' else p['rf_common_mode_v']
    if lo_only:open_peak=0.
    lines=['// HW09 single-balanced mixer. MOS order: drain gate source body.', 'simulator lang=spectre','global 0',f'include "{MODEL}"',
       '// Spectre port amplitude/DC are matched-load values; open-circuit source values are twice these.',
       f'RFPORT (rfdrive 0) port r={rs:.12g} num=1 type=sine dc={bias/2:.12g} ampl={open_peak/2:.12g} freq={tones[0]:.12g} pacmag=0.5 noisetemp={c["source_noise_temp_k"]-273.15:.12g} isnoisy=yes',
       f'RFSECOND (rf rfdrive) vsource dc=0 type=sine ampl={open_peak if two_tone else 0:.12g} freq={tones[1]:.12g}',
       f'LOP (lop 0) vsource dc={p["lo_common_mode_v"]:.12g} type=sine ampl={p["lo_vpp_per_leg"]/2:.12g} freq={c["lo_hz"]:.12g} sinephase=0',
       f'LON (lon 0) vsource dc={p["lo_common_mode_v"]:.12g} type=sine ampl={p["lo_vpp_per_leg"]/2:.12g} freq={c["lo_hz"]:.12g} sinephase=180']
    if kind=='active':
        lines += [f'VDD (vdd 0) vsource dc={c["vdd_v"]:.12g}',mos_line('M1',('tail','rf','0','0'),p['gm_width_um'],p['length_nm']),
          mos_line('M2',('outp','lop','tail','0'),p['switch_width_um'],p['length_nm']),mos_line('M3',('outn','lon','tail','0'),p['switch_width_um'],p['length_nm']),
          f'R1 (vdd outp) resistor r={p["rd_ohm"]:.12g}',f'R2 (vdd outn) resistor r={p["rd_ohm"]:.12g}']
    else:
        lines += [mos_line('M1',('outp','lop','rf','0'),p['switch_width_um'],p['length_nm']),mos_line('M2',('outn','lon','rf','0'),p['switch_width_um'],p['length_nm']),
          f'R1 (outp 0) resistor r={p["rl_ohm"]:.12g}',f'R2 (outn 0) resistor r={p["rl_ohm"]:.12g}']
    if c['load_cap_f']:
        lines += [f'CLP (outp 0) capacitor c={c["load_cap_f"]:.12g}',f'CLN (outn 0) capacitor c={c["load_cap_f"]:.12g}']
    lines += [f'simulatorOptions options temp={c["temp_c"]:.12g} tnom=27 reltol={reltol or a["reltol"]:.12g} vabstol=1e-9 iabstol=1e-13 gmin=1e-12 digits=12',
       'dcOp dc', 'dcOpInfo info what=oppoint where=rawfile',
       'save rf rfdrive outp outn lop lon '+('tail VDD:p M1:d M2:d M3:d' if kind=='active' else 'M1:d M2:d')+' LOP:p LON:p RFPORT:p',
       'saveOptions options save=selected currents=selected']
    if extra:lines.append(extra)
    else:
        end=stop or (a['transient_settle_s']+a['window_s'])
        lines.append(f'tran tran stop={end:.12g} maxstep={maxstep or a["maxstep_s"]:.12g} strobeperiod={a["strobe_s"]:.12g} errpreset=conservative')
    return '\n'.join(lines)+'\n'

def execute(name,text,timeout=300):
    if not re.fullmatch('[a-zA-Z0-9_.-]+',name):raise ValueError('Invalid simulation identifier')
    for path in (SIM,GEN,CURVES):path.mkdir(parents=True,exist_ok=True)
    raw=SIM/name;work=GEN/(name+'.scs');work.write_text(text)
    if raw.exists():shutil.rmtree(raw)
    raw.mkdir()
    env=dict(os.environ,CDS_LIC_FILE=LICENSE,LM_LICENSE_FILE=LICENSE)
    cmd=[SPECTRE,str(work),'+escchars','+log',str(raw/'spectre.out'),'-format','psfascii','-raw',str(raw),'+mt=1','+lqtimeout','60','-maxw','8','-maxn','5']
    start=time.monotonic()
    with (raw/'stdout.log').open('w') as stream:
        proc=subprocess.run(cmd,cwd=raw,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=timeout)
    log=(raw/'spectre.out').read_text(errors='replace') if (raw/'spectre.out').exists() else (raw/'stdout.log').read_text(errors='replace')
    if proc.returncode or re.search(r'\bERROR\s*\(',log,re.I):raise RuntimeError(f'Spectre {name} failed ({proc.returncode}):\n{log[-6500:]}')
    save_json(raw/'execution.json',{'status':'complete','completed_utc':now(),'elapsed_s':time.monotonic()-start,'netlist_sha256':digest(work),'command':cmd})
    return raw

NUMBER=re.compile(r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?')
def read_psf(path,axis='time',names=None,complex_values=False):
    series={};x=[];active=False
    for raw in Path(path).read_text().splitlines():
        line=raw.strip()
        if line=='VALUE':active=True;continue
        if not active or not line.startswith('"'):continue
        _,name,rest=line.split('"',2)
        if name!=axis and names is not None and name not in names:continue
        values=[float(v) for v in NUMBER.findall(rest)]
        if not values:continue
        if name==axis:x.append(values[0])
        elif complex_values and len(values)==2:series.setdefault(name,[]).append(complex(*values))
        elif len(values)==1:series.setdefault(name,[]).append(values[0])
    x=np.asarray(x);data={k:np.asarray(v) for k,v in series.items()}
    if len(x)<1 or not np.all(np.isfinite(x)) or (len(x)>1 and np.any(np.diff(x)<=0)):raise ValueError(f'Invalid PSF axis: {path}')
    for name,v in data.items():
        if len(v)!=len(x) or not np.all(np.isfinite(v)):raise ValueError(f'Malformed PSF {name}: {path}')
    if names and not set(names)<=set(data):raise ValueError(f'Missing PSF traces {set(names)-set(data)}: {path}')
    return x,data

def coherent_trace(raw,config,settle=None,window=None):
    a=config['analysis'];step=a['strobe_s'];settle=a['transient_settle_s'] if settle is None else settle;window=a['window_s'] if window is None else window
    assert all(abs(span/step-round(span/step))<1e-6 for span in (settle,window))
    files=list(raw.glob('tran*.tran'));assert len(files)==1
    t,v=read_psf(files[0]);n=int(round(window/step));start=int(round(settle/step))
    target=(start+np.arange(n))*step
    indices=np.searchsorted(t,target)
    indices=np.clip(indices,0,len(t)-1)
    left=np.maximum(indices-1,0);indices=np.where(abs(t[left]-target)<abs(t[indices]-target),left,indices)
    assert len(set(indices.tolist()))==n and np.max(abs(t[indices]-target))<step*1e-4,'Exact coherent strobe coverage missing'
    return target,{k:value[indices] for k,value in v.items()}

def amplitude(time_s,voltage,freq):
    # Coherent sinusoidal projection on the actual simulated samples.
    return float(abs((2/len(time_s))*np.dot(voltage,np.exp(-2j*np.pi*freq*time_s))))

def measure_transient(kind,config,name,pin_dbm,two_tone=False,maxstep=None,reltol=None,settle=None,window=None,keep_curve=False):
    analysis=config['analysis']
    if settle is None:settle=analysis['transient_settle_s' if two_tone else 'single_tone_settle_s']
    if window is None:window=analysis['window_s' if two_tone else 'single_tone_window_s']
    interval=settle+window
    raw=execute(name,deck(kind,config,pin_dbm,two_tone,maxstep=maxstep,reltol=reltol,stop=interval))
    t,v=coherent_trace(raw,config,settle,window);diff=v['outp']-v['outn'];c=config['common'];a=config['analysis']
    open_peak=math.sqrt(8*c['rs_ohm']*.001*10**(pin_dbm/10));rload=config[kind]['rd_ohm' if kind=='active' else 'rl_ohm']
    tones=a['rf_tones_hz'] if two_tone else [c['rf_hz']]
    ifreq=[abs(f-c['lo_hz']) for f in tones]
    fund=[amplitude(t,diff,f) for f in ifreq];vin=[amplitude(t,v['rf'],f) for f in tones]
    imfreq=[abs(2*tones[0]-tones[1]-c['lo_hz']),abs(2*tones[1]-tones[0]-c['lo_hz'])] if two_tone else []
    im3=[amplitude(t,diff,f) for f in imfreq]
    gain=[20*math.log10(x/open_peak) for x in fund]
    power_mw=-float(np.mean(v['VDD:p']))*c['vdd_v']*1e3 if kind=='active' else 0.
    assert abs(float(np.ptp(v['lop']-v['lon']))-2*config[kind]['lo_vpp_per_leg'])<.01,'LO phases/amplitudes do not match the intended differential drive.'
    if pin_dbm<=-40:
        assert abs(float(v['rf'].mean())-(config[kind]['rf_bias_v'] if kind=='active' else config[kind]['rf_common_mode_v']))<.01,'RF port DC normalization changed.'
    metrics={'pin_dbm':pin_dbm,'open_peak_v':open_peak,'fund_vpk':fund,'rf_node_vpk':vin,'im3_vpk':im3,'if_frequencies_hz':ifreq,
      'im3_frequencies_hz':imfreq,'gain_db':gain,'rf_node_gain_db':[20*math.log10(x/y) for x,y in zip(fund,vin)],
      'power_gain_db':[10*math.log10((x*x/(4*rload))/(.001*10**(pin_dbm/10))) for x in fund],
      'power_mw':power_mw,'mean_outp_v':float(v['outp'].mean()),'mean_outn_v':float(v['outn'].mean()),
      'mean_rf_v':float(v['rf'].mean()),'lo_diff_vpp':float(np.ptp(v['lop']-v['lon'])),
      'max_output_v':float(max(v['outp'].max(),v['outn'].max())),'min_output_v':float(min(v['outp'].min(),v['outn'].min())),
      'netlist':'netlists/generated/'+name+'.scs','netlist_sha256':digest(GEN/(name+'.scs')),'raw_file_sha256':digest(next(raw.glob('tran*.tran'))),
      'sample_count':len(t),'window_s':float(len(t)*a['strobe_s']),'settle_s':settle,'measurement_start_s':float(t[0]),'strobe_s':a['strobe_s'],'completed_utc':now()}
    if kind=='active':metrics.update(tail_min_v=float(v['tail'].min()),tail_max_v=float(v['tail'].max()),tail_mean_v=float(v['tail'].mean()))
    if two_tone:
        metrics['iip3_dbm']=[pin_dbm+10*math.log10(x/y) for x,y in zip(fund,im3)]
        center=sum(ifreq)/2;spacing=abs(ifreq[1]-ifreq[0])/2
        empty=[center+k*spacing for k in (-4,-2,0,2,4) if center+k*spacing>0]
        residual=max(amplitude(t,diff,f) for f in empty)
        metrics['empty_bin_residual_vpk']=residual
        metrics['im3_to_empty_bin_margin_db']=[20*math.log10(v/max(residual,np.finfo(float).tiny)) for v in im3]
    if keep_curve:
        path=CURVES/(kind+'_transient.npz' if not two_tone else kind+'_twotone.npz')
        np.savez_compressed(path,config_fingerprint=fingerprint(config),completed_utc=metrics['completed_utc'],time_s=t,vrf_v=v['rf'],vlo_p_v=v['lop'],vlo_n_v=v['lon'],vout_p_v=v['outp'],vout_n_v=v['outn'],vif_v=diff,
                            **({'tail_v':v['tail']} if kind=='active' else {}))
        metrics['curve_path']=str(path.relative_to(ROOT))
        spectrum=np.abs(np.fft.rfft(diff))/len(diff)*2;spectrum[0]/=2
        spectrum_path=CURVES/(kind+('_twotone_spectrum.npz' if two_tone else '_spectrum.npz'))
        np.savez_compressed(spectrum_path,config_fingerprint=fingerprint(config),completed_utc=metrics['completed_utc'],frequency_hz=np.fft.rfftfreq(len(diff),a['strobe_s']),amplitude_vpk=spectrum,pin_dbm=pin_dbm)
        metrics['spectrum_path']=str(spectrum_path.relative_to(ROOT))
    return metrics

def environment():
    version=subprocess.run([SPECTRE,'-W'],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=True).stdout.strip()
    return {'model_file':MODEL,'model_sha256':digest(MODEL),'spectre_bin':SPECTRE,'spectre_version':version,'remote_host':os.uname().nodename,'python':os.sys.executable,
            'license':LICENSE,'worker_version':VERSION,'worker_sha256':digest(__file__),
            'noise_module_sha256':digest(ROOT/'lib/noise.py') if (ROOT/'lib/noise.py').exists() else None,'rendered_plots_remotely':False}

def _run_campaign(config,stages=None):
    config=validate_config(config);stages=stages or ['design','single_tone','linearity','noise']
    if not set(stages)<={'design','single_tone','linearity','noise'}:raise ValueError('Unknown stage')
    result=json.loads(RESULT.read_text()) if RESULT.exists() else {}
    if result.get('config')!=config:result={}
    env=environment()
    if result and any(result.get('environment',{}).get(k)!=env.get(k) for k in ('worker_sha256','model_sha256','spectre_version','noise_module_sha256')):result={}
    result.update(schema_version=1,status='running',run_id=fingerprint(config)[:12],config=config,environment=env,updated_utc=now())
    circuits=result.setdefault('circuits',{})
    selection=ROOT/'references/design_selection.json'
    if selection.exists():result['design_selection']=json.loads(selection.read_text())
    for kind in ('passive','active'):
        row=circuits.setdefault(kind,{'parameters':deepcopy(config[kind]),'metrics':{},'curves':{},'notes':[]});row['status']='running'
        queue=list(stages)
        if any(s in queue for s in ('linearity','noise')) and 'single_tone' not in queue and row.get('single_tone',{}).get('status')!='complete':queue.insert(0,'single_tone')
        for stage in queue:
            if not config['analysis']['force'] and row.get(stage,{}).get('status')=='complete':continue
            print(f'{kind}: {stage}',flush=True)
            owned={'single_tone':('voltage_gain_db','rf_node_gain_db','power_gain_db','conversion_loss_db','power_conversion_loss_db','power_mw'),
                   'linearity':('p1db_dbm','iip3_dbm','iip3_lower_dbm','iip3_upper_dbm'),
                   'noise':('ssb_nf_db','dsb_nf_db')}
            for metric in owned.get(stage,()):row['metrics'].pop(metric,None)
            if stage in ('design','single_tone'):
                dependents=('single_tone','linearity','noise') if stage=='design' else ('linearity','noise')
                for dependency in dependents:
                    if dependency in row:row[dependency]['status']='stale'
                    for metric in owned.get(dependency,()):row['metrics'].pop(metric,None)
            row[stage]={'status':'running','started_utc':now()}
            save_json(RESULT,result)
            if stage in ('design','single_tone'):
                measurement=measure_transient(kind,config,kind+'_'+stage,config['analysis']['small_signal_pin_dbm'],keep_curve=stage=='single_tone')
                row[stage]={'status':'complete',**measurement}
                if stage=='single_tone':
                    row['metrics'].update(voltage_gain_db=measurement['gain_db'][0],rf_node_gain_db=measurement['rf_node_gain_db'][0],power_gain_db=measurement['power_gain_db'][0],
                        conversion_loss_db=-measurement['gain_db'][0],power_conversion_loss_db=-measurement['power_gain_db'][0],power_mw=measurement['power_mw'])
                    row['dc']={k:measurement[k] for k in ('mean_rf_v','mean_outp_v','mean_outn_v','min_output_v','max_output_v')}
                    row['dc'].update({k:measurement[k] for k in ('tail_min_v','tail_max_v','tail_mean_v') if k in measurement})
                    from operating_point import read_operating_points
                    import warnings
                    with warnings.catch_warnings(record=True) as recorded:
                        op=read_operating_points(SIM/(kind+'_'+stage)/'dcOpInfo.info')
                    fields=('id','gm','gds','vgs','vds','vth','vdsat','region')
                    row['dc']['operating_points']={name:{k:values[k] for k in fields if k in values} for name,values in op.items()}
                    row['dc']['static_op_note']='LO sources are both at their DC common mode in this static operating point. Dynamic tail/output extrema come from the settled LO-driven transient.'
                    row['dc']['omitted_nonfinite_op_fields']=[str(w.message) for w in recorded]
                    row['curves'].update(transient=measurement['curve_path'],spectrum='results/curves/'+kind+'_spectrum.npz')
                    reference=measure_transient(kind,config,kind+'_single_window_check',config['analysis']['small_signal_pin_dbm'],settle=20e-9,window=100e-9)
                    delta=reference['gain_db'][0]-measurement['gain_db'][0]
                    row['window_convergence']={'status':'complete' if abs(delta)<.02 else 'failed','gain_delta_db':delta,'tolerance_db':.02,
                      'short_settle_s':measurement['settle_s'],'short_window_s':measurement['window_s'],'reference':reference}
                    assert abs(delta)<.02,'Short and long coherent single-tone windows disagree.'
            elif stage=='linearity':
                row[stage]=linearity(kind,config,row)
            elif stage=='noise':
                from noise import measure_noise
                row[stage]=measure_noise(kind,config)
                row['metrics'].update({k:row[stage][k] for k in ('ssb_nf_db','dsb_nf_db') if k in row[stage]})
                row['curves']['noise']=row[stage].get('curve_path')
            save_json(RESULT,result)
        row['completed_utc']=now();row['status']='complete' if all(row.get(s,{}).get('status')=='complete' for s in ('single_tone','linearity','noise')) else 'partial'
        save_json(RESULT,result)
    result['status']='complete' if all(row['status']=='complete' for row in circuits.values()) else 'partial'
    result.update(completed_utc=now(),validation={'exact_coherent_grid':True,'source_port_open_voltage_factor':2,'source_and_load_conventions_explicit':True,'remote_plot_files_created':False})
    save_json(RESULT,result);return result

def run_campaign(config,stages=None):
    try:return _run_campaign(config,stages)
    except BaseException as exc:
        if RESULT.exists():
            failed=json.loads(RESULT.read_text());failed.update(status='failed',error=str(exc),failed_utc=now())
            for row in failed.get('circuits',{}).values():
                if row.get('status')=='running':
                    row['status']='failed'
                    for stage in ('design','single_tone','linearity','noise'):
                        if row.get(stage,{}).get('status')=='running':row[stage].update(status='failed',error=str(exc))
            save_json(RESULT,failed)
        raise

def linearity(kind,config,row):
    comp=[];ip=[];a=config['analysis'];c=config['common']
    for k,pin in enumerate(a['compression_pin_dbm']):
        print(f'  compression {pin:g} dBm',flush=True)
        comp.append(measure_transient(kind,config,f'{kind}_compression_{k:02d}',pin))
        if len(comp)>=4 and np.mean([v['gain_db'][0] for v in comp[:3]])-comp[-1]['gain_db'][0]>1.5:break
    baseline=float(np.mean([x['gain_db'][0] for x in comp[:3]]))
    assert np.ptp([x['gain_db'][0] for x in comp[:3]])<.1,'Low-drive compression baseline is not flat.'
    deficits=np.asarray([baseline-x['gain_db'][0] for x in comp]);pins=np.asarray([x['pin_dbm'] for x in comp]);hit=np.flatnonzero(deficits>=1)
    p1=None;p1_bracket=None
    if len(hit) and hit[0]>0:
        k=int(hit[0]);low,high=float(pins[k-1]),float(pins[k])
        for step in range(5):
            mid=(low+high)/2;check=measure_transient(kind,config,f'{kind}_compression_refine_{step}',mid)
            comp.append(check)
            if baseline-check['gain_db'][0]>=1:high=mid
            else:low=mid
        p1=(low+high)/2
        p1_bracket=[low,high]
    comp.sort(key=lambda x:x['pin_dbm'])
    def two_tone_job(pair):
        k,pin=pair
        print(f'  two-tone {pin:g} dBm per tone',flush=True)
        return measure_transient(kind,config,f'{kind}_iip3_{k:02d}',pin,True)
    with ThreadPoolExecutor(max_workers=a['parallel_jobs']) as pool:
        ip=list(pool.map(two_tone_job,enumerate(a['iip3_pin_dbm'])))
    x=np.asarray([r['pin_dbm'] for r in ip]);fund=np.asarray([r['fund_vpk'] for r in ip]);im=np.asarray([r['im3_vpk'] for r in ip])
    fd=20*np.log10(fund);imd=20*np.log10(im);candidates=[]
    for start in range(len(ip)-2):
        sl=slice(start,start+3)
        fs=np.asarray([np.polyfit(x[sl],fd[sl,j],1)[0] for j in range(2)])
        ims=np.asarray([np.polyfit(x[sl],imd[sl,j],1)[0] for j in range(2)])
        compression=float(np.max(abs(fd[sl]-fd[0]-(x[sl,None]-x[0]))))
        margin=min(min(r['im3_to_empty_bin_margin_db']) for r in ip[sl])
        if np.all(abs(fs-1)<.08) and np.all(abs(ims-3)<.25) and compression<.5 and margin>20:
            spread=float(np.ptp([r['iip3_dbm'] for r in ip[sl]],axis=0).max())
            candidates.append((spread,start,fs.tolist(),ims.tolist()))
    selected=None;convergence=None;iip=None
    if candidates:
        _,start,fs,ims=min(candidates);selected={'indices':list(range(start,start+3)),'pins_dbm':x[start:start+3].tolist(),'fundamental_slopes':fs,'im3_slopes':ims,
          'minimum_im3_to_empty_bin_margin_db':min(min(r['im3_to_empty_bin_margin_db']) for r in ip[start:start+3])}
        selected_index=start+1;original=ip[selected_index]
        tight=measure_transient(kind,config,kind+'_iip3_convergence',original['pin_dbm'],True,maxstep=a['maxstep_s']/2,reltol=a['reltol']/10,keep_curve=True)
        row['curves'].update(twotone=tight['curve_path'],twotone_spectrum=tight['spectrum_path'])
        diff=np.asarray(tight['iip3_dbm'])-np.asarray(original['iip3_dbm'])
        convergence={'original':original['iip3_dbm'],'tight':tight['iip3_dbm'],'delta_db':diff.tolist(),'passed':bool(np.max(abs(diff))<.3)}
        if convergence['passed']:iip=np.mean(np.asarray([r['iip3_dbm'] for r in ip[start:start+3]]),axis=0).tolist()
    stamp=now()
    np.savez_compressed(CURVES/(kind+'_compression.npz'),config_fingerprint=fingerprint(config),completed_utc=stamp,pin_dbm=np.asarray([r['pin_dbm'] for r in comp]),gain_db=np.asarray([r['gain_db'][0] for r in comp]),vout_vpk=np.asarray([r['fund_vpk'][0] for r in comp]))
    np.savez_compressed(CURVES/(kind+'_iip3.npz'),config_fingerprint=fingerprint(config),completed_utc=stamp,pin_dbm=x,fund_vpk=fund,im3_vpk=im)
    row['curves'].update(compression='results/curves/'+kind+'_compression.npz',iip3='results/curves/'+kind+'_iip3.npz')
    if p1 is not None:row['metrics']['p1db_dbm']=p1
    if iip is not None:row['metrics'].update(iip3_dbm=min(iip),iip3_lower_dbm=iip[0],iip3_upper_dbm=iip[1])
    status='complete' if p1 is not None and iip is not None else 'needs_validation'
    return {'status':status,'compression':comp,'baseline_gain_db':baseline,'p1db_dbm':p1,'p1db_bracket_dbm':p1_bracket,'two_tone':ip,'cubic_region':selected,'convergence':convergence,'iip3_each_side_dbm':iip,
            'input_power_convention':'Thevenin available source power per tone, Rs=50 ohm','completed_utc':now()}
