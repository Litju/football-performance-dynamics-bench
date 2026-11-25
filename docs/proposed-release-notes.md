# Proposed public research-software release notes

> **Unreleased proposal.** This is editorial copy for a future versioned GitHub source-code release, not evidence that a stable version, DOI, model-weight artifact, dataset or journal paper has been published. The maintainer must approve the final version, author/copyright and rights manifest before issuing anything.

## Football Performance Dynamics Bench — research software

FPD Bench provides typed football-performance benchmark definitions and research objects, deterministic target transformations and physical evaluators, source/measurement/eligibility contracts, reproducibility checks and inspectable aggregate scientific evidence.

The public research package focuses on **what a football prediction model knows at forecast time**, whether the target is absolute XY or origin-relative displacement, and why **realized future ball/opponent information** defines a conditional research task rather than a deployable ex-ante forecast.

### Included

- Versioned scientific contracts for the historical recovered benchmarks and prospective SkillCorner v2 absolute-position / displacement targets.
- Public Python CLI, evaluator modules, isolated synthetic regression tests, wheel/sdist packaging checks and frozen scientific-reproducibility/evidence validators.
- Source and rights metadata pinned to upstream SkillCorner Open Data, including source acquisition/verification rather than redistribution.
- A completed **four-match, research-only descriptive** football-motion study, with 18 frozen final-role DeepSets checkpoints' aggregate results, match-first errors and paired context contrasts.
- Scientific report, machine-readable non-reconstructive aggregates, figures and Paper A methodology manuscript with submission status clearly identified.
- Public scientific cards, reproduction walkthrough and a 3D schematic research-story companion; the site is **not** observed tracking playback or new empirical analysis.

### A bounded result

On four evaluation matches, history-only displacement DeepSets achieved **1.6680 m ADE** versus **2.2433 m** for one-second constant velocity (**25.6% lower descriptive ADE**). The independent scientific unit is **four matches**. Those values describe specific fixed models, source observations and match membership; they do **not** establish causality, inferential significance or generalization.

### Not included and not claimed

The protected 20-match population remains **`NOT_QUALIFIED`**. The original 234-fit experiment matrix was not completed and its 216 training LOMO fits were not run. No protected population truth, restricted match-scoped trajectories, original source rows or derivatives, evaluation receipts, trained checkpoint weights or private model-inference assets may be included.

`future_ball` and `future_opponent_plus_ball` are conditioned on **realized** future trajectories, so their lower measured errors cannot be described as operational forecasts. The data provider's broadcast-based tracking and extrapolation remain limitations; these are not independent physical ground truth, athlete assessment, clinical results or match deployment evidence.

### Attribution and licenses

Original rights-cleared code and project-written documentation are distributed under Apache-2.0. SkillCorner is the data provider and PySport the collaborating initiative; upstream source/data terms are separate. This repository's code license **does not** license or allow redistribution of SkillCorner core tracking, events, phases or row-level derivatives. See the [rights audit](data-rights.md) before reusing source material.

### Start with the research

- [Public repository](https://github.com/Litju/football-performance-dynamics-bench)
- [Benchmark cards](public-benchmark-cards.md) and [data/model/limitations cards](public-data-and-model-cards.md)
- [Public reproduction walkthrough](public-reproduction-walkthrough.md)
- [Scientific results](res440/results.md) and [public aggregate JSON](res440/findings.json)
- [Paper A manuscript and submission status](paper-a/submission-readiness.md)
- [Non-archival interactive research companion](https://fpd-bench-showcase.vercel.app)

**Before publication:** replace the proposed version with an actually verified version/tag; obtain contributor/rightsholder approvals, validate the exact release payload and its SHA-256 manifest, decide whether an archival deposit is allowed, and include a verified citation/DOI only after it exists. The [release gates](software-release-gates.md) remain authoritative.
