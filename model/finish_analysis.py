"""Finish the authorized finite experiment after the main simulation pipeline."""
from pathlib import Path
import argparse,json,subprocess,sys,time
from checkpoint import save
ROOT=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser();p.add_argument('--archive',required=True);p.add_argument('--helper',required=True);p.add_argument('--receipt',required=True);a=p.parse_args()
    status=ROOT/'results/postprocess_status.json';log=ROOT/'results/durable_pipeline.log'
    def stage(name):
        status.write_text(json.dumps({'stage':name,'epoch':time.time()},indent=2));print(name,flush=True)
    def check():print(json.dumps(save(a.archive,a.helper,a.receipt)),flush=True)
    stage('waiting_for_core_simulations')
    while 'SIMULATIONS_COMPLETE' not in log.read_text():
        if 'Traceback (most recent call last)' in log.read_text():raise RuntimeError('Core pipeline error: inspect durable_pipeline.log')
        time.sleep(10)
    for phase,n in [('main',2000),('challenge',512),('cash',125),('tail2031',125),('tail2033',125)]:
        assert sum(1 for _ in (ROOT/f'results/rdm/{phase}.jsonl').open())==n
    stage('supplemental_carry')
    subprocess.run([sys.executable,'carry_sensitivity.py'],cwd=ROOT,check=True);check()
    stage('scenario_discovery_and_matched_analysis')
    subprocess.run([sys.executable,'rdm_analyze.py'],cwd=ROOT,check=True)
    subprocess.run([sys.executable,'carry_analyze.py'],cwd=ROOT,check=True);check()
    stage('full_verification')
    subprocess.run([sys.executable,'verify.py'],cwd=ROOT,check=True)
    stage('scientific_figures')
    subprocess.run([sys.executable,'tools/build_figures.py'],cwd=ROOT,check=True);check()
    stage('analysis_verified_ready_for_interpretation');print('ANALYSIS_COMPLETE',flush=True)
if __name__=='__main__':main()
