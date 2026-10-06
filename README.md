# Football Performance Dynamics Bench

Reproducible benchmarks for performance-state estimation, multimodal state reconstruction, response forecasting, and conditional multi-agent motion in association football.

## Research families

- `workload_performance_state`: whole-session estimation remains partial and unavailable; signed tangential acceleration is an invalidated historical formulation with a recovered RMSE evaluator.
- `multimodal_state_estimation`: a scoped negative pilot with no selected target family.
- `future_response_forecasting`: a research family with no recovered executable historical benchmark.
- `conditional_multi_agent_motion_prediction`: reconstructed conditional absolute-position behavior and an origin-relative displacement implementation surface.

Conditional multi-agent response uses realized future opponent and ball context while withholding the target team's future positions. Causal forecasting instead requires ex-ante available exposures and an explicit causal information boundary; the two tasks are not interchangeable.

Reproducibility binds benchmark definition, data state and membership, split protocol, evaluator, schema, fixtures, and scientific provenance in a deterministic scientific lock. Governance and hosting state live separately. Population semantics are independent of the dataset membership used in one study.

## Quickstart

```bash
uv sync
uv run pytest
uv run fpdbench benchmarks list
uv run fpdbench validate
```

Python 3.12 or newer is required. No private datasets or checkpoints are included.
