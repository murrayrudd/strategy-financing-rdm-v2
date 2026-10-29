"""Locked exploratory design; equal sampling weights are not probabilities."""
from pathlib import Path
from dataclasses import asdict
from functools import lru_cache
import numpy as np
import csv,json,math,hashlib
from simulation import Future,Policy,Assumptions,START,END,money,D,Z,timedelta
ROOT=Path(__file__).resolve().parent
RANGES={
 'cagr':[-.30,.45], 'valuation_factor':[.35,2.5], 'shock_depth':[.15,.85],
 'shock_start':[.25,5.5], 'recovery_years':[.4,4.], 'closure_months':[0.,60.],
 'closure_threshold':[.2,.65], 'capacity':[.05,1.25], 'closure_start':[.25,6.],
 'strc_rate':[.10,.18], 'stress_spread':[0.,.06], 'strc_discount':[0.,20.],
 'operating_cashflow':[-3e8,1e8], 'fx_factor':[.75,1.35], 'valuation_stress':[0.,1.2],
 'tax_rate':[0.,.35], 'basis_fraction':[.4,1.2], 'annual_legal_budget':[.5e9,6e9],
 'common_budget':[3e9,12e9], 'strc_budget':[3e9,12e9], 'loan_rate':[.05,.15],
 'preferred_premium':[0.,.30], 'reference_volatility':[.35,1.], 'reference_years':[1.,5.]}
CATS={'put_fraction':[0.,.5,1.], 'renewal':[False,True], 'linked':[False,True],
 'legal_regime':['zero','finite','finite','finite','finite','finite','finite','finite','unlimited','unlimited'],
 'conversion_method':['physical','cash','combination'],
 'conversion_behavior':['eligible','eligible','eligible','maturity_only','none'],
 'issuer_calls':[False,True], 'stock_dividend_election':[False,True],
 'slow_settlement':[False,True], 'late_loan':[False,True], 'foreign_available':[False,True]}
POLICIES=[Policy(f'{kind}_{months}m',months,4e8 if kind in ('dual','capped') else 0,4e8,
                .5 if kind=='capped' else None,kind=='retire')
          for months in (3,12) for kind in ('common','dual','capped','retire')]

def design(n,seed,phase):
    rng=np.random.default_rng(seed);names=list(RANGES)+list(CATS)+['path_coordinate']
    u=np.column_stack([(rng.permutation(n)+rng.random(n))/n for _ in names]);out=[]
    for i,row in enumerate(u):
        x={'id':f'{phase}_{i:04d}','phase':phase,'path_seed':seed*10000+i}
        for name,v in zip(names,row):
            if name in RANGES:a,b=RANGES[name];x[name]=float(a+(b-a)*v)
            elif name in CATS:x[name]=CATS[name][min(len(CATS[name])-1,int(v*len(CATS[name])))]
            else:x['path_family']=('block' if v<(0.25 if phase=='main' else .5) else ('triangle' if phase=='main' else 'plateau'))
        out.append(x)
    return out

def assumptions(x,structure,cash=0.):
    legal=0. if x['legal_regime']=='zero' else 1e30 if x['legal_regime']=='unlimited' else x['annual_legal_budget']
    return Assumptions(name=x['id'],tax_rate=x['tax_rate'],basis_fraction_of_reported_cost=x['basis_fraction'],
      equity_settlement_days=3 if x['slow_settlement'] else 1,asset_settlement_days=5 if x['slow_settlement'] else 1,
      cash_legal_capacity_per_year=legal,stock_dividends_permitted=True,stock_dividend_election=x['stock_dividend_election'],
      foreign_liquidity_available=x['foreign_available'],other_loan_repayment='2027-06-30' if x['late_loan'] else '2026-07-01',
      other_loan_rate=x['loan_rate'],conversion_behavior=x['conversion_behavior'],conversion_method=x['conversion_method'],
      put_fraction=x['put_fraction'],issuer_calls=x['issuer_calls'],authorization_renewal=x['renewal'],
      new_common_program_budget=x['common_budget'],new_strc_program_budget=x['strc_budget'],initial_cash_increment=cash,
      common_valuation=structure,reference_volatility=x['reference_volatility'],reference_years=x['reference_years'])

def future(x):return Future(x['id'],x['cagr'],x['shock_start'],x['shock_depth'],x['recovery_years'],
 x['valuation_factor'],x['capacity'],x['closure_start'],x['closure_months']/12,x['strc_rate'],x['stress_spread'],
 x['strc_discount'],x['fx_factor'],x['operating_cashflow'])

@lru_cache(2)
def returns(phase):
    rows=list(csv.DictReader((ROOT/'data/historical/Bitcoin_daily_2014_2025.csv').open()))
    prices=np.array([float(r['price_usd']) for r in rows if ('2014'<=r['date'][:4]<='2019' if phase=='main' else '2020'<=r['date'][:4]<='2025')])
    return np.diff(np.log(prices))

