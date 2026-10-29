"""Dated v2 integration driver for controlled RDM experiments.

No optimizer and no estimated price impact. External paths are immutable.
Cash/share delivery, record entitlements and nominal accrual dates are separate.
The driver stops at an unpaid debt/operating commitment, but continues through
preferred suspension. Such stopping is a distress boundary, not a legal default
or bankruptcy forecast. Exact holder-level rounding is outside aggregate runs.
"""
from dataclasses import dataclass,field,asdict
from datetime import date,timedelta
from calendar import monthrange
from decimal import Decimal as D
from bisect import bisect_right
from pathlib import Path
from functools import lru_cache
import json,math,hashlib
from valuation import residual_reference
from mechanics import (Preferred,Liquidity,BitcoinPosition,money,cash_distribution_blockers,
    mandatory_dividend_amount,strk_stock_dividend,strc_rate_floor,thirty360,
    liquidation_preference,repurchase_excise,Cohort)
from date_rules import is_open,following,previous_trading,strf_deferred_date
from contracts import (advance,TERMS,conversion_eligible,valid_call,make_whole,
    observation_days,conversion_settlement,strk_conversion,preferred_retirement_allowed)

ROOT=Path(__file__).resolve().parent
OPEN=json.loads((ROOT/'data/opening.json').read_text())
PREF=json.loads((ROOT/'data/preferred_terms.json').read_text())
START=date(2026,6,30);END=date(2033,6,30);HORIZONS=[date(2031,6,30),END]
Z=D(0);EPS=D('.000001')
ORDER=['STRF','STRC','STRE','STRK','STRD']

@dataclass(frozen=True)
class Assumptions:
    name:str='central'
    tax_rate:float=.25
    basis_fraction_of_reported_cost:float=1.
    loss_offset_budget:float=0.
    equity_settlement_days:int=1
    asset_settlement_days:int=1
    cash_legal_capacity_per_year:float=1e30
    stock_dividends_permitted:bool=True
    stock_dividend_election:bool=False
    foreign_liquidity_available:bool=True
    treasury_haircut:float=0.
    other_loan_repayment:str='2026-07-01'
    other_loan_rate:float=.085
    conversion_behavior:str='eligible'
    conversion_method:str='physical'
    put_fraction:float=1.
    issuer_calls:bool=True
    authorization_renewal:bool=False
    # These are explicit future program assumptions, not filed authorizations.
    new_common_program_budget:float=6e9
    new_strc_program_budget:float=6e9
    exceptional_market_closures:tuple=()
    initial_cash_increment:float=0.
    strc_excise_covered:bool=True
    common_valuation:str='face'
    reference_volatility:float=.65
    reference_years:float=3.
    calibrate_opening_quote:bool=True

@dataclass(frozen=True)
class Policy:
    name:str
    reserve_months:int
    strc_monthly_gross:float
    common_monthly_growth:float
    preferred_asset_cap:float|None=None
    retire_strc_surplus:bool=False
    common_growth_rule:str='premium'

POLICIES=[Policy('growth_3m',3,4e8,4e8,common_growth_rule='unconditional'),
          Policy('reserve_12m',12,4e8,4e8,.5),
          Policy('common_only_12m',12,0,4e8),
          Policy('retire_strc_12m',12,0,4e8,None,True)]

@dataclass(frozen=True)
class Future:
    name:str
    cagr:float
    shock_start:float
    shock_depth:float
    recovery_years:float
    valuation_terminal_factor:float
    capacity:float
    closure_start:float
    closure_years:float
    strc_rate:float=.12
    stress_spread:float=.02
    strc_discount:float=5.
    fx_terminal_factor:float=1.
    annual_operating_cashflow:float=-6e7

FUTURES=[
 Future('steady_10pct',.10,2.,0.,1.,1.2,1.,10.,0.),
 Future('flat_closed_3y',0.,.5,.3,2.,.8,.5,.5,3.),
 Future('drawdown_recovery',.15,.75,.7,2.5,.9,.6,.75,2.),
 Future('persistent_decline',-.20,.5,.4,5.,.5,.25,.5,5.,.14,.04,15.,1.2,-2e8),
 Future('high_growth',.30,1.,.35,1.,1.8,1.,1.,.5,.12,.02,3.),
 Future('late_closure',.08,4.,.75,3.,.65,.7,4.,3.,.14,.04,15.,1.3,-1.5e8)]

@lru_cache(8)
def paths(future,end=END):
    """Controlled triangular shocks using the published generator's logic.
    Full realized future is stored only by the environment. Decisions receive
    current/past values; funding forecasts use current rates and known dates.
    """
    out={};peak=58714.;n=(end-START).days+90
    for i in range(n+1):
        t=i/365.25
        def pulse():
            if t<=future.shock_start:return 0.
            if t<future.shock_start+.20:return math.log1p(-future.shock_depth)*(t-future.shock_start)/.20
            if t<future.shock_start+.20+future.recovery_years:return math.log1p(-future.shock_depth)*(1-(t-future.shock_start-.20)/future.recovery_years)
            return 0.
        px=58714*math.exp(math.log1p(future.cagr)*t+pulse());peak=max(peak,px)
        stress=min(1.,(1-px/peak)/.6)
        mult=.9616113760674149*math.exp(math.log(future.valuation_terminal_factor)*min(t/5,1)-.6*stress)
        closed=future.closure_start<=t<future.closure_start+future.closure_years
        out[START+timedelta(days=i)]={
          'btc':money(px),'multiple':money(mult),'capacity':Z if closed else money(future.capacity*max(.1,1-.8*stress)),
          'fx':money(1.1408*math.exp(math.log(future.fx_terminal_factor)*min(t/5,1))),
          'strc_price':money(100-future.strc_discount*stress),'stress':money(stress),'sofr':D('.03')}
    return out

def path_digest(path):
    return hashlib.sha256(json.dumps({str(k):{a:str(b) for a,b in v.items()} for k,v in path.items()},sort_keys=True).encode()).hexdigest()

