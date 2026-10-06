"""Causal origin-relative displacement target and evaluator interface."""

from collections.abc import Mapping, Sequence
from typing import Protocol

from fpdbench.benchmarks.base import (
    BenchmarkDefinition,
    BenchmarkIdentity,
    ExecutionStatus,
    InformationBoundary,
    ScientificMaturity,
    TechnicalTaskContract,
    TemporalContract,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.forecast_origin import (
    ForecastOrigin,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.geometry import (
    PositionTrajectory,
    immutable_xy_frame,
    immutable_xy_trajectory,
)

BENCHMARK_ID = "conditional_multi_agent_motion_prediction/origin_relative_displacement_prediction"
REFERENCE_FRAME = "per-player physical XY displacement from causal forecast-origin position"


class DisplacementEvaluator(Protocol):
    def __call__(
        self,
        prediction_absolute_m: PositionTrajectory,
        truth_absolute_m: PositionTrajectory,
    ) -> Mapping[str, float]: ...


def make_origin_relative_displacement_target(
    future_target_positions_m: Sequence[Sequence[Sequence[float]]],
    origin_target_positions_m: Sequence[Sequence[float]],
) -> PositionTrajectory:
    """Subtract each target's physical origin position from its future positions."""
    origin = immutable_xy_frame(
        origin_target_positions_m,
        expected_entities=11,
        name="origin target positions",
    )
    future = immutable_xy_trajectory(
        future_target_positions_m,
        expected_steps=None,
        expected_entities=11,
        name="future target positions",
    )
    return tuple(
        tuple(
            (x - origin_x, y - origin_y)
            for (x, y), (origin_x, origin_y) in zip(step, origin, strict=True)
        )
        for step in future
    )


def invert_origin_relative_displacement(
    displacement_m: Sequence[Sequence[Sequence[float]]],
    origin_target_positions_m: Sequence[Sequence[float]],
) -> PositionTrajectory:
    """Recover physical absolute XY as displacement plus origin position."""
    origin = immutable_xy_frame(
        origin_target_positions_m,
        expected_entities=11,
        name="origin target positions",
    )
    relative = immutable_xy_trajectory(
        displacement_m,
        expected_steps=None,
        expected_entities=11,
        name="origin-relative displacement target",
    )
    return tuple(
        tuple(
            (x + origin_x, y + origin_y)
            for (x, y), (origin_x, origin_y) in zip(step, origin, strict=True)
        )
        for step in relative
    )


def evaluate_displacement(
    prediction_displacement_m: Sequence[Sequence[Sequence[float]]],
    truth_displacement_m: Sequence[Sequence[Sequence[float]]],
    origin: ForecastOrigin,
    evaluator: DisplacementEvaluator,
) -> Mapping[str, float]:
    if origin.target_origin_positions_m is None:
        raise ValueError("forecast origin must include observed target positions")
    prediction_absolute = invert_origin_relative_displacement(
        prediction_displacement_m, origin.target_origin_positions_m
    )
    truth_absolute = invert_origin_relative_displacement(
        truth_displacement_m, origin.target_origin_positions_m
    )
    return evaluator(prediction_absolute, truth_absolute)


__all__ = [
    "BENCHMARK_ID",
    "REFERENCE_FRAME",
    "DisplacementEvaluator",
    "evaluate_displacement",
    "invert_origin_relative_displacement",
    "make_origin_relative_displacement_target",
]


BENCHMARK = BenchmarkDefinition(
    identity=BenchmarkIdentity(
        scientific_id=BENCHMARK_ID,
        family_id="conditional_multi_agent_motion_prediction",
        task_id="origin_relative_displacement_prediction",
    ),
    task=TechnicalTaskContract(
        inputs=("causal observations available through the forecast origin",),
        targets=(REFERENCE_FRAME,),
        temporal=TemporalContract(),
        information_boundary=InformationBoundary(
            available_inputs=("causal history through forecast origin",),
            withheld_targets=("future target-team positions",),
            forbidden_information=("future target truth",),
        ),
        population_semantics="Target-team entities defined by a future evidence-backed contract.",
        data_state_binding=None,
        split_protocol_binding=None,
        evaluator_binding=(
            "evaluator interface accepts reconstructed physical absolute trajectories"
        ),
        execution_status=ExecutionStatus.EXECUTABLE,
        scientific_maturity=ScientificMaturity.PARTIAL,
        reconstruction_blockers=(
            (
                "Exact historical horizon, split, scorer, and parity results remain "
                "for later reconstruction."
            ),
        ),
        non_claims=("No exact historical scoring values or horizon are assigned here.",),
    ),
)
DISPLACEMENT_BENCHMARK = BENCHMARK
