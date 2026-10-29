"""Add a Bitcoin accumulation outcome to retained RDM results.

Pure post-processing: no simulator, policy, quote, or input is changed.
The numerator is settled Bitcoin; the denominator is modeled economic shares.
This is not Strategy's assumed-dilution KPI or its Net BPS definition.
"""
from pathlib import Path
from collections import defaultdict
import json, math, hashlib
import numpy as np

ROOT = Path(__file__).resolve().parent
MODEL = ROOT/'model/strategy_rdm_review_v2'
if not MODEL.exists(): MODEL = ROOT.parent
POLICIES = [f'{p}_{m}m' for m in (3,12) for p in ('common','dual','capped','retire')]
OPEN = json.loads((MODEL/'data/opening.json').read_text())
Q0 = OPEN['btc']/OPEN['basic_common_shares_rounded']
SATS = 100_000_000
checks = defaultdict(int)
sources = {}

def read(path):
    p = MODEL/path
    sources[path] = hashlib.sha256(p.read_bytes()).hexdigest()
    return p

def records(phase):
    return [dict(r,phase=phase) for line in read(f'results/rdm/{phase}.jsonl').open()
            for r in json.loads(line)['rows']]

def quantiles(v):
    return {'n':len(v), **({k:float(np.quantile(v,q)) for k,q in [('p10',.1),('median',.5),('p90',.9)]} if v else {})}

def valid(r):
    q=r['Bitcoin_per_economic_share']
    assert (q is not None)==r['cash_service']
    if q is not None:
        assert math.isclose(q,r['Bitcoin_units']/r['common_shares'],rel_tol=1e-12,abs_tol=1e-15)
        assert q>=0 and r['last_date']==r['horizon']
    checks['endpoint_ratio_and_censoring']+=1

def grows(r):
    return r['cash_service'] and r['Bitcoin_per_economic_share']>Q0

def summarize(rs, ids):
    shared=[r for r in rs if r['id'] in ids]
    alive=[r for r in rs if r['cash_service']]
    return {'n':len(rs),'cash_service':len(alive),'cash_and_BPS_growth':sum(grows(r) for r in rs),
      'BPS_growth_and_common_preservation':sum(grows(r) and r['common_preservation'] for r in rs),
      'common_preservation_without_BPS_growth':sum(r['common_preservation'] and not grows(r) for r in rs),
      'BPS_growth_without_common_preservation':sum(grows(r) and not r['common_preservation'] for r in rs),
      'joint_success_and_BPS_growth':sum(grows(r) and r['joint_success'] for r in rs),
      'policy_survivor_growth_pct':quantiles([100*(r['Bitcoin_per_economic_share']/Q0-1) for r in alive]),
      'shared_survivor_growth_pct':quantiles([100*(r['Bitcoin_per_economic_share']/Q0-1) for r in shared]),
      'shared_survivor_BPS_sats':quantiles([SATS*r['Bitcoin_per_economic_share'] for r in shared])}

raw=records('main')+records('challenge')
for r in raw: valid(r)
grouped=defaultdict(lambda:defaultdict(dict))
for r in raw:grouped[(r['phase'],r['structure'],r['horizon'])][r['id']][r['policy']]=r
summary=[];paired=[];domains=[]
for (phase,v,h),futures in sorted(grouped.items()):
    assert len(futures)==(2000 if phase=='main' else 512)
    assert all(set(ps)==set(POLICIES) for ps in futures.values())
    ids={i for i,ps in futures.items() if all(r['cash_service'] for r in ps.values())}
    domains.append({'phase':phase,'structure':v,'horizon':h,'n':len(ids),'future_ids':sorted(ids)})
    for p in POLICIES:
        rs=[ps[p] for ps in futures.values()]
        x={'phase':phase,'structure':v,'horizon':h,'policy':p,**summarize(rs,ids)}
        regret=[SATS*(max(r['Bitcoin_per_economic_share'] for r in futures[i].values())-futures[i][p]['Bitcoin_per_economic_share']) for i in sorted(ids)]
        assert all(z>=0 for z in regret)
        x['BPS_regret_sats']=quantiles(regret)
        x['BPS_regret_max_sats']=max(regret)
        summary.append(x)
    for p in POLICIES:
        common=[i for i,ps in futures.items() if ps['common_12m']['cash_service'] and ps[p]['cash_service']]
        pairs=[(futures[i]['common_12m'],futures[i][p]) for i in common]
        paired.append({'phase':phase,'structure':v,'horizon':h,'reference':'common_12m','alternative':p,'n':len(futures),'paired_survivors':len(pairs),
          'growth_gains':sum(not grows(ps['common_12m']) and grows(ps[p]) for ps in futures.values()),
          'growth_losses':sum(grows(ps['common_12m']) and not grows(ps[p]) for ps in futures.values()),
          'higher_BPS_lower_backing':sum(a['Bitcoin_per_economic_share']>b['Bitcoin_per_economic_share'] and a['common_backing_per_share']<b['common_backing_per_share'] for b,a in pairs),
          'lower_BPS_higher_backing':sum(a['Bitcoin_per_economic_share']<b['Bitcoin_per_economic_share'] and a['common_backing_per_share']>b['common_backing_per_share'] for b,a in pairs),
          'BPS_difference_sats':quantiles([SATS*(a['Bitcoin_per_economic_share']-b['Bitcoin_per_economic_share']) for b,a in pairs])})

