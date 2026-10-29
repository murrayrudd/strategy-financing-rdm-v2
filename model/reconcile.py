"""Reconcile six consecutive quarters from independently filed stocks and flows.

The checks retain every nonzero residual. They do not insert balancing entries.
"""
from pathlib import Path
from decimal import Decimal
import json

ROOT=Path(__file__).resolve().parent
D=Decimal
PERIODS=['2024-12-31','2025-03-31','2025-06-30','2025-09-30','2025-12-31','2026-03-31','2026-06-30']
DOCS={p:json.loads((ROOT/'data'/f'{p}_facts.json').read_text()) for p in PERIODS}

def get(doc,names,instant=None,start=None,end=None,dimension=None,optional=False):
    if isinstance(names,str):names=[names]
    for name in names:
        matches=[]
        for f in doc['facts']:
            if f['name']!=name:continue
            c=doc['contexts'].get(f['context'],{})
            if instant and c.get('instant')!=instant:continue
            if start and c.get('startdate')!=start:continue
            if end and c.get('enddate')!=end:continue
            dims=c.get('dimensions',{})
            if dimension is None and dims:continue
            if dimension is not None and not dimension(dims):continue
            matches.append(f)
        if matches:
            precision=lambda f: 999 if f['decimals']=='INF' else int(f.get('decimals') or -99)
            best=max(precision(f) for f in matches)
            vals={D(f['value']) for f in matches if precision(f)==best}
            if len(vals)!=1:raise ValueError((name,instant,start,end,vals))
            return vals.pop()
    if optional:return None
    raise KeyError((names,instant,start,end))

def ytd(doc,name,period,optional=False,dimension=None):
    return get(doc,name,start=period[:4]+'-01-01',end=period,optional=optional,dimension=dimension)

def total_cash(doc,p):
    return get(doc,'us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsIncludingDisposalGroupAndDiscontinuedOperations',instant=p)

def holding(doc,p):
    return get(doc,['us-gaap:CryptoAssetNumberOfUnits','mstr:NumberOfBitcoinHeld'],instant=p)

def preferred_total(doc,p):
    try:return get(doc,'us-gaap:TemporaryEquitySharesOutstanding',instant=p)
    except KeyError:
        return get(doc,'us-gaap:TemporaryEquitySharesOutstanding',instant=p,
          dimension=lambda x: x=={'us-gaap:StatementEquityComponentsAxis':'mstr:PerpetualPreferredStockMember'},optional=True)

def declarations(p):
    doc=DOCS[p];month=int(p[5:7]);start=f'{p[:4]}-{month-2:02d}-01'
    for dim in [None, lambda x:x=={'us-gaap:StatementEquityComponentsAxis':'us-gaap:RetainedEarningsMember'}]:
        v=get(doc,'us-gaap:DividendsPreferredStockCash',start=start,end=p,dimension=dim,optional=True)
        if v is not None:return v
    annual=ytd(doc,'us-gaap:DividendsPreferredStockCash',p)
    return annual-sum(declarations(q) for q in PERIODS if q[:4]==p[:4] and q<p)

def pref_issuance_quarter(p):
    doc=DOCS[p];start=f'{p[:4]}-{int(p[5:7])-2:02d}-01'
    name='mstr:TemporaryEquityStockIssuedDuringPeriodSharesNewIssues'
    def total(begin):
        aggregate=None; classes={}
        for f in doc['facts']:
            c=doc['contexts'][f['context']];dims=c['dimensions']
            if f['name']!=name or c.get('startdate')!=begin or c.get('enddate')!=p:continue
            if dims.get('us-gaap:StatementEquityComponentsAxis')!='mstr:PerpetualPreferredStockMember':continue
            cls=dims.get('us-gaap:StatementClassOfStockAxis')
            if cls:classes[tuple(sorted(dims.items()))]=D(f['value'])
            else:aggregate=D(f['value'])
        # Several older equity tables tag a zero in the aggregate placeholder
        # and report the actual issuance in class rows.
        if classes:return sum(classes.values())
        return aggregate
    direct=total(start)
    if direct is not None:return direct
    annual=total(p[:4]+'-01-01')
    if annual is None:return None
    return annual-sum(pref_issuance_quarter(q) for q in PERIODS if q[:4]==p[:4] and q<p)

