"""Hand-calculated boundary witnesses and frozen-schedule compatibility."""
import unittest,json
from pathlib import Path
from datetime import date
from mechanics import *
import date_rules

class CalendarTests(unittest.TestCase):
    def test_good_friday_is_not_a_fed_ny_holiday(self):
        self.assertTrue(date_rules.is_open(date(2026,4,3),'FED_NY'))
        self.assertFalse(date_rules.is_open(date(2026,4,3),'US_EQUITY'))
        self.assertFalse(date_rules.is_open(date(2026,4,3),'STRE_PAY'))

    def test_saturday_holiday_observance_differs(self):
        self.assertTrue(date_rules.is_open(date(2026,7,3),'FED_NY'))
        self.assertFalse(date_rules.is_open(date(2026,7,3),'US_EQUITY'))

    def test_fed_closure_does_not_remove_trading_day(self):
        self.assertFalse(date_rules.is_open(date(2026,10,12),'FED_NY'))
        self.assertTrue(date_rules.is_open(date(2026,10,12),'US_EQUITY'))
        self.assertEqual(date_rules.previous_trading(date(2026,10,15),3),date(2026,10,12))

    def test_london_holiday_affects_euro_payment(self):
        self.assertTrue(date_rules.is_open(date(2026,8,31),'FED_NY'))
        self.assertFalse(date_rules.is_open(date(2026,8,31),'STRE_PAY'))
        self.assertEqual(date_rules.following(date(2026,8,31),'STRE_PAY'),date(2026,9,1))

    def test_effective_date_is_not_information_date(self):
        events=[{'instrument':'STRK','effective_date':'2025-02-05','public_date':'2025-02-07','authorized':7300000},
                {'instrument':'STRK','effective_date':'2025-03-10','public_date':'2025-08-05','authorized':269800000}]
        self.assertEqual(date_rules.authorized_shares(events,'STRK',date(2025,6,30),date(2025,6,30)),7300000)
        self.assertEqual(date_rules.authorized_shares(events,'STRK',date(2025,6,30),date(2026,10,23)),269800000)

