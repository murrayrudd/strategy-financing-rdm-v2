"""Bounded, resumable batches. A future is the atomic matched comparison unit."""
from pathlib import Path
from dataclasses import asdict
from concurrent.futures import ProcessPoolExecutor,as_completed
import argparse,json,hashlib,time,os,traceback,sys
from simulation import Simulation,path_digest,HORIZONS,date,D
from rdm_design import POLICIES,assumptions,future,external_path,lock,features
ROOT=Path(__file__).resolve().parent
RUNTIME=['simulation.py','mechanics.py','contracts.py','date_rules.py','valuation.py','rdm_design.py','rdm_run.py']

def identity():
    files=[ROOT/n for n in RUNTIME]+list((ROOT/'data').glob('*.json'))+list((ROOT/'data/historical').glob('*'))
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files) if p.is_file()}

def flatten(result,structure,increment,horizons=HORIZONS):
    out=[]
    for h in horizons:
        raw=result['snapshots'][str(h)];censored='censored_at_distress_boundary' in raw;s=raw.get('terminal',raw)
        alive=not censored and not s['debt_shortfall'] and not s['operating_shortfall']
        continuity=alive and not s['first_preferred_miss'];preservation=alive and s['common_backing_change_fraction']>=0
        out.append({'id':result['future'],'policy':result['policy'],'structure':structure,'horizon':str(h),'cash_increment':increment,
          'cash_service':alive,'preferred_continuity':continuity,'common_preservation':preservation,'joint_success':alive and continuity and preservation,
          'censored':censored,'last_date':s['date'],'first_preferred_miss':s['first_preferred_miss'],
          'debt_shortfall':s['debt_shortfall'],'operating_shortfall':s['operating_shortfall'],
          'common_backing_per_share':s['common_backing_per_share'] if alive else None,
          'common_quote':s['common_quote'] if alive else None,'Bitcoin_units':s['Bitcoin_units'],
          'Bitcoin_per_economic_share':s['Bitcoin_units']/s['economic_common_shares'] if alive else None,
          'common_shares':s['economic_common_shares'],'preferred_arrears_usd':s['preferred_arrears_usd'],
          'cash_usd':s['cash_usd'],'STRC_shares':s['STRC_shares'],'debt_principal_usd':s['debt_principal_usd'],
          'metrics':s['metrics'],'max_cash_residual':result['max_cash_reconciliation_residual'],'path_sha256':result['path_sha256']})
    return out

def one(arg):
    x,increment,phase=arg
    try:
        path=external_path(x);rows=[];tail=phase.startswith('tail')
        if tail:
            start=date(int(phase[-4:]),6,30);end=date(start.year+1,6,30)
            for d,p in path.items():
                if d>start:p['capacity']=D(0)
        else:end=date(2033,6,30)
        digest=path_digest(path)
        for structure in ('face','continuation'):
            a=assumptions(x,structure,increment)
            for p in POLICIES:
                r=Simulation(future(x),p,a,end=end,external_path=path,external_digest=digest).run()
                if abs(r['max_cash_reconciliation_residual'])>0.01:raise AssertionError('cash conservation')
                if tail:
                    s=r['terminal'];r['snapshots'][str(end)]=s if s['date']==str(end) else {'censored_at_distress_boundary':s['date'],'terminal':s}
                rows.extend(flatten(r,structure,increment,[end] if tail else HORIZONS))
        return {'id':x['id'],'split':x['split'],'features':features(x),'rows':rows}
    except Exception:return {'id':x['id'],'error':traceback.format_exc()}

def load_rows(path):
    if not path.exists():return []
    raw=path.read_bytes();lines=raw.splitlines();out=[];valid_bytes=0
    for i,line in enumerate(lines):
        try:out.append(json.loads(line));valid_bytes+=len(line)+1
        except json.JSONDecodeError:
            if i!=len(lines)-1:raise
            # A torn final write can be discarded; complete earlier groups survive.
            path.write_bytes(raw[:valid_bytes]);break
    return out

def run(phase='main',limit=None,workers=8):
    lock();rd=ROOT/'results/rdm';rd.mkdir(parents=True,exist_ok=True)
    ids=identity();ip=rd/'run_identity.json'
    if ip.exists() and json.loads(ip.read_text())!=ids:raise RuntimeError('Code/input identity changed. Preserve prior run and start a fresh results directory.')
    ip.write_text(json.dumps(ids,indent=2))
    source='challenge' if phase=='challenge' else 'main'
    xs=json.loads((ROOT/f'data/rdm_{source}.json').read_text())
    if phase=='cash' or phase.startswith('tail'):xs=xs[::16]
    if phase=='pilot':xs=xs[:8]
    file=rd/f'{phase}.jsonl';old=load_rows(file);done={v['id'] for v in old};todo=[x for x in xs if x['id'] not in done]
    if limit is not None:todo=todo[:limit]
    increment=1e8 if phase=='cash' else 0.;start=time.time();errors=[]
    with file.open('a') as f,ProcessPoolExecutor(max_workers=workers) as pool:
        jobs={pool.submit(one,(x,increment,phase)):x['id'] for x in todo}
        for job in as_completed(jobs):
            answer=job.result()
            if 'error' in answer:errors.append(answer);print(json.dumps(answer),flush=True)
            else:
                f.write(json.dumps(answer,default=float,separators=(',',':'))+'\n');f.flush();os.fsync(f.fileno());done.add(answer['id'])
            status={'phase':phase,'completed_futures':len(done),'planned_futures':len(xs),'simulations':len(done)*16,
              'batch_elapsed_seconds':round(time.time()-start,2),'errors':len(errors),'utc_epoch':time.time()}
            (rd/'progress.json').write_text(json.dumps(status,indent=2))
            if len(done)%8==0:print(json.dumps(status),flush=True)
    (rd/f'{phase}_errors.json').write_text(json.dumps(errors,indent=2))
    if errors:raise RuntimeError(f'{len(errors)} execution errors; complete groups retained')
    return len(done),len(xs)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--phase',choices=['pilot','main','challenge','cash','tail2031','tail2033'],default='main');p.add_argument('--limit',type=int);p.add_argument('--workers',type=int,default=8)
    a=p.parse_args();run(a.phase,a.limit,a.workers)
