# Version history and research lineage

## Current release: 2.0.0, October 29, 2026

This repository accompanies the expanded paper **Financing resilience and shareholder outcomes in a Bitcoin treasury company: Robust decision making and regret analysis for Strategy**. It replaces the earlier *Strategy financing under deep uncertainty* working paper on the same [SSRN record](https://doi.org/10.2139/ssrn.7632598), retaining DOI **10.2139/ssrn.7632598**. The first historical financing-feasibility paper remains a separate publication.

The current study compares eight main policies, adds contractual STRC retirement and protected-retirement comparisons, tests alternative distribution screens and matched financing, and reports common residual-value and Bitcoin accumulation regret. It retains 49,114 base and supplementary simulations plus 12,178 technical-extension simulations, for 61,292 in total. BPS post-processing adds no simulations.

Release 2.0.0 packages the completed model and retained outputs. It changes no simulation engine, frozen input, policy rule, or saved endpoint. Publication scripts have been placed in descriptive directories; `PORTABILITY_CHANGES.json` records their source hashes and path/entrypoint adjustments. The approved October 29 legend corrections and landscape heatmap are included. Numerical table exports and evidence mappings accompany the code; the final manually edited manuscript is published separately.

## Earlier RDM paper and repository

- Earlier title: *Strategy financing under deep uncertainty*. Its SSRN record, https://doi.org/10.2139/ssrn.7632598, now identifies the updated paper; the DOI is shared across versions.
- Repository: https://github.com/murrayrudd/strategy-financing-rdm.
- Preserved release: https://github.com/murrayrudd/strategy-financing-rdm/releases/tag/v1.1.0.

That release records the earlier eleven-policy RDM design and its results. It should be used to reproduce that version of the paper. The current eight-policy design and structural extensions have their own frozen inputs, simulation records, and interpretation; the policy counts and numerical results are not interchangeable.

## First historical financing-feasibility paper

- Paper: *Financing feasibility and shareholder outcomes in a Bitcoin treasury company: Historical validation and conditional stress testing of Strategy*, https://doi.org/10.2139/ssrn.7593458.
- Repository: https://github.com/murrayrudd/strategy-financing-feasibility.

The first paper establishes earlier corporate modeling and historical work. Both preceding repositories remain useful historical records. This release includes the implementation and data it needs and has no runtime or download dependency on either repository.

No earlier repository is modified by this release. A later navigation update can direct readers from the earlier RDM README to this repository while preserving its tagged release and results.