# Existing common survivor domains allow direct comparison with residual regret.
oldreg=json.loads(read('results/technical_revision/regret_metric_diagnostics.json').read_text())
for x in oldreg:
    r=next(z for z in summary if z['phase']=='main' and all(z[k]==x[k] for k in ('structure','horizon','policy')))
    assert r['BPS_regret_sats']['n']==x['floored_regret_per_share']['n']
    checks['shared_domain_matches_residual_regret']+=1

# Reuse the technical screen comparison without running a new simulation.
cg=[]
for p in sorted((MODEL/'results/technical_revision/groups/capacity').glob('*.json')):
    g=json.loads(read(str(p.relative_to(MODEL))).read_text())
    cg.extend(dict(r,phase=g['phase']) for r in g['rows'])
selected={r['id'] for r in cg}
names=['common_12m','dual_12m','capped_12m','retire_12m','retire_protected_12m']
cg.extend(dict(r,distribution_mode='calendar_allowance') for r in raw if r['id'] in selected and r['policy'] in names)
for phase,name in [('main','legal_headroom'),('challenge','legal_headroom_challenge')]:
    for line in read(f'results/rdm/{name}.jsonl').open():
        g=json.loads(line)
        if g['id'] in selected:
            cg.extend(dict(r,phase=phase,policy='retire_protected_12m',distribution_mode='calendar_allowance') for r in g['rows'])
for r in cg: valid(r)
capdomains=json.loads(read('results/technical_revision/capacity_regret_common_domain.json').read_text())
cby=defaultdict(list)
for r in cg:cby[(r['phase'],r['structure'],r['horizon'],r['distribution_mode'])].append(r)
capacity=[]
for (phase,v,h,mode),rs in sorted(cby.items()):
    old=next(r for r in capdomains if (r['phase'],r['structure'],r['horizon'],r['distribution_mode'])==(phase,v,h,mode))
    ids=set(old['future_ids']);best=defaultdict(float)
    for r in rs:
        if r['id'] in ids:
            assert r['cash_service']
            best[r['id']]=max(best[r['id']],r['Bitcoin_per_economic_share'])
    for p in names:
        vals=[r for r in rs if r['policy']==p]
        x={'phase':phase,'structure':v,'horizon':h,'distribution_mode':mode,'policy':p,**summarize(vals,ids)}
        x['BPS_regret_sats']=quantiles([SATS*(best[r['id']]-r['Bitcoin_per_economic_share']) for r in vals if r['id'] in ids])
        assert x['BPS_regret_sats']['n']==old['n']
        checks['capacity_common_domains']+=1
        capacity.append(x)

# Matched funding uses its original selected domains and retains alternative failures.
fg=[]
for p in sorted((MODEL/'results/technical_revision/groups/funding').glob('*.json')):
    g=json.loads(read(str(p.relative_to(MODEL))).read_text())
    fg.extend(dict(r,phase=g['phase']) for r in g['rows'])
for r in fg:valid(r)
oldfund=json.loads(read('results/technical_revision/matched_funding_summary.json').read_text())
funding=[]
for old in oldfund:
    ids=set(old['matched_future_ids'])
    rs=[r for r in fg if r['id'] in ids and all(r[k]==old[k] for k in ('phase','structure','horizon'))]
    base={r['id']:r for r in rs if r['policy']=='replay_STRC_0pct'}
    for p in ['replay_STRC_0pct','replay_STRC_25pct','replay_STRC_50pct']:
        vals=[r for r in rs if r['policy']==p];pairs=[(base[r['id']],r) for r in vals if r['cash_service']]
        assert len(vals)==old['all_mixes_matched_futures']
        prior=next(r for r in old['policies'] if r['policy']==p)
        assert len(pairs)==prior['paired_common_survivors']
        funding.append({k:old[k] for k in ('phase','structure','horizon')}|{'policy':p,'n':len(vals),'paired_survivors':len(pairs),
          'cash_and_BPS_growth':sum(grows(r) for r in vals),
          'BPS_difference_sats':quantiles([SATS*(a['Bitcoin_per_economic_share']-b['Bitcoin_per_economic_share']) for b,a in pairs]),
          'higher_BPS_lower_backing':sum(a['Bitcoin_per_economic_share']>b['Bitcoin_per_economic_share'] and a['common_backing_per_share']<b['common_backing_per_share'] for b,a in pairs)})
        checks['funding_domains']+=1

result={'metric':'Settled Bitcoin per modeled economic common share; not the company assumed-dilution KPI.',
 'opening_BPS':Q0,'opening_sats_per_share':Q0*SATS,
 'growth_criterion':'Cash service through endpoint and strictly positive change from the opening ratio. Cash failures are not assigned an endpoint ratio or regret.',
 'quantile_method':'numpy.quantile default linear interpolation; equal design weights, not event probabilities.',
 'original_summary':summary,'paired_original':paired,'original_shared_survivor_domains':domains,
 'capacity_summary':capacity,'matched_funding':funding,
 'verification':dict(checks),'source_sha256':sources,'simulation_changes':False}
(ROOT/'bitcoin_per_share_analysis.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'opening_sats':Q0*SATS,'checks':dict(checks),'summary_records':len(summary),'capacity_records':len(capacity),'funding_records':len(funding)}))
for r in summary:
    if r['phase']=='main' and r['structure']=='continuation' and r['horizon']=='2033-06-30':
        print(json.dumps({k:r[k] for k in ['policy','cash_and_BPS_growth','BPS_growth_and_common_preservation','common_preservation_without_BPS_growth','shared_survivor_growth_pct','BPS_regret_sats']}))
