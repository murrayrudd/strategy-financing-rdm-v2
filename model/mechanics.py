"""Auditable v2 contract and cash transitions, independent of the frozen v1 code.

This is a tested integration component, not the production RDM driver. Unknown
legal capacity, tax lots, special-event conversion adjustments and authorizations
must be supplied explicitly. No optimization or endogenous market-price impact.
All monetary calculations use Decimal; input strings are preferred.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_FLOOR

D=Decimal
ZERO=D(0)
RANK={'STRF':0,'STRC':1,'STRE':2,'STRK':3,'STRD':4,'MSTR':5}
BASE={'STRF':D('.10'),'STRE':D('.10'),'STRK':D('.08'),'STRD':D('.10')}

def money(x):return x if isinstance(x,D) else D(str(x))

@dataclass
class Cohort:
    amount:D
    # Number of completed compounding periods since this dividend was missed.
    periods:int=0

@dataclass
class Preferred:
    ticker:str
    shares:D
    arrears:list=field(default_factory=list)
    missed_latest:bool=False
    paid_native:D=ZERO
    omitted_native:D=ZERO

    @property
    def unpaid(self):return sum((c.amount for c in self.arrears),ZERO)

    def compound(self,annual_rate=None):
        """Call once at the NEXT nominal regular boundary, before new accrual.

        F/E: missed cohorts earn 11%, then 12%, ... capped at 18% annually.
        K: 8%. C: applicable variable rate and 24 periods/year.
        D: declared unpaid dividends remain payable but earn no interest.
        """
        before=self.unpaid
        for c in self.arrears:
            if self.ticker in ('STRF','STRE'):
                rate=min(D('.18'),D('.11')+D('.01')*c.periods);denom=4
            elif self.ticker=='STRK':rate=D('.08');denom=4
            elif self.ticker=='STRC':
                if annual_rate is None:raise ValueError('STRC rate required')
                rate=money(annual_rate);denom=24
            else:rate=ZERO;denom=4
            c.amount*=1+rate/D(denom);c.periods+=1
        return self.unpaid-before

    def add_regular(self,amount,declared):
        amount=money(amount)
        if amount<0:raise ValueError('negative dividend')
        if self.ticker=='STRD' and not declared:
            self.omitted_native+=amount
        else:self.arrears.append(Cohort(amount))
        self.missed_latest=amount>0

    def settle(self,amount):
        """Satisfy oldest unpaid claims first. Payment is capped at the claim."""
        amount=money(amount)
        if amount<0:raise ValueError('negative settlement')
        if not amount:return ZERO
        remaining=min(amount,self.unpaid);paid=remaining
        for c in self.arrears:
            take=min(c.amount,remaining);c.amount-=take;remaining-=take
        self.arrears=[c for c in self.arrears if c.amount]
        self.paid_native+=paid
        # A zero payment cannot cure an omitted noncumulative STRD dividend.
        if paid>0 and not self.arrears:self.missed_latest=False
        return paid

def cash_distribution_blockers(ticker,accounts):
    """Current-series senior claims. No future pari passu securities assumed.

    Junior-stock payment exceptions must use their distinct route, not this
    cash gate. STRD's omitted last dividend can still restrict common payouts.
    """
    return [a.ticker for a in accounts if RANK[a.ticker]<RANK[ticker]
            and (a.unpaid>0 or a.missed_latest)]

def mandatory_dividend_amount(ticker,total_due,record_date,offerings):
    """Registered CASH offerings in the 90 days preceding the record date.

    Each entry supplies date, security, net_proceeds_usd, registered_cash.
    Conversion, employee issuance and convertible debt are excluded. This
    calculation establishes the proceeds-based ceiling; senior restrictions,
    lawful payment and STRK share settlement are separate constraints.
    """
    eligible={'STRF':{'MSTR','STRK'},'STRK':{'MSTR'}}.get(ticker,set())
    proceeds=ZERO
    for o in offerings:
        days=(record_date-date.fromisoformat(o['date'])).days
        if 1<=days<=90 and o['security'] in eligible and o['registered_cash']:
            proceeds+=money(o['net_proceeds_usd'])
    return min(money(total_due),proceeds)

def strk_stock_dividend(total_declared,stock_elected,vwap,available_shares,
                        floor='119.03',delivery_permitted=False):
    """Aggregate continuous-share envelope, before holder-level rounding.

    VWAP is the third VWAP trading day before payment. Floor cap is based on
    TOTAL declared dividend, including any cash election. Remaining dollars
    need legal cash settlement or remain unpaid. Fractional-holder settlement
    is deliberately not silently approximated as legally exact.
    """
    total,stock,vwap,avail,floor=map(money,(total_declared,stock_elected,vwap,available_shares,floor))
    if total<0 or stock<0 or stock>total or vwap<=0 or floor<=0 or avail<0:
        raise ValueError('invalid stock-dividend inputs')
    if not delivery_permitted:return {'shares':ZERO,'satisfied':ZERO,'remaining':total}
    px=D('.95')*vwap
    shares=min(stock/px,total/floor,avail)
    satisfied=shares*px
    return {'shares':shares,'satisfied':satisfied,'remaining':total-satisfied}

def fractional_cash(shares,vwap):
    """Per-holder cash in lieu uses full VWAP, not the 95% stock price."""
    shares=money(shares);whole=shares.to_integral_value(rounding=ROUND_FLOOR)
    return whole,(shares-whole)*money(vwap)

def strc_rate_floor(previous,sofr_notice,sofr_third_start,sofr_prior_window_min,
                    previous_arrears=False,fully_funded_declaration=False):
    prev,notice,start,low=map(money,(previous,sofr_notice,sofr_third_start,sofr_prior_window_min))
    reduction=D('.0025')+max(start-low,ZERO)
    floor=max(ZERO,notice,prev-reduction)
    if previous_arrears and not fully_funded_declaration:floor=max(floor,prev)
    return floor

def liquidation_preference(stated,prior_ten_prices,issuance_in_window,
                           adjustment_activated):
    """Prior ten completed trading days only; inputs must be point-in-time.

    STRK activation includes the July 7, 2025 amendment as an issuance event.
    No future issuance or today's closing price may enter this calculation.
    """
    stated=money(stated)
    if not adjustment_activated:return stated
    if len(prior_ten_prices)!=10:raise ValueError('ten prior trading closes required')
    prices=list(map(money,prior_ten_prices))
    if any(p<0 for p in prices):raise ValueError('negative price')
    return max(stated,sum(prices)/10,prices[-1] if issuance_in_window else ZERO)

def strc_redemption_cost(shares,outstanding,arrears_per_share,
                         protected_record_entitlement_per_share='0',price='101',
                         notice_valid=False,exchange_listed=False):
    """Ordinary contractual redemption, not clean-up, tax or market purchase.

    Notice timing, listing and protected record-date dividends must be supplied.
    The latter remain payable to record holders and are excluded from this
    redemption cheque to avoid duplicate settlement.
    """
    n,out,a,protected,p=map(money,(shares,outstanding,arrears_per_share,
                                 protected_record_entitlement_per_share,price))
    if not notice_valid or not exchange_listed:raise ValueError('redemption prerequisites')
    if n<=0 or n>out or n!=int(n) or p<101 or protected<0 or protected>a:
        raise ValueError('redemption inputs')
    if n<out and (out-n)*100<D('250000000'):raise ValueError('partial redemption minimum')
    return n*(p+a-protected)

def strc_november_branch(vote_approved,amendment_effective):
    return 'daily' if vote_approved and amendment_effective else 'semimonthly'

def conversion_shares(principal,ratio,eligible=False,adjusted_rate_verified=False):
    """Physical settlement only. No automatic in-the-money conversion.

    Special-event make-whole/antidilution and cash/combo settlement must first be
    resolved by the caller. A value of False fails closed instead of guessing.
    """
    p,r=money(principal),money(ratio)
    if p<0 or r<=0 or p%1000:raise ValueError('principal denomination or conversion rate')
    if not eligible or not adjusted_rate_verified:raise ValueError('conversion prerequisites')
    return p/1000*r

def call_market_trigger(prices,conversion_prices):
    if len(prices)!=30 or len(conversion_prices)!=30:raise ValueError('30 trading days required')
    eligible=[money(p)>=D('1.3')*money(k) for p,k in zip(prices,conversion_prices)]
    return eligible[-1] and sum(eligible)>=20

def thirty360(start,end):
    """Indenture 12 x 30-day months; partial months use a 30-day convention."""
    return D(360*(end.year-start.year)+30*(end.month-start.month)+min(end.day,30)-min(start.day,30))/360

@dataclass
class Liquidity:
    cash:D
    treasury:D=ZERO
    restricted:D=ZERO
    designation:D=ZERO
    tax_reserved:D=ZERO
    legal_budget:D|None=None
    pending:list=field(default_factory=list)
    ledger:list=field(default_factory=list)
    opening_cash:D=field(init=False)
    cash_changes:D=ZERO

    def __post_init__(self):
        for k in ['cash','treasury','restricted','designation','tax_reserved']:
            setattr(self,k,money(getattr(self,k)))
        self.opening_cash=self.cash
        if self.legal_budget is not None:self.legal_budget=money(self.legal_budget)

    @property
    def usable(self):return max(ZERO,self.cash-self.tax_reserved)

    def record(self,amount,kind):
        amount=money(amount);self.cash+=amount
        self.cash_changes+=amount
        self.ledger.append({'kind':kind,'cash_change':amount})

    def treasury_sale(self,amount,settlement_date,haircut='0'):
        amount,haircut=money(amount),money(haircut)
        if amount<0 or amount>self.treasury or not 0<=haircut<=1:raise ValueError('treasury sale')
        self.treasury-=amount
        self.pending.append((settlement_date,amount*(1-haircut),'treasury_settlement'))

    def settle(self,day):
        left=[]
        for due,amount,kind in self.pending:
            if due<=day:self.record(amount,kind)
            else:left.append((due,amount,kind))
        self.pending=left

    def pay(self,amount,kind,distribution=False):
        amount=money(amount)
        if amount<0:raise ValueError('negative payment')
        allowed=min(amount,self.usable)
        if distribution:
            if self.legal_budget is None:raise ValueError('legal distribution capacity unknown')
            allowed=min(allowed,max(ZERO,self.legal_budget))
            self.legal_budget-=allowed
        self.record(-allowed,kind)
        return allowed,amount-allowed

    def pay_tax(self,amount):
        amount=money(amount)
        paid=min(amount,self.tax_reserved,self.cash)
        self.tax_reserved-=paid;self.record(-paid,'cash_tax')
        return paid

    def cash_residual(self):
        return self.opening_cash+self.cash_changes-self.cash

@dataclass
class BitcoinPosition:
    units:D
    basis:D
    loss_offset_budget:D=ZERO

    def sell(self,units,price,fee_rate,tax_rate,liquidity,settlement_date):
        """Explicit average-basis scenario; no assertion about actual tax lots.

        Positive gains consume an explicit allowed loss-offset budget; losses
        do not create an immediate refund. Reserved tax cannot fund dividends.
        """
        n,p,f,t=map(money,(units,price,fee_rate,tax_rate))
        if n<0 or n>self.units or p<0 or not 0<=f<1 or not 0<=t<=1:raise ValueError('Bitcoin sale')
        removed=ZERO if self.units==0 else self.basis*n/self.units
        proceeds=n*p*(1-f);gain=max(ZERO,proceeds-removed)
        offset=min(gain,self.loss_offset_budget);self.loss_offset_budget-=offset
        tax=(gain-offset)*t
        self.units-=n;self.basis-=removed
        liquidity.pending.append((settlement_date,proceeds,'Bitcoin_settlement'))
        liquidity.tax_reserved+=tax
        return {'gross':n*p,'fees':n*p*f,'proceeds':proceeds,'basis_removed':removed,'tax_reserved':tax}

def repurchase_excise(covered_repurchases,eligible_issuances,rate='.01'):
    """Annual net base after explicit class qualification/exemption mapping."""
    return max(ZERO,money(covered_repurchases)-money(eligible_issuances))*money(rate)

def execute_preferred_period(account,regular,declared,liquidity,accounts,fx='1',
                              mandatory='0',pay_requested=True,annual_rate=None):
    """Cash-path transition. Real driver must schedule nominal and cash dates.

    Opening declared credits are part of the first scheduled settlements, not
    a second extra cash payment. The integration witness handles those credits.
    """
    fx=money(fx)
    if fx<=0:raise ValueError('positive FX required')
    interest=account.compound(annual_rate)
    account.add_regular(regular,declared)
    blockers=cash_distribution_blockers(account.ticker,accounts)
    wanted=account.unpaid if pay_requested else min(account.unpaid,money(mandatory))
    paid=ZERO
    if wanted and not blockers:
        paid_usd,_=liquidity.pay(wanted*fx,account.ticker+'_dividend',distribution=True)
        paid=account.settle(paid_usd/fx)
    return {'paid_native':paid,'unpaid_native':account.unpaid,'compound_native':interest,
            'blockers':blockers,'mandatory_unmet':max(ZERO,money(mandatory)-paid),
            'noncumulative_omitted':account.omitted_native}
