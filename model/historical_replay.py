"""Instrument-level historical checks, without invented daily transaction dates.

Shares use independent IPO/ATM disclosures and closing class counts. Convertible
principal is separate from net carrying value and repurchase cash. Quarterly
intervals remain intervals. This is a public-disclosure replay, not a brokerage
blotter or an assertion that every weekly 8-K has been transcribed.
"""
from pathlib import Path
from decimal import Decimal as D
import json,re
from reconcile import DOCS,PERIODS,get,ytd,common_total,common_flow,total_cash,holding

ROOT=Path(__file__).resolve().parent
CLASSES=['STRF','STRC','STRE','STRK','STRD']
IPO={'STRF':('2025-03-31',8500000),'STRC':('2025-09-30',28011111),
     'STRE':('2025-12-31',7750000),'STRK':('2025-03-31',7300000),'STRD':('2025-06-30',11764700)}
SID={'2024-12-31':'S01','2025-03-31':'S02','2025-06-30':'S03','2025-09-30':'S25',
     '2025-12-31':'S07','2026-03-31':'S08','2026-06-30':'S09'}

def cls(dims,k):return any(k in v for v in dims.values())

def closing(p,k):
    if p<IPO[k][0]:return D(0)
    if p=='2025-03-31':return D(8500000 if k=='STRF' else 7650000)
    return get(DOCS[p],'us-gaap:PreferredStockSharesIssued',instant=p,
               dimension=lambda ds:len(ds)==1 and cls(ds,k) and 'us-gaap:StatementClassOfStockAxis' in ds)

def atm_ytd(p,k):
    if p<IPO[k][0]:return D(0)
    d=DOCS[p]
    if p=='2025-03-31':return D(350000 if k=='STRK' else 0)
    if p in ('2025-06-30','2025-09-30'):
        v=get(d,'us-gaap:PreferredStockSharesIssued',instant=p,
              dimension=lambda ds:len(ds)==1 and cls(ds,k) and 'us-gaap:TypeOfArrangementAxis' in ds,optional=True)
        # STRD's first ATM did not begin until after the June quarter.
        return v if v is not None else D(0)
    if k=='STRE':return D(0) # no STRE ATM in these filings
    return ytd(d,'us-gaap:SaleOfStockNumberOfSharesIssuedInTransaction',p,
               dimension=lambda ds:cls(ds,k) and 'us-gaap:SubsidiarySaleOfStockAxis' in ds)

def instrument(ds):
    s=' '.join(ds.values())
    aliases={'2027':['2027','TwentyTwentySeven'],'2028':['2028','TwentyTwentyEight'],
       '2029':['2029','TwentyTwentyNine'],'2030B':['2030B','ThirtyB'],
       '2030A':['2030A','ThirtyA','TwentyThirtyMember','DueThirtyMember'],
       '2031':['2031','ThirtyOne'],'2032':['2032','ThirtyTwo']}
    for k,patterns in aliases.items():
        if any(a in s for a in patterns):return k
    return None

def principal(p,k):
    if k=='2030B' and p<'2025-03-31' or k=='2027' and p>='2025-03-31':return D(0)
    # In 2026 the displayed Outstanding Principal Amount column carries a
    # DebtInstrumentCarryingAmount tag. The column heading was checked directly.
    return get(DOCS[p],['mstr:DebtInstrumentOutstandingPrincipal','us-gaap:DebtInstrumentOutstandingPrincipal','us-gaap:DebtInstrumentCarryingAmount'],
               instant=p,dimension=lambda ds:instrument(ds)==k)

