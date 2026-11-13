"""Refine passive LO common mode with small single-finger devices."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'lib'))
from mixer import default_config,measure_transient,save_json,now

config=default_config();config['passive']['rl_ohm']=500
trials=[]
for width in (2.,5.,10.,20.):
    for cm in (.45,.5,.55,.6):
        cfg=deepcopy(config);cfg['passive'].update(switch_width_um=width,lo_common_mode_v=cm);trials.append(cfg)
def one(pair):
    k,cfg=pair
    small=measure_transient('passive',cfg,f'passive_refine_{k:02d}',-55,settle=5e-9,window=20e-9)
    row={'parameters':cfg['passive'],'gain_db':small['gain_db'][0],'power_gain_db':small['power_gain_db'][0],'measurement':small}
    print(json.dumps({k:v for k,v in row.items() if k!='measurement'}),flush=True);return row
with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(one,enumerate(trials)))
save_json(ROOT/'results/passive_refine.json',{'completed_utc':now(),'trials':results})
