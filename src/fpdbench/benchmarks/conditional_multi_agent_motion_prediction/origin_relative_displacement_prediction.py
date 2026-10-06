"""Recovered normalized origin-relative displacement benchmark contract."""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from fpdbench.benchmarks.base import (
    BenchmarkDefinition,
    BenchmarkIdentity,
    CausalStatus,
    ExecutionStatus,
    InformationBoundary,
    ResearchObjectType,
    ScientificDescriptor,
    ScientificMaturity,
    ScientificTaskType,
    TechnicalTaskContract,
    TemporalContract,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.forecast_origin import (
    ForecastOrigin,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.geometry import (
    PositionTrajectory,
    immutable_xy_trajectory,
    immutable_xy_vector,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.information import (
    validate_information_boundary,
)
from fpdbench.evaluation.metrics import PITCH_SCALE_M

from .absolute_position_prediction import (
    HISTORY_HZ,
    HISTORY_SECONDS,
    HISTORY_STEPS,
    HORIZON_HZ,
    HORIZON_SECONDS,
    HORIZON_STEPS,
)

BENCHMARK_ID = "conditional_multi_agent_motion_prediction/origin_relative_displacement_prediction"
REFERENCE_FRAME = (
    "Per-player future displacement relative to the same player's exact observed position "
    "at the causal forecast origin."
)
TARGET_SHAPE = (HORIZON_STEPS, 11, 2)


@dataclass(frozen=True, slots=True)
class DisplacementInputs:
    history_target_team_xy_m: PositionTrajectory
    history_opponent_team_xy_m: PositionTrajectory
    history_ball_xy_m: tuple[tuple[float, float], ...]
    realized_future_opponent_xy_m: PositionTrajectory
    realized_future_ball_xy_m: tuple[tuple[float, float], ...]
    forecast_origin: ForecastOrigin

    def __post_init__(self) -> None:
        history_target = immutable_xy_trajectory(
            self.history_target_team_xy_m,
            expected_steps=HISTORY_STEPS,
            expected_entities=11,
            name="history target-team XY",
        )
        history_opponent = immutable_xy_trajectory(
            self.history_opponent_team_xy_m,
            expected_steps=HISTORY_STEPS,
            expected_entities=11,
            name="history opponent-team XY",
        )
        history_ball = tuple(
            immutable_xy_vector(point, name="history ball XY") for point in self.history_ball_xy_m
        )
        if len(history_ball) != HISTORY_STEPS:
            raise ValueError("history ball XY must contain 25 time steps")
        future_opponent = immutable_xy_trajectory(
            self.realized_future_opponent_xy_m,
            expected_steps=HORIZON_STEPS,
            expected_entities=11,
            name="realized future opponent-team XY",
        )
        future_ball = tuple(
            immutable_xy_vector(point, name="realized future ball XY")
            for point in self.realized_future_ball_xy_m
        )
        if len(future_ball) != HORIZON_STEPS:
            raise ValueError("realized future ball XY must contain 15 time steps")

        origin = self.forecast_origin
        if origin.target_origin_positions_m is None:
            raise ValueError("forecast origin must include the observed target-team XY frame")
        if len(origin.available_information_times_s) != HISTORY_STEPS:
            raise ValueError("forecast origin must bind all 25 history timestamps")
        times = origin.available_information_times_s
        expected_interval = 1.0 / HISTORY_HZ
        if any(
            not math.isclose(right - left, expected_interval, rel_tol=0.0, abs_tol=1e-9)
            for left, right in zip(times, times[1:], strict=False)
        ):
            raise ValueError("history timestamps must use the canonical 5 Hz sampling interval")
        if origin.target_origin_positions_m != history_target[-1]:
            raise ValueError(
                "target origin must equal the final observed target-team history frame"
            )

        object.__setattr__(self, "history_target_team_xy_m", history_target)
        object.__setattr__(self, "history_opponent_team_xy_m", history_opponent)
        object.__setattr__(self, "history_ball_xy_m", history_ball)
        object.__setattr__(self, "realized_future_opponent_xy_m", future_opponent)
        object.__setattr__(self, "realized_future_ball_xy_m", future_ball)
        validate_information_boundary(self.feature_names)

    @property
    def feature_names(self) -> tuple[str, ...]:
        return (
            "history_target_team_xy",
            "history_opponent_team_xy",
            "history_ball_xy",
            "realized_future_opponent_xy",
            "realized_future_ball_xy",
        )


class DisplacementEvaluator(Protocol):
    def __call__(
        self,
        prediction_absolute_m: PositionTrajectory,
        truth_absolute_m: PositionTrajectory,
    ) -> Mapping[str, float]: ...


def make_origin_relative_displacement_target(
    future_target_positions_m: Sequence[Sequence[Sequence[float]]],
    origin: ForecastOrigin,
) -> PositionTrajectory:
    """Return fixed [15, 11, 2] displacement normalized by the pitch dimensions."""
    if origin.target_origin_positions_m is None:
        raise ValueError("forecast origin must include the observed target-team XY frame")
    origin_positions = origin.target_origin_positions_m
    future = immutable_xy_trajectory(
        future_target_positions_m,
        expected_steps=HORIZON_STEPS,
        expected_entities=11,
        name="future target positions",
    )
    return tuple(
        tuple(
            ((x - origin_x) / PITCH_SCALE_M[0], (y - origin_y) / PITCH_SCALE_M[1])
            for (x, y), (origin_x, origin_y) in zip(step, origin_positions, strict=True)
        )
        for step in future
    )


def normalized_displacement_to_physical(
    displacement_normalized: Sequence[Sequence[Sequence[float]]],
) -> PositionTrajectory:
    """Convert pitch-normalized displacements to physical metres."""
    normalized = immutable_xy_trajectory(
        displacement_normalized,
        expected_steps=HORIZON_STEPS,
        expected_entities=11,
        name="normalized displacement target",
    )
    return tuple(
        tuple((x * PITCH_SCALE_M[0], y * PITCH_SCALE_M[1]) for x, y in frame)
        for frame in normalized
    )


def invert_origin_relative_displacement(
    displacement_normalized: Sequence[Sequence[Sequence[float]]],
    origin: ForecastOrigin,
) -> PositionTrajectory:
    """Recover physical absolute XY from normalized displacement and exact origin XY."""
    if origin.target_origin_positions_m is None:
        raise ValueError("forecast origin must include observed target positions")
    origin_positions = origin.target_origin_positions_m
    physical = normalized_displacement_to_physical(displacement_normalized)
    return tuple(
        tuple(
            (delta_x + origin_x, delta_y + origin_y)
            for (delta_x, delta_y), (origin_x, origin_y) in zip(
                frame, origin_positions, strict=True
            )
        )
        for frame in physical
    )


def evaluate_displacement(
    prediction_normalized: Sequence[Sequence[Sequence[float]]],
    truth_normalized: Sequence[Sequence[Sequence[float]]],
    origin: ForecastOrigin,
    evaluator: DisplacementEvaluator,
) -> Mapping[str, float]:
    if origin.target_origin_positions_m is None:
        raise ValueError("forecast origin must include observed target positions")
    prediction_absolute = invert_origin_relative_displacement(prediction_normalized, origin)
    truth_absolute = invert_origin_relative_displacement(truth_normalized, origin)
    return evaluator(prediction_absolute, truth_absolute)


__all__ = [
    "BENCHMARK_ID",
    "REFERENCE_FRAME",
    "TARGET_SHAPE",
    "DisplacementEvaluator",
    "DisplacementInputs",
    "evaluate_displacement",
    "invert_origin_relative_displacement",
    "make_origin_relative_displacement_target",
    "normalized_displacement_to_physical",
]


_TASK = TechnicalTaskContract(
    inputs=(
        "observed target-team history",
        "observed opponent-team history",
        "observed ball history",
        "realized future opponent-team XY",
        "realized future ball XY",
    ),
    targets=("normalized future displacement, shape [15, 11, 2], divided by [52.5, 34.0] metres",),
    temporal=TemporalContract(
        history_seconds=HISTORY_SECONDS,
        history_hz=HISTORY_HZ,
        history_steps=HISTORY_STEPS,
        horizon_seconds=HORIZON_SECONDS,
        horizon_hz=HORIZON_HZ,
        horizon_steps=HORIZON_STEPS,
    ),
    information_boundary=InformationBoundary(
        available_inputs=(
            "observed target-team history",
            "observed opponent-team history",
            "observed ball history",
        ),
        withheld_targets=("future target-team XY", "future target-team-derived features"),
        forbidden_information=(
            "future target-team features",
            "future aggregates",
            "event labels",
            "score",
            "absolute timestamp",
            "file identity",
            "row order",
            "target encoding",
            "numeric player, team, or match identifiers",
        ),
        conditional_future_context=(
            "realized future opponent-team XY",
            "realized future ball XY",
        ),
    ),
    population_semantics="Directed target-team player trajectories within evaluated match windows.",
    data_state_binding=None,
    split_protocol_binding=None,
    evaluator_binding=None,
    execution_status=ExecutionStatus.PARTIAL,
    scientific_maturity=ScientificMaturity.PARTIAL,
    reconstruction_blockers=(
        "Historical scorer/result parity remains incomplete.",
        "The displacement-specific GeneratedCalibration lock is unrecovered and is not inferred.",
    ),
    non_claims=(
        (
            "Realized future opponent and ball paths are conditional context, "
            "not an ex-ante exposure forecast."
        ),
        "The target team's future positions are never model inputs.",
    ),
)

BENCHMARK = BenchmarkDefinition(
    identity=BenchmarkIdentity(
        scientific_id=BENCHMARK_ID,
        family_id="conditional_multi_agent_motion_prediction",
        task_id="origin_relative_displacement_prediction",
    ),
    descriptor=ScientificDescriptor.from_task(
        _TASK,
        public_name="Conditional multi-agent origin-relative displacement prediction",
        technical_name="origin_relative_displacement_prediction",
        research_question=(
            "Given observed scene history and realized future opponent and ball positions, "
            "what are the target-team players' future displacements from their exact origin XY?"
        ),
        scientific_task_type=ScientificTaskType.CONDITIONAL_RESPONSE_PREDICTION,
        prediction_or_inference_target=(
            "Normalized future XY displacement for 11 target-team players over 3 seconds."
        ),
        input_modalities=("player tracking XY", "ball tracking XY"),
        conditioning_information=(
            "observed target-team history",
            "observed opponent-team history",
            "observed ball history",
            "realized future opponent-team XY",
            "realized future ball XY",
        ),
        target_representation=(
            "(future target XY minus exact causal-origin target XY) / [52.5, 34.0], "
            "shape [15, 11, 2]."
        ),
        reference_frame=REFERENCE_FRAME,
        history_interpretation="Observed scene history available through the forecast origin.",
        horizon_interpretation="Future target-team response over the 3-second horizon.",
        source_sampling_hz=25.0,
        unit_of_evaluation="Target-team player trajectory within a match window.",
        causal_status=CausalStatus.CONDITIONAL_ON_REALIZED_FUTURE_CONTEXT,
        scientific_metric_family=("ADE", "FDE", "XY-RMSE", "population SRE"),
        research_object_type=ResearchObjectType.BENCHMARK,
    ),
    task=_TASK,
)
DISPLACEMENT_BENCHMARK = BENCHMARK
