"""Select an illustrative matched case by a declared median-spread rule."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parent

def main():
    rd=ROOT/'results/rdm';out=ROOT/'results/analysis';domain=json.loads((out/'marginal_cash_common_domain.json').read_text())
    ids=next(r['future_ids'] for r in domain if r['horizon']=='2033-06-30');base={json.loads(s)['id']:json.loads(s) for s in (rd/'main.jsonl').open()};extra={json.loads(s)['id']:json.loads(s) for s in (rd/'cash.jsonl').open()}
    def row(g,policy):return next(v for v in g['rows'] if v['horizon']=='2033-06-30' and v['structure']=='continuation' and v['policy']==policy)
    candidates=[]
    for ident in ids:
        effects={p:(row(extra[ident],p)['common_backing_per_share']-row(base[ident],p)['common_backing_per_share'])*371603000/1e8 for p in ('common_12m','retire_12m')}
        candidates.append((abs(effects['retire_12m']-effects['common_12m']),ident,effects))
    if not candidates:result={'status':'No common survivor domain; no witness selected'}
    else:
        spread,ident,effects=sorted(candidates)[len(candidates)//2];rows=[]
        for p in ('common_12m','retire_12m'):
            a,b=row(base[ident],p),row(extra[ident],p)
            rows.append({'policy':p,'finite_backing_gain_per_extra_dollar':effects[p],
              'changes':{k:b[k]-a[k] for k in ['Bitcoin_units','common_shares','STRC_shares','cash_usd','common_backing_per_share','debt_principal_usd']},
              'flow_changes':{k:b['metrics'][k]-a['metrics'][k] for k in a['metrics']},'base':a,'extra_cash':b})
        result={'status':'Illustrative matched case; not a representative forecast','selection':'Median absolute difference between common_12m and retire_12m cash effects, among the common survival domain; ties sorted by future ID','id':ident,'structure':'continuation','horizon':'2033-06-30','domain_futures':len(candidates),'absolute_cash_effect_spread':spread,'features':base[ident]['features'],'comparisons':rows}
    (out/'cash_mechanism_witness.json').write_text(json.dumps(result,indent=2));print(result.get('id',result['status']))
if __name__=='__main__':main()
