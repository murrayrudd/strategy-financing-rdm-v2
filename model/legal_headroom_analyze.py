"""Report the post-hoc legal-headroom diagnostic separately from core RDM."""
from pathlib import Path
import json,hashlib
import pandas as pd
ROOT=Path(__file__).resolve().parent

def main():
    rd=ROOT/'results/rdm';out=ROOT/'results/analysis';out.mkdir(exist_ok=True)
    groups=[json.loads(s) for s in (rd/'legal_headroom.jsonl').open()];assert len(groups)==125
    variant=pd.DataFrame([{**r,'legal_regime':g['legal_regime']} for g in groups for r in g['rows']]);base=pd.DataFrame([r for s in (rd/'main.jsonl').open() for r in json.loads(s)['rows'] if r['policy']=='retire_12m'])
    keys=['id','horizon','structure','policy'];pairs=variant.merge(base,on=keys,suffixes=('_headroom','_original'),validate='one_to_one');rows=[]
    for stratum in ['all','zero','finite','unlimited']:
        subset=pairs if stratum=='all' else pairs[pairs.legal_regime==stratum]
        for (h,structure),g in subset.groupby(['horizon','structure']):
            rows.append({'horizon':h,'structure':structure,'legal_regime':stratum,'n':len(g),
             **{o:{'original_successes':int(g[o+'_original'].sum()),'headroom_successes':int(g[o+'_headroom'].sum()),'rescued':int((g[o+'_headroom']&~g[o+'_original']).sum()),'lost':int((~g[o+'_headroom']&g[o+'_original']).sum())} for o in ['cash_service','preferred_continuity','common_preservation','joint_success']}})
    result={'status':'Post-hoc mechanism diagnostic; not part of the locked eight-policy ranking or independent validation','futures':125,'simulations':250,
      'extension_sha256':hashlib.sha256((ROOT/'legal_headroom_sensitivity.py').read_bytes()).hexdigest(),
      'raw_sha256':hashlib.sha256((rd/'legal_headroom.jsonl').read_bytes()).hexdigest(),'rows':rows}
    (out/'legal_headroom_summary.json').write_text(json.dumps(result,indent=2));print(json.dumps([r for r in rows if r['horizon']=='2033-06-30' and r['legal_regime']=='all'],indent=2))
if __name__=='__main__':main()
