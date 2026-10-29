import unittest
from dataclasses import replace
from datetime import date
from simulation import *
from valuation import residual_reference

class ReviewTests(unittest.TestCase):
    def sim(self,**kw):return Simulation(FUTURES[0],POLICIES[0],Assumptions(**kw))
    def test_both_structures_preserve_published_opening_quote(self):
        for mode in ('face','continuation'):
            for vol in (.35,.65,1.):
                s=self.sim(common_valuation=mode,reference_volatility=vol)
                self.assertAlmostEqual(float(s.quote()),86.93,places=10)
    def test_cash_intervention_does_not_recalibrate_quote(self):
        for mode in ('face','continuation'):
            a=self.sim(common_valuation=mode);b=self.sim(common_valuation=mode,initial_cash_increment=1e8)
            self.assertEqual(a.quote_scale,b.quote_scale)
            self.assertGreater(b.quote(),a.quote())
    def test_pending_issuance_delivery_does_not_manufacture_value(self):
        for k in ('MSTR','STRC'):
            for mode in ('face','continuation'):
                s=self.sim(common_valuation=mode);s.day=date(2026,7,1);s.pt=s.path[s.day]
                s.issue(k,D(1e7));q=s.quote();w=s.backing();n=s.economic_common()
                for o in s.pending:o['due']=s.day
                s.settle_pending()
                self.assertLess(abs(s.quote()-q),D('.00000001'));self.assertEqual(s.economic_common(),n)
                self.assertLess(abs(s.backing()-w),D('.000001'))
    def test_pending_strk_delivery_preserves_denominator(self):
        s=self.sim();s.pending.append({'kind':'STRK_conversion','shares':D(1000),'due':START})
        q=s.quote();s.settle_pending();self.assertEqual(s.quote(),q)
    def test_taxes_offset_pending_receipts_before_cash_available(self):
        s=self.sim();s.liq.cash=D(10);s.liq.tax_reserved=D(30)
        s.liq.pending=[(START,D(25),'sale')]
        self.assertEqual(s.projected_cash(),D(5))
    def debt_only(self):
        s=self.sim();s.sched=[];s.other=Z;s.future=replace(s.future,annual_operating_cashflow=0)
        s.debt={k:Z for k in s.debt};s.debt['2028']=D(1000)
        s.day=date(2027,9,2);s.pt=s.path[s.day];s.coupon_records[('2028',2027,9)]=D(1000)
        return s
    def test_no_coupons_after_full_put(self):
        s=self.debt_only();self.assertEqual(s.needed(370),D('1003.125'))
    def test_partial_put_retains_only_remaining_future_coupons(self):
        s=self.debt_only();s.debt['2028']=D(2000);s.coupon_records[('2028',2027,9)]=D(2000)
        s.a=replace(s.a,put_fraction=.5)
        self.assertEqual(s.needed(380),D('2012.500'))
    def test_record_coupon_survives_pending_conversion(self):
        s=self.debt_only();s.conversions['2028']={'principal':D(1000),'method':'physical','settle':date(2027,9,7)}
        self.assertEqual(s.needed(30),D('3.125'));self.assertEqual(s.debt_accrued(),D('3.125'))
    def test_holiday_coupon_remains_accrued_until_payment(self):
        s=self.debt_only();s.day=date(2029,9,15);s.coupon_records={('2028',2029,9):D(1000)}
        self.assertEqual(s.debt_accrued(),D('3.125'))
    def test_call_conversion_deadline_precedes_redemption(self):
        s=self.sim();red=date(2027,5,17);s.calls['2028']={'redemption':red}
        self.assertEqual(s.conversion_deadline('2028'),date(2027,5,13))
    def test_pending_preferred_consumes_cap(self):
        s=self.sim();s.policy=replace(s.policy,preferred_asset_cap=.30)
        s.issue('STRC',D(6e9));first=s.gross_issued['STRC'];s.issue('STRC',D(6e9))
        self.assertLessEqual(s.gross_issued['STRC']-first,D(100))
    def test_lp_activation_and_trade_window(self):
        s=self.sim();s.preferred_prices={k:[D(110)]*9+[D(130)] for k in ORDER}
        self.assertEqual(s.lp('STRE'),D(100));self.assertEqual(s.lp('STRF'),D(112))
        s.strc_issue_days=[s.day];self.assertEqual(s.lp('STRC'),D(130))
    def test_zero_observation_limit_is_defined(self):
        for mode in ('cash','combination'):
            r=conversion_settlement(1000,10,mode,[0]*20)
            self.assertEqual(r['cash'],0);self.assertEqual(r['shares'],0)
        with self.assertRaises(ValueError):conversion_settlement(1000,10,'cash',[-1]*20)
    def test_current_close_excluded_from_preference(self):
        s=self.sim();s.preferred_prices['STRF']=[D(110)]*10+[D(200)];s.latest_preferred_close=s.day
        self.assertEqual(s.lp('STRF'),D(110))
    def test_reserve_forecast_extends_past_reporting_endpoint(self):
        s=self.sim();s.day=END;s.pt=s.path[END]
        self.assertGreater(s.needed(365),D('1000000000'))
    def test_reporting_horizon_does_not_change_prefix(self):
        a=Simulation(FUTURES[0],POLICIES[1],end=date(2031,6,30)).run()
        b=Simulation(FUTURES[0],POLICIES[1]).run()
        self.assertEqual(a['snapshots']['2031-06-30'],b['snapshots']['2031-06-30'])
    def test_reference_bounds(self):
        self.assertEqual(residual_reference(100,50,0,3),50)
        self.assertEqual(residual_reference(100,-10,.65,3),110)
        self.assertGreater(residual_reference(100,150,.65,3),0)
        self.assertLessEqual(residual_reference(100,150,.65,3),100)
    def test_cash_running_total_matches_independent_journal_sum(self):
        s=self.sim();s.end=date(2027,6,30);s.run()
        self.assertEqual(s.liq.cash_changes,sum((e['cash_change'] for e in s.liq.ledger),Z))
    def test_zero_carry_matches_core_and_positive_carry_uses_settled_assets(self):
        from carry_sensitivity import CarrySimulation
        a=Simulation(FUTURES[0],POLICIES[1],end=date(2027,6,30)).run()
        b=CarrySimulation(FUTURES[0],POLICIES[1],end=date(2027,6,30),net_yield=0).run()
        self.assertEqual(a,b)
        s=CarrySimulation(FUTURES[0],POLICIES[1],net_yield=.05)
        before=s.liq.cash;expected=(s.liq.cash+s.liq.treasury)*s.net_daily_return
        s.day=date(2026,7,1);s.settle_pending();self.assertEqual(s.liq.cash-before,expected)
        s.settle_pending();self.assertEqual(s.liq.cash-before,expected)

if __name__=='__main__':unittest.main()