@lru_cache(None)
def schedule(end=END):
    out=[]
    for y in range(2026,end.year+1):
        for m in range(1,13):
            e=date(y,m,monthrange(y,m)[1]);mid=date(y,m,15)
            prev_end=date(y,m,1)-timedelta(days=1)
            for n,record in [(mid,prev_end),(e,mid)]:
                if START<n<=end:
                    out.append({'ticker':'STRC','nominal':n,'record':record,'start':record,
                                'pay':following(n,'FED_NY')})
            if m in (3,6,9,12) and START<e<=end:
                pm=m-3;py=y
                if pm<=0:pm+=12;py-=1
                start=date(py,pm,monthrange(py,pm)[1])
                for ticker in ('STRF','STRE','STRK','STRD'):
                    out.append({'ticker':ticker,'nominal':e,'record':mid,'start':start,
                                'pay':following(e,'STRE_PAY' if ticker=='STRE' else 'FED_NY')})
    return tuple(sorted(out,key=lambda e:(e['nominal'],ORDER.index(e['ticker']))))

class Simulation:
    def __init__(self,future,policy,assumptions=Assumptions(),end=END,keep_ledger=False,external_path=None,external_digest=None):
        self.future=future;self.policy=policy;self.a=assumptions;self.end=end;self.path=external_path if external_path is not None else paths(future,END)
        self.external_digest=external_digest
        self.day=START;self.pt=self.path[START];self.keep_ledger=keep_ledger;self.events=[]
        unavailable=Z if self.a.foreign_liquidity_available else money(OPEN['non_US_cash_and_investments_approx_usd'])
        self.liq=Liquidity(money(OPEN['cash_usd'])-unavailable+money(self.a.initial_cash_increment),
            OPEN['treasury_investments_usd'],money(OPEN['restricted_cash_usd'])+unavailable,
            legal_budget=money(self.a.cash_legal_capacity_per_year))
        self.btc=BitcoinPosition(money(OPEN['btc']),money(OPEN['reported_Bitcoin_acquisition_cost_usd'])*money(self.a.basis_fraction_of_reported_cost),money(self.a.loss_offset_budget))
        self.pref={p['id']:Preferred(p['id'],money(p['shares'])) for p in PREF}
        self.total_issued={k:a.shares for k,a in self.pref.items()}
        self.common=money(OPEN['basic_common_shares_rounded']);self.common_A=money(OPEN['basic_class_A_shares'])
        self.debt={k:money(v['principal_usd']) for k,v in TERMS.items()};self.other=money(40044000)
        self.pending=[];self.conversions={};self.calls={};self.records={};self.coupon_records={};self.stock_notices={}
        self.coupon_paid=set();self._quarter_key=None;self._quarter_prices=[]
        self.pay_events={};self.record_events={};self.nominal_events={}
        # A reporting endpoint does not terminate perpetual contractual payments.
        # Fixed forecast coverage keeps shorter and longer runs prefix-identical.
        self.sched=[dict(e) for e in schedule(date(2036,6,30))];self.series={k:[] for k in ORDER}
        for e in self.sched:
            e['id']=e['ticker']+'_'+str(e['nominal']);self.series[e['ticker']].append(e)
            self.record_events.setdefault(e['record'],[]).append(e);self.nominal_events.setdefault(e['nominal'],[]).append(e)
            self.pay_events.setdefault(e['pay'],[]).append(e)
        self.series_dates={k:[e['nominal'] for e in v] for k,v in self.series.items()}
        self.funding_schedule=sorted(self.sched,key=lambda e:e['pay']);self.funding_days=[e['pay'] for e in self.funding_schedule]
        self._lp_cache={};self._debt_cache=None;self._accrual_cache=None;self._quote_cache=None
        self.strc_rate=D('.12');self.rate_next=None;self.opening_credit=money(OPEN['initial_preferred_dividends_payable_usd'])
        self.opening_credits={date(2026,7,15):D('50262046.18079823'),date(2026,7,31):D('52447352.5'),date(2026,8,15):D('52447352.5')}
        self.unallocated_opening_payable=D('248.81920177')
        self.offerings=[];self.gross_issued={'MSTR':Z,'STRC':Z};self.tax_paid=Z;self.excise_repurchases={};self.excise_issuances={}
        self.trade_prices=[];self.stock_price_by_date={};self.strc_prices=[];self.strc_issue_days=[]
        self.preferred_prices={k:[D(100)]*10 for k in ORDER};self.latest_preferred_close=None
        self.first_miss=None;self.debt_shortfall=None;self.operating_shortfall=None;self.cash_legal_block=None
        self.metrics={'btc_sold':Z,'btc_purchased':Z,'common_gross':Z,'strc_gross':Z,'common_from_conversion':Z,
          'common_from_dividend':Z,'preferred_paid_usd':Z,'preferred_omitted_usd':Z,'mandatory_unmet_usd':Z,
          'debt_principal_paid':Z,'conversion_cash_paid':Z,'strc_retired':Z,'debt_converted_principal':Z,
          'tax_reserved_total':Z,'call_notices':0,'strf_deferral_notices':0,'strf_efforts_observations':0}
        self.snapshots={};self.max_cash_residual=Z;self.last_month=None;self.initial_bps=self.backing()/self.common
        self.last_nominal={k:START for k in ORDER};self.missed_periods={k:0 for k in ORDER};self.deferrals={}
        self.record(START) # June 30 entitlement for the first STRC settlement.
        # Calibrate once, before any intervention. Extra cash does not change scale.
        base_backing=self.backing()-money(self.a.initial_cash_increment)
        s=self.btc.units*self.pt['btc'];ref=base_backing
        if self.a.common_valuation=='continuation':ref=money(residual_reference(s,s-base_backing,self.a.reference_volatility,self.a.reference_years))
        elif self.a.common_valuation!='face':raise ValueError('unknown common valuation')
        self.quote_scale=(D('86.93')*self.common/(max(EPS,ref)*self.pt['multiple']) if self.a.calibrate_opening_quote else D(1))

    def log(self,kind,**kw):
        if self.keep_ledger:self.events.append({'date':str(self.day),'kind':kind,**kw})

    def fx(self,k):return self.pt['fx'] if k=='STRE' else D(1)
    def due_arrears_usd(self):return sum((p.unpaid*self.fx(k) for k,p in self.pref.items()),Z)
    def priority_blockers(self,k):
        total=self.due_arrears_usd()
        fully_funded=self.liq.usable>=total and self.liq.legal_budget>=total
        blockers=[]
        for j in ORDER[:ORDER.index(k)]:
            p=self.pref[j]
            pending_due=following(self.last_nominal[j],'STRE_PAY' if j=='STRE' else 'FED_NY')
            # An ordinary holiday deferral, fully declared and funded, is not an
            # unpaid past-due dividend. Preserve the senior cash for its own date.
            timely_funded=(self.day<pending_due and fully_funded)
            if not timely_funded and (p.unpaid>EPS or p.missed_latest):blockers.append(j)
        return blockers
    def debt_accrued(self):
        state_key=(self.day,tuple(self.debt.values()),tuple((k,o['principal']) for k,o in self.conversions.items()),tuple(self.coupon_records.items()),len(self.coupon_paid))
        if self._debt_cache is not None and self._debt_cache[0]==state_key:return self._debt_cache[1]
        credits={'2028':D('1853990.6980195614'),'2030A':D('1468507.4835798503'),
                 '2031':D('1551336.078303076'),'2032':D('745165.7400975126')}
        value=Z
        for k,t in TERMS.items():
            n=self.debt[k]-self.conversions.get(k,{}).get('principal',Z)
            rate=money(t['coupon_rate'])
            if not rate:continue
            months=(6,12) if k=='2032' else (3,9)
            prior=max(date(y,m,15) for y in (self.day.year-1,self.day.year) for m in months if date(y,m,15)<=self.day)
            nxt=min(date(y,m,15) for y in (self.day.year,self.day.year+1) for m in months if date(y,m,15)>self.day)
            if prior<START:
                credit=credits[k]*n/money(t['principal_usd']);full=n*money(t['coupon_rate'])/2
                value+=credit+(full-credit)*money((self.day-START).days)/money((nxt-START).days)
            else:value+=n*rate*thirty360(prior,self.day)
            # A recorded coupon survives conversion and nominal weekend dates.
            for y in (self.day.year-1,self.day.year):
                for m in months:
                    rec=date(y,m,1);nom=date(y,m,15);key=(k,y,m)
                    if key in self.coupon_records and key not in self.coupon_paid and rec<=self.day<=following(nom,'FED_NY'):
                        recorded=self.coupon_records[key]
                        value+=(recorded if self.day>=nom else max(Z,recorded-n))*rate/2
        self._debt_cache=(state_key,value)
        return value
    def available_common(self):
        # Reserve max indenture make-whole delivery plus STRK conversions and an
        # explicit 5m award buffer; do not confuse total authorization with free shares.
        from contracts import TABLES
        reserved=sum((p/1000*D(TABLES[k]['max_total_conversion_rate']) for k,p in self.debt.items()),Z)+self.pref['STRK'].shares*D('.1')+D(5000000)
        pending=sum((o.get('shares',Z) for o in self.pending if o['kind'] in ('MSTR','STRK_conversion')),Z)
        return max(Z,D(10330000000)-self.common_A-reserved-pending)

    def accrued_undue(self):
        key=(self.day,tuple(p.shares for p in self.pref.values()),self.strc_rate,self.rate_next,len(self.records),self.pt['fx'])
        if self._accrual_cache is not None and self._accrual_cache[0]==key:return self._accrual_cache[1]
        total=Z
        for k,events in self.series.items():
            i=bisect_right(self.series_dates[k],self.day);e=events[i] if i<len(events) else None
            if not e or self.day<=e['start']:continue
            if k=='STRC' and e['nominal'] in self.opening_credits:continue
            if k=='STRD':continue # future undeclared noncumulative distributions are not a claim
            amount=self.records[e['id']] if e['id'] in self.records else self.expected_regular(e)
            fraction=money((self.day-e['start']).days)/money((e['nominal']-e['start']).days)
            total+=amount*min(D(1),fraction)*self.fx(k)
        self._accrual_cache=(key,total)
        return total

    def backing(self):
        faces=sum((p.shares*self.lp(k)*self.fx(k) for k,p in self.pref.items()),Z)
        faces+=sum((o['shares']*self.lp('STRC') for o in self.pending if o['kind']=='STRC'),Z)
        pending_cash=sum((v for _,v,_ in self.liq.pending),Z)+sum((o.get('net',Z) for o in self.pending if o['kind'] in ('MSTR','STRC')),Z)
        pending_btc=sum((o.get('units',Z) for o in self.pending if o['kind']=='BTC_buy'),Z)
        return ((self.btc.units+pending_btc)*self.pt['btc']+self.liq.cash+self.liq.treasury+self.liq.restricted+pending_cash+D(75778000)
          -self.liq.tax_reserved-sum(self.debt.values(),Z)-self.other-faces-self.due_arrears_usd()-self.opening_credit-self.accrued_undue()-self.debt_accrued())

    def lp(self,k):
        # Opening ten-price history is synthetic flat $100, consistent with the
        # reported opening preference; STRE has no modeled post-IPO activation.
        prices=self.preferred_prices[k][-11:-1] if self.latest_preferred_close==self.day else self.preferred_prices[k][-10:]
        cutoff=previous_trading(self.day,10)
        issued=k=='STRC' and any(cutoff<=d<=self.day for d in self.strc_issue_days)
        key=(tuple(prices),issued)
        if k in self._lp_cache and self._lp_cache[k][0]==key:return self._lp_cache[k][1]
        value=liquidation_preference(100,prices,issued,k!='STRE');self._lp_cache[k]=(key,value)
        return value

    def economic_common(self):
        return self.common+sum((o['shares'] for o in self.pending if o['kind'] in ('MSTR','STRK_conversion')),Z)

    def projected_cash(self):
        pending=sum((v for _,v,_ in self.liq.pending),Z)+sum((o.get('net',Z) for o in self.pending),Z)
        return max(Z,self.liq.cash+pending-self.liq.tax_reserved)

    def quote(self):
        # A complete valuation state key allows repeated same-event quotes to
        # reuse arithmetic. Every asset, claim, pending delivery and entitlement
        # that enters the quote is represented; current external marks are fixed.
        key=(self.day,self.pt['btc'],self.pt['fx'],self.pt['multiple'],self.btc.units,
             self.liq.cash,self.liq.treasury,self.liq.restricted,self.liq.tax_reserved,
             tuple(self.liq.pending),tuple(tuple(o.items()) for o in self.pending),
             self.common,tuple(self.debt.values()),self.other,self.opening_credit,
             tuple((p.shares,p.unpaid) for p in self.pref.values()),
             self.strc_rate,self.rate_next,len(self.records),tuple(self.coupon_records.items()),
             len(self.coupon_paid),tuple((k,o['principal']) for k,o in self.conversions.items()),
             tuple((k,tuple(v[-10:])) for k,v in self.preferred_prices.items()),len(self.strc_issue_days))
        if self._quote_cache is not None and self._quote_cache[0]==key:return self._quote_cache[1]
        backing=self.backing();ref=max(Z,backing)
        if self.a.common_valuation=='continuation':
            s=(self.btc.units+sum((o.get('units',Z) for o in self.pending if o['kind']=='BTC_buy'),Z))*self.pt['btc']
            ref=money(residual_reference(s,s-backing,self.a.reference_volatility,self.a.reference_years))
        value=self.quote_scale*self.pt['multiple']*ref/self.economic_common()
        self._quote_cache=(key,value)
        return value

    def expected_regular(self,e):
        k=e['ticker'];rate=self.strc_rate if k=='STRC' else D('.08') if k=='STRK' else D('.1')
        if k=='STRC' and e['record']==self.day and self.day.day==15 and self.rate_next is not None:rate=self.rate_next
        n=self.pref[k].shares
        if k=='STRC' and e['nominal'] in self.opening_credits:
            base=money(next(p['shares'] for p in PREF if p['id']=='STRC'))
            return self.opening_credits[e['nominal']]+max(Z,n-base)*100*rate/24
        return n*100*rate/(24 if k=='STRC' else 4)

    def record(self,day):
        for e in self.record_events.get(day,[]):
            self.records[e['id']]=self.expected_regular(e)
            if e['ticker']=='STRK' and self.a.stock_dividend_election:
                self.stock_notices[e['id']]=self.records[e['id']]+self.pref['STRK'].unpaid
                self.log('STRK_irrevocable_stock_election_notice',declared=self.stock_notices[e['id']],payment=str(e['pay']))
            self.log('dividend_record',security=e['ticker'],nominal=str(e['nominal']),shares=self.pref[e['ticker']].shares,amount=self.records[e['id']])
        for k,t in TERMS.items():
            if day.month in ((6,12) if k=='2032' else (3,9)) and day.day==1:
                self.coupon_records[(k,day.year,day.month)]=max(Z,self.debt[k]-self.conversions.get(k,{}).get('principal',Z))

    def needed(self,days):
        # Known commitments valued at CURRENT rates/FX; no future price queries.
        until=self.day+timedelta(days=days);amount=self.due_arrears_usd()
        for e in (self.funding_schedule[bisect_right(self.funding_days,self.day):bisect_right(self.funding_days,until)] if self.sched else []):
            if self.day<e['pay']<=until and e['nominal']>self.day:
                amount+=(self.records[e['id']] if e['id'] in self.records else self.expected_regular(e))*self.fx(e['ticker'])
        for k,t in TERMS.items():
            principal=self.debt[k];rate=money(t['coupon_rate'])
            put=following(date.fromisoformat(t['holder_put_nominal']),'FED_NY')
            mat=following(date.fromisoformat(t['maturity_nominal']),'FED_NY')
            red=self.calls.get(k,{}).get('redemption',mat)
            if k in self.conversions:
                o=self.conversions[k]
                if self.day<o['settle']<=until and o['method']!='physical':
                    observed=list(o['vwaps']);estimate=observed+[self.quote()]*(20-len(observed))
                    amount+=conversion_settlement(o['principal'],o['rate'],o['method'],estimate)['cash']
            else:
                remain=principal
                if self.day<put<=min(until,red,mat):
                    retired=(remain*money(self.a.put_fraction)/1000).to_integral_value(rounding='ROUND_FLOOR')*1000
                    amount+=retired;remain-=retired
                if self.day<min(red,mat)<=until:amount+=remain
            for y in range(self.day.year,until.year+1):
                for m in ((6,12) if k=='2032' else (3,9)):
                    rec=date(y,m,1);pay=following(date(y,m,15),'FED_NY')
                    if not self.day<pay<=until:continue
                    recorded=self.coupon_records.get((k,y,m))
                    if recorded is not None:n=recorded
                    elif k in self.conversions:n=Z
                    else:
                        n=principal
                        if self.day<min(red,mat)<=rec:n=Z
                        elif self.day<put<=rec:n-=(n*money(self.a.put_fraction)/1000).to_integral_value(rounding='ROUND_FLOOR')*1000
                    amount+=n*rate/2
        loan=following(date.fromisoformat(self.a.other_loan_repayment),'FED_NY')
        if self.day<loan<=until:amount+=self.other
        if self.other and self.day<loan:
            last=getattr(self,'last_loan_interest',START)
            for y in range(self.day.year,until.year+1):
                for m in range(1,13):
                    d=min(date(y,m,monthrange(y,m)[1]),loan)
                    if self.day<d<=until and d>last:
                        amount+=self.other*money(self.a.other_loan_rate)*money((d-last).days)/365;last=d
        for y in range(self.day.year,until.year+1):
            for m in range(1,13):
                if self.day<date(y,m,monthrange(y,m)[1])<=until:amount+=max(Z,-money(self.future.annual_operating_cashflow))/12
        return amount

    def conversion_deadline(self,k):
        cal='FED_NY' if k=='2030B' else 'US_EQUITY'
        deadline=advance(date.fromisoformat(TERMS[k]['maturity_nominal']),-2,cal)
        if k in self.calls:deadline=min(deadline,advance(self.calls[k]['redemption'],-2,cal))
        return deadline

    def settlement(self,day,days,calendar='US_EQUITY'):
        if days==0:return day
        d=day
        for _ in range(days):
            d=advance(d,1,calendar)
            while str(d) in self.a.exceptional_market_closures:d=advance(d,1,calendar)
        return d

    def settle_pending(self):
        self.liq.settle(self.day)
        for o in list(self.pending):
            if o['due']>self.day:continue
            kind=o['kind']
            if kind in ('MSTR','STRC'):
                self.liq.record(o['net'],'issue_'+kind)
                if kind=='MSTR':self.common+=o['shares'];self.common_A+=o['shares']
                else:
                    self.pref['STRC'].shares+=o['shares'];self.total_issued['STRC']+=o['shares']
                self.offerings.append({'date':str(self.day),'security':kind,'net_proceeds_usd':o['net'],'registered_cash':True})
                if kind=='MSTR':self.excise_issuances[self.day.year]=self.excise_issuances.get(self.day.year,Z)+o['gross']
            elif kind=='BTC_buy':self.btc.units+=o['units'];self.btc.basis+=o['cost']
            elif kind=='STRC_redemption':self.execute_redemption(o)
            elif kind=='STRK_conversion':
                self.common+=o['shares'];self.common_A+=o['shares'];self.metrics['common_from_conversion']+=o['shares']
            self.log('settlement',security=kind,**{k:v for k,v in o.items() if k not in ('kind','due')})
            self.pending.remove(o)

    def pay_debt(self,amount,kind,k=None,principal=False):
        paid,short=self.liq.pay(amount,kind)
        if principal and k:
            if k=='other':self.other-=paid
            else:self.debt[k]-=paid
            self.metrics['debt_principal_paid']+=paid
        if short>EPS and self.debt_shortfall is None:
            self.debt_shortfall={'date':str(self.day),'kind':kind,'security':k,'amount_usd':short}
        self.log(kind,security=k,requested=amount,paid=paid,shortfall=short)

    def debt_payments(self):
        for k,t in TERMS.items():
            coupon_months=(6,12) if k=='2032' else (3,9)
            for m in coupon_months:
                nominal=date(self.day.year,m,15)
                if following(nominal,'FED_NY')==self.day:
                    n=self.coupon_records.get((k,nominal.year,m),self.debt[k])
                    # Principal retired before the record date has no coupon entitlement.
                    amount=n*money(t['coupon_rate'])/2
                    if amount:self.pay_debt(amount,'debt_coupon',k)
                    self.coupon_paid.add((k,nominal.year,m))
            if k in self.conversions:continue
            nominal=None;fraction=D(1)
            if following(date.fromisoformat(t['holder_put_nominal']),'FED_NY')==self.day:
                nominal=date.fromisoformat(t['holder_put_nominal']);fraction=money(self.a.put_fraction)
            elif following(date.fromisoformat(t['maturity_nominal']),'FED_NY')==self.day:nominal=date.fromisoformat(t['maturity_nominal'])
            if nominal and self.debt[k]>0 and fraction:
                n=(self.debt[k]*fraction/1000).to_integral_value(rounding='ROUND_FLOOR')*1000
                self.pay_debt(n,'debt_principal',k,True)
        loan=following(date.fromisoformat(self.a.other_loan_repayment),'FED_NY')
        if self.other and (self.day.day==monthrange(self.day.year,self.day.month)[1] or self.day==loan):
            prev=getattr(self,'last_loan_interest',START)
            interest=self.other*money(self.a.other_loan_rate)*money((self.day-prev).days)/365
            self.pay_debt(interest,'other_interest','other');self.last_loan_interest=self.day
        if self.other and self.day==loan:self.pay_debt(self.other,'other_principal','other',True)

    def pref_nominal(self):
        for e in self.nominal_events.get(self.day,[]):
            k=e['ticker'];p=self.pref[k];interest=p.compound(self.strc_rate if k=='STRC' else None)
            amt=self.records.get(e['id'],self.expected_regular(e))
            senior_due=sum((self.pref[j].unpaid*self.fx(j) for j in ORDER[:ORDER.index(k)]),Z)
            declared=k!='STRD' or (self.liq.usable>=senior_due+amt and self.liq.legal_budget>=senior_due+amt)
            p.add_regular(amt,declared)
            if not declared:self.metrics['preferred_omitted_usd']+=amt
            if k=='STRC' and e['nominal'] in self.opening_credits:self.opening_credit-=self.opening_credits[e['nominal']]
            self.last_nominal[k]=self.day
            self.log('dividend_due',security=k,amount=amt,compound=interest,declared=declared,record=str(e['record']),payment=str(e['pay']))

    def pay_preferences(self):
        due_tickers={e['ticker'] for e in self.pay_events.get(self.day,[])}
        # Catch up old arrears on a business day after financing has arrived.
        due_tickers|={k for k,p in self.pref.items() if p.unpaid and is_open(self.day,'STRE_PAY' if k=='STRE' else 'FED_NY')
            and following(self.last_nominal[k],'STRE_PAY' if k=='STRE' else 'FED_NY')<=self.day}
        for k in ORDER:
            if k not in due_tickers:continue
            p=self.pref[k];fx=self.fx(k);was=p.unpaid;paid=Z;stockpaid=Z
            blockers=self.priority_blockers(k)
            stock_event=next((e for e in self.pay_events.get(self.day,[]) if e['ticker']=='STRK' and e['id'] in self.stock_notices),None)
            if k=='STRK' and p.unpaid and stock_event and self.a.stock_dividends_permitted:
                vd=previous_trading(self.day,3);vwap=self.stock_price_by_date.get(vd,Z)
                if vwap>0:
                    declared=self.stock_notices[stock_event['id']]
                    ans=strk_stock_dividend(declared,min(p.unpaid,declared),vwap,self.available_common(),delivery_permitted=True)
                    self.common+=ans['shares'];self.common_A+=ans['shares'];stockpaid=p.settle(ans['satisfied'])
                    self.metrics['common_from_dividend']+=ans['shares']
            if not blockers and p.unpaid:
                paid_usd,short=self.liq.pay(p.unpaid*fx,k+'_dividend',distribution=True);paid=p.settle(paid_usd/fx)
                self.metrics['preferred_paid_usd']+=paid_usd
                if short and self.liq.legal_budget<=EPS and self.cash_legal_block is None:self.cash_legal_block=str(self.day)
            if k in ('STRF','STRK'):
                e=next((e for e in self.pay_events.get(self.day,[]) if e['ticker']==k),None)
                if e:
                    mandatory=mandatory_dividend_amount(k,was,e['record'],self.offerings)
                    self.metrics['mandatory_unmet_usd']+=max(Z,mandatory-paid-stockpaid)
            # Decimal arithmetic can leave sub-microdollar residues. They are
            # not economic suspensions and must not activate a priority gate.
            if 0<p.unpaid<=EPS:
                self.log('sub_microdollar_claim_rounding',security=k,amount=p.unpaid);p.settle(p.unpaid)
            if p.unpaid>EPS or (k=='STRD' and p.missed_latest):
                if self.first_miss is None:self.first_miss={'date':str(self.day),'security':k}
                if k in {e['ticker'] for e in self.pay_events.get(self.day,[])}:
                    self.missed_periods[k]+=1
                    if k=='STRF':
                        deferred=strf_deferred_date(self.last_nominal[k]);self.deferrals[deferred]=was
                        self.metrics['strf_deferral_notices']+=1
            else:self.missed_periods[k]=0
            self.log('preferred_settlement',security=k,cash_native=paid,stock_satisfied=stockpaid,unpaid=p.unpaid,blockers=blockers)

    def conversion_actions(self):
        if not any(self.debt.values()) and not self.pref['STRK'].shares:return
        qdate=date(self.day.year,3*((self.day.month-1)//3)+1,1)-timedelta(days=1)
        if qdate!=self._quarter_key:
            self._quarter_key=qdate;self._quarter_prices=[v for d,v in self.trade_prices if d<=qdate][-30:]
        quarter_prices=self._quarter_prices
        prices=[v for d,v in self.trade_prices[-30:]]
        for k,t in TERMS.items():
            if self.debt[k]<=0:continue
            if k in self.conversions:
                o=self.conversions[k]
                if self.day in o.get('observations',[]):o['vwaps'].append(self.quote())
                if self.day==o['settle']:
                    result=conversion_settlement(o['principal'],o['rate'],o['method'],o.get('vwaps'))
                    from contracts import TABLES
                    if result['shares']>self.available_common()+o['principal']/1000*D(TABLES[k]['max_total_conversion_rate']):raise ValueError('conversion delivery authorization')
                    self.pay_debt(result['cash'],'conversion_cash',k)
                    if self.debt_shortfall:return
                    self.debt[k]-=o['principal'];self.common+=result['shares'];self.common_A+=result['shares']
                    self.metrics['common_from_conversion']+=result['shares'];self.metrics['debt_converted_principal']+=o['principal']
                    self.metrics['conversion_cash_paid']+=result['cash'];self.log('conversion_delivered',security=k,**result)
                    del self.conversions[k]
                continue
            if k in self.calls and self.day==self.calls[k]['redemption']:
                couponmonths=(6,12) if k=='2032' else (3,9)
                prior=max(date(y,m,15) for y in (self.day.year-1,self.day.year) for m in couponmonths if date(y,m,15)<=self.day)
                protected=self.day.month in couponmonths and 1<self.day.day<=15
                interest=Z if protected else self.debt[k]*money(t['coupon_rate'])*thirty360(prior,self.day)
                self.pay_debt(interest,'call_accrued_interest',k);self.pay_debt(self.debt[k],'call_principal',k,True)
                continue
            rate=money(t['split_adjusted_base_conversion_shares_per_1000']);quote=self.quote()
            if not is_open(self.day,'US_EQUITY') or quote<=0:continue
            called=k in self.calls
            if self.a.issuer_calls and not called and self.day<date.fromisoformat(t['maturity_nominal']):
                red=following(self.day+timedelta(days=32),'FED_NY') if self.a.conversion_method=='physical' else advance(self.day,32,'US_EQUITY')
                if valid_call(k,self.day,red,self.debt[k],self.debt[k],prices,rate,physical=self.a.conversion_method=='physical'):
                    sp=sum(prices[-5:],Z)/5
                    extra=make_whole(k,self.day,sp,rate)
                    self.calls[k]={'notice':self.day,'redemption':red,'extra':extra};called=True
                    self.metrics['call_notices']+=1;self.log('issuer_call_notice',security=k,redemption=str(red),make_whole_extra=extra)
            mat=date.fromisoformat(t['maturity_nominal'])
            maturity_deadline=advance(mat,-2,'FED_NY' if k=='2030B' else 'US_EQUITY')
            deadline=self.conversion_deadline(k)
            eligible=conversion_eligible(k,self.day,quarter_prices,rate,called=called)
            elect=(self.a.conversion_behavior=='eligible' or self.a.conversion_behavior=='respond_call_only' and called
                   or self.a.conversion_behavior=='maturity_only' and self.day>=deadline-timedelta(days=4))
            if called:rate+=self.calls[k]['extra']
            if eligible and elect and quote*rate>1000 and self.day<=deadline:
                n=self.debt[k];method=self.a.conversion_method;call=self.calls.get(k,{})
                obs=[] if method=='physical' else observation_days(k,self.day,call.get('notice'),call.get('redemption'))
                if obs and obs[0]<self.day:
                    vw=[self.stock_price_by_date[d] for d in obs if d<self.day]
                else:vw=[]
                if self.day in obs:vw.append(quote)
                settle=advance(self.day,2,'FED_NY') if method=='physical' else advance(obs[-1],2,'FED_NY')
                if method=='physical' and called and (call['redemption']-self.day).days<=15:settle=call['redemption']
                self.conversions[k]={'principal':n,'rate':rate,'method':method,'observations':obs,'vwaps':vw,'settle':settle}
                # Record-holder coupon survives. Ordinary converting holder funds it,
                # unless the documented call/maturity exception applies.
                m=self.day.month
                if m in ((6,12) if k=='2032' else (3,9)) and 1<self.day.day<15:
                    coupon=n*money(t['coupon_rate'])/2
                    exempt=(called and call['redemption']<=advance(date(self.day.year,m,15),1,'FED_NY')) or self.day>=maturity_deadline-timedelta(days=15)
                    if not exempt:self.liq.record(coupon,'converting_holder_coupon_in')
                self.log('holder_conversion_election',security=k,principal=n,method=method,settlement=str(settle),rate=rate)
        p=self.pref['STRK']
        if p.shares and self.a.conversion_behavior=='eligible' and is_open(self.day,'FED_NY') and self.quote()*D('.1')>100:
            e=next((e for e in self.series['STRK'] if e['record']<self.day<=e['pay'] and e['id'] in self.records),None)
            protected=self.records[e['id']] if e else Z
            ans=strk_conversion(p.shares,arrears=p.unpaid,protected=protected,entire_holder_position=True)
            if ans['common_shares']>self.available_common()+p.shares*D('.1'):raise ValueError('STRK delivery authorization')
            self.liq.record(ans['converting_holder_cash_in'],'STRK_converting_holder_dividend_in')
            keep=min(p.unpaid,protected) if e and e['nominal']<self.day else Z
            p.arrears=[Cohort(keep)] if keep else [];p.shares=Z;p.missed_latest=keep>0
            self.pending.append({'kind':'STRK_conversion','due':advance(self.day,2,'FED_NY'),'shares':ans['common_shares']})
            self.log('STRK_holder_conversion',**ans)

    def budget_remaining(self,k):
        years=max(0,self.day.year-2026) if self.a.authorization_renewal else 0
        limit=money(self.a.new_common_program_budget if k=='MSTR' else self.a.new_strc_program_budget)*(1+years)
        return max(Z,limit-self.gross_issued[k])

    def issue(self,k,gross):
        px=self.quote() if k=='MSTR' else self.pt['strc_price']
        if px<=0 or self.pt['capacity']<=0:return
        gross=min(gross,self.budget_remaining(k))
        free=self.available_common() if k=='MSTR' else max(Z,D(282556565)-self.pref['STRC'].shares-sum((o['shares'] for o in self.pending if o['kind']=='STRC'),Z))
        gross=min(gross,free*px)
        if k=='STRC' and self.policy.preferred_asset_cap is not None:
            cap=money(self.policy.preferred_asset_cap)
            prices=self.preferred_prices['STRC'][-11:-1] if self.latest_preferred_close==self.day else self.preferred_prices['STRC'][-10:]
            proposed_lp=liquidation_preference(100,prices,True,True)
            claims=sum((p.shares*(proposed_lp if j=='STRC' else self.lp(j))*self.fx(j) for j,p in self.pref.items()),Z)+sum((o['shares']*proposed_lp for o in self.pending if o['kind']=='STRC'),Z)
            assets=self.btc.units*self.pt['btc']+self.liq.cash+self.liq.treasury+sum((v for _,v,_ in self.liq.pending),Z)+sum((o.get('net',Z)+o.get('units',Z)*self.pt['btc'] for o in self.pending),Z)
            denominator=proposed_lp-cap*D('.99')*px
            if denominator>0:gross=min(gross,max(Z,cap*assets-claims)/denominator*px)
        shares=(gross/px).to_integral_value(rounding='ROUND_FLOOR');gross=shares*px
        if gross<=0:return
        net=gross*D('.99');due=self.settlement(self.day,self.a.equity_settlement_days)
        self.pending.append({'kind':k,'due':due,'net':net,'gross':gross,'shares':shares,'trade':str(self.day)})
        if k=='STRC':self.strc_issue_days.append(self.day)
        self.gross_issued[k]+=gross;self.metrics['common_gross' if k=='MSTR' else 'strc_gross']+=gross
        self.log('issue_trade',security=k,gross=gross,shares=shares,settlement=str(due))

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
        if monthly and self.policy.strc_monthly_gross and self.pt['strc_price']>=95 and self.backing()>0:
            allowed=True
            if self.policy.preferred_asset_cap is not None:
                pref=sum((p.shares*100*self.fx(k) for k,p in self.pref.items()),Z)
                allowed=pref< money(self.policy.preferred_asset_cap)*(self.btc.units*self.pt['btc']+self.liq.cash+self.liq.treasury)
            if allowed:self.issue('STRC',money(self.policy.strc_monthly_gross)*self.pt['capacity'])
        if monthly or spendable<near:
            growth=money(self.policy.common_monthly_growth) if monthly and (self.policy.common_growth_rule=='unconditional' or self.backing()>0 and self.quote()*self.economic_common()>self.backing()*D('1.02')) else Z
            need=max(Z,target-spendable)+growth
            self.issue('MSTR',min(need/D('.99'),D('1100000000')*self.pt['capacity']))
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

    def execute_redemption(self,o):
        p=self.pref['STRC'];n=min(o['shares'],p.shares)
        self.liq.restricted-=o['escrow'];self.liq.record(o['escrow'],'redemption_release_setaside')
        if n<=0:return
        if cash_distribution_blockers('STRC',list(self.pref.values())):
            self.log('redemption_unfunded',reason='senior dividend restriction');return
        # Locked record claims survive retirement. Undeclared accrual from the
        # current record date is excluded from redemption cheque and paid on its
        # recorded date; this assumption is surfaced in the scope register.
        arrears_fraction=p.unpaid*n/p.shares
        current=next((e for e in self.series['STRC'] if e['nominal']>=self.day),None)
        protected=Z
        if current and current['record']<self.day<=current['pay'] and current['id'] in self.records:
            protected=self.records[current['id']]*n/p.shares
        accrual=n*100*self.strc_rate*thirty360(current['start'] if current else self.day,self.day)
        # Current ordinary redemption includes accrued dividends to and including
        # redemption; record entitlement deduction cannot exceed accrued amount.
        cost=n*101+arrears_fraction+max(Z,accrual-protected)
        if self.liq.usable<cost or self.liq.legal_budget<cost:
            self.log('redemption_unfunded',requested=cost,available=self.liq.usable);return
        self.liq.pay(cost,'STRC_redemption',distribution=True);p.settle(arrears_fraction);p.shares-=n
        self.metrics['strc_retired']+=n
        # Class qualification for excise remains explicit: conservative covered
        # repurchase input, annually netted against eligible common issuance only.
        if self.a.strc_excise_covered:self.excise_repurchases[self.day.year]=self.excise_repurchases.get(self.day.year,Z)+n*self.pt['strc_price']
        self.log('STRC_redemption',shares=n,cash=cost,protected_record_claim=protected)

    def snapshot(self):
        backing=self.backing();bps=backing/self.economic_common()
        return {'date':str(self.day),'cash_usd':self.liq.cash,'treasuries_usd':self.liq.treasury,'tax_reserved_usd':self.liq.tax_reserved,
          'Bitcoin_units':self.btc.units,'common_shares':self.common,'debt_principal_usd':sum(self.debt.values(),Z)+self.other,
          'preferred_arrears_usd':self.due_arrears_usd(),'STRC_shares':self.pref['STRC'].shares,
          'common_backing_usd':backing,'common_backing_per_share':bps,'common_backing_change_fraction':bps/self.initial_bps-1,
          'economic_common_shares':self.economic_common(),'common_quote':self.quote(),
          'first_preferred_miss':self.first_miss,'debt_shortfall':self.debt_shortfall,'operating_shortfall':self.operating_shortfall,
          'cash_legal_capacity_first_binding':self.cash_legal_block,'missed_period_counters':dict(self.missed_periods),
          'preferred_suspension':self.first_miss is not None,'common_backing_nonpositive':backing<=0,
          'material_common_backing_loss':bps<self.initial_bps*D('.5'),'metrics':dict(self.metrics),'tax_paid_usd':self.tax_paid,
          'cash_reconciliation_residual':self.liq.cash_residual()}

    def run(self):
        for i in range(1,(self.end-START).days+1):
            self.day=START+timedelta(days=i);self.pt=self.path[self.day]
            if self.day.month==1 and self.day.day==1:self.liq.legal_budget=money(self.a.cash_legal_capacity_per_year)
            self.settle_pending()
            if self.day.day==15:
                lag=max(START,self.day-timedelta(days=20));target=money(self.future.strc_rate)+money(self.future.stress_spread)*self.path[lag]['stress']
                floor=strc_rate_floor(self.strc_rate,self.pt['sofr'],self.pt['sofr'],self.pt['sofr'],self.pref['STRC'].unpaid>EPS)
                self.rate_next=max(target,floor)
            if self.day.day==16 and self.rate_next is not None:self.strc_rate=self.rate_next
            self.conversion_actions()
            self.debt_payments()
            monthend=self.day.day==monthrange(self.day.year,self.day.month)[1]
            if monthend:
                op=money(self.future.annual_operating_cashflow)/12
                if op>=0:self.liq.record(op,'operating_receipt')
                else:
                    paid,short=self.liq.pay(-op,'operating_payment')
                    if short>EPS and self.operating_shortfall is None:self.operating_shortfall={'date':str(self.day),'amount_usd':short}
            # Debt and continuing operating commitments precede discretionary
            # preferred cash; a preferred omission can then continue as its own state.
            self.pref_nominal()
            if not self.debt_shortfall and not self.operating_shortfall:self.pay_preferences()
            if monthend and self.day.month in (3,6,9,12):
                tax=self.liq.pay_tax(self.liq.tax_reserved);self.tax_paid+=tax
            if monthend and self.day.month==12:
                excise=repurchase_excise(self.excise_repurchases.get(self.day.year,Z),self.excise_issuances.get(self.day.year,Z))
                self.liq.tax_reserved+=excise
            if not self.debt_shortfall and not self.operating_shortfall:self.finance()
            self.record(self.day)
            if is_open(self.day,'US_EQUITY'):
                quote=self.quote();self.trade_prices.append((self.day,quote));self.stock_price_by_date[self.day]=quote;self.strc_prices.append(self.pt['strc_price'])
                for k in ORDER:self.preferred_prices[k].append(self.pt.get('preferred_price_'+k,self.pt['strc_price'] if k=='STRC' else D(100)))
                self.latest_preferred_close=self.day
            self.max_cash_residual=max(self.max_cash_residual,abs(self.liq.cash_residual()))
            if self.day in HORIZONS:self.snapshots[str(self.day)]=self.snapshot()
            if self.debt_shortfall or self.operating_shortfall:break
        terminal=self.snapshot()
        for h in HORIZONS:
            if h<=self.end and str(h) not in self.snapshots:self.snapshots[str(h)]={'censored_at_distress_boundary':str(self.day),'terminal':terminal}
        return {'future':self.future.name,'policy':self.policy.name,'assumptions':asdict(self.a),
          'path_sha256':self.external_digest or path_digest(self.path),'snapshots':self.snapshots,'terminal':terminal,
          'max_cash_reconciliation_residual':self.max_cash_residual,'ledger':self.events if self.keep_ledger else None,
          'scope':'controlled deterministic futures; counts are not probabilities; aggregate share envelope; no price impact or optimization'}

if __name__=='__main__':
    result=Simulation(FUTURES[0],POLICIES[0],keep_ledger=True).run()
    (ROOT/'results/integration_smoke.json').write_text(json.dumps(result,indent=2,default=str))
    print(json.dumps(result['terminal'],indent=2,default=str))