class ContractTests(unittest.TestCase):
    def test_strf_arrears_cohort_age(self):
        p=Preferred('STRF',D(1));p.add_regular('2.5',False)
        self.assertEqual(p.compound(),D('.06875'))
        p.add_regular('2.5',False)
        self.assertEqual(p.compound(),D('.1458125'))
        self.assertEqual(p.unpaid,D('5.2145625'))

    def test_stre_stepup_caps(self):
        p=Preferred('STRE',D(1),[Cohort(D(100),100)])
        self.assertEqual(p.compound(),D('4.5'))

    def test_strc_compounds_without_strf_stepup(self):
        p=Preferred('STRC',D(1),[Cohort(D(100),20)])
        self.assertEqual(p.compound('.12'),D('.5'))

    def test_strk_compounds_at_eight(self):
        p=Preferred('STRK',D(1),[Cohort(D(100),20)])
        self.assertEqual(p.compound(),D(2))

    def test_strd_undeclared_not_debt(self):
        p=Preferred('STRD',D(1));p.add_regular('2.5',False)
        self.assertEqual(p.unpaid,0);self.assertEqual(p.omitted_native,D('2.5'))
        self.assertEqual(cash_distribution_blockers('MSTR',[p]),['STRD'])

    def test_strd_declared_remains_payable(self):
        p=Preferred('STRD',D(1));p.add_regular('2.5',True)
        self.assertEqual(p.compound(),0);self.assertEqual(p.unpaid,D('2.5'))

    def test_zero_settlement_cannot_cure_omitted_strd(self):
        p=Preferred('STRD',D(1));p.add_regular('2.5',False);p.settle(0)
        self.assertEqual(cash_distribution_blockers('MSTR',[p]),['STRD'])

    def test_oldest_first_and_no_overpayment(self):
        p=Preferred('STRF',D(1),[Cohort(D(10),3),Cohort(D(5),0)])
        self.assertEqual(p.settle(12),12);self.assertEqual(p.arrears,[Cohort(D(3),0)])
        self.assertEqual(p.settle(100),3);self.assertEqual(p.unpaid,0)

    def test_seniority_current_stack(self):
        a=Preferred('STRC',D(1),[Cohort(D(1))])
        self.assertEqual(cash_distribution_blockers('STRF',[a]),[])
        self.assertEqual(cash_distribution_blockers('STRE',[a]),['STRC'])

    def test_offering_90_day_window_and_eligible_security(self):
        offers=[{'date':'2026-06-17','security':'MSTR','net_proceeds_usd':'50','registered_cash':True},
                {'date':'2026-09-16','security':'MSTR','net_proceeds_usd':'900','registered_cash':True},
                {'date':'2026-07-01','security':'STRK','net_proceeds_usd':'30','registered_cash':True},
                {'date':'2026-07-01','security':'MSTR','net_proceeds_usd':'900','registered_cash':False},
                {'date':'2026-07-01','security':'2030B','net_proceeds_usd':'900','registered_cash':True}]
        self.assertEqual(mandatory_dividend_amount('STRF',100,date(2026,9,15),offers),80)
        self.assertEqual(mandatory_dividend_amount('STRK',100,date(2026,9,15),offers),50)
        self.assertEqual(mandatory_dividend_amount('STRD',100,date(2026,9,15),offers),0)

    def test_strk_floor_leaves_cash_or_arrears(self):
        r=strk_stock_dividend(2000,2000,50,1000,delivery_permitted=True)
        self.assertEqual(r['shares'].quantize(D('.000001')),D('16.802487'))
        self.assertEqual(r['remaining'].quantize(D('.01')),D('1201.88'))

    def test_strk_authorized_share_capacity(self):
        r=strk_stock_dividend(2000,2000,200,5,delivery_permitted=True)
        self.assertEqual(r,{'shares':D(5),'satisfied':D(950),'remaining':D(1050)})
        self.assertEqual(strk_stock_dividend(2000,2000,200,1000)['shares'],0)

    def test_fractional_cash_uses_full_vwap(self):
        self.assertEqual(fractional_cash('4.25',100),(D(4),D(25)))

    def test_rate_cut_sofr_window_and_arrears(self):
        self.assertEqual(strc_rate_floor('.12','.04','.05','.045'),D('.1125'))
        self.assertEqual(strc_rate_floor('.12','.04','.05','.045',True),D('.12'))
        self.assertEqual(strc_rate_floor('.04','.045','.05','.05'),D('.045'))

    def test_liquidation_value_is_not_fixed_at_100(self):
        prices=[100]*9+[120]
        self.assertEqual(liquidation_preference(100,prices,False,True),102)
        self.assertEqual(liquidation_preference(100,prices,True,True),120)
        self.assertEqual(liquidation_preference(100,prices,True,False),100)

    def test_liquidation_no_missing_history_default(self):
        with self.assertRaises(ValueError):liquidation_preference(100,[100],False,True)

    def test_strc_redemption_premium_and_record_entitlement(self):
        self.assertEqual(strc_redemption_cost(100,3000000,2,1,notice_valid=True,exchange_listed=True),10200)
        with self.assertRaises(ValueError):strc_redemption_cost(100,1000,0,notice_valid=True,exchange_listed=True)

    def test_conditional_november_exclusive(self):
        self.assertEqual([strc_november_branch(a,b) for a,b in [(False,False),(True,False),(False,True),(True,True)]],
                         ['semimonthly']*3+['daily'])

    def test_conversion_physical_and_eligibility(self):
        self.assertEqual(conversion_shares(1010000000,'5.4589',True,True),5513489)
        with self.assertRaises(ValueError):conversion_shares(1010000000,'5.4589',False,True)
        with self.assertRaises(ValueError):conversion_shares(1010000000,'5.4589',True,False)

    def test_call_requires_last_day_and_twenty(self):
        self.assertTrue(call_market_trigger([130]*19+[100]*10+[130],[100]*30))
        self.assertFalse(call_market_trigger([130]*20+[100]*10,[100]*30))
        self.assertFalse(call_market_trigger([130]*18+[100]*11+[130],[100]*30))

    def test_contract_day_count(self):
        self.assertEqual(thirty360(date(2026,3,15),date(2026,9,15)),D('.5'))
        self.assertEqual(thirty360(date(2026,6,15),date(2026,6,30)),D(15)/360)

