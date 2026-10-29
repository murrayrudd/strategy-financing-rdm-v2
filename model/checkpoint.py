"""Persist complete model and finished groups; stop on any uncertain upload.

Library helper is supplied externally by the active environment. Offline users
can omit it and retain local ZIPs. No credentials or helper internals are copied.
"""
from pathlib import Path
import argparse,json,zipfile,hashlib,subprocess,sys,os
ROOT=Path(__file__).resolve().parent

def save(destination,helper=None,receipt_path=None):
    out=Path(destination).resolve();out.parent.mkdir(parents=True,exist_ok=True)
    entries=[p for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.zip','.tmp','.partial')]
    entries=[p for p in entries if not any(part in ('render','pre_optimization') for part in p.parts)]
    manifest={}
    tmp=out.with_suffix('.partial')
    with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in entries:
            data=p.read_bytes();name=str(p.relative_to(ROOT));manifest[name]=hashlib.sha256(data).hexdigest()
            z.writestr('strategy_v2_complete/'+name,data)
        z.writestr('strategy_v2_complete/CHECKPOINT_SHA256.json',json.dumps(manifest,indent=2))
    os.replace(tmp,out)
    if not helper:return {'local_path':str(out),'files':len(entries)}
    receipt=Path(receipt_path);item={'local_path':str(out),'purpose':'create_library_file','library_artifact_type':'other'}
    if receipt.exists():
        prior=json.loads(receipt.read_text())['results'][0]
        if prior['status']!='succeeded':raise RuntimeError('Previous upload not confirmed; do not retry an unknown mutation')
        item={'local_path':str(out),'purpose':'replace_library_file','library_file_id':prior['library_file_id'],
              'version_reason':'Durable code and completed RDM batch checkpoint'}
        if prior.get('current_version_number') is not None:item['expected_current_version']=prior['current_version_number']
    result=subprocess.run([sys.executable,str(helper)],input=json.dumps({'uploads':[item]}),text=True,capture_output=True)
    if result.returncode:
        receipt.with_suffix('.failure.txt').write_text(result.stdout+'\n'+result.stderr)
        raise RuntimeError('Checkpoint upload failed; stopping before another batch')
    response=json.loads(result.stdout)
    if len(response.get('results',[]))!=1 or response['results'][0]['status']!='succeeded':
        receipt.with_suffix('.failure.json').write_text(result.stdout);raise RuntimeError('Checkpoint not confirmed')
    receipt.write_text(json.dumps(response,indent=2))
    return {'files':len(entries),'saved':True,'version':response['results'][0].get('current_version_number')}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('destination');p.add_argument('--helper');p.add_argument('--receipt');a=p.parse_args()
    print(json.dumps(save(a.destination,a.helper,a.receipt)))
