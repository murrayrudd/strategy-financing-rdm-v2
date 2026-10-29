"""Finite batches, durable saves, then analysis. Resumes only matching inputs."""
from pathlib import Path
import argparse,json,subprocess,sys,time
from checkpoint import save
ROOT=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser();p.add_argument('--archive',required=True);p.add_argument('--helper',required=True);p.add_argument('--receipt',required=True);p.add_argument('--batch',type=int,default=64);p.add_argument('--workers',type=int,default=8);a=p.parse_args()
    status=ROOT/'results/pipeline_status.json'
    def checkpoint(stage):
        status.write_text(json.dumps({'stage':stage,'epoch':time.time()},indent=2))
        print(json.dumps({'checkpoint':stage,**save(a.archive,a.helper,a.receipt)}),flush=True)
    checkpoint('reviewed_code_before_full_run')
    for phase,total in [('main',2000),('challenge',512),('cash',125),('tail2031',125),('tail2033',125)]:
        while True:
            f=ROOT/f'results/rdm/{phase}.jsonl';done=sum(1 for _ in f.open()) if f.exists() else 0
            if done>=total:break
            subprocess.run([sys.executable,str(ROOT/'rdm_run.py'),'--phase',phase,'--limit',str(a.batch),'--workers',str(a.workers)],check=True)
            checkpoint(phase)
    checkpoint('all_simulations_complete')
    print('SIMULATIONS_COMPLETE',flush=True)

if __name__=='__main__':main()
