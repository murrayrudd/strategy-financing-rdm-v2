"""Preselected diagnostic for positive net returns on settled liquid assets.

The main experiment uses zero carrying return. This supplementary experiment
credits net-of-tax cash-equivalent returns of 3% and 5% annually, compounded
daily, on settled cash and Treasury balances; no yield on pending/restricted
assets. It is a policy sensitivity, not an observed Treasury yield forecast.
"""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import json,hashlib,os,time,traceback
from simulation import Simulation,START,D,money,path_digest
from rdm_design import POLICIES,assumptions,future,external_path
from rdm_run import flatten,identity
ROOT=Path(__file__).resolve().parent
class CarrySimulation(Simulation):
    def __init__(self,*args,net_yield=0.,**kwargs):
        self.net_daily_return=money((1+net_yield)**(1/365.25)-1);self.last_carry_date=START;self.carry_earned=D(0)
        super().__init__(*args,**kwargs)
    def settle_pending(self):
        if self.day>self.last_carry_date:
            earned=max(D(0),self.liq.cash+self.liq.treasury)*self.net_daily_return
            if earned:self.liq.record(earned,'net_liquid_asset_return');self.carry_earned+=earned
            self.last_carry_date=self.day
        super().settle_pending()

def one(task):
    x,rate=task
    try:
        path=external_path(x);digest=path_digest(path);rows=[]
        for structure in ('face','continuation'):
            for policy in POLICIES:
                s=CarrySimulation(future(x),policy,assumptions(x,structure),external_path=path,external_digest=digest,net_yield=rate)
                rows.extend(flatten(s.run(),structure,0.))
        return {'id':x['id'],'net_yield':rate,'rows':rows}
    except Exception:return {'id':x['id'],'net_yield':rate,'error':traceback.format_exc()}

def run(limit=None,workers=8):
    from durable_run import atomic
    rd=ROOT/'results/rdm';out=rd/'carry.jsonl';ip=rd/'carry_identity.json';folder=rd/'groups/carry';folder.mkdir(parents=True,exist_ok=True)
    ident={'model':identity(),'extension_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
      'selection':'Every sixty-fourth main future in immutable generation order','rates':[.03,.05],'future_count':32,'simulations':1024}
    if ip.exists():assert json.loads(ip.read_text())==ident
    else:atomic(ip,ident)
    def key(a):return a['id']+'_'+str(round(a['net_yield']*100))
    if out.exists():
        for line in out.open():
            a=json.loads(line);p=folder/(key(a)+'.json')
            if p.exists():assert json.loads(p.read_text())==a
            else:atomic(p,a)
    done={p.stem for p in folder.glob('*.json')};xs=json.loads((ROOT/'data/rdm_main.json').read_text())[::64]
    tasks=[(x,r) for x in xs for r in (.03,.05) if x['id']+'_'+str(round(r*100)) not in done]
    if limit is not None:tasks=tasks[:limit]
    errors=[]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for answer in pool.map(one,tasks,chunksize=1):
            if 'error' in answer:errors.append(answer)
            else:atomic(folder/(key(answer)+'.json'),answer)
    tmp=out.with_suffix('.jsonl.tmp')
    with tmp.open('w') as f:
        for p in sorted(folder.glob('*.json')):f.write(p.read_text())
        f.flush();os.fsync(f.fileno())
    os.replace(tmp,out);atomic(rd/'carry_errors.json',errors)
    if errors:raise RuntimeError(errors[0])
    print('Carry diagnostic groups:',len(list(folder.glob('*.json'))),'/64',flush=True)
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--limit',type=int);p.add_argument('--workers',type=int,default=8);a=p.parse_args();run(a.limit,a.workers)
