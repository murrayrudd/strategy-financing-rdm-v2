"""Separate signed common backing from a nonnegative residual-payoff proxy.

This is post-processing. It changes no prices, behavior, or original outputs.
The floor is neither a market-value estimate nor a recovery model at failure.
"""
from pathlib import Path
from collections import defaultdict
import json, statistics
from simulation import OPEN
from technical_experiments import OUT, atomic

ROOT=Path(__file__).resolve().parent
ENDOWMENT=1e8
INITIAL_SHARES=OPEN['basic_common_shares_rounded']

def summary(values):
    import numpy as np
    if not values:return {'n':0}
    return {'n':len(values),'median':float(np.median(values)),
            'p10':float(np.quantile(values,.1)),'p90':float(np.quantile(values,.9)),
            'maximum':max(values),'minimum':min(values)}

def read_rows(name):
    return [r for line in (ROOT/f'results/rdm/{name}.jsonl').open()
              for r in json.loads(line)['rows']]

def main():
    baseline=read_rows('main');cash=read_rows('cash')
    key=lambda r:(r['id'],r['structure'],r['horizon'],r['policy'])
    idx={key(r):r for r in baseline}
    domains={r['horizon']:set(r['future_ids']) for r in json.loads(
        (ROOT/'results/analysis/marginal_cash_common_domain.json').read_text())}
    grouped=defaultdict(list);cases=[]
    for c in cash:
        if c['id'] not in domains[c['horizon']]:continue
        b=idx[key(c)];assert b['cash_service'] and c['cash_service']
        bps0,bps1=b['common_backing_per_share'],c['common_backing_per_share']
        raw=(bps1-bps0)*INITIAL_SHARES/ENDOWMENT
        floored=(max(0.,bps1)-max(0.,bps0))*INITIAL_SHARES/ENDOWMENT
        total_change=bps1*c['common_shares']-bps0*b['common_shares']
        record={'id':c['id'],'horizon':c['horizon'],'structure':c['structure'],
                'policy':c['policy'],'raw_change_per_extra_dollar':raw,
                'floored_change_per_extra_dollar':floored,
                'base_backing_per_share':bps0,'extra_backing_per_share':bps1,
                'total_backing_change_usd':total_change,
                'common_share_change':c['common_shares']-b['common_shares']}
        grouped[(c['horizon'],c['structure'],c['policy'])].append(record)
        if raw<0:cases.append(record)
    cash_summary=[]
    for (h,v,p),rs in sorted(grouped.items()):
        cash_summary.append({'horizon':h,'structure':v,'policy':p,'n':len(rs),
            'raw':summary([r['raw_change_per_extra_dollar'] for r in rs]),
            'floored':summary([r['floored_change_per_extra_dollar'] for r in rs]),
            'raw_negative':sum(r['raw_change_per_extra_dollar']<0 for r in rs),
            'floored_negative':sum(r['floored_change_per_extra_dollar']<0 for r in rs),
            'raw_negative_but_total_backing_improves':sum(r['raw_change_per_extra_dollar']<0 and r['total_backing_change_usd']>0 for r in rs),
            'both_residuals_nonpositive':sum(r['base_backing_per_share']<=0 and r['extra_backing_per_share']<=0 for r in rs)})
    # Same all-policy survivor conditioning as the original regret analysis;
    # all eight original policies remain in this comparison.
    grouped=defaultdict(lambda:defaultdict(dict))
    for r in baseline:grouped[(r['horizon'],r['structure'])][r['id']][r['policy']]=r
    regrets=[]
    for (h,v),futures in sorted(grouped.items()):
        bypolicy=defaultdict(lambda:{'raw':[],'floored':[]})
        for fid,ps in futures.items():
            assert len(ps)==8
            if not all(r['cash_service'] for r in ps.values()):continue
            raw={p:r['common_backing_per_share'] for p,r in ps.items()}
            floor={p:max(0.,z) for p,z in raw.items()}
            for p in ps:
                bypolicy[p]['raw'].append(max(raw.values())-raw[p])
                bypolicy[p]['floored'].append(max(floor.values())-floor[p])
        for p,vs in sorted(bypolicy.items()):
            assert all(0<=b<=a+1e-8 for a,b in zip(vs['raw'],vs['floored']))
            regrets.append({'horizon':h,'structure':v,'policy':p,
                'raw_regret_per_share':summary(vs['raw']),
                'floored_regret_per_share':summary(vs['floored']),
                'regret_changed_futures':sum(abs(a-b)>1e-9 for a,b in zip(vs['raw'],vs['floored']))})
    atomic(OUT/'cash_metric_diagnostics.json',{
        'interpretation':'Finite $100 million opening-cash perturbation on the same original all-policy, both-valuation survivor domains. Signed backing remains a solvency diagnostic; max(backing,0) per economic share is a residual-payoff proxy, not fair value. Failed futures remain censored, not assigned zero recovery.',
        'summary':cash_summary,'negative_raw_cases':cases})
    atomic(OUT/'regret_metric_diagnostics.json',regrets)
    print(json.dumps({'cash_comparisons':sum(r['n'] for r in cash_summary),
        'negative_raw_effect_records':len(cases),
        'negative_floored_effect_records':sum(c['floored_change_per_extra_dollar']<0 for c in cases),
        'negative_raw_but_total_backing_improves':sum(c['total_backing_change_usd']>0 for c in cases),
        'regret_summary_records':len(regrets)}))

if __name__=='__main__':main()
