# Replication instructions

## 1. Obtain and check the complete release

Either extract `strategy-rdm-v2.0.0-complete.zip` from this repository’s version 2.0.0 release, or clone the repository and run:

```bash
python scripts/get_materials.py
python scripts/verify_release.py
```

The first command downloads only this repository’s complete release archive. It validates the archive checksum, inventory, and every archived file, and refuses to overwrite changes to model files or pinned requirements. It preserves existing documentation and packaging scripts, allowing README and citation updates on the current branch without changing the frozen research release. For an archive already downloaded, use `python scripts/get_materials.py --archive /path/to/strategy-rdm-v2.0.0-complete.zip`. No earlier repository, account credential, live market feed, or SEC retrieval is required.

The complete archive includes code, all frozen inputs, 34 archived SEC documents, the cited investor briefing, complete retained experiment records, transaction traces, result summaries, figure data, and all 19 numerical tables. Normal Python dependencies are installed separately.

## 2. Install dependencies and verify the model

Use Python 3.12. The original experiment recorded Python 3.12.14 and the package versions in `model/audit/environment.json` and `technical_revision_environment.json`. The root `requirements.txt` preserves those direct dependency pins and adds Pillow for figure handling.

```bash
python -m venv .venv
```

Activate with `source .venv/bin/activate` on Linux/macOS or `.venv\Scripts\Activate.ps1` in Windows PowerShell. Then run:

```bash
python -m pip install -r requirements.txt
python scripts/verify_release.py --model
```

This checks the frozen files under `model/` and the pinned requirements against the release hashes, copies the model into a temporary directory, runs the 94 engineering tests and source/history checks, verifies saved experiment identities and matched paths, and reproduces the technical summaries and BPS/regret calculations. It compares seven regenerated summaries with the released values. The temporary copy is discarded; supplied research files remain unchanged. Current documentation and packaging scripts are versioned in Git separately from the archived research files. This is verification and post-processing, not a fresh execution of the full simulation ensemble.

## 3. Rebuild the figures and inspect the tables

```bash
python scripts/rebuild_figures.py
```

The eight figures are written in PNG, PDF, and SVG to `model/publication/figures/`. Exact plotted values are in `model/publication/figure_data/` and `source_data/`; all numerical tables are in `model/publication/tables/`. The policy comparison and payment legends use the approved lower placement, and the attainment heatmap is landscape. See `MANUSCRIPT_MAP.md` for the connection to the paper.

Figure rebuilding changes image metadata and may change renderer-specific bytes. Run the integrity check before rebuilding, and use a separate working copy if you want to preserve the original images byte for byte. Scientific values, simulation outputs, and policy definitions are unaffected.

## 4. Recompute endpoint analyses

In a separate working copy, change into `model/` and run:

```bash
python technical_value_diagnostics.py
python technical_analyze.py
python analysis/analyze_bitcoin_per_share.py
```

These commands read saved simulations. The BPS script verifies the settled-Bitcoin/share ratio, censoring conventions, and shared-survival domains across 108,720 endpoint records, including repeated controls. That endpoint count is not an additional simulation count. The analysis preserves the distinction between absolute BPS growth and relative accumulation regret.

To repeat the original scenario-discovery analysis, run `python rdm_analyze.py`, followed by `python carry_analyze.py`, `python legal_headroom_analyze.py`, and `python legal_headroom_challenge_analyze.py`. The scenario-discovery script fixes the Python hash seed to preserve categorical tie behavior. The recorded tests distinguish the original holdout/challenge design from the subsequently examined structural-sensitivity cases.

## 5. Fresh simulation runs

Full reruns are substantially more expensive than the checks above. First make a separate copy of the complete release. Move its `model/results/` directory outside that working copy and create an empty replacement. Keep the frozen input tables and the original release elsewhere as reference evidence. Existing matching outputs are otherwise reused by the resumable runners.

From that fresh copy’s `model/` directory, first reproduce the controlled and core experiments:

```bash
python run_experiments.py
python boundary_experiments.py
python rdm_run.py --phase pilot --limit 0
python durable_run.py --phase main --limit 2000 --workers 4
python durable_run.py --phase challenge --limit 512 --workers 4
python durable_run.py --phase cash --limit 125 --workers 4
python durable_run.py --phase tail2031 --limit 125 --workers 4
python durable_run.py --phase tail2033 --limit 125 --workers 4
python carry_sensitivity.py --workers 4
python legal_headroom_sensitivity.py --work ../rerun_headroom --workers 4
python legal_headroom_validation.py --work ../rerun_headroom_challenge --workers 4
python rdm_analyze.py
python carry_analyze.py
python legal_headroom_analyze.py
python legal_headroom_challenge_analyze.py
```

Use initially empty headroom work directories. Set `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, and `MKL_NUM_THREADS` to `1` when using multiple workers. The `--limit` argument is the maximum number of pending futures processed in one invocation. Smaller batches are safe; repeat the command until the phase’s documented count is complete. Do not change code or frozen inputs while resuming an experiment.

Then run the structural and mechanism extension:

```bash
python technical_experiments.py --phase capacity --workers 4
python technical_experiments.py --phase funding --workers 1
python technical_traces.py
python technical_value_diagnostics.py
python technical_supplementary_traces.py
python technical_cash_screen_checks.py
python technical_analyze.py
python analysis/analyze_bitcoin_per_share.py
```

The retained study comprises 49,114 base/supplementary simulations and 12,178 extension simulations. Protocol and execution identities are in `data/rdm_protocol.json`, `results/rdm/`, and `results/technical_revision/`. Historical helper scripts that refer to the original checkpoint-saving environment are retained because the frozen audit identity covers them; the commands above do not require that environment or its upload helpers.

## Verification scope

Checks establish internal consistency, preservation of source and input identities, and reproduction of specified calculations. They do not make exploratory shares probabilities or identify omitted market-price feedback. The annual distribution allowance is an experimental institutional constraint; alternative screens do not identify actual lawful distribution capacity. The model represents contractual STRC redemption, not open-market repurchase at a discount.
