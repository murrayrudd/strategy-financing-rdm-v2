"""Local payment-boundary probe; no global monotonicity or probability claim."""
from concurrent.futures import ProcessPoolExecutor,as_completed
from dataclasses import replace
import json
from simulation import *

def task(policy):
    runs=[];rows=[]
    variants=[Assumptions(),Assumptions(name='loan_late_low_rate',other_loan_repayment='2027-06-30',other_loan_rate=.052),
       Assumptions(name='loan_late_high_rate',other_loan_repayment='2027-06-30',other_loan_rate=.15)]
    for a in variants:
        def evaluate(cagr):
            f=Future('local_boundary',cagr,.75,.45,2.,.8,.5,.75,3.,.12,.02,8.,1.1,-1e8)
            v=Simulation(f,policy,a).run()['terminal']
            passes=v['debt_shortfall'] is None and v['operating_shortfall'] is None and v['date']==str(END)
            runs.append({'policy':policy.name,'variant':a.name,'cagr':cagr,'payment_feasible_to_2033':passes,
                'terminal_date':v['date'],'preferred_suspension':v['preferred_suspension'],'debt_shortfall':v['debt_shortfall'],
                'operating_shortfall':v['operating_shortfall'],'common_backing_per_share':v['common_backing_per_share']})
            return passes
        grid=[-.4,-.3,-.2,-.1,0,.1,.2];ok=[evaluate(c) for c in grid];monotone=ok==sorted(ok)
        intervals=[(grid[i],grid[i+1]) for i in range(len(grid)-1) if not ok[i] and ok[i+1]]
        if monotone and len(intervals)==1:
            low,high=intervals[0]
            for _ in range(9):
                mid=(low+high)/2
                if evaluate(mid):high=mid
                else:low=mid
            rows.append({'policy':policy.name,'variant':a.name,'coarse_monotone':True,'failure_cagr':low,'feasible_cagr':high,'bracket_width':high-low})
        else:rows.append({'policy':policy.name,'variant':a.name,'coarse_monotone':monotone,'coarse_results':ok,'status':'no unique bracket; no bisection claim'})
    return rows,runs

def main():
    rows=[];runs=[]
    with ProcessPoolExecutor(max_workers=2) as pool:
        for job in as_completed([pool.submit(task,p) for p in POLICIES]):
            rr,ss=job.result();rows.extend(rr);runs.extend(ss);print('Boundary policy complete',rr[0]['policy'],flush=True)
    out={'scope':'Local CAGR slice with identical non-CAGR inputs; no global monotonicity claim.',
         'rows':rows,'runs':runs,'simulation_count':len(runs)}
    (ROOT/'results/loan_boundary_sensitivity.json').write_text(json.dumps(out,indent=2,default=str))
    print(json.dumps(rows,indent=2))
if __name__=='__main__':main()
