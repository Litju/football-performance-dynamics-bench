# Football Performance Dynamics Bench

Reproducible benchmarks for performance-state estimation, multimodal state reconstruction, response forecasting, and conditional multi-agent motion in association football.

**Interactive research story:** [fpd-bench-showcase.vercel.app](https://fpd-bench-showcase.vercel.app) — a 3D, scroll-driven companion to Paper A showing what each information regime may see at the forecast origin and the four-match descriptive results. It is non-archival research communication built only from the public aggregate [findings](docs/res440/findings.json); pitch motion is schematic. Source and checks: [`site/`](site/README.md).

## Start here

1. **What FPD Bench investigates.** Conditional multi-agent motion prediction in football tracking data: given observed history, what can be predicted about a target team's positions, and how the answer depends on which future information (if any) the model may see. The information regimes (`history_only`, `future_ball`, `future_opponent_plus_ball`) are explicit and not interchangeable.
2. **What runs now.** The public checkout executes the benchmark definitions, transforms, evaluators, validators and synthetic regression references described in the [reproducibility model](docs/reproducibility.md). It contains no private datasets, tracking bytes, checkpoints or private truth. Run the checks in [Quickstart](#quickstart).
3. **What the evidence is.** The completed [four-match descriptive study](docs/res440/results.md) is research-only. Its independent unit is four matches, its protected population status is `NOT_QUALIFIED`, and it makes no significance, generalization, causal or deployment claims. The original 234-fit design is incomplete and the 216 training leave-one-match-out fits were never run.
4. **Paper A (methodology).** The benchmark-methodology manuscript, its [supplement](docs/paper-a/supplement.md) and [submission-readiness record](docs/paper-a/submission-readiness.md) are in `docs/paper-a/`. It presents one bounded descriptive demonstration on the four matches. The repository does not record a journal submission, peer review or publication status.
5. **Interactive companion.** The [research showcase](https://fpd-bench-showcase.vercel.app) is a non-archival communication aid built from the public findings file. Its pitch motion is schematic, not tracking data ([source](site/README.md)).
6. **Limits and release status.** Every public capability is labelled in the [capability matrix](docs/reproducibility.md#public-reproducibility-boundary) as `PUBLIC_EXECUTABLE`, `PUBLIC_VERIFIABLE`, `LOCAL_EVIDENCE_VERIFIABLE`, `UNAVAILABLE_PUBLIC_ARTIFACT` or `FORBIDDEN_PRIVATE_TRUTH`. This is a development version (`0.1.0.dev0`) without a tagged release, DOI, or `CITATION.cff`; see [licensing, attribution and citation policy](docs/licensing-and-governance.md).

## Public research cards

- [Prospective benchmark cards](docs/public-benchmark-cards.md): the absolute XY and origin-relative displacement target contracts, three information regimes, historical-versus-prospective identity, match-level evaluation and executable boundaries.
- [Source, baseline, model and limitations cards](docs/public-data-and-model-cards.md): the pinned SkillCorner source and rights scope, deterministic references, frozen DeepSets development/evaluation, observed tracking quality, uncertainty and responsible non-uses.
- [Public reproduction walkthrough](docs/public-reproduction-walkthrough.md): clean-clone CLI checks, an invented trajectory evaluator example, public aggregate arithmetic verification, source verification boundaries, LOMO interpretation and figure regeneration.

The cards describe research-only, four-match **descriptive** findings. They do not distribute SkillCorner rows, trained weights, private evidence, or authorize protected population qualification. The complete scientific authorities remain the versioned protocol, [published results](docs/res440/results.md), [Paper A evidence](docs/paper-a-evidence.md) and [data rights policy](docs/data-rights.md).

## Contributing and release state

The public research checkout is a **development distribution** (`0.1.0.dev0`), not an approved `v1.0.0` release. See the [changelog](CHANGELOG.md), [contribution and source-rights requirements](CONTRIBUTING.md), [software release gate and author/citation approvals](docs/software-release-gates.md), and [proposed release notes](docs/proposed-release-notes.md). No DOI, archival paper acceptance, protected population qualification or raw-data redistribution is implied.

## Research families

- `workload_performance_state`: a partial, non-executable whole-session historical study and an invalidated signed-acceleration formulation with a recovered diagnostic RMSE evaluator.
- `multimodal_state_estimation`: a scoped negative pilot with no selected target family.
- `future_response_forecasting`: a research family with no recovered historical benchmark or assigned target, scorer, model, or horizon.
- `conditional_multi_agent_motion_prediction`: the recovered absolute-position and origin-relative displacement benchmark identities; displacement reconstruction remains partial pending scorer/result parity.

The registry's executable benchmark identities are the recovered historical `conditional_multi_agent_motion_prediction/absolute_position_prediction` and `conditional_multi_agent_motion_prediction/origin_relative_displacement_prediction`. The separate [prospective SkillCorner protocol](docs/prospective-skillcorner-protocol.md) freezes two new pre-training identities without changing those historical locks. Families and research objects have separate discovery commands: `fpdbench families list` and `fpdbench research-objects list`.

Conditional multi-agent response uses realized future opponent and ball context while withholding the target team's future positions. Causal forecasting instead requires ex-ante available exposures and an explicit causal information boundary; the two tasks are not interchangeable.

See [the benchmark transition record](docs/benchmark-transitions.md) for the final R2 parity and lineage decisions.
See [the scientific evaluation library](docs/evaluation.md) for formulas, units, population semantics, zero-variance handling, and calibration limits.
See [Paper A's manuscript PDF](docs/paper-a/manuscript.pdf), [supplement](docs/paper-a/supplement.md), and [submission-readiness record](docs/paper-a/submission-readiness.md) for the complete review package.

See [Paper A's related-work and claim-evidence matrix](docs/paper-a-related-work-and-claims.md) for contribution scope, verified research references, and remaining scientific gaps.
See [Paper A's methods draft](docs/paper-a-methods.md) for the benchmark/evaluation framework and prospective study methodology.
See [Paper A's evidence package](docs/paper-a-evidence.md) for the benchmark/task and reproducibility matrices, genealogy, information-boundary and evaluation-design schematics, and the bounded four-match empirical demonstration.

Reproducibility binds benchmark definition, data state and membership, split protocol, evaluator, schema, fixtures, and scientific provenance in a deterministic scientific lock. Governance and hosting state live separately. Population semantics are independent of the dataset membership used in one study.

## Quickstart

This public smoke check needs no private data, model checkpoints, or external PR #25 fixture package:

```bash
uv sync --locked --python 3.12
uv run fpdbench benchmarks list
uv run fpdbench validate
uv run pytest -q tests/unit/test_validation.py
```

For the **complete test suite**, use the CPython 3.12 `uv sync --locked --all-groups` environment and first install the pinned PR #25 *synthetic source package* as described in [test prerequisites](docs/reproducibility.md#test-prerequisites). Running unrestricted `uv run pytest` without that prerequisite is not a valid full-suite verification. The `research-training` group pins CPU PyTorch 2.6.0; CPython 3.14 has no compatible wheel, and 3.13 was not tested here. No private datasets or checkpoints are included.

Original FPD Bench code and project-written documentation are licensed under [Apache-2.0](LICENSE). The license does not grant rights to upstream datasets, models, or artifacts; restricted artifact bytes are not distributed. See the [licensing, attribution, and citation policy](docs/licensing-and-governance.md).

## Data source and rights

The [football-motion results](docs/res440/results.md) report the completed
four-match descriptive study: physical trajectory errors, paired realized-context contrasts,
comparable history-only baselines, and scientific figures. These are research-only
descriptive findings; protected population status remains `NOT_QUALIFIED`.

The prospective [SkillCorner source card](docs/skillcorner-source-card.md), [FPD data card](docs/skillcorner-data-card.md), [Croissant/RAI JSON-LD draft](src/fpdbench/data_sources/skillcorner_croissant_rai_draft.json), and [machine-readable metadata status](src/fpdbench/data_sources/skillcorner_croissant_rai_status.json) document the source, measurement and eligibility contracts, RAI considerations, and current publication blockers. These cards describe a prospective research dataset; they do not announce a downloadable row-level release.

SkillCorner Open Data is an external prospective source; no SkillCorner data bytes are included here. The immutable upstream commit, selected source matches, file identities, acquisition contract, and drift checks are recorded in the [SkillCorner source authority](docs/skillcorner-source-authority.md). The rights boundary and attribution rules are in [the SkillCorner Open Data rights audit](docs/data-rights.md). Future studies must pin an upstream revision and explicit match list rather than identify the source as “whatever is currently published.”

The prospective 10 Hz to 5 Hz measurement transform, entity/missingness rules, and data-state identity are defined in the [SkillCorner 5 Hz measurement data state](docs/skillcorner-data-state.md) and can be verified offline with `fpdbench data-states verify`.

The additive nullable-ball successor is documented in the [v2 measurement](docs/skillcorner-data-state-v2.md), [v2 eligibility policy](docs/skillcorner-window-eligibility-v2.md), [v2 protocol](docs/prospective-skillcorner-protocol-v2.md), [v2 execution plan](docs/prospective-experiment-plan-v2.md), [protected population gate](docs/prospective-population-qualification-v2.md), and [v2 data card](docs/skillcorner-data-card-v2.md). Verify its authorities explicitly with `fpdbench data-states verify skillcorner_5hz_v2` and `fpdbench eligibility verify skillcorner_window_v2`.

The first [v2 population producer and independent-verifier handoff](docs/prospective-population-producer-v2.md) is synthetic-only and empirically unqualified.