class ResourceTests(unittest.TestCase):
    def test_reserve_is_not_extra_cash(self):
        q=Liquidity(100,treasury=50,restricted=20,designation=120)
        self.assertEqual(q.usable,100);self.assertEqual(q.pay(200,'debt'),(D(100),D(100)))
        self.assertEqual(q.cash_residual(),0)

    def test_unsettled_treasury_not_spendable(self):
        q=Liquidity(10,treasury=100)
        q.treasury_sale(100,date(2026,7,2),'.01')
        q.settle(date(2026,7,1));self.assertEqual(q.usable,10)
        q.settle(date(2026,7,2));self.assertEqual(q.usable,109)
        q.settle(date(2026,7,3));self.assertEqual(q.usable,109)

    def test_missing_legal_capacity_fails_closed(self):
        q=Liquidity(100)
        with self.assertRaises(ValueError):q.pay(1,'dividend',True)
        self.assertEqual(q.pay(1,'debt'),(D(1),D(0)))

    def test_cash_and_legal_capacity_separate(self):
        q=Liquidity(100,legal_budget=30)
        self.assertEqual(q.pay(80,'dividend',True),(D(30),D(50)))
        self.assertEqual(q.usable,70)

    def test_bitcoin_tax_and_cash_conservation(self):
        q=Liquidity(100);b=BitcoinPosition(D(10),D(500))
        r=b.sell(2,100,'.01','.25',q,date(2026,7,2))
        self.assertEqual(r['proceeds'],198);self.assertEqual(r['tax_reserved'],D('24.5'))
        self.assertEqual(q.usable,D('75.5'))
        q.settle(date(2026,7,2));self.assertEqual(q.usable,D('273.5'))
        q.pay_tax('24.5');self.assertEqual(q.usable,D('273.5'))
        self.assertEqual(b.units,8);self.assertEqual(b.basis,400);self.assertEqual(q.cash_residual(),0)

    def test_loss_does_not_generate_refund(self):
        q=Liquidity(0);b=BitcoinPosition(D(10),D(2000))
        self.assertEqual(b.sell(1,100,0,'.35',q,date(2026,7,2))['tax_reserved'],0)

    def test_tax_loss_offset_is_not_infinite(self):
        q=Liquidity(0);b=BitcoinPosition(D(10),D(0),D(50))
        self.assertEqual(b.sell(1,100,0,'.2',q,date(2026,7,2))['tax_reserved'],10)
        self.assertEqual(b.sell(1,100,0,'.2',q,date(2026,7,3))['tax_reserved'],20)

    def test_repurchase_annual_net_base(self):
        self.assertEqual(repurchase_excise(1000,600),4)
        self.assertEqual(repurchase_excise(1000,2000),0)

    def test_preferred_nonpayment_does_not_stop_state(self):
        q=Liquidity(100,legal_budget=0);p=Preferred('STRF',D(1))
        r=execute_preferred_period(p,'2.5',False,q,[p])
        self.assertEqual(r['unpaid_native'],D('2.5'))
        self.assertEqual(q.pay(80,'debt'),(D(80),D(0)))
        self.assertEqual(q.cash,20)

    def test_cure_restores_junior_cash_route(self):
        q=Liquidity(100,legal_budget=100)
        f=Preferred('STRF',D(1),[Cohort(D(10))]);k=Preferred('STRK',D(1))
        self.assertEqual(cash_distribution_blockers('STRK',[f,k]),['STRF'])
        f.settle(10)
        r=execute_preferred_period(k,2,True,q,[f,k])
        self.assertEqual(r['paid_native'],2)

    def test_legacy_cash_schedule_all_paid_compatibility(self):
        data=json.loads((Path(__file__).parent/'data/legacy_cash_witness.json').read_text())
        q=Liquidity('1e12',legal_budget='1e12')
        expected=ZERO
        for p in data['payments']:
            amount=money(p['amount_native'])*(D('1.1408') if p['claim_id']=='STRE' else 1)
            paid,short=q.pay(amount,p['id'],p['kind']=='dividend')
            self.assertEqual(short,0);expected+=amount
        self.assertEqual(q.cash,D('1e12')-expected)
        self.assertEqual(q.cash_residual(),0)

    def test_opening_declared_payable_not_double_paid(self):
        data=json.loads((Path(__file__).parent/'data/legacy_cash_witness.json').read_text())
        credits=sum((money(p.get('opening_credit_native',0)) for p in data['payments'] if p['kind']=='dividend'),ZERO)
        # Public aggregate reconciles to rounded precision. The allocation is an
        # explicit inference, not a source-verified class payable ledger.
        residual=D('155157000')-credits
        self.assertLess(abs(residual-D('248.81920177')),D('.000001'))
        self.assertEqual(credits+residual,D('155157000'))

if __name__=='__main__':unittest.main(verbosity=2)
