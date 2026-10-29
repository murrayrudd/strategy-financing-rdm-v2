"""Explicit distribution screens for the technical revision.

These are scenario screens, NOT estimates or certifications of lawful funds.
The inherited annual allowance is retained only as a named legacy stress rule.
Debt, contractual priorities, settlement, and cash availability stay in the core.
"""
from collections import deque
from datetime import timedelta, date
from simulation import Simulation, D, Z, money

MODES = ('calendar_allowance', 'rolling_allowance', 'no_exogenous_allowance',
         'net_asset_screen', 'net_asset_screen_20')

class CapacitySimulation(Simulation):
    def __init__(self, *args, distribution_mode='calendar_allowance',
                 protect_preferred=False, capital_buffer=0, **kwargs):
        if distribution_mode not in MODES:
            raise ValueError('Unknown distribution mode')
        self.distribution_mode = distribution_mode
        self.protect_preferred = protect_preferred
        self.capital_buffer = money(capital_buffer)
        if self.capital_buffer < 0:
            raise ValueError('Negative capital buffer')
        self.distribution_history = deque()
        self.distribution_total = Z
        self.screen_bindings = 0
        self.screen_minimum = D('1e30')
        self.trace_states = []
        super().__init__(*args, **kwargs)
        original_pay = self.liq.pay
        def pay(amount, kind, distribution=False):
            if distribution:
                self.refresh_capacity()
                if money(amount) > self.liq.legal_budget:
                    self.screen_bindings += 1
            paid, short = original_pay(amount, kind, distribution)
            if distribution and paid:
                self.distribution_history.append((self.day, paid))
                self.distribution_total += paid
            return paid, short
        self.liq.pay = pay
        self.refresh_capacity()

    def net_asset_screen(self):
        # Remove preferred equity claims and dividend accruals from the common
        # residual to recover a pre-distribution financial net-asset reference.
        # This is NOT DGCL statutory surplus: board valuation, actual capital,
        # declared-dividend legal treatment and net-profit alternatives differ.
        faces = sum((p.shares*self.lp(k)*self.fx(k) for k,p in self.pref.items()), Z)
        faces += sum((o['shares']*self.lp('STRC') for o in self.pending if o['kind']=='STRC'), Z)
        net_assets = (self.backing()+faces+self.due_arrears_usd()
                      +self.opening_credit+self.accrued_undue())
        par_floor = D('.001')*(self.economic_common()+sum((p.shares*self.fx(k) for k,p in self.pref.items()),Z)
                     +sum((o['shares'] for o in self.pending if o['kind']=='STRC'),Z))
        bitcoin_value = (self.btc.units+sum((o.get('units',Z) for o in self.pending if o['kind']=='BTC_buy'),Z))*self.pt['btc']
        haircut = D('.20') if self.distribution_mode=='net_asset_screen_20' else Z
        return max(Z, net_assets-par_floor-self.capital_buffer-haircut*bitcoin_value)

    def refresh_capacity(self):
        mode = self.distribution_mode
        if mode=='rolling_allowance':
            cutoff=self.day-timedelta(days=365)
            while self.distribution_history and self.distribution_history[0][0]<=cutoff:
                self.distribution_total -= self.distribution_history.popleft()[1]
            self.liq.legal_budget=max(Z,money(self.a.cash_legal_capacity_per_year)-self.distribution_total)
        elif mode=='no_exogenous_allowance':
            self.liq.legal_budget=D('1e30')
        elif mode.startswith('net_asset_screen'):
            self.liq.legal_budget=self.net_asset_screen()
        self.screen_minimum=min(self.screen_minimum,self.liq.legal_budget)
        return self.liq.legal_budget

    def protected_amount(self):
        amount=self.due_arrears_usd()
        for e in self.funding_schedule:
            if self.day<e['pay']<=date(self.day.year,12,31) and e['nominal']>self.day:
                amount+=(self.records[e['id']] if e['id'] in self.records else self.expected_regular(e))*self.fx(e['ticker'])
        return amount

    def pref_nominal(self):
        self.refresh_capacity()
        super().pref_nominal()

    def pay_preferences(self):
        self.refresh_capacity()
        super().pay_preferences()

    def execute_redemption(self, order):
        self.refresh_capacity()
        super().execute_redemption(order)

    def finance(self):
        self.refresh_capacity()
        original=self.liq.legal_budget
        if self.protect_preferred:
            assert self.a.equity_settlement_days>0 and self.a.asset_settlement_days>0
            self.liq.legal_budget=max(Z,original-self.protected_amount())
        try:
            super().finance()
        finally:
            self.liq.legal_budget=original
            self.refresh_capacity()

    def log(self, kind, **kw):
        # The inherited logger marked a rejected proposal as a notice. Distinguish
        # rejected proposals without changing any numerical decision or balance.
        if kind=='STRC_redemption_notice' and not any(
            o['kind']=='STRC_redemption' and o.get('notice')==str(self.day)
            and o['shares']==kw.get('shares') for o in self.pending):
            kind='STRC_redemption_proposal_blocked'
        super().log(kind,**kw)

    def record(self, day):
        super().record(day)
        if self.keep_ledger:
            self.trace_states.append({
                'date':str(day),'cash':float(self.liq.cash),'usable_cash':float(self.liq.usable),
                'treasuries':float(self.liq.treasury),'restricted_cash':float(self.liq.restricted),
                'tax_reserved':float(self.liq.tax_reserved),'distribution_screen':float(self.liq.legal_budget),
                'Bitcoin_units':float(self.btc.units),'common_shares':float(self.economic_common()),
                'backing':float(self.backing()),'STRC_shares':float(self.pref['STRC'].shares),
                'arrears':float(self.due_arrears_usd()),
                'pending_receipts':float(sum((v for _,v,_ in self.liq.pending),Z)+sum((o.get('net',Z) for o in self.pending),Z)),
                'metrics':{k:float(v) for k,v in self.metrics.items()}})

