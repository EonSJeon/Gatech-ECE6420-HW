#!/usr/bin/env python3
"""Read-only server PSF conversion streamed into local GUI result directories.

Reads completed native ADE numerical files through the official Cadence PSF
utility. The server writes no files and launches no simulation or plots. A
gzip/tar stream carries only converted text and conversion hash evidence.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tarfile

SERVER_CODE=r'''
import hashlib,io,json,pathlib,subprocess,sys,tarfile
from datetime import datetime,timezone
request=json.load(sys.stdin);root=pathlib.Path(request['root']).resolve()
tool='/tools/software/cadence/ic/latest/tools/dfII/bin/psf'
failures=[];converted=[];family_indexes=[]
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as archive:
    def add(name,content):
        item=tarfile.TarInfo(name);item.size=len(content);item.mode=0o600
        archive.addfile(item,io.BytesIO(content))
    for relative in request['files']:
        path=(root/relative).resolve()
        if not str(path).startswith(str(root)+'/simulation/cadence_gui/') or not path.is_file():
            failures.append({'source':relative,'reason':'Source missing or outside GUI data root'});continue
        source_hash=hashlib.sha256(path.read_bytes()).hexdigest()
        command=[tool,'-f','%.17g','-i',str(path)]
        run=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
        if (run.returncode==1 and run.stderr.strip()==b'Error: No traces available.'
                and path.name=='pac.pac' and list(path.parent.glob('pac.*.pac'))):
            source=pathlib.PurePosixPath(relative)
            destination=source.parent.parent/'ascii'/(source.name+'.family-index.json')
            evidence={'status':'native_family_index_without_waveform','source':relative,
                      'source_sha256':source_hash,'official_converter_diagnostic':'No traces available',
                      'measurement_location':'Explicit harmonic child files retained and converted separately',
                      'completed_utc':datetime.now(timezone.utc).isoformat()}
            add(str(destination),(json.dumps(evidence,indent=2)+'\n').encode())
            family_indexes.append(str(destination));continue
        if run.returncode or not run.stdout.startswith(b'HEADER\n') or b'\nVALUE\n' not in run.stdout:
            failures.append({'source':relative,'returncode':run.returncode,'reason':run.stderr.decode(errors='replace')[-1500:]});continue
        source=pathlib.PurePosixPath(relative)
        destination=source.parent.parent/'ascii'/source.name
        ascii_hash=hashlib.sha256(run.stdout).hexdigest()
        evidence={'status':'complete','origin':'official_Cadence_PSF_17digit_ASCII_conversion',
                  'source':relative,'source_sha256':source_hash,'ascii':str(destination),
                  'ascii_sha256':ascii_hash,'double_precision_format':'%.17g','command':command,
                  'completed_utc':datetime.now(timezone.utc).isoformat(),
                  'stderr':run.stderr.decode(errors='replace')}
        add(str(destination),run.stdout)
        add(str(destination)+'.conversion.json',(json.dumps(evidence,indent=2)+'\n').encode())
        converted.append(str(destination))
    add('conversion_summary.json',json.dumps({'converted':converted,'failures':failures,'family_indexes':family_indexes}).encode())
'''


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def convert(project,history,host='gt-ece',remote_root='/nethome/sjeon84/Gatech-ECE6420/HW09',force=False):
    project=Path(project).resolve()
    if not re.fullmatch(r'Interactive\.\d+',history):raise ValueError('Invalid native history name')
    sys.path.insert(0,str(project/'lib'))
    from remote_bridge import RemoteConfig
    remote=RemoteConfig(host=host,directory=remote_root)
    base=project/'simulation/cadence_gui/HW09_Mixers/mixer_campaign/maestro/results/maestro'/history/'1'
    files=[];cached=[];cached_indexes=[]
    for test in sorted(base.iterdir()):
        log=test/'psf/spectre.out'
        if not log.is_file() or not re.search(r'spectre completes with\s+0 errors',log.read_text(errors='replace'),re.I):continue
        for path in sorted((test/'psf').iterdir()):
            if not path.is_file() or path.suffix not in {'.tran','.pac','.pnoise'}:continue
            dest=test/'ascii'/path.name;meta=Path(str(dest)+'.conversion.json')
            index_meta=Path(str(dest)+'.family-index.json')
            if not force and index_meta.is_file():
                evidence=json.loads(index_meta.read_text())
                if (evidence.get('status')=='native_family_index_without_waveform'
                        and evidence.get('source_sha256')==sha(path)):
                    cached_indexes.append(str(index_meta.relative_to(project)));continue
            if not force and dest.is_file() and meta.is_file():
                evidence=json.loads(meta.read_text())
                if evidence.get('source_sha256')==sha(path) and evidence.get('ascii_sha256')==sha(dest):
                    cached.append(str(dest.relative_to(project)));continue
            files.append(str(path.relative_to(project)))
    if not files:return {'converted':[],'cached':cached,'failures':[],
                         'family_indexes':cached_indexes}
    payload=json.dumps({'root':remote_root,'files':files}).encode()
    compile(SERVER_CODE,'cadence_psf_conversion_server','exec')
    process=subprocess.Popen(remote.command('python3 -c '+shlex.quote(SERVER_CODE)),
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    process.stdin.write(payload);process.stdin.close();summary=None
    try:
        with tarfile.open(fileobj=process.stdout,mode='r|gz') as archive:
            for member in archive:
                stream=archive.extractfile(member)
                if stream is None:raise ValueError('Unexpected non-file conversion stream member')
                content=stream.read()
                if member.name=='conversion_summary.json':summary=json.loads(content);continue
                target=(project/member.name).resolve()
                if not target.is_relative_to(base) or '/ascii/' not in str(target):
                    raise ValueError('Conversion stream path escapes actual GUI history')
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
        stderr=process.stderr.read().decode(errors='replace');code=process.wait()
        if code or summary is None:raise RuntimeError('PSF conversion stream failed: '+stderr[-2000:])
    except BaseException as exc:
        process.terminate();process.wait()
        detail=process.stderr.read().decode(errors='replace')
        raise RuntimeError('PSF conversion stream failed: '+detail[-2000:]) from exc
    for relative in summary['converted']:
        evidence=json.loads((project/(relative+'.conversion.json')).read_text())
        if evidence['source_sha256']!=sha(project/evidence['source']):
            raise ValueError('Native source changed during conversion or fetch: '+evidence['source'])
        if evidence['ascii_sha256']!=sha(project/relative):raise ValueError('Converted PSF hash mismatch')
    for relative in summary['family_indexes']:
        evidence=json.loads((project/relative).read_text())
        if evidence['source_sha256']!=sha(project/evidence['source']):
            raise ValueError('Native PAC family index changed during conversion or fetch')
    summary['cached']=cached
    summary['family_indexes']+=cached_indexes
    (base.parent/'local_conversion_audit.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',required=True,type=Path);p.add_argument('--history',required=True)
    p.add_argument('--host',default='gt-ece');p.add_argument('--remote-root',default='/nethome/sjeon84/Gatech-ECE6420/HW09')
    p.add_argument('--force',action='store_true')
    a=p.parse_args();result=convert(a.root,a.history,a.host,a.remote_root,a.force)
    print(json.dumps({'converted_count':len(result['converted']),'cached_count':len(result['cached']),
                      'native_family_index_count':len(result.get('family_indexes',[])),
                      'failures':result['failures']},indent=2))
