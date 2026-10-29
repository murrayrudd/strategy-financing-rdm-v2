"""Analyze only complete, identity-matched technical comparison groups."""
from pathlib import Path
from collections import defaultdict
import json,csv,statistics,hashlib
from technical_experiments import OUT,ROOT,selected,config,atomic,NAMES

OUTCOMES=('cash_service','preferred_continuity','common_preservation','joint_success')

def records(phase):
    files=sorted((OUT/'groups'/phase).glob('*.json'))
    groups=[json.loads(p.read_text()) for p in files]
    assert {x['id'] for x in groups}=={x['id'] for x in selected()},(phase,len(groups))
    return groups

def original_rows():
    ids={x['id'] for x in selected()};rows=[]
    for phase in ('main','challenge'):
        for line in (ROOT/f'results/rdm/{phase}.jsonl').open():
            g=json.loads(line)
            if g['id'] not in ids:continue
            for r in g['rows']:
                if r['policy'] in NAMES:
                    rows.append(dict(r,phase=phase,distribution_mode='calendar_allowance',original_regime=g['features']['legal_regime']))
    for phase,name in [('main','legal_headroom'),('challenge','legal_headroom_challenge')]:
        for line in (ROOT/f'results/rdm/{name}.jsonl').open():
            g=json.loads(line)
            if g['id'] not in ids:continue
            for r in g['rows']:
                rows.append(dict(r,phase=phase,policy='retire_protected_12m',distribution_mode='calendar_allowance',original_regime=g['legal_regime']))
    return rows

def count_summary(rows,fields):
    groups=defaultdict(list)
    for r in rows:groups[tuple(r[k] for k in fields)].append(r)
    out=[]
    for key,rs in sorted(groups.items()):
        item=dict(zip(fields,key));item['n']=len(rs)
        item.update({k:sum(r[k] for r in rs) for k in OUTCOMES})
        item['median_common_gross']=statistics.median(r['metrics']['common_gross'] for r in rs)
        item['median_STRC_gross']=statistics.median(r['metrics']['strc_gross'] for r in rs)
        out.append(item)
    return out

def paired(rows,comparison_field,reference,group_fields):
    groups=defaultdict(dict)
    for r in rows:
        groups[tuple(r[k] for k in group_fields)].setdefault(r[comparison_field],{})[r['id']]=r
    out=[]
    for key,g in sorted(groups.items()):
        base=g[reference]
        for alternative,byid in sorted(g.items()):
            if alternative==reference:continue
            assert set(base)==set(byid)
            item=dict(zip(group_fields,key),reference=reference,alternative=alternative,n=len(base))
            for metric in OUTCOMES:
                item[metric]={'reference_successes':sum(r[metric] for r in base.values()),
                    'alternative_successes':sum(r[metric] for r in byid.values()),
                    'gains':sum(not base[i][metric] and byid[i][metric] for i in base),
                    'losses':sum(base[i][metric] and not byid[i][metric] for i in base)}
            common=[i for i in base if base[i]['cash_service'] and byid[i]['cash_service']]
            item['paired_survivors']=len(common)
            item['median_backing_difference_per_share']=statistics.median(byid[i]['common_backing_per_share']-base[i]['common_backing_per_share'] for i in common) if common else None
            out.append(item)
    return out

def capacity_regret(rows):
    """Keep the future set constant across screens and valuation mechanisms."""
    import numpy as np
    result=[]
    for phase in ('main','challenge'):
        for horizon in ('2031-06-30','2033-06-30'):
            rs=[r for r in rows if r['phase']==phase and r['horizon']==horizon]
            byid=defaultdict(list)
            for r in rs:byid[r['id']].append(r)
            assert all(len(z)==50 for z in byid.values())
            ids={i for i,z in byid.items() if all(r['cash_service'] for r in z)}
            for mode in sorted({r['distribution_mode'] for r in rs}):
                for structure in ('face','continuation'):
                    values=defaultdict(dict)
                    for r in rs:
                        if r['id'] in ids and r['distribution_mode']==mode and r['structure']==structure:
                            values[r['id']][r['policy']]=r['common_backing_per_share']
                    for policy in NAMES:
                        raw=[max(v.values())-v[policy] for v in values.values()]
                        floor=[max(0.,max(v.values()))-max(0.,v[policy]) for v in values.values()]
                        assert all(0<=b<=a+1e-8 for a,b in zip(raw,floor))
                        result.append({'phase':phase,'horizon':horizon,'distribution_mode':mode,
                            'structure':structure,'policy':policy,'n':len(ids),'future_ids':sorted(ids),
                            'domain':'Same futures surviving under all five 12-month candidates, all five capacity screens and both valuation mechanisms; cash failures are reported separately.',
                            'raw_median_regret_per_share':float(np.median(raw)) if raw else None,
                            'floored_median_regret_per_share':float(np.median(floor)) if floor else None,
                            'floored_p90_regret_per_share':float(np.quantile(floor,.9)) if floor else None,
                            'floored_max_regret_per_share':max(floor) if floor else None})
    return result

