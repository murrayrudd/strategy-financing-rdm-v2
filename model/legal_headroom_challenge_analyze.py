"""Evaluate the declared refinement screen on the separate challenge futures."""
from pathlib import Path
import json,hashlib,time,argparse
import pandas as pd
ROOT=Path(__file__).resolve().parent

def main(wait=False):
    rd=ROOT/'results/rdm';raw=rd/'legal_headroom_challenge.jsonl';ident=rd/'legal_headroom_challenge_identity.json'
    while not (raw.exists() and ident.exists()):
        if not wait:raise FileNotFoundError(raw)
        time.sleep(10)
    out=ROOT/'results/analysis';out.mkdir(exist_ok=True)
    groups=[json.loads(s) for s in raw.open()];assert len(groups)==512
    variant=pd.DataFrame([{**r,'legal_regime':g['legal_regime']} for g in groups for r in g['rows']])
    base=pd.DataFrame([r for s in (rd/'challenge.jsonl').open() for r in json.loads(s)['rows']])
    measures=['cash_service','preferred_continuity','common_preservation','joint_success']
    def outcomes(g):return {o:{'original_successes':int(g[o+'_original'].sum()),'headroom_successes':int(g[o+'_headroom'].sum()),'rescued':int((g[o+'_headroom']&~g[o+'_original']).sum()),'lost':int((~g[o+'_headroom']&g[o+'_original']).sum())} for o in measures}
    pairs=variant.merge(base[base.policy=='retire_12m'],on=['id','horizon','structure','policy'],suffixes=('_headroom','_original'),validate='one_to_one');rows=[]
    for stratum in ['all','zero','finite','unlimited']:
        subset=pairs if stratum=='all' else pairs[pairs.legal_regime==stratum]
        for (h,structure),g in subset.groupby(['horizon','structure']):rows.append({'horizon':h,'structure':structure,'legal_regime':stratum,'n':len(g),**outcomes(g)})
    comparisons=[]
    for policy,g0 in base.groupby('policy'):
        paired=variant.drop(columns='policy').merge(g0,on=['id','horizon','structure'],suffixes=('_headroom','_original'),validate='one_to_one')
        for (h,structure),g in paired.groupby(['horizon','structure']):comparisons.append({'horizon':h,'structure':structure,'compared_with':policy,'n':len(g),**outcomes(g)})
    screened=[r for r in rows if r['horizon']=='2033-06-30' and r['legal_regime']=='all']
    for r in screened:r['declared_screen_pass']=r['preferred_continuity']['rescued']>r['preferred_continuity']['lost'] and r['cash_service']['lost']==0 and r['joint_success']['rescued']>r['joint_success']['lost']
    result={'status':'Prospective challenge test of a refinement developed after the main analysis; no tuning on challenge results','futures':512,'simulations':1024,
      'raw_sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'extension_sha256':hashlib.sha256((ROOT/'legal_headroom_sensitivity.py').read_bytes()).hexdigest(),
      'declared_screen_pass_both_valuations':all(r['declared_screen_pass'] for r in screened),'rows':rows,'comparisons_to_locked_policies':comparisons}
    (out/'legal_headroom_challenge_summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(screened,indent=2),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--wait',action='store_true');main(p.parse_args().wait)
