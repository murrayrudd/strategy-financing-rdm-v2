# Manuscript-to-output map

All paths in the following table are relative to `model/`. Large files become available after extracting the complete release. The manuscript’s outcome definitions and comparison domains remain separate in the data.

| Evidence | Authoritative output or input |
| --- | --- |
| Policy definitions and uncertainty ranges; Tables 1–2 | `rdm_design.py`, `data/rdm_protocol.json`, `data/rdm_main.json`, `data/rdm_challenge.json` |
| Opening balances and contracts; Tables A1–A5 | `data/opening.json`, `data/debt_terms.json`, `data/preferred_terms.json`, `data/authorization_events.json`, `data/calendars.json`, `data/source_manifest.json` |
| Main payment/backing attainment; Table 3 and Tables B1–B2 | `results/analysis/robustness_summary.json` |
| Main common residual regret; Table 3 and Table B3 | `results/technical_revision/regret_metric_diagnostics.json` |
| Distribution screens; Table 4 and Table B4 | `results/technical_revision/capacity_outcome_counts.json` |
| Regret across screens; Table B5 | `results/technical_revision/capacity_regret_common_domain.json` |
| Matched funding; Table 5 and Table B6 | `results/technical_revision/matched_funding_summary.json`, `results/technical_revision/groups/funding/` |
| BPS, positive accumulation, accumulation regret; Table 6 and Table B8 | `analysis/bitcoin_per_share_analysis.json`, `analysis/analyze_bitcoin_per_share.py` |
| Protected-retirement challenge; Table B7 | `results/analysis/legal_headroom_challenge_summary.json`, `legal_headroom_cash_loss_cases.json` |
| Marginal cash mechanisms | `results/technical_revision/cash_metric_diagnostics.json`, `trace_summary.json`, `supplementary_trace_summary.json`, `traces/` |
| Scenario discovery | `results/analysis/scenario_discovery.json`, `discovery_readiness.json` |
| Financing closure and liquid-asset carry | `results/analysis/closure_tail_results.json`, `carry_sensitivity_summary.json` |

`publication/tables/` contains all 19 numerical tables as CSV files, with titles and row counts in `index.json`. These exports preserve the evidence tables from the integrated source; subsequent manual prose and figure-number changes do not change those values. `analysis/claim_ledger.json` records headline selectors and values. `analysis/paper_numerical_supplement.json` collects detailed summaries.

## Figures

| Figure filename | Builder in `publication/` | Data/domain |
| --- | --- | --- |
| `rdm_framework` and `study_timing` | `build_methods_figures.py` | Schematics of the specified design and event sequence |
| `Payment_Outcomes` | `build_payment_outcomes.py` | Eight policies, 2,000 main futures each, June 2033 continuation, annual allowance |
| `Figure_3_Policy_Comparisons` | `build_policy_comparisons.py` | 125 main-subset futures for attainment; 110 shared survivors for regret |
| `matched_funding_tradeoff` | `build_funding_and_regret_figures.py` | 92 matched main futures, including 90 paired survivors and two alternative failures |
| `cash_residual` | `build_cash_figure.py` | Original common-survivor domains for the opening-cash experiment |
| `regret_objectives` | `build_funding_and_regret_figures.py` | 1,740 shared main continuation survivors, eight policies |
| `Figure_B1_landscape` | `build_attainment_heatmap.py` | 128 attainment percentages across policy, objective, horizon, and valuation |

The user’s current Figure 3 is the policy comparison chart. The payment chart uses a descriptive filename to avoid conflicting numbering. Use the plotted content and this map when inserting figures into a manually revised manuscript. PNG, PDF, and SVG outputs are in `publication/figures/`; CSV plotting values are in `publication/figure_data/` and `publication/source_data/`.

## Interpretation

Joint success combines cash service, preferred continuity, and common backing preservation. BPS remains a separate gross accumulation measure. Continuous regret is conditional on the stated common-survival domain; full-domain counts retain failed paths. Matched-funding gains in BPS are relative to all-common funding and need not imply growth from opening. No reported design share is a forecast probability.
