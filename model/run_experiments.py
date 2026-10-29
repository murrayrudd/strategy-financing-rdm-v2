"""Paired controlled stress design. These counts are not probabilities."""
from concurrent.futures import ProcessPoolExecutor,as_completed
from dataclasses import replace,asdict
from pathlib import Path
from decimal import Decimal as D
from datetime import date
import json,traceback,hashlib,sys
from simulation import *

BASE=Assumptions()
VARIANTS=[BASE,
 replace(BASE,name='tax_zero',tax_rate=0),
 replace(BASE,name='tax_high_low_basis',tax_rate=.35,basis_fraction_of_reported_cost=.5),
 replace(BASE,name='slow_settlement',equity_settlement_days=3,asset_settlement_days=5),
 replace(BASE,name='legal_capacity_075bn',cash_legal_capacity_per_year=7.5e8),
 replace(BASE,name='legal_capacity_zero',cash_legal_capacity_per_year=0,stock_dividends_permitted=False),
 replace(BASE,name='loan_late_low_rate',other_loan_repayment='2027-06-30',other_loan_rate=.052),
 replace(BASE,name='loan_late_high_rate',other_loan_repayment='2027-06-30',other_loan_rate=.15),
 replace(BASE,name='cash_conversion',conversion_method='cash'),
 replace(BASE,name='combination_conversion',conversion_method='combination'),
 replace(BASE,name='no_conversion',conversion_behavior='none',issuer_calls=False),
 replace(BASE,name='no_holder_puts',put_fraction=0),
 replace(BASE,name='program_renewal',authorization_renewal=True),
 replace(BASE,name='stock_dividends',stock_dividend_election=True),
 replace(BASE,name='less_usable_liquidity',foreign_liquidity_available=False,treasury_haircut=.01),
 replace(BASE,name='cash_no_holder_puts',put_fraction=0,conversion_method='cash'),
 replace(BASE,name='combination_no_holder_puts',put_fraction=0,conversion_method='combination')]

def one(task):
    f,p,a=task
    r=Simulation(f,p,a).run()
    if r['max_cash_reconciliation_residual']>D('.01'):raise AssertionError('cash ledger failed')
    return r

def endpoint(r,h):
    v=r['snapshots'][h]
    return (v['terminal'],False) if 'terminal' in v else (v,v['debt_shortfall'] is None and v['operating_shortfall'] is None)

def summarize(results):
    rows=[];changes=[]
    central={(r['future'],r['policy']):r for r in results if r['assumptions']['name']=='central'}
    no_puts={(r['future'],r['policy']):r for r in results if r['assumptions']['name']=='no_holder_puts'}
    for p in POLICIES:
        for h in map(str,HORIZONS):
            rs=[r for r in results if r['policy']==p.name and r['assumptions']['name']!='cash_increment_100m']
            eps=[endpoint(r,h) for r in rs]
            rows.append({'policy':p.name,'horizon':h,'runs':len(rs),
              'reached_horizon':sum(ok for _,ok in eps),
              'debt_payment_shortfall':sum(v['debt_shortfall'] is not None for v,_ in eps),
              'operating_payment_shortfall':sum(v['operating_shortfall'] is not None for v,_ in eps),
              'ever_preferred_suspension':sum(v['preferred_suspension'] for v,_ in eps),
              'nonpositive_common_backing_at_endpoint':sum(v['common_backing_nonpositive'] for v,_ in eps),
              'common_backing_loss_gt_50pct_at_endpoint':sum(v['material_common_backing_loss'] for v,_ in eps)})
    for r in results:
        if r['assumptions']['name'] in ('central','cash_increment_100m'):continue
        reference=no_puts if r['assumptions']['name'] in ('cash_no_holder_puts','combination_no_holder_puts') else central
        b=reference[r['future'],r['policy']]
        assert b['path_sha256']==r['path_sha256']
        for h in map(str,HORIZONS):
            v,ok=endpoint(r,h);vb,okb=endpoint(b,h)
            flags=['preferred_suspension','material_common_backing_loss','common_backing_nonpositive']
            changes.append({'future':r['future'],'policy':r['policy'],'variant':r['assumptions']['name'],'reference_variant':b['assumptions']['name'],'horizon':h,
              'changed_reach_horizon':ok!=okb,'changed_preferred_suspension':v['preferred_suspension']!=vb['preferred_suspension'],
              'changed_common_loss_class':v['material_common_backing_loss']!=vb['material_common_backing_loss'],
              'common_backing_per_share_delta':v['common_backing_per_share']-vb['common_backing_per_share'] if ok and okb else None,
              'endpoint_comparable':ok and okb})
    sensitivity=[]
    for a in VARIANTS[1:]:
        for h in map(str,HORIZONS):
            cr=[c for c in changes if c['variant']==a.name and c['horizon']==h]
            sensitivity.append({'variant':a.name,'horizon':h,'paired_comparisons':len(cr),
               **{k:sum(c[k] for c in cr) for k in ['changed_reach_horizon','changed_preferred_suspension','changed_common_loss_class']},
               'max_abs_backing_per_share_change_when_comparable':max([abs(c['common_backing_per_share_delta']) for c in cr if c['endpoint_comparable']]+[Z])})
    marginal=[]
    for r in results:
        if r['assumptions']['name']!='cash_increment_100m':continue
        b=central[r['future'],r['policy']];assert b['path_sha256']==r['path_sha256']
        for h in map(str,HORIZONS):
            v,ok=endpoint(r,h);vb,okb=endpoint(b,h)
            marginal.append({'future':r['future'],'policy':r['policy'],'horizon':h,'both_reach_horizon':ok and okb,
              'change_reached_horizon':int(ok)-int(okb),
              'conditional_common_backing_value_per_added_dollar':(v['common_backing_per_share']-vb['common_backing_per_share'])*D(OPEN['basic_common_shares_rounded'])/D(1e8) if ok and okb else None,
              'definition':'Difference in backing per share times opening common shares / $100m additional initial cash; excludes optimized decisions and price impact.'})
    return {'design':'6 controlled external paths x 17 assumption sets x 4 policies, plus 24 paired $100m cash perturbations. Cash/mixed settlement with no puts is paired to the no-put physical branch. No probability interpretation.',
      'core_runs':len(results)-len(marginal)//2,'cash_perturbation_runs':len(marginal)//2,'horizons':list(map(str,HORIZONS)),
      'outcome_counts':rows,'sensitivity':sensitivity,'paired_changes':changes,'marginal_cash':marginal,
      'all_external_path_pairs_identical':True,'max_cash_residual':max(r['max_cash_reconciliation_residual'] for r in results),
      'censoring':'A debt or operating cash shortfall stops the corporate simulation. Later endpoints are censored; preferred suspension alone does not stop it.',
      'publication_limit':'Controlled integration experiments are not the comprehensive RDM/PRIM analysis or a calibrated viability probability.'}

