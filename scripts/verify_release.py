"""Verify release integrity; optionally reproduce checks in an isolated copy."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', action='store_true', help='Run engineering/source checks and reproduce result summaries in a temporary copy.')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'MATERIALS_MANIFEST.json').read_text())
    failed = []
    for name, record in manifest['files'].items():
        path = ROOT / name
        if not path.is_file():
            failed.append([name, 'missing'])
        elif path.stat().st_size != record['bytes'] or digest(path) != record['sha256']:
            failed.append([name, 'changed'])
    if failed:
        print(json.dumps({'status': 'FAIL', 'files': failed}, indent=2))
        raise SystemExit('Obtain the complete materials, or use a clean release checkout.')
    report = {'status': 'PASS', 'files_checked': len(manifest['files']), 'full_study_rerun': False}
    if args.model:
        with tempfile.TemporaryDirectory(prefix='strategy-rdm-verify-') as temporary:
            model = Path(temporary) / 'model'
            for name in manifest['files']:
                if not name.startswith('model/'):
                    continue
                target = Path(temporary) / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            comparisons = [
                'results/technical_revision/regret_metric_diagnostics.json',
                'results/technical_revision/cash_metric_diagnostics.json',
                'results/technical_revision/capacity_outcome_counts.json',
                'results/technical_revision/capacity_regret_common_domain.json',
                'results/technical_revision/matched_funding_summary.json',
                'results/technical_revision/verification.json',
                'analysis/bitcoin_per_share_analysis.json',
            ]
            expected = {name: json.loads((model / name).read_text()) for name in comparisons}
            for name in ['verify.py', 'technical_value_diagnostics.py', 'technical_analyze.py', 'analysis/analyze_bitcoin_per_share.py']:
                run = subprocess.run([sys.executable, name], cwd=model, capture_output=True, text=True)
                if run.returncode:
                    print(run.stdout + run.stderr)
                    raise SystemExit('Verification failed: ' + name)
            for name, value in expected.items():
                if json.loads((model / name).read_text()) != value:
                    raise SystemExit('Reproduced summary differs: ' + name)
            core = json.loads((model / 'results/verification_summary.json').read_text())
            technical = json.loads((model / 'results/technical_revision/verification.json').read_text())
            report.update(engineering_tests=core['tests'], source_documents=core['source_hashes'],
                          historical_instrument_checks=core['historical_instrument_checks'],
                          cash_schedule_checks=core['matched_cash_schedule_checks'],
                          reproduced_summary_files=len(comparisons),
                          technical_reference_matches=technical['exact_reference_endpoint_matches'],
                          supplied_results_unchanged=True)
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
