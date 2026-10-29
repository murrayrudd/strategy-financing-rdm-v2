"""Post-diagnostic traces of cash effects that remain negative after flooring."""
import json,gzip
from technical_traces import trace,compare,ROOT,OUT,atomic

def main():
    x=json.loads((OUT/'cash_metric_diagnostics.json').read_text())
    candidates=[r for r in x['negative_raw_cases'] if r['horizon']=='2033-06-30'
                and r['floored_change_per_extra_dollar']<0]
    candidates.sort(key=lambda r:(r['floored_change_per_extra_dollar'],r['id'],r['structure'],r['policy']))
    chosen=[candidates[len(candidates)//2],candidates[0]]
    atomic(OUT/'supplementary_trace_selection.json',{
        'rule':'After detecting signed-residual effects, select the median and most negative 2033 cash-effect records that remain negative after applying a zero floor to common residual backing. This is diagnostic selection, not validation.',
        'eligible_records':len(candidates),'selected':chosen})
    xs={r['id']:r for r in json.loads((ROOT/'data/rdm_main.json').read_text())}
    pairs=[]
    for case in chosen:
        fid,v,p=case['id'],case['structure'],case['policy'];runs=[]
        for cash in (0,1e8):
            r=trace(xs[fid],v,p,cash)
            name=f'{fid}_{v}_{p}_cash{int(cash)}_protected0.json.gz'
            with gzip.open(OUT/'traces'/name,'wt') as f:json.dump(r,f,separators=(',',':'))
            runs.append(r)
        pair=compare(*runs)
        pairs.append({'type':'negative_floored_cash_effect','id':fid,'structure':v,'policy':p,
                      'effect':case['floored_change_per_extra_dollar'],**pair})
    atomic(OUT/'supplementary_trace_summary.json',{'simulations':len(chosen)*2,'comparisons':pairs})
    print(json.dumps({'simulations':len(chosen)*2,'cases':chosen}))

if __name__=='__main__':main()
