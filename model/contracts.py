"""Contract calculations used by the integrated dated driver.

Market eligibility is distinct from a holder's election. Event facts such as a
fundamental change or a tax event are explicit, never inferred from prices.
"""
from datetime import date,timedelta
from decimal import Decimal as D,ROUND_FLOOR
from pathlib import Path
import json,bisect
from functools import lru_cache
from date_rules import is_open,following,previous_trading
from mechanics import money,thirty360

ROOT=Path(__file__).resolve().parent
TABLES=json.loads((ROOT/'data/make_whole_tables.json').read_text()) if (ROOT/'data/make_whole_tables.json').exists() else {}
TERMS={x['instrument']:x for x in json.loads((ROOT/'data/debt_terms.json').read_text())}

@lru_cache(maxsize=30000)
def advance(day,n,calendar='FED_NY'):
    direction=1 if n>=0 else -1
    for _ in range(abs(n)):
        day+=timedelta(days=direction)
        while not is_open(day,calendar):day+=timedelta(days=direction)
    return day

def make_whole(instrument,event_date,stock_price,base_rate=None):
    t=TABLES[instrument];p=money(stock_price);xs=list(map(D,t['prices']))
    ds=[date.fromisoformat(r['date']) for r in t['rows']]
    if not ds[0]<=event_date<=ds[-1]:raise ValueError('event outside make-whole table')
    if p<xs[0] or p>xs[-1]:return D(0)
    i=max(0,min(len(xs)-2,bisect.bisect_right(xs,p)-1));j=max(0,min(len(ds)-2,bisect.bisect_right(ds,event_date)-1))
    wx=(p-xs[i])/(xs[i+1]-xs[i]);wt=D((event_date-ds[j]).days)/D((ds[j+1]-ds[j]).days)
    def row(k):
        ys=list(map(D,t['rows'][k]['additional_shares_per_1000']));return ys[i]*(1-wx)+ys[i+1]*wx
    extra=row(j)*(1-wt)+row(j+1)*wt
    base=money(base_rate if base_rate is not None else TERMS[instrument]['split_adjusted_base_conversion_shares_per_1000'])
    return max(D(0),min(extra,D(t['max_total_conversion_rate'])-base))

def price_trigger(prices,rate,require_last=False,strict=False):
    if len(prices)!=30:return False
    threshold=D('1.3')*1000/money(rate)
    flags=[money(p)>threshold if strict else money(p)>=threshold for p in prices]
    return sum(flags)>=20 and (not require_last or flags[-1])

def conversion_eligible(instrument,day,prior_quarter_prices,rate=None,called=False,
                        bond_discount_window_verified=False,corporate_event_verified=False):
    t=TERMS[instrument];rate=rate or t['split_adjusted_base_conversion_shares_per_1000']
    # The end-of-maturity conversion deadline is checked by the event scheduler.
    return (day>=date.fromisoformat(t['unconditional_conversion_window_start']) or called
            or bond_discount_window_verified or corporate_event_verified
            or price_trigger(prior_quarter_prices,rate,strict=t.get('call_price_strictly_greater',False)))

def valid_call(instrument,notice,redemption,outstanding,called,prior_prices,rate,physical=True,accelerated=False):
    t=TERMS[instrument];o,n=map(money,(outstanding,called))
    if accelerated or n<=0 or n>o or n%1000:return False
    if notice<date.fromisoformat(t['issuer_call_earliest_nominal']):return False
    if n<o and o-n<t['partial_call_min_remaining_usd']:return False
    if not price_trigger(prior_prices,rate,True,t['call_price_strictly_greater']):return False
    if not is_open(redemption,'FED_NY'):return False
    if physical:return (15 if instrument=='2030B' else 30)<=(redemption-notice).days<=45
    lo,hi=(25,45) if instrument=='2030B' else (30,40)
    return advance(notice,lo,'US_EQUITY')<=redemption<=advance(notice,hi,'US_EQUITY')