def main():
    out=ROOT/'results';out.mkdir(exist_ok=True)
    tasks=[(f,p,a) for f in FUTURES for a in VARIANTS for p in POLICIES]
    tasks.extend((f,p,replace(BASE,name='cash_increment_100m',initial_cash_increment=1e8)) for f in FUTURES for p in POLICIES)
    results=[];errors=[]
    if '--resume' in sys.argv and (out/'controlled_runs.json').exists():
        old=json.loads((ROOT/'results/controlled_experiment_design.json').read_text())
        # Resume only if all numerical engine inputs and runtime source match.
        assert old['futures']==[asdict(x) for x in FUTURES] and old['policies']==[asdict(x) for x in POLICIES]
        for name in ['simulation.py','contracts.py','mechanics.py','date_rules.py']:
            assert old['code_files_sha256'][name]==hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
        cached=json.loads((out/'controlled_runs.json').read_text(),parse_float=D)
        # Monetary result strings must be restored for arithmetic summaries.
        def restore(v):
            if isinstance(v,dict):return {k:restore(x) for k,x in v.items()}
            if isinstance(v,list):return [restore(x) for x in v]
            if isinstance(v,str):
                try:return D(v)
                except Exception:return v
            return v
        cached=[restore(r) for r in cached]
        for f,p,a in list(tasks):
            hit=next((r for r in cached if r['future']==f.name and r['policy']==p.name and r['assumptions']==json.loads(json.dumps(asdict(a)),parse_float=D)),None)
            if hit is not None:results.append(hit);tasks.remove((f,p,a))
        print('Reused verified runs',len(results),'new tasks',len(tasks),flush=True)
    (ROOT/'results/controlled_experiment_design.json').write_text(json.dumps({'futures':[asdict(x) for x in FUTURES],
       'policies':[asdict(x) for x in POLICIES],'assumptions':[asdict(x) for x in VARIANTS],
       'cash_perturbation':1e8,'code_files_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
       for name in ['simulation.py','contracts.py','mechanics.py','date_rules.py','run_experiments.py']}},indent=2))
    with ProcessPoolExecutor(max_workers=4) as pool:
        jobs={pool.submit(one,t):t for t in tasks}
        for job in as_completed(jobs):
            t=jobs[job]
            try:results.append(job.result())
            except Exception as e:errors.append({'future':t[0].name,'policy':t[1].name,'assumptions':t[2].name,'error':repr(e),'traceback':traceback.format_exc()})
            if (len(results)+len(errors))%24==0:print('Completed',len(results),'errors',len(errors),flush=True)
    results.sort(key=lambda r:(r['future'],r['assumptions']['name'],r['policy']))
    (out/'controlled_runs.json').write_text(json.dumps(results,indent=2,default=str))
    (out/'experiment_errors.json').write_text(json.dumps(errors,indent=2))
    if errors:print('ERRORS',len(errors));raise SystemExit(1)
    summary=summarize(results)
    (out/'controlled_summary.json').write_text(json.dumps(summary,indent=2,default=str))
    print(json.dumps({k:v for k,v in summary.items() if k in ('core_runs','cash_perturbation_runs','max_cash_residual','outcome_counts')},indent=2,default=str))

if __name__=='__main__':main()
