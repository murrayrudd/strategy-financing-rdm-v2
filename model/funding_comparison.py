"""Fixed financing schedule comparison; a mechanism experiment, not a policy forecast."""
from pathlib import Path
from dataclasses import replace
import json, traceback
from simulation import Simulation,D,Z,money,path_digest,is_open,advance,cash_distribution_blockers,preferred_retirement_allowed
from distribution_capacity import CapacitySimulation
from rdm_design import POLICIES,assumptions,future,external_path
from rdm_run import flatten

class FundingReference(CapacitySimulation):
    def __init__(self,*args,**kwargs):
        self.funding_plan={}
        super().__init__(*args,**kwargs)
    def issue(self,k,gross):
        before=self.gross_issued[k]
        super().issue(k,gross)
        actual=self.gross_issued[k]-before
        if k=='MSTR' and actual:
            assert str(self.day) not in self.funding_plan
            self.funding_plan[str(self.day)]={'requested':gross,'gross':actual}

class FundingReplay(CapacitySimulation):
    def __init__(self,*args,funding_plan,preferred_fraction=0,**kwargs):
        self.funding_plan=funding_plan
        self.preferred_fraction=money(preferred_fraction)
        if not 0<=self.preferred_fraction<=1:raise ValueError('Financing fraction')
        self.replay_events=[]
        super().__init__(*args,**kwargs)
    def replay_funding(self):
        p=self.funding_plan.get(str(self.day))
        if p is None:return
        before=dict(self.gross_issued);quote=self.quote()
        eligible=self.pt['strc_price']>=95 and self.backing()>0
        f=self.preferred_fraction
        if f==0:
            self.issue('MSTR',p['requested'])
        else:
            self.issue('MSTR',p['gross']*(1-f))
            if eligible:self.issue('STRC',p['gross']*f)
        actual=sum((self.gross_issued[k]-before[k] for k in before),Z)
        tolerance=quote+self.pt['strc_price']+D('.01')
        self.replay_events.append({'date':str(self.day),'target_gross':float(p['gross']),
          'actual_gross':float(actual),'common_gross':float(self.gross_issued['MSTR']-before['MSTR']),
          'preferred_gross':float(self.gross_issued['STRC']-before['STRC']),
          'gap':float(p['gross']-actual),'rounding_tolerance':float(tolerance),
          'funding_matched':abs(actual-p['gross'])<=tolerance,'preferred_gate_open':eligible})
    def finance(self):
        if not is_open(self.day,'US_EQUITY') or str(self.day) in self.a.exceptional_market_closures:return
        monthly=self.last_month!=(self.day.year,self.day.month)
        if monthly:self.last_month=(self.day.year,self.day.month)
        target=self.needed(round(self.policy.reserve_months*365.25/12));near=self.needed(12)
        pending=sum((v for _,v,_ in self.liq.pending),Z)+sum((o.get('net',Z) for o in self.pending),Z)
        spendable=self.projected_cash()
        if self.liq.treasury and spendable<target:
            amount=min(self.liq.treasury,target-spendable)
            due=self.settlement(self.day,self.a.asset_settlement_days,'FED_NY')
            self.liq.treasury_sale(amount,due,self.a.treasury_haircut);spendable+=amount*(1-money(self.a.treasury_haircut))
        self.replay_funding()
        pending=sum((v for _,v,_ in self.liq.pending),Z)+sum((o.get('net',Z) for o in self.pending),Z)
        spendable=self.projected_cash()
        # Asset sales implement the policy's stated reserve target, including
        # known put/call and conversion settlements, at CURRENT market inputs.
        # A reserve is an asset-use rule, never a second asset.
        funding_target=max(near,target)
        if spendable<funding_target and self.btc.units:
            px=self.pt['btc'];basis_per=self.btc.basis/self.btc.units
            net_per=px*D('.999')-max(Z,px*D('.999')-basis_per)*money(self.a.tax_rate)
            units=min(self.btc.units,D(100000),(funding_target-spendable)/net_per)
            due=self.settlement(self.day,self.a.asset_settlement_days,'FED_NY')
            sale=self.btc.sell(units,px,'.001',self.a.tax_rate,self.liq,due)
            self.metrics['btc_sold']+=units;self.metrics['tax_reserved_total']+=sale['tax_reserved']
            self.log('Bitcoin_sale',units=units,settlement=str(due),**sale)
        if self.deferrals:self.metrics['strf_efforts_observations']+=1
        # Discretionary allocation uses settled cash, after pending commitments.
        if monthly:
            surplus=max(Z,self.liq.usable-target)
            if self.policy.retire_strc_surplus and surplus>D('1010000') and self.pref['STRC'].unpaid==0 and not cash_distribution_blockers('STRC',list(self.pref.values())):
                outstanding=self.pref['STRC'].shares
                n=min(outstanding,(surplus/D('101.6')).to_integral_value(rounding='ROUND_FLOOR'))
                if preferred_retirement_allowed('STRC','ordinary',n,outstanding,self.total_issued['STRC']):
                    due=advance(self.day,3,'FED_NY')
                    escrow=n*D('101.6')
                    if escrow>surplus or escrow>self.liq.legal_budget:continue_retirement=False
                    else:continue_retirement=True
                    if continue_retirement:
                        self.liq.record(-escrow,'redemption_setaside');self.liq.restricted+=escrow
                        self.pending.append({'kind':'STRC_redemption','due':due,'shares':n,'escrow':escrow,'notice':str(self.day)})
                    self.log('STRC_redemption_notice',shares=n,redemption=str(due))
            elif surplus>1000 and self.backing()>0:
                amount=min(surplus,D(100000)*self.pt['btc'])
                self.liq.pay(amount,'Bitcoin_purchase')
                units=amount*D('.999')/self.pt['btc'];due=self.settlement(self.day,self.a.asset_settlement_days,'FED_NY')
                self.pending.append({'kind':'BTC_buy','due':due,'units':units,'cost':amount});self.metrics['btc_purchased']+=units
        if self.a.equity_settlement_days==0 or self.a.asset_settlement_days==0:self.settle_pending()