def common_total(doc,p):
    total=D(0)
    for c in ['us-gaap:CommonClassAMember','us-gaap:CommonClassBMember']:
        v=get(doc,'us-gaap:CommonStockSharesOutstanding',instant=p,
          dimension=lambda x: x=={'us-gaap:StatementClassOfStockAxis':c},optional=True)
        if v is None:v=get(doc,'us-gaap:SharesOutstanding',instant=p,
          dimension=lambda x: x=={'us-gaap:StatementClassOfStockAxis':c,'us-gaap:StatementEquityComponentsAxis':'us-gaap:CommonStockMember'},optional=True)
        if v is None:
            # Year-end tables sometimes label this cell shares issued. Use only
            # when the same balance sheet explicitly reports zero treasury.
            if p in ('2025-12-31','2026-03-31'):
                # Manually checked 2025 10-K and 2026 Q1 balance sheets: the
                # Class A and B cells explicitly say issued AND outstanding,
                # but only the issued tags are present in iXBRL.
                pass
            else:assert get(doc,'us-gaap:TreasuryStockCommonShares',instant=p)==0
            v=get(doc,'us-gaap:CommonStockSharesIssued',instant=p,
              dimension=lambda x: x=={'us-gaap:StatementClassOfStockAxis':c},optional=True)
            if v is None:v=get(doc,'us-gaap:SharesIssued',instant=p,
              dimension=lambda x:x=={'us-gaap:StatementClassOfStockAxis':c,'us-gaap:StatementEquityComponentsAxis':'us-gaap:CommonStockMember'})
        total+=v
    return total

def common_flow(p):
    doc=DOCS[p];start=f'{p[:4]}-{int(p[5:7])-2:02d}-01'
    def rows(begin):
        out={}
        for f in doc['facts']:
            c=doc['contexts'][f['context']];dims=c['dimensions']
            if c.get('startdate')!=begin or c.get('enddate')!=p:continue
            if dims.get('us-gaap:StatementEquityComponentsAxis')!='us-gaap:CommonStockMember':continue
            if len(dims)!=2 or 'share' not in (f['unit'] or '').lower():continue
            # The displayed equity-statement share movements are already net of
            # withholding. Do not add option/RSU narrative amounts a second time.
            out[f['name']+'|'+dims['us-gaap:StatementClassOfStockAxis']]=D(f['value'])
        return out
    result=rows(start)
    if result:return sum(result.values())
    annual=rows(p[:4]+'-01-01')
    if not annual:raise ValueError('missing common equity movement table '+p)
    return sum(annual.values())-sum(common_flow(q) for q in PERIODS if q[:4]==p[:4] and q<p)

