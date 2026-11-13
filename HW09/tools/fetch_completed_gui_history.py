#!/usr/bin/env python3
"""Fetch only finished actual GUI jobs; never start simulation or import plots."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile


def fetch(project,history):
    root=Path(project).resolve()
    if not re.fullmatch(r'Interactive\.\d+',history):raise ValueError('Invalid native GUI history')
    sys.path.insert(0,str(root/'lib'));from remote_bridge import RemoteConfig
    remote=RemoteConfig.load()
    relative='simulation/cadence_gui/HW09_Mixers/mixer_campaign/maestro/results/maestro/'+history+'/1'
    server=remote.directory+'/'+relative
    code=('import pathlib,re,json; p=pathlib.Path('+repr(server)+'); '
          'names=[x.name for x in p.iterdir() if x.is_dir() and (x/"psf/spectre.out").is_file() and '
          're.search(r"spectre completes with\\s+0 errors",(x/"psf/spectre.out").read_text(errors="replace"))]; '
          'print(json.dumps(sorted(names)))')
    response=subprocess.run(remote.command('python3 -c '+shlex.quote(code)),text=True,capture_output=True,check=True)
    names=json.loads(response.stdout)
    if not all(re.fullmatch('[A-Za-z0-9_]+',name) for name in names):raise ValueError('Unexpected actual native test directory')
    dest=root/relative;dest.mkdir(parents=True,exist_ok=True);(root/'.cache').mkdir(exist_ok=True)
    if names:
        with tempfile.NamedTemporaryFile('w',dir=root/'.cache',delete=False) as f:
            f.write('\n'.join(n+'/' for n in names)+'\n');listing=Path(f.name)
        try:
            command=['rsync','-azr','--files-from='+str(listing)]
            command+=['--exclude='+s for s in ('*.png','*.svg','*.jpg','*.pdf','*.cdslck')]
            command+=['-e',shlex.join(remote.ssh()),remote.host+':'+server+'/',str(dest)+'/']
            subprocess.run(command,check=True)
        finally:listing.unlink()
    summary={'history':history,'completed_native_tests':names}
    (dest.parent/'local_completed_tests.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True,type=Path)
    p.add_argument('--history',required=True);a=p.parse_args();r=fetch(a.root,a.history)
    print(json.dumps({'history':r['history'],'fetched_completed_tests':len(r['completed_native_tests'])}))
