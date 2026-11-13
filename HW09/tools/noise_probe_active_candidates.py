#!/usr/bin/env python3
"""Bounded active-mixer candidate comparison; numerical output only."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'lib'))
import mixer
from noise import measure_noise


def main():
    output=ROOT/'results/active_candidate_check.json'
    result={'schema_version':1,'status':'running','measurement':'active candidate noise and three-point two-tone comparison',
            'source_helper_sha256':mixer.digest(__file__),'mixer_module_sha256':mixer.digest(mixer.__file__),
            'noise_module_sha256':mixer.digest(sys.modules['noise'].__file__),
            'source_power_convention':'Thevenin available power per tone, Rs=50 ohm',
            'candidates':{},'started_utc':mixer.now()}
    for label,width,bias in [('A',10.,.70),('B',15.,.65)]:
        config=mixer.default_config()
        config['active'].update(gm_width_um=width,switch_width_um=20.,rd_ohm=500.,rf_bias_v=bias,lo_common_mode_v=.8,lo_vpp_per_leg=.4)
        config['passive']['rl_ohm']=500.
        mixer.validate_config(config)
        prefix='noise_probe_candidate_'+label.lower()
        row={'status':'running','config':deepcopy(config),'config_fingerprint':mixer.fingerprint(config)}
        result['candidates'][label]=row;mixer.save_json(output,result)
        print('Candidate '+label+': noise',flush=True)
        row['noise']=measure_noise('active',config,run_label=prefix)
        row['two_tone']=[]
        for i,pin in enumerate([-35.,-30.,-25.]):
            print('Candidate '+label+': two-tone '+str(pin)+' dBm per tone',flush=True)
            row['two_tone'].append(mixer.measure_transient('active',config,prefix+'_iip3_'+str(i),pin,two_tone=True))
            mixer.save_json(output,result)
        pins=np.array([entry['pin_dbm'] for entry in row['two_tone']])
        fund=np.array([entry['fund_vpk'] for entry in row['two_tone']])
        im3=np.array([entry['im3_vpk'] for entry in row['two_tone']])
        fslopes=[float(np.polyfit(pins,20*np.log10(fund[:,j]),1)[0]) for j in range(2)]
        islopes=[float(np.polyfit(pins,20*np.log10(im3[:,j]),1)[0]) for j in range(2)]
        scaling=bool(all(abs(s-1)<.08 for s in fslopes) and all(abs(s-3)<.25 for s in islopes))
        estimates=np.array([entry['iip3_dbm'] for entry in row['two_tone']])
        row['linearity_check']={'fundamental_slopes':fslopes,'im3_slopes':islopes,
            'cubic_scaling_passed':scaling,'iip3_estimates_dbm':estimates.tolist(),
            'iip3_spread_each_side_db':np.ptp(estimates,axis=0).tolist(),
            'mean_iip3_each_side_dbm':np.mean(estimates,axis=0).tolist() if scaling else None,
            'note':'Exploratory three-point comparison; final campaign independently validates its selected region.'}
        # One tighter transient tests numerical stability without changing the
        # prescribed sweep or modifying campaign results.
        original=row['two_tone'][1]
        tight=mixer.measure_transient('active',config,prefix+'_iip3_tight',-30.,two_tone=True,
            maxstep=config['analysis']['maxstep_s']/2,reltol=config['analysis']['reltol']/10)
        delta=np.asarray(tight['iip3_dbm'])-np.asarray(original['iip3_dbm'])
        row['linearity_check']['convergence']={'original_iip3_dbm':original['iip3_dbm'],
            'tight_iip3_dbm':tight['iip3_dbm'],'delta_db':delta.tolist(),
            'passed':bool(np.max(abs(delta))<.3),'tight_measurement':tight}
        row['status']='complete' if row['noise']['status']=='complete' and scaling and np.max(abs(delta))<.3 else 'needs_validation'
        row['completed_utc']=mixer.now();mixer.save_json(output,result)
        print(json.dumps({'candidate':label,'status':row['status'],'ssb_nf_db':row['noise']['ssb_nf_db'],
            'dsb_nf_db':row['noise']['dsb_nf_db'],'fund_slopes':fslopes,'im3_slopes':islopes,
            'iip3_each_side_dbm':row['linearity_check']['mean_iip3_each_side_dbm'],
            'numerical_delta_db':delta.tolist()}),flush=True)
    result['status']='complete' if all(row['status']=='complete' for row in result['candidates'].values()) else 'needs_validation'
    result['completed_utc']=mixer.now();mixer.save_json(output,result)


def extend_lower_power():
    """Retain original points and add a less-compressed three-point window."""
    output=ROOT/'results/active_candidate_check.json'
    result=json.loads(output.read_text())
    for label,row in result['candidates'].items():
        config=row['config'];prefix='noise_probe_candidate_'+label.lower()
        print('Candidate '+label+': additional -40dBm per tone',flush=True)
        extra=mixer.measure_transient('active',config,prefix+'_iip3_minus40',-40.,two_tone=True)
        row['additional_two_tone']=[extra]
        points=[extra]+row['two_tone'][:2]
        pins=np.array([r['pin_dbm'] for r in points])
        fd=20*np.log10(np.array([r['fund_vpk'] for r in points]))
        imd=20*np.log10(np.array([r['im3_vpk'] for r in points]))
        fs=[float(np.polyfit(pins,fd[:,j],1)[0]) for j in range(2)]
        ims=[float(np.polyfit(pins,imd[:,j],1)[0]) for j in range(2)]
        passed=bool(all(abs(s-1)<.08 for s in fs) and all(abs(s-3)<.25 for s in ims))
        estimates=np.array([r['iip3_dbm'] for r in points])
        row['lower_power_cubic_region']={'pins_dbm':pins.tolist(),'fundamental_slopes':fs,'im3_slopes':ims,
             'passed':passed,'mean_iip3_each_side_dbm':np.mean(estimates,axis=0).tolist() if passed else None,
             'iip3_estimates_dbm':estimates.tolist(),'iip3_spread_each_side_db':np.ptp(estimates,axis=0).tolist(),
             'numerical_convergence':row['linearity_check']['convergence']['passed']}
        row['status']='complete' if passed and row['noise']['status']=='complete' and row['linearity_check']['convergence']['passed'] else 'needs_validation'
        mixer.save_json(output,result)
        print(json.dumps({'candidate':label,**row['lower_power_cubic_region']}),flush=True)
    result.update(status='complete' if all(r['status']=='complete' for r in result['candidates'].values()) else 'needs_validation',
                  extended_utc=mixer.now(),extension_helper_sha256=mixer.digest(__file__))
    mixer.save_json(output,result)


if __name__=='__main__':
    if '--extend-lower-power' in sys.argv:extend_lower_power()
    else:main()
