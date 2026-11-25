# Football Performance Dynamics Bench v1.0.0 — public research software

This is the first **source-code and research-documentation release** of Football Performance Dynamics Bench (FPD Bench). It is a release of the **software framework and public research evidence**, not a claim that the underlying protected scientific benchmark has qualified for production or that a journal paper has been accepted.

## What is included

- Typed football research families, benchmark/task definitions and prospective SkillCorner measurement, eligibility and protocol authorities.
- Deterministic geometric target transformations and shared scientific evaluation (ADE, FDE, scalar-coordinate XY RMSE), public provenance verification and scientific-lock tooling.
- Public source/benchmark/model/limitation cards, a public-only reproduction walkthrough, and a standard-library checker that reconciles released match-level aggregate statistics.
- Historical benchmark reconstruction records and the bounded **four-match descriptive** football-motion study.
- Public research results and non-reconstructive figures, with provenance hashes, source rights and scientific limitations.
- The separate online 3D research companion, which is schematic and non-archival.

## Bounded scientific result

On four fixed evaluation matches, the history-only DeepSets model using origin-relative displacement achieved **1.6680 m ADE** against **2.2433 m** for one-second constant velocity (**25.6% lower descriptive ADE**). The experiment considered **18 frozen DeepSets checkpoints** (six configurations × three seeds), **72 match/seed records**, and **51,713 overlapping evaluation windows**. **Only four matches are independent evaluation units.**

The two realized-future regimes, `future_ball` and `future_opponent_plus_ball`, are **conditional** prediction settings and **not** deployable ex-ante forecasts. This report does not establish significance, causal response, generalization to other matches/leagues/seasons, or operational deployment suitability.

## What this release does not contain

- **No raw SkillCorner tracking, event, phase or source-derived row-level data**, identifying player trajectories, private receipts, truth masks, private result packages or model checkpoint weights.
- **No completed original 234-fit design** and **no 216-fit training LOMO**. These remain incomplete/deferred.
- **No qualified protected evaluation population.** The protected status stays `NOT_QUALIFIED`.
- **No trained-model inference reproducibility from public weights** and no claim of validation against independent physical ground truth.
- **No journal publication or accepted/peer-reviewed Paper A claim.**

Publicly inspectable aggregates and cryptographic identities do not make unavailable private data or trained-model computation reproducible from this distribution.

## Installation and verification

Python **3.12** is the tested full development environment. `uv` is used for lockfile-managed installation.

```bash
git clone https://github.com/Litju/football-performance-dynamics-bench.git
cd football-performance-dynamics-bench
git checkout v1.0.0
uv sync --locked --python 3.12
uv run fpdbench benchmarks list
uv run fpdbench validate
uv run python tools/inspect_public_findings.py
```

The full suite has a separately pinned **public synthetic** streaming-integration source-package prerequisite. See [test prerequisites](https://github.com/Litju/football-performance-dynamics-bench/blob/v1.0.0/docs/reproducibility.md#test-prerequisites), the [public reproduction walkthrough](https://github.com/Litju/football-performance-dynamics-bench/blob/v1.0.0/docs/public-reproduction-walkthrough.md), and [release gate policy](https://github.com/Litju/football-performance-dynamics-bench/blob/v1.0.0/docs/software-release-gates.md).

## Citation, source attribution and license

The software citation is [`CITATION.cff`](https://github.com/Litju/football-performance-dynamics-bench/blob/v1.0.0/CITATION.cff), with **Julio Rodriguez** as the owner-approved sole software author. Original, rights-cleared project code and documentation are licensed under **Apache-2.0**; this does not sublicense upstream datasets or private checkpoints.

Upstream source: **SkillCorner Open Data**, released by SkillCorner in collaboration with **PySport**, at the pinned source revision specified in [the source card](https://github.com/Litju/football-performance-dynamics-bench/blob/v1.0.0/docs/skillcorner-source-card.md). Core source-data/row-level redistribution rights remain restricted by the [rights policy](https://github.com/Litju/football-performance-dynamics-bench/blob/v1.0.0/docs/data-rights.md).

**Archiving:** this GitHub source-code release is separate from any later Zenodo/archive deposit. No DOI is asserted here unless a separately issued DOI is verified and added subsequently. An absent DOI does not become a fabricated placeholder citation.

## Research resources

- [Scientific result and limitations](https://github.com/Litju/football-performance-dynamics-bench/blob/v1.0.0/docs/res440/results.md)
- [Public result aggregates](https://github.com/Litju/football-performance-dynamics-bench/blob/v1.0.0/docs/res440/findings.json)
- [Prospective benchmark cards](https://github.com/Litju/football-performance-dynamics-bench/blob/v1.0.0/docs/public-benchmark-cards.md)
- [Source, baseline and model cards](https://github.com/Litju/football-performance-dynamics-bench/blob/v1.0.0/docs/public-data-and-model-cards.md)
- [Public reproduction walkthrough](https://github.com/Litju/football-performance-dynamics-bench/blob/v1.0.0/docs/public-reproduction-walkthrough.md)
- [Public aggregate-safe asset policy](https://github.com/Litju/football-performance-dynamics-bench/blob/v1.0.0/docs/public-asset-inventory.md)
- [Paper A submission-readiness record](https://github.com/Litju/football-performance-dynamics-bench/blob/v1.0.0/docs/paper-a/submission-readiness.md)
- [Interactive research companion](https://fpd-bench-showcase.vercel.app)
