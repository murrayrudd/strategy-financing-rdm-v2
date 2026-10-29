"""Deterministic diagnostic selection and reconciled transaction traces."""
from pathlib import Path
from collections import defaultdict
from dataclasses import replace
import json, gzip
from simulation import D,Z,OPEN,path_digest
from distribution_capacity import CapacitySimulation
from rdm_design import POLICIES,assumptions,future,external_path
from technical_experiments import atomic,OUT

ROOT=Path(__file__).resolve().parent

class TraceSimulation(CapacitySimulation):
    def __init__(self,*args,**kwargs):
        self.dated_cash=[]
        super().__init__(*args,keep_ledger=True,**kwargs)
        original=self.liq.record
        def record(amount,kind):
            original(amount,kind)
            self.dated_cash.append({'date':str(self.day),'kind':kind,'amount':float(amount),'cash_after':float(self.liq.cash)})
        self.liq.record=record

def raw_groups(phase):
    return {x['id']:x for x in map(json.loads,(ROOT/f'results/rdm/{phase}.jsonl').open())}

def choose():
    baseline=raw_groups('main');cash=raw_groups('cash')
    ids=next(z['future_ids'] for z in json.loads((ROOT/'results/analysis/marginal_cash_common_domain.json').read_text()) if z['horizon']=='2033-06-30')
    effects={};negative=[];reversals=[]
    for fid in ids:
        effects[fid]={}
        for v in ('face','continuation'):
            for p in ('common_12m','dual_12m','capped_12m','retire_12m'):
                filt=lambda r:r['structure']==v and r['policy']==p and r['horizon']=='2033-06-30'
                b=next(r for r in baseline[fid]['rows'] if filt(r));c=next(r for r in cash[fid]['rows'] if filt(r))
                m=OPEN['basic_common_shares_rounded']*(c['common_backing_per_share']-b['common_backing_per_share'])/1e8
                effects[fid][(v,p)]=m
                if m<0:negative.append({'id':fid,'structure':v,'policy':p,'effect':m})
        a=effects[fid][('face','common_12m')]-effects[fid][('face','retire_12m')]
        b=effects[fid][('continuation','common_12m')]-effects[fid][('continuation','retire_12m')]
        if a*b<0:reversals.append({'id':fid,'face_spread':a,'continuation_spread':b,'magnitude':abs(a)+abs(b)})
    negative.sort(key=lambda r:(r['effect'],r['id'],r['structure'],r['policy']))
    reversals.sort(key=lambda r:(r['magnitude'],r['id']))
    return {'selection_rule':'Median negative finite cash effect across 12-month policies and both valuations in the existing common-survival domain; median magnitude among within-future common-versus-retirement ranking reversals. Refinement traces include all four previously reported cash-loss comparisons.',
      'negative_candidates':len(negative),'negative_case':negative[len(negative)//2] if negative else None,
      'reversal_candidates':len(reversals),'reversal_case':reversals[len(reversals)//2] if reversals else None,
      'refinement_cases':json.loads((ROOT/'results/analysis/legal_headroom_cash_loss_cases.json').read_text())}

def trace(x,structure,policy,cash=0,protect=False,mode='calendar_allowance'):
    path=external_path(x);p=next(p for p in POLICIES if p.name==policy)
    s=TraceSimulation(future(x),p,assumptions(x,structure,cash),external_path=path,external_digest=path_digest(path),
        distribution_mode=mode,protect_preferred=protect)
    r=s.run();r['daily_states']=s.trace_states;r['dated_cash']=s.dated_cash
    assert abs(r['max_cash_reconciliation_residual'])<.01
    return json.loads(json.dumps(r,default=float))

def compare(a,b,cutoff=None):
    cutoff=cutoff or min(a['terminal']['date'],b['terminal']['date'])
    def state(r):return next(s for s in r['daily_states'] if s['date']==cutoff)
    s0,s1=state(a),state(b)
    def flows(r):
        d=defaultdict(float)
        for e in r['dated_cash']:
            if e['date']<=cutoff:d[e['kind']]+=e['amount']
        return d
    f0,f1=flows(a),flows(b);diff={k:f1[k]-f0[k] for k in sorted(set(f0)|set(f1))}
    initial=b['assumptions']['initial_cash_increment']-a['assumptions']['initial_cash_increment']
    actual=s1['cash']-s0['cash'];residual=actual-initial-sum(diff.values())
    assert abs(residual)<.05,(cutoff,residual)
    W0,W1,N0,N1=s0['backing'],s1['backing'],s0['common_shares'],s1['common_shares']
    assets=.5*(1/N0+1/N1)*(W1-W0);shares=.5*(W0+W1)*(1/N1-1/N0)
    return {'date':cutoff,'base_state':s0,'treatment_state':s1,
      'cash_difference':actual,'initial_endowment_difference':initial,'cash_flow_differences':diff,
      'cash_bridge_residual':residual,'backing_per_share_difference':W1/N1-W0/N0,
      'backing_numerator_effect_per_share':assets,'share_denominator_effect_per_share':shares,
      'backing_decomposition_residual':W1/N1-W0/N0-assets-shares,
      'metric_differences':{k:s1['metrics'][k]-s0['metrics'][k] for k in s0['metrics']}}

def main():
    selection=choose();atomic(OUT/'trace_selection.json',selection)
    xs={x['id']:x for name in ('main','challenge') for x in json.loads((ROOT/f'data/rdm_{name}.json').read_text())}
    folder=OUT/'traces';folder.mkdir(parents=True,exist_ok=True);cache={}
    def get(fid,v,p,c=0,protect=False):
        key=(fid,v,p,c,protect)
        if key not in cache:
            r=trace(xs[fid],v,p,c,protect)
            name=f'{fid}_{v}_{p}_cash{int(c)}_protected{int(protect)}.json.gz'
            with gzip.open(folder/name,'wt') as f:json.dump(r,f,separators=(',',':'))
            cache[key]=r
        return cache[key]
    pairs=[]
    for x in selection['refinement_cases']:
        a=get(x['id'],x['structure'],'retire_12m');b=get(x['id'],x['structure'],'retire_12m',protect=True)
        expected=x['debt_shortfall'] or x['operating_shortfall'];observed=b['terminal']['debt_shortfall'] or b['terminal']['operating_shortfall']
        assert abs(expected['amount_usd']-observed['amount_usd'])<.01
        pairs.append({'type':'refinement_cash_loss','id':x['id'],'structure':x['structure'],**compare(a,b,x['last_date'])})
    x=selection['negative_case']
    if x:
        a=get(x['id'],x['structure'],x['policy']);b=get(x['id'],x['structure'],x['policy'],1e8)
        pair=compare(a,b);assert pair['backing_per_share_difference']<0
        pairs.append({'type':'negative_cash_effect',**x,**pair})
    x=selection['reversal_case']
    if x:
        for v in ('face','continuation'):
            for p in ('common_12m','retire_12m'):
                a=get(x['id'],v,p);b=get(x['id'],v,p,1e8)
                pairs.append({'type':'valuation_ranking_reversal','id':x['id'],'structure':v,'policy':p,**compare(a,b)})
    atomic(OUT/'trace_summary.json',{'simulations':len(cache),'comparisons':pairs})
    print(json.dumps({'trace_simulations':len(cache),'paired_traces':len(pairs),'negative_case':selection['negative_case'],'reversal_case':selection['reversal_case']}),flush=True)

if __name__=='__main__':main()