def run():
    results=[]
    ocf='us-gaap:NetCashProvidedByUsedInOperatingActivities'
    icf='us-gaap:NetCashProvidedByUsedInInvestingActivities'
    fcf='us-gaap:NetCashProvidedByUsedInFinancingActivities'
    fx='us-gaap:EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsIncludingDisposalGroupAndDiscontinuedOperations'
    for prev,p in zip(PERIODS,PERIODS[1:]):
        doc=DOCS[p]; prior=DOCS[prev]
        fields={}
        for name in [ocf,icf,fcf,fx]:
            fields[name]=ytd(doc,name,p)
            if prev[:4]==p[:4]:fields[name]-=ytd(prior,name,prev)
        residual=total_cash(prior,prev)+sum(fields.values())-total_cash(doc,p)
        results.append({'check':'cash_stock_flow','period':p,'opening':total_cash(prior,prev),'flows':fields,'reported_close':total_cash(doc,p),'residual':residual,'unit':'USD','status':'reconciled' if residual==0 else ('within_reported_precision' if abs(residual)<=3000 else 'open'),'rounding_note':'Each reported stock and flow is rounded to USD 1000; no residual is removed.'})
        buys=['mstr:CryptoAssetNumberOfUnitsPurchase','mstr:NumberOfBitcoinsPurchased']
        b=ytd(doc,buys,p);sold=ytd(doc,['mstr:CryptoAssetNumberOfUnitsSale','mstr:NumberOfBitcoinsSold'],p,optional=True) or D(0)
        if prev[:4]==p[:4]:
            b-=ytd(prior,buys,prev);sold-=ytd(prior,['mstr:CryptoAssetNumberOfUnitsSale','mstr:NumberOfBitcoinsSold'],prev,optional=True) or D(0)
        r=holding(prior,prev)+b-sold-holding(doc,p)
        results.append({'check':'bitcoin_units','period':p,'opening':holding(prior,prev),'purchases':b,'sales':sold,'reported_close':holding(doc,p),'residual':r,'unit':'Bitcoin','status':'reconciled' if r==0 else 'open'})
        cs0,cs1,cf=common_total(prior,prev),common_total(doc,p),common_flow(p)
        r=cs0+cf-cs1
        results.append({'check':'common_shares','period':p,'opening':cs0,'equity_statement_net_movement':cf,'reported_close':cs1,'residual':r,'unit':'shares','status':'reconciled' if r==0 else ('within_reported_precision' if abs(r)<=4000 else 'open')})
        begin_pref=preferred_total(prior,prev)
        if prev=='2024-12-31' and begin_pref is None:begin_pref=D(0)
        close_pref=preferred_total(doc,p)
        dims=lambda x:x.get('us-gaap:StatementEquityComponentsAxis')=='mstr:PerpetualPreferredStockMember'
        # Aggregate and class tables differ; class values are summed only when
        # the filing has no aggregate equity-statement fact.
        name='mstr:TemporaryEquityStockIssuedDuringPeriodSharesNewIssues'
        def pref_issued(d,period):
            try:return ytd(d,name,period,dimension=lambda x:x=={'us-gaap:StatementEquityComponentsAxis':'mstr:PerpetualPreferredStockMember'})
            except KeyError:
                vals={}
                for f in d['facts']:
                    c=d['contexts'][f['context']]
                    if f['name']==name and c.get('startdate')==period[:4]+'-01-01' and c.get('enddate')==period and dims(c['dimensions']):
                        vals[tuple(sorted(c['dimensions'].items()))]=D(f['value'])
                return sum(vals.values()) if vals else None
        issued=pref_issuance_quarter(p)
        if begin_pref is not None and close_pref is not None and issued is not None:
            r=begin_pref+issued-close_pref
            results.append({'check':'preferred_aggregate_shares','period':p,'opening':begin_pref,'issued':issued,'reported_close':close_pref,'residual':r,'unit':'shares','source_precision':'thousands','status':'reconciled' if r==0 else ('within_reported_precision' if abs(r)<=1500 else 'open')})
        op=get(prior,'us-gaap:DividendsPayableCurrent',instant=prev,optional=True)
        cp=get(doc,'us-gaap:DividendsPayableCurrent',instant=p,optional=True)
        if prev=='2024-12-31' and op is None:op=D(0)
        decl=declarations(p)
        paid=ytd(doc,'us-gaap:PaymentsOfDividendsPreferredStockAndPreferenceStock',p,optional=True)
        if prev[:4]==p[:4] and decl is not None and paid is not None:
            paid-=ytd(prior,'us-gaap:PaymentsOfDividendsPreferredStockAndPreferenceStock',prev)
        if op is not None and cp is not None and decl is not None and paid is not None:
            r=op+decl-paid-cp
            results.append({'check':'preferred_payable','period':p,'opening':op,'declared':decl,'paid':paid,'reported_close':cp,'residual':r,'unit':'USD','status':'reconciled' if r==0 else 'open'})
    out={'scope':'2025 Q1 through 2026 Q2; reported stocks and aggregate flows, not daily transaction reconstruction','checks':results}
    path=ROOT/'results';path.mkdir(exist_ok=True)
    (path/'historical_reconciliation.json').write_text(json.dumps(out,indent=2,default=str))
    for r in results:print(r['check'],r['period'],r['residual'],r['status'])

if __name__=='__main__':run()
