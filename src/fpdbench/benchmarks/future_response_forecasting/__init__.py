"""Research family only; no historical executable benchmark was recovered."""

from fpdbench.benchmarks.base import (
    BenchmarkDefinition,
    BenchmarkIdentity,
    ExecutionStatus,
    InformationBoundary,
    ScientificMaturity,
    TechnicalTaskContract,
    TemporalContract,
)

FAMILY_ID = "future_response_forecasting"
BENCHMARK_ID = FAMILY_ID
RECONSTRUCTION_BLOCKERS = (
    "Causal history variables and modality whitelist are unrecovered.",
    "Ex-ante exposure definition and availability proof are unrecovered.",
    "Target, units, reference frame, horizon, cadence, and population are unrecovered.",
    "Dataset lineage, split, evaluator, viability evidence, and model lineage are unrecovered.",
)

BENCHMARK = BenchmarkDefinition(
    identity=BenchmarkIdentity(scientific_id=BENCHMARK_ID, family_id=FAMILY_ID, task_id=None),
    task=TechnicalTaskContract(
        inputs=(),
        targets=(),
        temporal=TemporalContract(),
        information_boundary=InformationBoundary(available_inputs=(), withheld_targets=()),
        population_semantics="Unrecovered.",
        data_state_binding=None,
        split_protocol_binding=None,
        evaluator_binding=None,
        execution_status=ExecutionStatus.UNRECOVERABLE,
        scientific_maturity=ScientificMaturity.UNRECOVERABLE,
        reconstruction_blockers=RECONSTRUCTION_BLOCKERS,
        non_claims=(
            (
                "Realized future opponent and ball paths are conditional response context, "
                "not ex-ante exposure."
            ),
            "No target, scorer, model, exposure, or horizon is assigned.",
        ),
    ),
)
