"""Prospective challenge evaluation of the frozen headroom refinement.

Specified after the main-set mechanism diagnostic, before examining challenge
outcome summaries. The refinement is unchanged; no parameter or threshold tuning.
"""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import json,hashlib,os,argparse,time
from legal_headroom_sensitivity import one
from durable_run import atomic
from rdm_run import identity
ROOT=Path(__file__).resolve().parent

def main(work,workers=2):
    work=Path(work);work.mkdir(parents=True,exist_ok=True);folder=work/'groups';folder.mkdir(exist_ok=True)
    config={'model':identity(),'extension_sha256':hashlib.sha256((ROOT/'legal_headroom_sensitivity.py').read_bytes()).hexdigest(),
      'validation_runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
      'challenge_design_sha256':hashlib.sha256((ROOT/'data/rdm_challenge.json').read_bytes()).hexdigest(),
      'timing':'Refinement frozen after 125-main-future mechanism diagnostic and before inspecting challenge outcomes. Reuses all 512 pre-generated challenge futures without changing their inputs.',
      'futures':512,'simulations':1024,
      'screen':'At June 2033, under each valuation: preferred-continuity rescues exceed losses; no paired cash-service losses; joint-success rescues exceed losses. All separate outcomes and losses are still reported.'}
    ip=work/'identity.json'
    if ip.exists():assert json.loads(ip.read_text())==config
    else:atomic(ip,config)
    declaration=ROOT/'audit/legal_headroom_validation_declaration.json'
    if not declaration.exists():atomic(declaration,{'locked_epoch':time.time(),**config})
    xs=json.loads((ROOT/'data/rdm_challenge.json').read_text());todo=[x for x in xs if not (folder/(x['id']+'.json')).exists()];errors=[]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for answer in pool.map(one,todo,chunksize=1):
            if 'error' in answer:errors.append(answer)
            else:atomic(folder/(answer['id']+'.json'),answer)
    assert not errors,errors[:1]
    rows=[json.loads(p.read_text()) for p in sorted(folder.glob('*.json'))];assert len(rows)==512
    base={json.loads(s)['id']:json.loads(s) for s in (ROOT/'results/rdm/challenge.jsonl').open()};assert len(base)==512
    matched=0
    for g in rows:
        for v in g['rows']:
            b=next(r for r in base[g['id']]['rows'] if r['policy']==v['policy'] and r['structure']==v['structure'] and r['horizon']==v['horizon'])
            assert v['path_sha256']==b['path_sha256']
            if g['legal_regime']=='unlimited':assert v==b;matched+=1
    config['unlimited_regime_exact_endpoint_matches']=matched
    raw=work/'legal_headroom_challenge.jsonl';raw.write_text(''.join(json.dumps(r,separators=(',',':'))+'\n' for r in rows))
    atomic(work/'legal_headroom_challenge_identity.json',config)
    target=ROOT/'results/rdm';os.replace(raw,target/raw.name);os.replace(work/'legal_headroom_challenge_identity.json',target/'legal_headroom_challenge_identity.json')
    print('LEGAL_HEADROOM_CHALLENGE_COMPLETE',matched,'exact unlimited-regime endpoint controls',flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--work',required=True);p.add_argument('--workers',type=int,default=2);a=p.parse_args();main(a.work,a.workers)
