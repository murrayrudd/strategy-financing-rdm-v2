"""Check the two remaining-negative witnesses under the new capacity screens.

Post-review mechanism checks only. No case reselection or policy tuning.
"""
from pathlib import Path
import json
from simulation import OPEN
from rdm_design import POLICIES,assumptions,future,external_path
from distribution_capacity import CapacitySimulation
from rdm_run import flatten
from technical_experiments import ROOT,OUT,atomic

def main():
    selection=json.loads((OUT/'supplementary_trace_selection.json').read_text())
    xs={x['id']:x for x in json.loads((ROOT/'data/rdm_main.json').read_text())}
    modes=['rolling_allowance','no_exogenous_allowance','net_asset_screen_20']
    atomic(OUT/'cash_screen_check_protocol.json',{'cases':selection['selected'],'modes':modes,
        'selection':'The same median and largest remaining negative cash-effect witnesses; no reselection.',
        'planned_simulations':12,'purpose':'Determine whether these two diagnosed cash effects persist under different distribution screens; not a new population-level result.'})
    out=[]
    for c in selection['selected']:
        x=xs[c['id']];path=external_path(x);p=next(z for z in POLICIES if z.name==c['policy'])
        for mode in modes:
            rows=[]
            for cash in (0,1e8):
                r=CapacitySimulation(future(x),p,assumptions(x,c['structure'],cash),external_path=path,
                    distribution_mode=mode).run()
                assert abs(r['max_cash_reconciliation_residual'])<.01
                rows.append(next(z for z in flatten(r,c['structure'],cash) if z['horizon']=='2033-06-30'))
            b,t=rows;both=b['cash_service'] and t['cash_service']
            effect=(max(0,float(t['common_backing_per_share']))-max(0,float(b['common_backing_per_share'])))*OPEN['basic_common_shares_rounded']/1e8 if both else None
            out.append({'id':x['id'],'policy':p.name,'structure':c['structure'],'mode':mode,
                'base_cash_service':b['cash_service'],'extra_cash_service':t['cash_service'],
                'floored_effect_per_extra_dollar':effect,'baseline':b,'extra_cash':t})
    atomic(OUT/'cash_screen_checks.json',{'simulations':12,'comparisons':out})
    print(json.dumps([{k:v for k,v in r.items() if k not in ('baseline','extra_cash')} for r in out],indent=2))

if __name__=='__main__':main()
