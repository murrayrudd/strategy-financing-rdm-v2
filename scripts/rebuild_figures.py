"""Rebuild all eight publication figures from retained outputs."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / 'model'
if not (MODEL / 'results/rdm/main.jsonl').exists():
    raise SystemExit('First run python scripts/get_materials.py or extract the complete release archive.')
for script in ['build_methods_figures.py', 'build_cash_figure.py', 'build_funding_and_regret_figures.py',
               'build_policy_comparisons.py', 'build_payment_outcomes.py', 'build_attainment_heatmap.py']:
    subprocess.run([sys.executable, str(MODEL / 'publication' / script)], cwd=MODEL, check=True)
print('Figures: model/publication/figures; exact values: figure_data and source_data.')
