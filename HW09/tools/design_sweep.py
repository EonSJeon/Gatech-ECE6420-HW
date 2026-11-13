#!/usr/bin/env python3
"""Bounded, headless Spectre design exploration; numerical data only."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'lib'))
from mixer import default_config,measure_transient,save_json,now,digest,MODEL

def main():
    config=default_config();config['active']['rd_ohm']=config['passive']['rl_ohm']=500.
    config['active']['switch_width_um']=20.
    trials=[]
    for w in (5.,10.,15.):
        for bias in (.65,.70,.75):
            p=deepcopy(config);p['active'].update(gm_width_um=w,rf_bias_v=bias)
            trials.append(('active',p))
    for w in (10.,20.,40.,80.):
        for cm in (.6,.65,.7,.75):
            p=deepcopy(config);p['passive'].update(switch_width_um=w,lo_common_mode_v=cm)
            trials.append(('passive',p))
    def one(pair):
        k,(kind,cfg)=pair
        small=measure_transient(kind,cfg,f'{kind}_scout_{k:02d}',-55,settle=5e-9,window=20e-9)
        large=measure_transient(kind,cfg,f'{kind}_scout_large_{k:02d}',-25,settle=5e-9,window=20e-9)
        row={'kind':kind,'parameters':cfg[kind],'gain_db':small['gain_db'][0],
             'rf_node_gain_db':small['rf_node_gain_db'][0],'power_gain_db':small['power_gain_db'][0],
             'power_mw':small['power_mw'],'compression_at_minus25_dbm_db':small['gain_db'][0]-large['gain_db'][0],
             'single_tone':small,'large_signal':large}
        print(json.dumps({k:v for k,v in row.items() if k not in ('single_tone','large_signal')}),flush=True)
        return row
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(one,enumerate(trials)))
    payload={'completed_utc':now(),'model_sha256':digest(MODEL),'fixed_load_ohm_per_branch':500,
             'selection_intent':'Compare source-referenced gain, power, dynamic headroom and compression at -25dBm. Final selection also requires full IIP3 and periodic-noise validation.',
             'trials':results}
    save_json(ROOT/'results/design_sweep.json',payload)
    return payload

if __name__=='__main__':main()