def funding_one(x):
    try:
        path=external_path(x);digest=path_digest(path);rows=[];diagnostics=[]
        p=next(p for p in POLICIES if p.name=='common_12m')
        for structure in ('face','continuation'):
            a=assumptions(x,structure)
            ref=FundingReference(future(x),p,a,external_path=path,external_digest=digest,
                                  distribution_mode='no_exogenous_allowance')
            rr=ref.run();reference_rows=flatten(rr,structure,0)
            for frac in (0.,.25,.5):
                s=FundingReplay(future(x),p,a,external_path=path,external_digest=digest,
                    distribution_mode='no_exogenous_allowance',funding_plan=ref.funding_plan,preferred_fraction=frac)
                result=s.run();these=flatten(result,structure,0)
                if frac==0:
                    assert these==reference_rows,'All-common fixed-schedule control did not reproduce the reference'
                assert abs(result['max_cash_reconciliation_residual'])<.01
                for row in these:
                    h=row['horizon'];rh=next(z for z in reference_rows if z['horizon']==h)
                    events=[e for e in s.replay_events if e['date']<=h]
                    row.update(policy=f'replay_STRC_{int(frac*100)}pct',distribution_mode='no_exogenous_allowance',
                        reference_cash_service=rh['cash_service'],
                        financing_matched_to_stop=all(e['funding_matched'] for e in events),
                        funding_gap_usd=sum(e['gap'] for e in events),
                        funding_target_usd=sum(e['target_gross'] for e in events),
                        funding_unmatched_events=sum(not e['funding_matched'] for e in events))
                    rows.append(row)
                diagnostics.append({'structure':structure,'fraction':frac,'events':s.replay_events})
        return {'id':x['id'],'phase':x['phase'],'rows':rows,'funding_diagnostics':diagnostics,'simulations':8}
    except Exception:return {'id':x['id'],'error':traceback.format_exc()}