def external_path(x):
    n=(END-START).days+366+90;t=np.arange(n+1)/365.25
    trend=np.log1p(x['cagr'])*t
    def shock(start,depth,recovery,plateau=False):
        dt=t-start
        if plateau:shape=np.clip(dt/.2,0,1)*np.clip((recovery+.7-dt)/.5,0,1)
        else:shape=np.where(dt<=.2,np.clip(dt/.2,0,1),np.clip(1-(dt-.2)/recovery,0,1))
        return np.log1p(-depth)*shape
    if x['path_family']=='block':
        rng=np.random.default_rng(x['path_seed']);r=returns(x['phase']);v=[]
        while len(v)<n:
            j=int(rng.integers(0,len(r)-180+1));v.extend(r[j:j+180])
        v=np.array(v[:n]);noise=np.r_[0,np.cumsum(v-v.mean())]
    else:
        noise=shock(x['shock_start'],x['shock_depth'],x['recovery_years'],x['path_family']=='plateau')
        noise+=shock(x['shock_start']+2.5,x['shock_depth']*.55,x['recovery_years']*.65,x['path_family']=='plateau')
    btc=58714*np.exp(trend+noise);drawdown=1-btc/np.maximum.accumulate(btc);stress=np.minimum(1,drawdown/.6)
    clock=(t>=x['closure_start'])&(t<x['closure_start']+x['closure_months']/12)
    closed=(clock | (drawdown>x['closure_threshold'])) if x['linked'] else clock
    linkstress=stress if x['linked'] else np.zeros_like(stress)
    multiple=.9616113760674149*np.exp(np.log(x['valuation_factor'])*np.minimum(t/5,1)-x['valuation_stress']*linkstress)
    capacity=np.where(closed,0,x['capacity']*np.maximum(.1,1-.8*linkstress))
    premium=100*x['preferred_premium']*np.minimum(t/2,1)
    out={}
    for i in range(n+1):
        out[START+timedelta(days=i)]={'btc':money(btc[i]),'multiple':money(multiple[i]),'capacity':money(capacity[i]),
          'fx':money(1.1408*math.exp(math.log(x['fx_factor'])*min(t[i]/5,1))),
          'strc_price':money(100+premium[i]-x['strc_discount']*linkstress[i]),'stress':money(stress[i]),'sofr':D('.03'),
          **{'preferred_price_'+k:money(100+premium[i]) for k in ('STRF','STRE','STRK','STRD')}}
    return out

def features(x):
    return {k:v for k,v in x.items() if k not in ('id','phase','path_seed','split')}

def lock():
    main=design(2000,20261022,'main');challenge=design(512,20261023,'challenge')
    rng=np.random.default_rng(71926);train=set(int(i) for i in rng.permutation(2000)[:1500])
    for i,x in enumerate(main):x['split']='train' if i in train else 'holdout'
    for x in challenge:x['split']='challenge'
    protocol={'main_futures':2000,'challenge_futures':512,'cash_futures':125,'cash_increment_usd':1e8,
      'cash_selection':'Every sixteenth main future in immutable generation order', 'policies':[asdict(p) for p in POLICIES],
      'structures':['face','continuation'],'horizons':['2031-06-30','2033-06-30'],'ranges':RANGES,'categorical_allocations':CATS,
      'main_seed':20261022,'challenge_seed':20261023,'split_seed':71926,'train':1500,'holdout':500,
      'price_anchor_usd':86.93,'anchor_source':'Supplied paper v11 Section 2.4 and Appendix A1; not a new market-price observation.',
      'closure_tail_futures':125,'closure_tail_selection':'Every sixteenth main future, identical to the cash perturbation subset',
      'closure_tail_starts':['2031-06-30','2033-06-30'],'closure_tail_ends':['2032-06-30','2034-06-30'],
      'closure_tail_rule':'Set both issuance channels to zero after the original endpoint; all other path inputs and policy rules unchanged. Evaluate only conditional on survival to closure.',
      'legal_zero_scope':'Zero cash distribution budget; stock dividend permission remains distinct and enabled.',
      'interpretation':'Design shares are not event probabilities. No calibrated probability distribution or optimizer.',
      'discovery':{'PRIM_peel':.05,'PRIM_paste':.05,'min_mass':.05,'max_restricted_dimensions':4,'max_boxes':3,'training_density_target':.9,
       'validation_density_screen':.8,'validation_coverage_screen':.7,'min_validation_cases':20,'stability_subsamples':12,'median_Jaccard_screen':.6,
       'CART_max_depth':3,'CART_min_leaf_fraction':.03,'thresholds_status':'Research screening criteria; failure limits claims rather than initiating post-hoc tuning.'}}
    for name,data in [('rdm_main.json',main),('rdm_challenge.json',challenge),('rdm_protocol.json',protocol)]:
        p=ROOT/'data'/name;content=json.dumps(data,indent=2)
        if p.exists() and p.read_text()!=content:raise ValueError('locked design changed '+name)
        p.write_text(content)
    return protocol

if __name__=='__main__':print(json.dumps(lock(),indent=2))
