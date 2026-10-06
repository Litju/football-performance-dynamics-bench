"""Partial historical whole-session target family; execution is unavailable."""

from fpdbench.benchmarks.base import (
    BenchmarkDefinition,
    BenchmarkIdentity,
    ExecutionStatus,
    InformationBoundary,
    ScientificMaturity,
    TechnicalTaskContract,
    TemporalContract,
)

BENCHMARK_ID = "workload_performance_state/whole_session_performance_state"

BENCHMARK = BenchmarkDefinition(
    identity=BenchmarkIdentity(
        scientific_id=BENCHMARK_ID,
        family_id="workload_performance_state",
        task_id="whole_session_performance_state",
    ),
    task=TechnicalTaskContract(
        inputs=("synthetic exposure context", "session or player-week context"),
        targets=(
            "distance",
            "distance per minute",
            "peak speed",
            "high-speed running and sprint distance",
            "acceleration and event counts",
            "inertial sensor rate",
            "session rating of perceived exertion",
            "heart-rate-derived training impulse",
            "acute and chronic workload",
            "training monotony and strain",
        ),
        temporal=TemporalContract(),
        information_boundary=InformationBoundary(
            available_inputs=("session or player-week context",),
            withheld_targets=("whole-session performance outcomes",),
        ),
        population_semantics="Synthetic player-week grouped exposures; exact population unknown.",
        data_state_binding=None,
        split_protocol_binding=None,
        evaluator_binding=None,
        execution_status=ExecutionStatus.NON_EXECUTABLE,
        scientific_maturity=ScientificMaturity.PARTIAL,
        reconstruction_blockers=(
            "Original feature schema and exposure generator are unavailable.",
            "Target units, formulas, causal boundary, horizon, and population are unresolved.",
            "No independent evaluator or executable benchmark identity was recovered.",
            "No direct model binding survives.",
        ),
        non_claims=(
            "The task does not establish a separate causal future-response benchmark.",
            "Signed tangential-acceleration models are not whole-session experts.",
        ),
    ),
)
