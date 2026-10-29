"""Post-hoc mechanism diagnostic; excluded from the locked eight-policy design.

After viewing the complete main outcome table, test whether reserving the
scenario's legal cash-distribution capacity for current-year preferred payments
changes the retirement policy's tradeoff. The preselected 125 cash-subset futures
are reused; this is explanatory analysis, not independent validation or a new
prespecified robust-policy recommendation. Future declarations use current
shares/rates/FX; STRK is conservatively included as a cash claim.
"""
from pathlib import Path
from dataclasses import replace
from concurrent.futures import ProcessPoolExecutor
import json,hashlib,os,argparse,traceback
from simulation import Simulation,D,Z,date,path_digest
from rdm_design import POLICIES,assumptions,future,external_path
from rdm_run import identity,flatten
from durable_run import atomic
ROOT=Path(__file__).resolve().parent
class HeadroomSimulation(Simulation):
    def finance(self):
        assert self.a.equity_settlement_days>0 and self.a.asset_settlement_days>0
        protected=self.due_arrears_usd();yearend=date(self.day.year,12,31)
        for e in self.funding_schedule:
            if self.day<e['pay']<=yearend and e['nominal']>self.day:
                protected+=(self.records[e['id']] if e['id'] in self.records else self.expected_regular(e))*self.fx(e['ticker'])
        original=self.liq.legal_budget
        try:
            self.liq.legal_budget=max(Z,original-protected)
            # With positive settlement lags, this only changes the retirement
            # authorization gate; cash distributions occur outside finance().
            super().finance()
        finally:self.liq.legal_budget=original

def one(x):
    try:
        path=external_path(x);digest=path_digest(path);rows=[]
        policy=next(p for p in POLICIES if p.name=='retire_12m')
        for structure in ('face','continuation'):
            s=HeadroomSimulation(future(x),policy,assumptions(x,structure),external_path=path,external_digest=digest)
            rows.extend(flatten(s.run(),structure,0.))
        return {'id':x['id'],'legal_regime':x['legal_regime'],'rows':rows}
    except Exception:return {'id':x['id'],'error':traceback.format_exc()}

def main(work,workers=2):
    work=Path(work);work.mkdir(parents=True,exist_ok=True);folder=work/'groups';folder.mkdir(exist_ok=True)
    meta={'model':identity(),'extension_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'timing':'Post-hoc diagnostic specified after viewing the completed main outcome table; no change to main policies, discovery thresholds, or holdout assignments.',
      'selection':'Every sixteenth main future, the existing preselected cash subset','futures':125,'simulations':250,'scope':'Reserve current-year preferred cash capacity before authorizing surplus STRC retirement; no optimized policy or statutory-surplus calculation.'}
    ip=work/'identity.json'
    if ip.exists():assert json.loads(ip.read_text())==meta
    else:atomic(ip,meta)
    xs=json.loads((ROOT/'data/rdm_main.json').read_text())[::16];todo=[x for x in xs if not (folder/(x['id']+'.json')).exists()];errors=[]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(one,todo,chunksize=1):
            if 'error' in result:errors.append(result)
            else:atomic(folder/(result['id']+'.json'),result)
    assert not errors,errors[:1]
    results=[json.loads(p.read_text()) for p in sorted(folder.glob('*.json'))];assert len(results)==125
    base={json.loads(s)['id']:json.loads(s) for s in (ROOT/'results/rdm/main.jsonl').open()}
    equivalent=0
    for g in results:
        assert len(g['rows'])==4
        for r in g['rows']:
            b=next(v for v in base[g['id']]['rows'] if v['policy']==r['policy'] and v['structure']==r['structure'] and v['horizon']==r['horizon'])
            assert r['path_sha256']==b['path_sha256']
            if g['legal_regime']=='unlimited':assert r==b;equivalent+=1
    assert equivalent>0
    meta['unlimited_regime_exact_endpoint_matches']=equivalent
    raw=work/'legal_headroom.jsonl';raw.write_text(''.join(json.dumps(r,separators=(',',':'))+'\n' for r in results))
    atomic(work/'legal_headroom_identity.json',meta)
    # Publish completed immutable files once, avoiding concurrent partial files
    # while the main pipeline archives completed batches.
    target=ROOT/'results/rdm';os.replace(raw,target/raw.name);os.replace(work/'legal_headroom_identity.json',target/'legal_headroom_identity.json')
    print('LEGAL_HEADROOM_COMPLETE',equivalent,'exact unlimited-regime endpoint controls',flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--work',required=True);p.add_argument('--workers',type=int,default=2);a=p.parse_args();main(a.work,a.workers)
