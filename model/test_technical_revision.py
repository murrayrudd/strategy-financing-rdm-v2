import json, unittest
from pathlib import Path
from dataclasses import replace
from datetime import date,timedelta
from distribution_capacity import CapacitySimulation
from simulation import Simulation,D,Z,FUTURES,Assumptions
from rdm_design import POLICIES,assumptions,future,external_path
from rdm_run import flatten
from funding_comparison import FundingReference,FundingReplay

ROOT=Path(__file__).resolve().parent

class TechnicalRevisionTests(unittest.TestCase):
    def make(self,mode='calendar_allowance',**kw):
        return CapacitySimulation(FUTURES[0],POLICIES[4],Assumptions(cash_legal_capacity_per_year=1e9),distribution_mode=mode,**kw)
    def test_calendar_preserves_core_numerical_results(self):
        x=json.loads((ROOT/'data/rdm_main.json').read_text())[16];path=external_path(x)
        for p in (POLICIES[4],POLICIES[7]):
            for v in ('face','continuation'):
                a=assumptions(x,v)
                one=Simulation(future(x),p,a,external_path=path).run()
                two=CapacitySimulation(future(x),p,a,external_path=path).run()
                self.assertEqual(flatten(one,v,0),flatten(two,v,0))
    def test_frozen_headroom_rule_is_preserved(self):
        from legal_headroom_sensitivity import HeadroomSimulation
        x=json.loads((ROOT/'data/rdm_challenge.json').read_text())[123];path=external_path(x);p=POLICIES[7];a=assumptions(x,'face')
        one=HeadroomSimulation(future(x),p,a,external_path=path).run()
        two=CapacitySimulation(future(x),p,a,external_path=path,protect_preferred=True).run()
        self.assertEqual(flatten(one,'face',0),flatten(two,'face',0))
    def test_rolling_does_not_replenish_at_year_boundary(self):
        s=self.make('rolling_allowance');s.day=date(2026,12,31)
        s.liq.pay(D('400000000'),'test',True)
        s.day=date(2027,1,1);s.liq.legal_budget=D('1000000000')
        self.assertEqual(s.refresh_capacity(),D('600000000'))
        s.day=date(2027,12,31)
        self.assertEqual(s.refresh_capacity(),D('1000000000'))
    def test_distribution_debits_but_debt_does_not_consume_allowance(self):
        s=self.make('rolling_allowance');s.day=date(2026,7,1)
        s.liq.pay(10,'debt');self.assertEqual(s.refresh_capacity(),D('1000000000'))
        s.liq.pay(20,'dividend',True);self.assertEqual(s.refresh_capacity(),D('999999980'))
    def test_net_asset_screen_responds_to_cash_and_price(self):
        s=self.make('net_asset_screen');before=s.refresh_capacity()
        s.liq.record(100,'cash_endowment')
        self.assertAlmostEqual(float(s.refresh_capacity()-before),100,places=5)
        before=s.refresh_capacity();s.pt=dict(s.pt,btc=s.pt['btc']-1)
        self.assertAlmostEqual(float(s.refresh_capacity()-before),-float(s.btc.units),places=4)
    def test_liquidation_preferences_are_not_statutory_capital(self):
        s=self.make('net_asset_screen');before=s.refresh_capacity()
        s.preferred_prices['STRF']=[D(150)]*10
        self.assertAlmostEqual(float(s.refresh_capacity()-before),0,places=4)
    def test_equity_issue_adds_assets_and_par_without_double_counting(self):
        s=self.make('net_asset_screen');before=s.refresh_capacity()
        s.issue('STRC',D('1000000'));o=s.pending[-1]
        self.assertAlmostEqual(float(s.refresh_capacity()-before),float(o['net']-o['shares']*D('.001')),places=3)
    def test_haircut_is_explicit_and_material(self):
        a=self.make('net_asset_screen');b=self.make('net_asset_screen_20')
        self.assertAlmostEqual(float(a.refresh_capacity()-b.refresh_capacity()),float(a.btc.units*a.pt['btc']*D('.2')),places=2)
    def test_rejected_retirement_is_not_logged_as_notice(self):
        s=self.make(keep_ledger=True);s.log('STRC_redemption_notice',shares=D(10),redemption='2026-07-07')
        self.assertEqual(s.events[-1]['kind'],'STRC_redemption_proposal_blocked')
    def test_funding_replay_matches_reference_exactly(self):
        x=json.loads((ROOT/'data/rdm_main.json').read_text())[16];path=external_path(x);p=POLICIES[4];a=assumptions(x,'continuation')
        ref=FundingReference(future(x),p,a,external_path=path,distribution_mode='no_exogenous_allowance');r=ref.run()
        replay=FundingReplay(future(x),p,a,external_path=path,distribution_mode='no_exogenous_allowance',funding_plan=ref.funding_plan);s=replay.run()
        self.assertEqual(flatten(r,'continuation',0),flatten(s,'continuation',0))
    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(ValueError):self.make('legal_exact')

if __name__=='__main__':unittest.main()