def main():
    assert json.loads((OUT/'protocol.json').read_text())==config()
    cg=records('capacity');fg=records('funding')
    rows=original_rows()
    for g in cg:
        assert len(g['rows'])==80
        rows.extend(dict(r,phase=g['phase'],original_regime=g['original_regime']) for r in g['rows'])
    # Verify each fixed external path and the common funding reference across
    # independent experiment implementations.
    idx={(r['id'],r['structure'],r['horizon'],r['distribution_mode'],r['policy']):r for r in rows}
    references=0
    for g in fg:
        for r in g['rows']:
            if r['policy']!='replay_STRC_0pct':continue
            b=idx[(r['id'],r['structure'],r['horizon'],'no_exogenous_allowance','common_12m')]
            for key in ('path_sha256',*OUTCOMES,'common_backing_per_share','cash_usd','metrics'):
                assert r[key]==b[key],(r['id'],key)
            references+=1
    for k in {(r['id'],r['structure'],r['horizon']) for r in rows}:
        digests={r['path_sha256'] for r in rows if (r['id'],r['structure'],r['horizon'])==k}
        assert len(digests)==1
    counts=count_summary(rows,['phase','distribution_mode','structure','horizon','policy'])
    strata=count_summary(rows,['phase','original_regime','distribution_mode','structure','horizon','policy'])
    policy=paired(rows,'policy','common_12m',['phase','distribution_mode','structure','horizon'])
    capacity=paired(rows,'distribution_mode','calendar_allowance',['phase','policy','structure','horizon'])
    refinement=paired([r for r in rows if r['policy'] in ('retire_12m','retire_protected_12m')],
                      'policy','retire_12m',['phase','distribution_mode','structure','horizon'])
    regret=capacity_regret(rows)
    funding=[]
    for phase in ('main','challenge'):
        for v in ('face','continuation'):
            for h in ('2031-06-30','2033-06-30'):
                candidates={g['id']:{r['policy']:r for r in g['rows'] if r['structure']==v and r['horizon']==h} for g in fg if g['phase']==phase}
                references_surviving={i for i,z in candidates.items() if z['replay_STRC_0pct']['cash_service']}
                matched={i for i in references_surviving if all(r['financing_matched_to_stop'] for r in candidates[i].values())}
                item={'phase':phase,'structure':v,'horizon':h,'selected_futures':len(candidates),
                    'reference_survivors':len(references_surviving),'all_mixes_matched_futures':len(matched),
                    'matched_future_ids':sorted(matched),'financing_unmatched_future_ids':sorted(references_surviving-matched),
                    'policies':[]}
                for p in ('replay_STRC_0pct','replay_STRC_25pct','replay_STRC_50pct'):
                    vals=[candidates[i][p] for i in sorted(matched)];base=[candidates[i]['replay_STRC_0pct'] for i in sorted(matched)]
                    result={'policy':p,'n':len(vals),**{k:sum(r[k] for r in vals) for k in OUTCOMES}}
                    result['paired_common_survivors']=sum(r['cash_service'] for r in vals)
                    diffs=[r['common_backing_per_share']-b['common_backing_per_share'] for b,r in zip(base,vals) if r['cash_service']]
                    result['median_backing_difference_per_share']=statistics.median(diffs) if diffs else None
                    result['median_total_gross_usd']=statistics.median(r['metrics']['common_gross']+r['metrics']['strc_gross'] for r in vals) if vals else None
                    result['max_funding_gap_before_stop_usd']=max((abs(r['funding_gap_usd']) for r in vals),default=None)
                    result['paired_joint_gains']=sum(not b['joint_success'] and r['joint_success'] for b,r in zip(base,vals))
                    result['paired_joint_losses']=sum(b['joint_success'] and not r['joint_success'] for b,r in zip(base,vals))
                    item['policies'].append(result)
                funding.append(item)
    for name,obj in [('capacity_outcome_counts',counts),('capacity_by_original_regime',strata),
                     ('paired_policy_comparisons',policy),('paired_capacity_comparisons',capacity),
                     ('paired_refinement_comparisons',refinement),('matched_funding_summary',funding),
                     ('capacity_regret_common_domain',regret)]:atomic(OUT/(name+'.json'),obj)
    with (OUT/'capacity_outcome_counts.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(counts[0]));w.writeheader();w.writerows(counts)
    trace=json.loads((OUT/'trace_summary.json').read_text())
    extra=json.loads((OUT/'supplementary_trace_summary.json').read_text())
    cash_checks=json.loads((OUT/'cash_screen_checks.json').read_text())
    verification={'capacity_futures':len(cg),'funding_futures':len(fg),'capacity_simulations':sum(g['simulations'] for g in cg),
        'funding_simulations':sum(g['simulations'] for g in fg),'trace_simulations':trace['simulations']+extra['simulations'],
        'cash_screen_simulations':cash_checks['simulations'],
        'exact_reference_endpoint_matches':references,
        'external_paths_matched':True,'maximum_cash_reconciliation_residual':max(abs(r['max_cash_residual']) for r in rows+[r for g in fg for r in g['rows']]),
        'maximum_trace_cash_bridge_residual':max(abs(r['cash_bridge_residual']) for r in trace['comparisons']+extra['comparisons']),
        'baseline_core_hashes_unchanged':all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in json.loads((ROOT/'audit/technical_revision_baseline_hashes.json').read_text()).items()),
        'complete':True}
    matching=[]
    for g in fg:
        for d in g['funding_diagnostics']:
            es=d['events']
            if d['fraction'] and es and all(e['funding_matched'] for e in es):
                matching.append(sum(abs(e['gap']) for e in es)/sum(e['target_gross'] for e in es))
    verification['maximum_cumulative_rounding_gap_fraction_among_fully_matched_replays']=max(matching)
    assert max(matching)<.001,'Whole-share funding mismatch became economically material'
    assert verification['baseline_core_hashes_unchanged']
    for c in cash_checks['comparisons']:
        assert c['baseline']['path_sha256']==c['extra_cash']['path_sha256']
        verification['maximum_cash_reconciliation_residual']=max(verification['maximum_cash_reconciliation_residual'],abs(c['baseline']['max_cash_residual']),abs(c['extra_cash']['max_cash_residual']))
    atomic(OUT/'verification.json',verification)
    print(json.dumps(verification,indent=2))

if __name__=='__main__':main()
