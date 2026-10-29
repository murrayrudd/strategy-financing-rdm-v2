"""Frozen, resumable technical experiments, separate from the original design."""
from pathlib import Path
from dataclasses import replace
from concurrent.futures import ProcessPoolExecutor, as_completed
import argparse, hashlib, json, os, time, traceback
from simulation import Simulation, D, Z, money, path_digest
from distribution_capacity import CapacitySimulation
from rdm_design import POLICIES, assumptions, future, external_path
from rdm_run import flatten, identity

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results/technical_revision'
NEW_MODES=('rolling_allowance','no_exogenous_allowance','net_asset_screen','net_asset_screen_20')
NAMES=('common_12m','dual_12m','capped_12m','retire_12m','retire_protected_12m')

def atomic(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(obj,default=float,separators=(',',':')))
    os.replace(tmp,path)

def selected():
    return json.loads((ROOT/'data/rdm_main.json').read_text())[::16]+json.loads((ROOT/'data/rdm_challenge.json').read_text())[::4]

def config():
    return {'version':'technical-review-1','source_model':identity(),
      'extension_hashes':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ('distribution_capacity.py','technical_experiments.py','funding_comparison.py')},
      'selection':'125 main futures at indices 0,16,...;128 challenge futures at indices 0,4,...; identical external paths within each comparison',
      'futures':[x['id'] for x in selected()], 'structures':['face','continuation'],
      'policies':list(NAMES),'new_capacity_modes':list(NEW_MODES),
      'planned_capacity_simulations':253*2*5*4,
      'interpretation':'Post-review sensitivity. Existing challenge cases have previously been examined; this is not a newly untouched validation set.',
      'legal_scope':'No automatic annual legal allowance was located. Annual and rolling allowances are institutional stress scenarios. Net-asset screens are financial proxies, not actual statutory surplus or a legal opinion.',
      'net_asset_screens':'Pre-distribution net-asset reference minus par-value floor and optional 20% Bitcoin valuation haircut; no net-profit alternative, board capital or special redemption capital-reduction exception inferred.',
      'funding_comparison':'Under no_exogenous_allowance, replay the common_12m reference gross issuance schedule with 0%,25%,50% STRC shares of financing; retain execution gates and whole-share rounding. Report reference survivors whose target financing is matched through evaluation or distress. An exact all-common replay checks event order; the reference is compared with capacity outputs. This offline mechanism comparison is not an implementable management policy.',
      'planned_funding_simulations':253*2*4,
      'freeze_rule':'Do not alter modes, sample, or screening to improve policy rankings. Preserve original core and results.'}

def capacity_one(x):
    try:
        path=external_path(x);digest=path_digest(path);rows=[]
        for mode in NEW_MODES:
            for structure in ('face','continuation'):
                for name in NAMES:
                    p=next(p for p in POLICIES if p.name==('retire_12m' if name=='retire_protected_12m' else name))
                    s=CapacitySimulation(future(x),p,assumptions(x,structure),external_path=path,external_digest=digest,
                       distribution_mode=mode,protect_preferred=name=='retire_protected_12m')
                    result=s.run()
                    assert abs(result['max_cash_reconciliation_residual'])<.01
                    for row in flatten(result,structure,0):
                        row.update(policy=name,distribution_mode=mode,screen_bindings=s.screen_bindings)
                        rows.append(row)
        return {'id':x['id'],'phase':x['phase'],'original_regime':x['legal_regime'],'rows':rows,'simulations':40}
    except Exception:
        return {'id':x['id'],'error':traceback.format_exc()}

def run(phase,workers=8,limit=None):
    OUT.mkdir(parents=True,exist_ok=True);cp=OUT/'protocol.json';c=config()
    if cp.exists():
        assert json.loads(cp.read_text())==c,'Experiment identity changed'
    else: atomic(cp,c)
    folder=OUT/'groups'/phase;folder.mkdir(parents=True,exist_ok=True)
    todo=[x for x in selected() if not (folder/(x['id']+'.json')).exists()]
    if limit is not None:todo=todo[:limit]
    if phase=='capacity':worker=capacity_one
    elif phase=='funding':
        from funding_comparison import funding_one
        worker=funding_one
    else:raise ValueError(phase)
    t=time.monotonic();done=len(list(folder.glob('*.json')));errors=[]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        tasks={pool.submit(worker,x):x['id'] for x in todo}
        for job in as_completed(tasks):
            r=job.result()
            if 'error' in r:
                errors.append(r);atomic(OUT/'errors'/(phase+'_'+r['id']+'.json'),r)
            else:atomic(folder/(r['id']+'.json'),r);done+=1
            status={'phase':phase,'complete_futures':done,'planned_futures':253,'errors':len(errors),'elapsed_seconds':round(time.monotonic()-t,1)}
            atomic(OUT/('progress_'+phase+'.json'),status)
            print(json.dumps(status),flush=True)
    if errors:raise RuntimeError(errors[0])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--phase',choices=['capacity','funding'],required=True);p.add_argument('--workers',type=int,default=8);p.add_argument('--limit',type=int)
    a=p.parse_args();run(a.phase,a.workers,a.limit)
