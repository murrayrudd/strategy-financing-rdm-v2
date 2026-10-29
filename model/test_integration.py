import unittest,json
from dataclasses import replace
from datetime import date,timedelta
from decimal import Decimal as D
from pathlib import Path
from contracts import *
from simulation import *

class ContractTests(unittest.TestCase):
    def test_makewhole_all_vertices_and_split(self):
        cells=0
        for k,t in TABLES.items():
            base=D(TERMS[k]['split_adjusted_base_conversion_shares_per_1000'])
            for row in t['rows']:
                for price,expected in zip(t['prices'],row['additional_shares_per_1000']):
                    actual=make_whole(k,date.fromisoformat(row['date']),price)
                    self.assertEqual(actual,min(D(expected),D(t['max_total_conversion_rate'])-base));cells+=1
        self.assertEqual(cells,498)
        self.assertEqual(TABLES['2030A']['prices'][0],'105.101')
        self.assertEqual(TABLES['2030A']['rows'][0]['additional_shares_per_1000'][0],'2.8370')

    def test_interpolation_and_outside_price_range(self):
        t=TABLES['2028'];d0=date.fromisoformat(t['rows'][0]['date']);d1=date.fromisoformat(t['rows'][1]['date'])
        dt=d0+(d1-d0)//2;p=(D(t['prices'][0])+D(t['prices'][1]))/2
        self.assertGreater(make_whole('2028',dt,p),D(0))
        self.assertEqual(make_whole('2028',dt,1),D(0))
        self.assertEqual(make_whole('2028',dt,10000),D(0))
        with self.assertRaises(ValueError):make_whole('2028',date(2040,1,1),200)

    def test_combination_is_daily_not_average_price(self):
        ans=conversion_settlement(1000,10,'combination',[50]*10+[200]*10)
        self.assertEqual(ans['cash'],750)
        self.assertEqual(ans['shares'],D('2.5'))
        cash=conversion_settlement(1000,10,'cash',[50]*10+[200]*10)
        self.assertEqual(cash['cash'],1250)
        with self.assertRaises(ValueError):conversion_settlement(1000,10,'cash',[100]*19)

    def test_call_notice_periods_differ(self):
        day=date(2027,3,22);rate=D('6.6770')
        red=following(day+timedelta(days=20),'FED_NY')
        self.assertFalse(valid_call('2030A',day,red,8e8,8e8,[1000]*30,rate))
        red=following(day+timedelta(days=32),'FED_NY')
        self.assertTrue(valid_call('2030A',day,red,8e8,8e8,[1000]*30,rate))
        self.assertFalse(valid_call('2030A',day,red,8e8,750e6,[1000]*30,rate))
        self.assertTrue(valid_call('2030B',day,following(day+timedelta(days=20),'FED_NY'),2e9,2e9,[1000]*30,D('2.3072')))

    def test_strict_2030b_threshold(self):
        rate=D('2.3072');boundary=D('1.3')*1000/rate
        self.assertTrue(price_trigger([boundary]*30,rate))
        self.assertFalse(price_trigger([boundary]*30,rate,strict=True))

    def test_twenty_day_observation_and_quarter_trigger(self):
        d=observation_days('2028',date(2027,5,3))
        self.assertEqual(len(d),20)
        self.assertEqual(d[0],advance(date(2027,5,3),2,'US_EQUITY'))
        self.assertFalse(conversion_eligible('2028',date(2027,5,3),[]))
        self.assertTrue(conversion_eligible('2028',date(2027,5,3),[1000]*30))

    def test_record_entitlement_and_holder_cash(self):
        ans=conversion_coupon_entitlement(1000,'.02',date(2027,9,8),date(2027,9,1),date(2027,9,15))
        self.assertEqual(ans,{'record_holder_cash':D(10),'converting_holder_cash_in':D(10)})
        ans=conversion_coupon_entitlement(1000,'.02',date(2027,9,8),date(2027,9,1),date(2027,9,15),True)
        self.assertEqual(ans['converting_holder_cash_in'],0)
        self.assertEqual(strk_conversion(5,entire_holder_position=True,protected=3)['converting_holder_cash_in'],3)
        with self.assertRaises(ValueError):strk_conversion(5)

    def test_preferred_retirement_routes(self):
        self.assertTrue(preferred_retirement_allowed('STRC','ordinary',100,3000000,3000000))
        self.assertFalse(preferred_retirement_allowed('STRC','ordinary',600000,3000000,3000000))
        self.assertFalse(preferred_retirement_allowed('STRF','ordinary',100,100,100))
        self.assertTrue(preferred_retirement_allowed('STRE','cleanup',100,100,1000))
        self.assertFalse(preferred_retirement_allowed('STRD','tax',100,100,1000))
        self.assertEqual(preferred_retirement_price('STRK','tax',100,2,1,110),111)

class DriverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.flat=Future('test_flat',0,10,0,1,1,0,0,20,.12,0,0,1,0)
        cls.funded=Assumptions(initial_cash_increment=1e11,conversion_behavior='none',issuer_calls=False,
            tax_rate=0,other_loan_repayment='2027-06-30')
        cls.hold=Policy('funded_contract_witness',24,0,0)

    def test_cash_contract_compatibility_with_frozen_schedule(self):
        r=Simulation(self.flat,self.hold,self.funded,keep_ledger=True).run()
        legacy=json.loads((ROOT/'data/legacy_cash_witness.json').read_text())
        expected={};actual={}
        for p in legacy['payments']:
            if p['claim_id']=='other_secured':continue
            key=p['claim_id'],p['kind'];expected[key]=expected.get(key,Z)+money(p['amount_native'])*(D('1.1408') if p['claim_id']=='STRE' else 1)
        for e in r['ledger']:
            if e['kind']=='preferred_settlement':
                key=e['security'],'dividend';amount=e['cash_native']*(D('1.1408') if e['security']=='STRE' else 1)
            elif e['kind'] in ('debt_coupon','debt_principal'):
                key=e['security'],'interest' if e['kind']=='debt_coupon' else 'principal';amount=e['paid']
            else:continue
            actual[key]=actual.get(key,Z)+amount
        # Zero coupon instruments need no interest key.
        expected={k:v for k,v in expected.items() if v};actual={k:v for k,v in actual.items() if v}
        self.assertEqual(set(expected),set(actual))
        comparison=[]
        for k in expected:
            residual=actual[k]-expected[k];self.assertLess(abs(residual),D('.00001'),str(k))
            comparison.append({'instrument':k[0],'kind':k[1],'legacy_usd':expected[k],'v2_usd':actual[k],'residual':residual})
        self.assertIsNone(r['terminal']['first_preferred_miss'])
        self.assertIsNone(r['terminal']['debt_shortfall'])
        (ROOT/'results/frozen_cash_schedule_comparison.json').write_text(json.dumps({'checks':comparison,'all_match':True,
            'scope':'Fixed existing instruments, all cash, all puts; excludes the unverified legacy other-loan amortization. This is cash-schedule compatibility, not equivalence of full RDM engines.'},indent=2,default=str))

    def test_preferred_suspension_continues_without_debt_default(self):
        a=replace(self.funded,cash_legal_capacity_per_year=0)
        r=Simulation(self.flat,self.hold,a,end=date(2027,6,30)).run()['terminal']
        self.assertEqual(r['date'],'2027-06-30');self.assertIsNotNone(r['first_preferred_miss'])
        self.assertIsNone(r['debt_shortfall']);self.assertGreater(r['preferred_arrears_usd'],0)
        self.assertGreater(r['metrics']['preferred_omitted_usd'],0)

    def test_settlement_receipt_not_spendable_on_trade(self):
        s=Simulation(FUTURES[0],POLICIES[0],end=date(2026,7,31))
        s.day=date(2026,7,1);s.pt=s.path[s.day];before=s.liq.cash
        s.issue('MSTR',D(1000000));self.assertEqual(s.liq.cash,before)
        s.day=s.pending[0]['due'];s.settle_pending();self.assertGreater(s.liq.cash,before)

    def test_late_known_authorization_not_imported(self):
        s=Simulation(FUTURES[0],POLICIES[0]);s.issue('STRC',D(1e12))
        self.assertLessEqual(s.gross_issued['STRC'],D(6e9))
        self.assertLessEqual(sum(o['shares'] for o in s.pending)+s.pref['STRC'].shares,D(282556565))

    def test_physical_and_cash_conversion_driver_paths(self):
        for mode in ['physical','cash','combination']:
            a=replace(self.funded,conversion_behavior='eligible',conversion_method=mode,put_fraction=0)
            r=Simulation(self.flat,self.hold,a,end=date(2027,6,30),keep_ledger=True).run()
            self.assertGreater(r['terminal']['metrics']['debt_converted_principal'],0,mode)
            self.assertIsNone(r['terminal']['debt_shortfall'])
            self.assertLess(r['max_cash_reconciliation_residual'],D('.001'))
            (ROOT/f'results/conversion_{mode}_witness.json').write_text(json.dumps(r,indent=2,default=str))

    def test_new_share_record_entitlement_survives_retirement(self):
        s=Simulation(self.flat,self.hold,self.funded)
        s.day=date(2026,8,31);s.pt=s.path[s.day];s.record(s.day)
        e=next(e for e in s.sched if e['ticker']=='STRC' and e['record']==s.day)
        locked=s.records[e['id']];old=s.pref['STRC'].shares
        s.pref['STRC'].shares-=1000000
        self.assertEqual(s.records[e['id']],locked)
        e2=next(e for e in s.sched if e['ticker']=='STRC' and e['record']>s.day)
        self.assertLess(s.expected_regular(e2),old*100*s.strc_rate/24)

    def test_stock_dividend_changes_common_shares_and_cash(self):
        a=replace(self.funded,stock_dividend_election=True)
        r=Simulation(self.flat,self.hold,a,end=date(2027,6,30)).run()['terminal']
        self.assertGreater(r['metrics']['common_from_dividend'],0)
        self.assertIsNone(r['debt_shortfall'])

    def test_issuer_call_and_makewhole_are_executed(self):
        a=replace(self.funded,conversion_behavior='respond_call_only',issuer_calls=True,put_fraction=0)
        r=Simulation(self.flat,self.hold,a,end=date(2027,6,30),keep_ledger=True).run()
        self.assertGreater(r['terminal']['metrics']['call_notices'],0)
        self.assertGreater(r['terminal']['metrics']['debt_converted_principal'],0)
        self.assertIsNone(r['terminal']['debt_shortfall'])
        self.assertTrue(any(e['kind']=='issuer_call_notice' and e['make_whole_extra']>0 for e in r['ledger']))
        (ROOT/'results/issuer_call_witness.json').write_text(json.dumps(r,indent=2,default=str))

    def test_ordinary_strc_redemption_is_delivered(self):
        a=replace(self.funded,initial_cash_increment=1e10)
        p=Policy('redemption_witness',12,0,0,None,True)
        r=Simulation(self.flat,p,a,end=date(2027,6,30),keep_ledger=True).run()
        self.assertGreater(r['terminal']['metrics']['strc_retired'],0)
        self.assertLess(r['terminal']['STRC_shares'],D(OPEN['btc'])*1000)
        self.assertIsNone(r['terminal']['debt_shortfall'])
        self.assertFalse(any(e['kind']=='redemption_unfunded' for e in r['ledger']))
        (ROOT/'results/STRC_retirement_witness.json').write_text(json.dumps(r,indent=2,default=str))

    def test_pending_cash_conversion_enters_funding_forecast(self):
        s=Simulation(self.flat,self.hold,self.funded,end=date(2027,6,30))
        s.day=date(2026,7,1);s.pt=s.path[s.day];s.sched=[];s.other=0
        s.debt={k:D(0) for k in s.debt};s.debt['2028']=D(1000)
        s.conversions['2028']={'principal':D(1000),'rate':D(10),'method':'cash','vwaps':[],
                             'settle':date(2026,7,30)}
        self.assertLess(abs(s.needed(30)-s.quote()*10),D('.000001'))

if __name__=='__main__':unittest.main()
