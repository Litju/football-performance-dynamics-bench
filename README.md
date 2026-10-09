# Football Performance Dynamics Bench

Reproducible benchmarks for performance-state estimation, multimodal state reconstruction, response forecasting, and conditional multi-agent motion in association football.

## Research families

- `workload_performance_state`: a partial, non-executable whole-session historical study and an invalidated signed-acceleration formulation with a recovered diagnostic RMSE evaluator.
- `multimodal_state_estimation`: a scoped negative pilot with no selected target family.
- `future_response_forecasting`: a research family with no recovered historical benchmark or assigned target, scorer, model, or horizon.
- `conditional_multi_agent_motion_prediction`: the recovered absolute-position and origin-relative displacement benchmark identities; displacement reconstruction remains partial pending scorer/result parity.

Only `conditional_multi_agent_motion_prediction/absolute_position_prediction` and `conditional_multi_agent_motion_prediction/origin_relative_displacement_prediction` are benchmark identities. Families and research objects have separate discovery commands: `fpdbench families list` and `fpdbench research-objects list`.

Conditional multi-agent response uses realized future opponent and ball context while withholding the target team's future positions. Causal forecasting instead requires ex-ante available exposures and an explicit causal information boundary; the two tasks are not interchangeable.

See [the benchmark transition record](docs/benchmark-transitions.md) for the final R2 parity and lineage decisions.
See [the scientific evaluation library](docs/evaluation.md) for formulas, units, population semantics, zero-variance handling, and calibration limits.

Reproducibility binds benchmark definition, data state and membership, split protocol, evaluator, schema, fixtures, and scientific provenance in a deterministic scientific lock. Governance and hosting state live separately. Population semantics are independent of the dataset membership used in one study.

## Quickstart

```bash
uv sync
uv run pytest
uv run fpdbench benchmarks list
uv run fpdbench validate
```

Python 3.12 or newer is required. No private datasets or checkpoints are included.

This public research-software repository is under active release preparation, and licensing is not finalized. Public visibility does not grant redistribution rights for referenced datasets, models, or artifacts; restricted artifact bytes are not distributed.

## Data source and rights

SkillCorner Open Data is an external prospective source; no SkillCorner data bytes are included here. The immutable upstream commit, selected source matches, file identities, acquisition contract, and drift checks are recorded in the [SkillCorner source authority](docs/skillcorner-source-authority.md). The rights boundary and attribution rules are in [the SkillCorner Open Data rights audit](docs/data-rights.md). Future studies must pin an upstream revision and explicit match list rather than identify the source as “whatever is currently published.”

The prospective 10 Hz to 5 Hz measurement transform, entity/missingness rules, and data-state identity are defined in the [SkillCorner 5 Hz measurement data state](docs/skillcorner-data-state.md) and can be verified offline with `fpdbench data-states verify`.
