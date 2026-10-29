"""Verify the portable RDM package without rerunning the full ensemble."""
from pathlib import Path
import json,hashlib,unittest,io
from rdm_run import identity
import historical_replay,reconcile
ROOT=Path(__file__).resolve().parent
def main():
    stream=io.StringIO();suite=unittest.defaultTestLoader.discover(str(ROOT),pattern='test_*.py')
    tests=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (ROOT/'results/final_tests.txt').write_text(stream.getvalue())
    if not tests.wasSuccessful():print(stream.getvalue());raise SystemExit(1)
    sources=json.loads((ROOT/'data/source_manifest.json').read_text())
    for s in sources:assert hashlib.sha256((ROOT/s['packaged_path']).read_bytes()).hexdigest()==s['sha256']
    reconcile.run();hist=historical_replay.run();assert not any(c['status']=='open' for c in hist['checks'])
    assert json.loads((ROOT/'results/frozen_cash_schedule_comparison.json').read_text())['all_match']
    assert identity()==json.loads((ROOT/'results/rdm/run_identity.json').read_text()),'RDM engine/input changed'
    seen={};counts={};max_residual=0.;censored=0
    for phase,n in [('main',2000),('challenge',512),('cash',125),('tail2031',125),('tail2033',125)]:
        rows=[json.loads(s) for s in (ROOT/f'results/rdm/{phase}.jsonl').open()]
        assert len(rows)==n and len({r['id'] for r in rows})==n
        assert json.loads((ROOT/f'results/rdm/{phase}_errors.json').read_text())==[]
        count=0
        for r in rows:
            assert len(r['rows'])==(16 if phase.startswith('tail') else 32)
            assert len({v['path_sha256'] for v in r['rows']})==1
            assert len({(v['structure'],v['policy'],v['horizon']) for v in r['rows']})==len(r['rows'])
            for v in r['rows']:
                assert v['common_backing_per_share'] is not None or not v['cash_service']
                if v['censored']:assert not v['cash_service'] and v['common_backing_per_share'] is None
                max_residual=max(max_residual,abs(v['max_cash_residual']));censored+=v['censored'];count+=1
            if phase=='main':seen[r['id']]=r
            if phase=='cash':assert r['rows'][0]['path_sha256']==seen[r['id']]['rows'][0]['path_sha256']
        counts[phase]={'futures':n,'simulations':n*16,'endpoint_rows':count}
    transport=json.loads((ROOT/'results/rdm/transport_identity.json').read_text())
    assert transport['runner_sha256']==hashlib.sha256((ROOT/'durable_run.py').read_bytes()).hexdigest()
    for phase,c in counts.items():
        folder=ROOT/f'results/rdm/groups/{phase}';assert len(list(folder.glob('*.json')))==c['futures']
        for line in (ROOT/f'results/rdm/{phase}.jsonl').open():
            g=json.loads(line);assert json.loads((folder/(g['id']+'.json')).read_text())==g
    carry=[json.loads(s) for s in (ROOT/'results/rdm/carry.jsonl').open()]
    assert len(carry)==64 and len({(g['id'],g['net_yield']) for g in carry})==64
    assert json.loads((ROOT/'results/rdm/carry_errors.json').read_text())==[]
    ci=json.loads((ROOT/'results/rdm/carry_identity.json').read_text())
    assert ci['model']==identity() and ci['extension_sha256']==hashlib.sha256((ROOT/'carry_sensitivity.py').read_bytes()).hexdigest()
    selected={x['id'] for x in json.loads((ROOT/'data/rdm_main.json').read_text())[::64]}
    assert {g['id'] for g in carry}==selected
    for g in carry:
        assert len(g['rows'])==32 and g['net_yield'] in (.03,.05)
        assert all(v['path_sha256']==seen[g['id']]['rows'][0]['path_sha256'] for v in g['rows'])
        max_residual=max(max_residual,max(abs(v['max_cash_residual']) for v in g['rows']))
    legal=[json.loads(s) for s in (ROOT/'results/rdm/legal_headroom.jsonl').open()]
    assert len(legal)==125 and len({g['id'] for g in legal})==125
    li=json.loads((ROOT/'results/rdm/legal_headroom_identity.json').read_text())
    assert li['model']==identity() and li['extension_sha256']==hashlib.sha256((ROOT/'legal_headroom_sensitivity.py').read_bytes()).hexdigest()
    matched_unlimited=0
    for g in legal:
        assert len(g['rows'])==4
        for v in g['rows']:
            b=next(r for r in seen[g['id']]['rows'] if r['policy']==v['policy'] and r['structure']==v['structure'] and r['horizon']==v['horizon'])
            assert v['path_sha256']==b['path_sha256']
            max_residual=max(max_residual,abs(v['max_cash_residual']))
            if g['legal_regime']=='unlimited':assert v==b;matched_unlimited+=1
    assert matched_unlimited==li['unlimited_regime_exact_endpoint_matches'] and matched_unlimited>0
    ls=json.loads((ROOT/'results/analysis/legal_headroom_summary.json').read_text())
    assert ls['raw_sha256']==hashlib.sha256((ROOT/'results/rdm/legal_headroom.jsonl').read_bytes()).hexdigest()
    refined=[json.loads(s) for s in (ROOT/'results/rdm/legal_headroom_challenge.jsonl').open()]
    assert len(refined)==512 and len({g['id'] for g in refined})==512
    ri=json.loads((ROOT/'results/rdm/legal_headroom_challenge_identity.json').read_text())
    assert ri['model']==identity() and ri['extension_sha256']==hashlib.sha256((ROOT/'legal_headroom_sensitivity.py').read_bytes()).hexdigest()
    assert ri['validation_runner_sha256']==hashlib.sha256((ROOT/'legal_headroom_validation.py').read_bytes()).hexdigest()
    challenge={json.loads(s)['id']:json.loads(s) for s in (ROOT/'results/rdm/challenge.jsonl').open()}
    exact=0
    for g in refined:
        assert len(g['rows'])==4
        for v in g['rows']:
            b=next(r for r in challenge[g['id']]['rows'] if r['policy']==v['policy'] and r['structure']==v['structure'] and r['horizon']==v['horizon'])
            assert v['path_sha256']==b['path_sha256'];max_residual=max(max_residual,abs(v['max_cash_residual']))
            if g['legal_regime']=='unlimited':assert v==b;exact+=1
    assert exact==ri['unlimited_regime_exact_endpoint_matches'] and exact>0
    rs=json.loads((ROOT/'results/analysis/legal_headroom_challenge_summary.json').read_text())
    assert rs['raw_sha256']==hashlib.sha256((ROOT/'results/rdm/legal_headroom_challenge.jsonl').read_bytes()).hexdigest()
    ca=json.loads((ROOT/'results/analysis/carry_sensitivity_summary.json').read_text())
    assert ca['raw_sha256']==hashlib.sha256((ROOT/'results/rdm/carry.jsonl').read_bytes()).hexdigest()
    assert max_residual<.01
    assert sum(r['split']=='train' for r in seen.values())==1500 and sum(r['split']=='holdout' for r in seen.values())==500
    controlled=json.loads((ROOT/'results/controlled_runs.json').read_text());assert len(controlled)==432
    assert json.loads((ROOT/'results/experiment_errors.json').read_text())==[]
    cd=json.loads((ROOT/'results/controlled_experiment_design.json').read_text())
    for name,sha in cd['code_files_sha256'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha
    boundary=json.loads((ROOT/'results/loan_boundary_sensitivity.json').read_text())
    discovery=json.loads((ROOT/'results/analysis/scenario_discovery.json').read_text());assert len(discovery)==96 and len({r['key'] for r in discovery})==96
    assert sum('stability' in r for r in discovery)==18
    readiness=json.loads((ROOT/'results/analysis/discovery_readiness.json').read_text())
    ae=json.loads((ROOT/'results/analysis/analysis_environment.json').read_text());assert ae['python_hash_seed']=='0'
    ai=json.loads((ROOT/'results/analysis/analysis_identity.json').read_text())
    assert ai['run_identity_sha256']==hashlib.sha256((ROOT/'results/rdm/run_identity.json').read_bytes()).hexdigest()
    common_cash=json.loads((ROOT/'results/analysis/marginal_cash_common_domain.json').read_text());assert len(common_cash)==32
    extra=[json.loads(s) for s in (ROOT/'results/rdm/cash.jsonl').open()]
    for h in ('2031-06-30','2033-06-30'):
        expected={g['id'] for g in extra if all(v['cash_service'] for v in g['rows']+seen[g['id']]['rows'] if v['horizon']==h)}
        for r in common_cash:
            if r['horizon']==h:assert set(r['future_ids'])==expected and r['common_survivor_futures']==len(expected)
    assert ai['analysis_sha256']==hashlib.sha256((ROOT/'rdm_analyze.py').read_bytes()).hexdigest()
    for phase,sha in ai['data_sha256'].items():assert hashlib.sha256((ROOT/f'results/rdm/{phase}.jsonl').read_bytes()).hexdigest()==sha
    result={'engineering_status':'PASS','tests':tests.testsRun,'source_hashes':len(sources),'historical_instrument_checks':len(hist['checks']),
      'matched_cash_schedule_checks':15,'RDM_runs':counts,'total_RDM_simulations':sum(c['simulations'] for c in counts.values()),
      'refined_policy_challenge_simulations':1024,'posthoc_legal_headroom_simulations':250,'supplemental_carry_simulations':1024,'total_new_simulations_including_controlled_and_boundary':sum(c['simulations'] for c in counts.values())+1024+1024+250+432+boundary['simulation_count'],'controlled_runs':432,'local_boundary_runs':boundary['simulation_count'],'max_cash_residual_usd':max_residual,
      'censored_endpoint_rows':censored,'scenario_discovery':readiness,'full_locked_design_complete':True,
      'publication_readiness':'Engineering pass does not certify journal readiness or actual legal/tax position.'}
    (ROOT/'results/verification_summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