def observation_days(instrument,conversion,notice=None,redemption=None):
    t=TERMS[instrument];cut=date.fromisoformat(t['unconditional_conversion_window_start'])
    call_window=False
    if notice is not None and redemption is not None:
        cal='FED_NY' if instrument=='2030B' else 'US_EQUITY'
        call_window=notice<=conversion<=advance(redemption,-2,cal)
    if call_window:start=advance(redemption,-21,'US_EQUITY')
    elif conversion<cut or instrument=='2030B' and conversion==cut:start=advance(conversion,2,'US_EQUITY')
    else:start=advance(date.fromisoformat(t['maturity_nominal']),-21,'US_EQUITY')
    return [start]+[advance(start,i,'US_EQUITY') for i in range(1,20)]

def conversion_settlement(principal,rates,method,prices=None,specified_dollars=1000,
                          round_holder=False,fraction_price=None):
    p=money(principal)
    if p<=0 or p%1000:raise ValueError('notes require $1000 denominations')
    n=p/1000
    if method=='physical':
        shares=n*money(rates);cash=D(0)
    elif method in ('cash','combination'):
        if prices is None or len(prices)!=20:raise ValueError('20 observed VWAP trading days required')
        rates=[money(rates)]*20 if not isinstance(rates,(list,tuple)) else list(map(money,rates))
        if len(rates)!=20 or any(money(x)<0 for x in prices):raise ValueError('observation inputs')
        cash=shares=D(0)
        for r,px in zip(rates,map(money,prices)):
            value=r*px/20
            c=value if method=='cash' else min(value,money(specified_dollars)/20)
            cash+=n*c
            if method=='combination' and px:shares+=n*(value-c)/px
    else:raise ValueError('unverified settlement election')
    if round_holder and shares:
        if fraction_price is None:raise ValueError('holder rounding requires contractual fraction price')
        whole=shares.to_integral_value(rounding=ROUND_FLOOR);cash+=(shares-whole)*money(fraction_price);shares=whole
    return {'cash':cash,'shares':shares,'principal_extinguished':p}

def conversion_coupon_entitlement(principal,rate,conversion,record,payment,exempt=False):
    coupon=money(principal)*money(rate)/2
    protected=record<conversion<payment
    return {'record_holder_cash':coupon if protected else D(0),
            'converting_holder_cash_in':coupon if protected and not exempt else D(0)}

def preferred_retirement_price(ticker,route,liquidation,arrears_per_share,protected_per_share=0,
                                five_day_average=None,stated=100):
    lp,a,protected,st=map(money,(liquidation,arrears_per_share,protected_per_share,stated))
    if protected>a or protected<0:raise ValueError('invalid protected entitlement')
    if route=='ordinary':
        if ticker!='STRC':raise ValueError('ordinary par call not authorized for this series')
        base=D(101)
    elif route=='fundamental_change':base=st
    elif route in ('cleanup','tax'):
        if ticker=='STRK' and route=='tax':
            if five_day_average is None:raise ValueError('STRK tax redemption needs five-day average')
            base=max(lp,money(five_day_average))
        else:base=lp
    else:raise ValueError('unknown contractual retirement route')
    return base+a-protected

def preferred_retirement_allowed(ticker,route,shares,outstanding,total_ever_issued,
                                  verified_event=False,listed=True):
    n,o,total=map(money,(shares,outstanding,total_ever_issued))
    if n<=0 or n>o or n!=int(n):return False
    if route=='ordinary':return ticker=='STRC' and listed and (n==o or (o-n)*100>=250000000)
    if route=='cleanup':return n==o and o<D('.25')*total
    if route=='tax':return verified_event and n==o
    if route=='fundamental_change':return verified_event
    return False

def strk_conversion(shares,rate='.1',arrears=0,protected=0,entire_holder_position=False,dividend_cash_exempt=False):
    """At holder election; accrued dividends are not automatically paid on conversion.
    A separately declared record-holder entitlement survives; exact shareholder
    fractional aggregation requires holder data and is kept outside this envelope.
    """
    n,r=map(money,(shares,rate));minimum=(1/r).to_integral_value(rounding='ROUND_CEILING')
    if n<=0 or (n<minimum and not entire_holder_position) or n!=int(n):raise ValueError('STRK minimum conversion denomination')
    return {'common_shares':n*r,'retired_preferred':n,'protected_cash':money(protected),
            'converting_holder_cash_in':D(0) if dividend_cash_exempt else money(protected),
            'unpaid_dividends_not_separately_paid':max(D(0),money(arrears)-money(protected))}