def run():
    checks=[];ledger=[];snapshots=[]
    for p in PERIODS:
        snapshots.append({'date':p,'source_id':SID[p],'cash_including_restricted':total_cash(DOCS[p],p),
          'Bitcoin_units':holding(DOCS[p],p),'common_shares':common_total(DOCS[p],p),
          'preferred_shares':{k:closing(p,k) for k in CLASSES},
          'convertible_principal':{k:principal(p,k) for k in ['2027','2028','2029','2030A','2030B','2031','2032']}})
    transactions={
      ('2025-03-31','2027'):{'retired':1050000000,'issued':0,'type':'holder conversion/redemption','common_delivered':7373528,'source_id':'S02','cash_separate_note':'$143,000 total conversion/redemption cash, not $1.05bn cash principal'},
      ('2025-03-31','2030B'):{'retired':0,'issued':2000000000,'type':'debt issue','date':'2025-02-21','source_id':'S02'},
      ('2025-06-30','2031'):{'retired':89000,'issued':0,'type':'holder conversion settled','common_delivered':382,'source_id':'S03'},
      ('2025-12-31','2031'):{'retired':2000,'issued':0,'type':'holder conversion settled','common_delivered':8,'cash_fractional':190.05,'source_id':'S07','election_interval':'2025 Q3'},
      ('2026-06-30','2029'):{'retired':1500000000,'issued':0,'type':'negotiated debt repurchase','cash_paid':1378649000,'source_id':'S09'}}
    for n,p in enumerate(PERIODS[1:],1):
        prev=PERIODS[n-1];start=f'{p[:4]}-{int(p[5:7])-2:02d}-01'
        for k in CLASSES:
            ipo=D(IPO[k][1]) if p==IPO[k][0] else D(0)
            atm=atm_ytd(p,k)-(atm_ytd(prev,k) if prev[:4]==p[:4] else 0)
            begin=closing(prev,k);close=closing(p,k);res=begin+ipo+atm-close
            checks.append({'check':'preferred_class_shares','period':p,'instrument':k,'opening':begin,'IPO_issued':ipo,'ATM_issued':atm,'closing':close,'residual':res,'status':'reconciled' if res==0 else 'open','source_id':SID[p]})
            if ipo or atm:ledger.append({'interval_start':start,'interval_end':p,'instrument':k,'type':'preferred issue','IPO_shares':ipo,'ATM_shares':atm,'date_resolution':'quarter; do not assign to one trade date','source_id':SID[p]})
        for k in ['2027','2028','2029','2030A','2030B','2031','2032']:
            begin=principal(prev,k);close=principal(p,k);tx=transactions.get((p,k),{'issued':0,'retired':0})
            res=begin+D(tx['issued'])-D(tx['retired'])-close
            checks.append({'check':'convertible_principal','period':p,'instrument':k,'opening':begin,'issued':tx['issued'],'retired':tx['retired'],'closing':close,'residual':res,'status':'reconciled' if res==0 else 'open','source_id':SID[p]})
            if tx['issued'] or tx['retired']:ledger.append({'interval_start':start,'interval_end':p,'instrument':k,**tx})
        ledger.append({'interval_start':start,'interval_end':p,'instrument':'MSTR','type':'common stock movements','flows':common_flow(p),'source_id':SID[p],'precision':'equity statement, thousands of shares'})
    # Independently disclosed class cash dividends in the 2026 H1 table.
    div={'STRF':64198000,'STRC':394295000,'STRE':44478000,'STRK':56083000,'STRD':70121000}
    paid=ytd(DOCS['2026-06-30'],'us-gaap:PaymentsOfDividendsPreferredStockAndPreferenceStock','2026-06-30')
    checks.append({'check':'H1_class_cash_dividend_sum','period':'2026-06-30','sum_class_cash':sum(div.values()),'cash_flow_paid':paid,'residual':D(sum(div.values()))-paid,'status':'reconciled' if sum(div.values())==paid else 'open','source_id':'S09'})
    for k,v in div.items():ledger.append({'interval_start':'2026-01-01','interval_end':'2026-06-30','instrument':k,'type':'cash dividend paid','cash_usd':v,'source_id':'S09'})
    # Delivered 2031 shares agree with rate plus per-holder rounding bounds.
    for p,n,shares in [('2025-06-30',89000,382),('2025-12-31',2000,8)]:
        theoretical=D(n)/1000*D('4.2970')
        checks.append({'check':'2031_conversion_share_envelope','period':p,'principal':n,'continuous_shares':theoretical,'delivered_whole_shares':shares,'fractional_gap':theoretical-shares,'status':'within_holder_rounding_envelope' if 0<=theoretical-shares<1 else 'open','source_id':SID[p]})
    out={'scope':'Modern financing history, 2025 Q1–2026 Q2. Quarter interval replay with instrument-level independent checks. Weekly transaction transcription remains separate.',
       'snapshots':snapshots,'transaction_ledger':ledger,'checks':checks,
       'precision_notes':['2025 Q1 preferred class counts checked against class equity rows; first STRK IPO 7.3m plus 0.35m ATM.',
         'A debt face-amount tag in offering descriptions is not used as current outstanding principal.',
         'Public issuance and payment aggregates do not identify beneficial holders or tax lots.',
         'Historical record does not replace observed closing cash with a constructed balancing amount.'],
       'unresolved_bridges':[{'item':'Bitcoin sale note versus cash flow','amount_usd':42167000},
                             {'item':'H1 preferred dividends payable','amount_usd':1013000}]}
    (ROOT/'results/instrument_historical_replay.json').write_text(json.dumps(out,indent=2,default=str))
    counts={s:sum(c['status']==s for c in checks) for s in sorted({c['status'] for c in checks})}
    print(json.dumps({'checks':len(checks),'status':counts,'ledger_rows':len(ledger),'open':[(c.get('instrument'),c['period'],str(c.get('residual'))) for c in checks if c['status']=='open']}))
    return out

if __name__=='__main__':run()
