"""Supported full-row RMSE behavior for the invalidated 10 Hz formulation."""

from collections.abc import Sequence
from dataclasses import dataclass

from fpdbench.benchmarks.base import (
    BenchmarkDefinition,
    BenchmarkIdentity,
    ExecutionStatus,
    InformationBoundary,
    ScientificMaturity,
    TechnicalTaskContract,
    TemporalContract,
)
from fpdbench.evaluation.metrics.relative_error import rmse

BENCHMARK_ID = "workload_performance_state/signed_tangential_acceleration_estimation"
DOCUMENTED_RMSE_INTERVAL_M_S2 = (0.04, 0.075)


@dataclass(frozen=True, slots=True)
class SignedTangentialAccelerationEvaluation:
    rmse_m_s2: float
    scored_samples: int
    normalization: str = "none"
    aggregation: str = "global full-row RMSE"


def evaluate_signed_tangential_acceleration(
    prediction_m_s2: Sequence[float], truth_m_s2: Sequence[float]
) -> SignedTangentialAccelerationEvaluation:
    """Return the recovered global RMSE; no lost B5 submetric is inferred."""
    return SignedTangentialAccelerationEvaluation(
        rmse_m_s2=rmse(prediction_m_s2, truth_m_s2),
        scored_samples=len(truth_m_s2),
    )


BENCHMARK = BenchmarkDefinition(
    identity=BenchmarkIdentity(
        scientific_id=BENCHMARK_ID,
        family_id="workload_performance_state",
        task_id="signed_tangential_acceleration_estimation",
    ),
    task=TechnicalTaskContract(
        inputs=("causal GNSS and inertial sensor history", "public player-session context"),
        targets=("signed horizontal tangential acceleration in metres per second squared",),
        temporal=TemporalContract(target_hz=10.0),
        information_boundary=InformationBoundary(
            available_inputs=("causal sensor history", "public player-session context"),
            withheld_targets=("clean signed tangential acceleration at the scored sample",),
            forbidden_information=("future sensor observations",),
        ),
        population_semantics="Grouped synthetic exposures; exact target population unresolved.",
        data_state_binding=None,
        split_protocol_binding=None,
        evaluator_binding="global full-row RMSE, no normalization",
        execution_status=ExecutionStatus.PARTIAL,
        scientific_maturity=ScientificMaturity.INVALIDATED,
        reconstruction_blockers=(
            "The exact feature whitelist and data binding are partial.",
            "A split identifier crosswalk remains unresolved.",
            "The historical B5 raw single-channel submetric formula and aggregation are lost.",
        ),
        non_claims=(
            "The recovered RMSE does not restore the invalidated benchmark formulation.",
            "No unrecovered single-channel submetric is supplied.",
        ),
    ),
)
