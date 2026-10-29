# Strategy financing resilience under deep uncertainty

Self-contained code, data, and replication materials for Murray A. Rudd’s **Financing resilience and shareholder outcomes in a Bitcoin treasury company: Robust decision making and regret analysis for Strategy**.

**Model release: 2.0.0 · October 29, 2026.** This release supports the expanded Strategy RDM paper. The updated paper replaces the earlier *Strategy financing under deep uncertainty* paper on the same [SSRN record](https://doi.org/10.2139/ssrn.7632598), retaining DOI **10.2139/ssrn.7632598**. The replication materials below correspond to the updated model and retained results; links to the preceding papers appear under **Research basis**.

The study examines Strategy’s long-term payment resilience and the consequences of financing decisions for preferred and common investors. Eight financing and liquidity policies face the same 2,000 exploratory futures under two common valuation mechanisms, with 512 challenge futures and a further 253-future structural and matched-funding analysis. The corporate opening is June 30, 2026, with primary evaluation dates in June 2031 and June 2033.

## Main findings

- Payment capacity and protection of investor objectives differ. Common financing with a 12-month liquidity target maintains cash service in 1,857 of 2,000 main continuation futures at June 2033, while meeting the three payment and backing objectives in 680.
- Distribution constraints can reverse policy rankings. Preferred retirement can reduce median residual-value regret while increasing upper-tail regret.
- Payment resilience does not establish Bitcoin accumulation. No main continuation survivor achieves BPS growth above opening at June 2033 under the baseline annual allowance; policy-specific median declines among the 1,740 shared survivors range from 36.5% to 43.2%.
- Replacing some common funding with STRC can improve Bitcoin per share relative to all-common funding while weakening common backing and joint attainment. Accumulation regret and common residual-value regret can rank policies differently.

Exploratory shares describe the tested conditions, not probabilities of corporate survival. BPS uses modeled economic common shares and differs from Strategy’s published assumed-dilution KPI. Preferred retirement follows contractual redemption rules; open-market buybacks and direct Bitcoin/STRC price impacts are outside these experiments.

## Get the complete materials

The [version 2.0.0 release](https://github.com/murrayrudd/strategy-financing-rdm-v2/releases/tag/v2.0.0) contains **strategy-rdm-v2.0.0-complete.zip**: the model, frozen inputs, archived evidence, complete saved results, tables, figures, and replication scripts. Download and extract that archive to work without Git. No earlier Strategy repository is required.

Alternatively, clone this repository and retrieve the same materials:

```bash
git clone https://github.com/murrayrudd/strategy-financing-rdm-v2.git
cd strategy-financing-rdm-v2
python scripts/get_materials.py
python scripts/verify_release.py
```

The repository keeps the code, readable settings, key summaries, tables, and documentation directly browsable. Large result records, archived filings, and image files are supplied in this repository’s release archive. `RELEASE_ASSETS.json` records its checksum; `MATERIALS_MANIFEST.json` identifies every included research file.

## Reproduce

Use Python 3.12; the original simulation environment was Python 3.12.14. After obtaining the complete materials:

```bash
python -m venv .venv
# Activate .venv using the command for your operating system.
python -m pip install -r requirements.txt
python scripts/verify_release.py --model
python scripts/rebuild_figures.py
```

`--model` verifies the retained engineering checks, sources, experiment identities, technical comparisons, and BPS/regret calculations in a temporary working copy. It does not rerun the 61,292-simulation study or alter the supplied results. Figure reconstruction likewise uses saved outputs. [Replication instructions](docs/REPRODUCING.md) distinguish verification, post-processing, and a fresh simulation run.

## Find the evidence

| Material | Location |
| --- | --- |
| Simulation engine, policies, funding and distribution mechanics | [`model/`](model/) |
| Opening state, contracts, calendars, uncertainty design, source registry | [`model/data/`](model/data/) |
| Original and structural results, transaction traces, identities | [Browse summaries and identities](model/results/) · [Download complete results and traces (ZIP)](https://github.com/murrayrudd/strategy-financing-rdm-v2/releases/download/v2.0.0/strategy-rdm-v2.0.0-complete.zip) |
| BPS calculations, numerical supplement, headline claim ledger | [`model/analysis/`](model/analysis/) |
| Figure scripts, exact plotting data, all 19 table exports | [`model/publication/`](model/publication/) |
| Manuscript-to-output map | [`docs/MANUSCRIPT_MAP.md`](docs/MANUSCRIPT_MAP.md) |
| Recorded checks for this release | [`docs/VERIFICATION.json`](docs/VERIFICATION.json) |
| Relationship to earlier papers and repositories | [`docs/VERSION_HISTORY.md`](docs/VERSION_HISTORY.md) |

The figure set includes the corrected grayscale policy comparison and payment charts with legends below the axes, plus the landscape attainment heatmap. Descriptive filenames identify plots independently of numbering in the manually edited manuscript. The repository does not distribute an outdated manuscript draft as the final paper.

## Research basis

**Rudd, M. A. (2026).** *Financing resilience and shareholder outcomes in a Bitcoin treasury company: Robust decision making and regret analysis for Strategy*. SSRN working paper.

[https://doi.org/10.2139/ssrn.7632598](https://doi.org/10.2139/ssrn.7632598).

This paper replaces the earlier *Strategy financing under deep uncertainty* version on the same SSRN record and builds on [Financing feasibility and shareholder outcomes in a Bitcoin treasury company: Historical validation and conditional stress testing of Strategy](https://doi.org/10.2139/ssrn.7593458). The [earlier RDM replication repository](https://github.com/murrayrudd/strategy-financing-rdm) preserves that version’s model and results. The present repository includes all materials required to reproduce the expanded analysis and has no dependency on either earlier repository.

## Citation

If you use this code or its results in research, please cite the accompanying paper and identify model version **2.0.0** and the repository commit used:

```bibtex
@unpublished{Rudd2026StrategyResilience,
  author = {Rudd, Murray A.},
  title = {Financing resilience and shareholder outcomes in a Bitcoin treasury company: Robust decision making and regret analysis for Strategy},
  year = {2026},
  doi = {10.2139/ssrn.7632598},
  url = {https://doi.org/10.2139/ssrn.7632598},
  note = {SSRN working paper; updated version of Strategy financing under deep uncertainty}
}
```

[CITATION.cff](CITATION.cff) supplies machine-readable software metadata and the preferred paper citation through GitHub’s **Cite this repository** option. The [versioned code and results release](https://github.com/murrayrudd/strategy-financing-rdm-v2/releases/tag/v2.0.0) provides a fixed reference for replication. The software has no separate DOI.

## License

Original project code and associated software documentation are available under the [MIT License](LICENSE.md). See [license scope](LICENSE_SCOPE.md) for coverage of inherited code and the distinction between software and data. Coin Metrics data retain CC BY-NC 4.0 terms; other third-party material retains its source terms. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Author

**Murray A. Rudd, Ph.D.** – Institutional economist and policy researcher

- ORCID: [0000-0001-9533-5070](https://orcid.org/0000-0001-9533-5070)
- SSRN: [Author profile](https://papers.ssrn.com/sol3/cf_dev/AbsByAuth.cfm?per_id=5958022)
- Google Scholar: [Profile](https://scholar.google.co.uk/citations?hl=en&user=84qbofEAAAAJ)
