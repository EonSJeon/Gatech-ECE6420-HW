#!/usr/bin/env python3
"""Run the Python Spectre API on the school server and export numbers only."""
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'lib'))
os.environ['HW09_EXECUTION_MODE']='server'
os.environ.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
from mixer import default_config,run_campaign,save_json,now,SIM

def main():
    request=json.loads(sys.stdin.read() or '{}')
    audit={'started_utc':now(),'status':'running','rendered_plots':False,'stages':request.get('stages')}
    try:
        result=run_campaign(request.get('config',default_config()),request.get('stages'))
        audit['status']=result['status']
    except BaseException as exc:
        audit.update(status='failed',error=str(exc));raise
    finally:
        audit['finished_utc']=now();save_json(SIM/'last_run.json',audit)
    print('Remote numerical computation finished; plots are rendered locally.',flush=True)

if __name__=='__main__':main()
