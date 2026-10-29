"""Atomic per-future persistence around the unchanged numerical RDM worker."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import argparse,json,os,time,hashlib
from rdm_run import ROOT,one,identity,lock


def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+f'.{os.getpid()}.tmp')
    with tmp.open('w') as f:
        json.dump(value,f,default=float,separators=(',',':'));f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)


def key(answer):
    k=answer['id']
    assert k and all(c.isalnum() or c in '-_.' for c in k)
    return k


def groups(phase):
    rd=ROOT/'results/rdm';folder=rd/'groups'/phase;folder.mkdir(parents=True,exist_ok=True)
    old=rd/f'{phase}.jsonl'
    if old.exists():
        for line in old.open():
            answer=json.loads(line);p=folder/(key(answer)+'.json')
            if p.exists():assert json.loads(p.read_text())==answer, f'Conflicting {phase} result {key(answer)}'
            else:atomic(p,answer)
    return folder


def compile_groups(phase,folder):
    path=ROOT/f'results/rdm/{phase}.jsonl';tmp=path.with_suffix('.jsonl.tmp');count=0
    with tmp.open('w') as f:
        for p in sorted(folder.glob('*.json')):
            answer=json.loads(p.read_text());assert 'error' not in answer
            f.write(json.dumps(answer,default=float,separators=(',',':'))+'\n');count+=1
        f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)
    assert sum(1 for _ in path.open())==count
    return count


def run(phase,limit=None,workers=8):
    lock();rd=ROOT/'results/rdm';expected=json.loads((rd/'run_identity.json').read_text())
    assert identity()==expected, 'Numerical engine or inputs changed'
    transport={'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'worker':'rdm_run.one; numerical worker unchanged','persistence':'One fsynced atomic JSON file per whole future; JSONL compiled atomically at batch boundary'}
    tp=rd/'transport_identity.json'
    if tp.exists():assert json.loads(tp.read_text())==transport
    else:atomic(tp,transport)
    source='challenge' if phase=='challenge' else 'main';xs=json.loads((ROOT/f'data/rdm_{source}.json').read_text())
    if phase=='cash' or phase.startswith('tail'):xs=xs[::16]
    if phase=='pilot':xs=xs[:8]
    folder=groups(phase);done={p.stem for p in folder.glob('*.json')};todo=[x for x in xs if x['id'] not in done]
    if limit is not None:todo=todo[:limit]
    increment=1e8 if phase=='cash' else 0.;start=time.time();errors=[]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for answer in pool.map(one,[(x,increment,phase) for x in todo],chunksize=1):
            if 'error' in answer:errors.append(answer)
            else:atomic(folder/(key(answer)+'.json'),answer);done.add(answer['id'])
            if len(done)%8==0:
                status={'phase':phase,'completed_futures':len(done),'planned_futures':len(xs),'simulations':len(done)*16,'batch_elapsed_seconds':round(time.time()-start,2),'errors':len(errors),'utc_epoch':time.time(),'verified_atomic_files':len(list(folder.glob('*.json')))}
                atomic(rd/'progress.json',status);print(json.dumps(status),flush=True)
    count=compile_groups(phase,folder);atomic(rd/f'{phase}_errors.json',errors)
    assert count==len(done)
    if errors:raise RuntimeError(errors[0])
    return count,len(xs)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--phase',required=True,choices=['pilot','main','challenge','cash','tail2031','tail2033']);p.add_argument('--limit',type=int);p.add_argument('--workers',type=int,default=8);a=p.parse_args();print(run(a.phase,a.limit,a.workers),flush=True)
