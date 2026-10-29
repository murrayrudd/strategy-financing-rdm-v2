"""Supplementary carrying-return sensitivity; no change to the main protocol."""
from pathlib import Path
import json,hashlib
import pandas as pd
ROOT=Path(__file__).resolve().parent

def main():
    rd=ROOT/'results/rdm';out=ROOT/'results/analysis';groups=[json.loads(s) for s in (rd/'carry.jsonl').open()]
    assert len(groups)==64 and len({(g['id'],g['net_yield']) for g in groups})==64
    carry=pd.DataFrame([{**r,'net_yield':g['net_yield']} for g in groups for r in g['rows']])
    base=pd.DataFrame([r for s in (rd/'main.jsonl').open() for r in json.loads(s)['rows']])
    keys=['id','policy','structure','horizon'];paired=carry.merge(base,on=keys,suffixes=('_carry','_base'),validate='many_to_one');summary=[]
    for k,g in paired.groupby(['net_yield','horizon','structure','policy']):
        survivors=g[g.cash_service_carry & g.cash_service_base];change=survivors.common_backing_per_share_carry-survivors.common_backing_per_share_base
        summary.append({**dict(zip(['net_yield','horizon','structure','policy'],k)),'n':len(g),'both_survive':len(survivors),
          'median_backing_change_usd_per_share':float(change.median()) if len(change) else None,
          **{o:{'rescued':int((g[o+'_carry']&~g[o+'_base']).sum()),'lost':int((~g[o+'_carry']&g[o+'_base']).sum())} for o in ['cash_service','preferred_continuity','common_preservation','joint_success']}})
    result={'selection':'Every sixty-fourth main future; 32 futures, two yields, 16 comparisons','simulations':1024,
      'interpretation':'Supplementary finite sensitivity, not a sampled yield probability model or observed Treasury schedule. Net returns credited daily to settled liquid assets; pending and restricted assets excluded.',
      'extension_sha256':hashlib.sha256((ROOT/'carry_sensitivity.py').read_bytes()).hexdigest(),
      'raw_sha256':hashlib.sha256((rd/'carry.jsonl').read_bytes()).hexdigest(),'rows':summary}
    (out/'carry_sensitivity_summary.json').write_text(json.dumps(result,indent=2));print('Carry analysis complete')
if __name__=='__main__':main()
