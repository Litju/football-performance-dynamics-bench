"""Recovered normalized origin-relative displacement benchmark contract."""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from fpdbench.benchmarks.base import (
    UNKNOWN,
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
    UnknownValue,
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
from fpdbench.evaluation.metrics import PITCH_SCALE_M, population_standardized_relative_error

from .absolute_position_prediction import (
    HISTORY_HZ,
    HISTORY_SECONDS,
    HISTORY_STEPS,
    HORIZON_HZ,
    HORIZON_SECONDS,
    HORIZON_STEPS,
)

BENCHMARK_ID = "conditional_multi_agent_motion_prediction/origin_relative_displacement_prediction"
HISTORICAL_FINAL_MODEL_ID = "historical_final_public_displacement_reference"
REFERENCE_FRAME = (
    "Per-player future displacement relative to the same player's exact observed position "
    "at the causal forecast origin."
)
TARGET_SHAPE = (HORIZON_STEPS, 11, 2)


@dataclass(frozen=True, slots=True)
class GeneratedCalibrationContract:
    """Known wrapper settings; the displacement calibration lock is absent."""

    lower_is_better: bool = True
    target_weight: float = 1.0
    floor: float = 1.0
    perfect: float = 0.0
    quality_floor_mode: str = "effective_no_info"
    naive_score_bounds: tuple[float, float] = (1e-6, 0.10)
    calibration_lock_state: UnknownValue = UNKNOWN
    reference_vector: tuple[float, ...] | UnknownValue = UNKNOWN
    no_information_ceiling_vector: tuple[float, ...] | UnknownValue = UNKNOWN
    x_ref: float | UnknownValue = UNKNOWN
    calibrated_reward: float | UnknownValue = UNKNOWN


@dataclass(frozen=True, slots=True)
class RawDisplacementEvaluatorConfiguration:
    metric_id: str = "sre.rmse_over_population_std.v1"
    target_type: str = "PopulationSRETarget"
    target_count: int = 330
    degrees_of_freedom: int = 0
    standard_deviation_population: str = "evaluated population truth per scalar target"
    per_target_weight: float = 1.0
    raw_clipping: None = None
    zero_variance_policy: str = "rmse"
    perfect_score: float = 0.0
    population_mean_predictor_sre: float = 1.0
    no_information_condition: str = "target variance is nonzero"
    generated_calibration: GeneratedCalibrationContract = GeneratedCalibrationContract()


RAW_DISPLACEMENT_EVALUATOR = RawDisplacementEvaluatorConfiguration()


@dataclass(frozen=True, slots=True)
class RawDisplacementSRE:
    per_scalar_sre: tuple[float, ...]
    raw_sre: float
    population_rows: int

    def __post_init__(self) -> None:
        if len(self.per_scalar_sre) != TARGET_SHAPE[0] * TARGET_SHAPE[1] * TARGET_SHAPE[2]:
            raise ValueError("raw displacement SRE must contain 330 scalar targets")
        if self.population_rows <= 0 or not math.isfinite(self.raw_sre):
            raise ValueError("raw displacement SRE requires a finite score and nonempty population")


def evaluate_raw_displacement_sre(
    prediction: Sequence[PositionTrajectory],
    truth: Sequence[PositionTrajectory],
) -> RawDisplacementSRE:
    """Score 330 scalars with evaluation-population SD and equal unit weights."""
    if not truth or len(prediction) != len(truth):
        raise ValueError("prediction and truth must have the same nonempty population")
    predicted_rows = tuple(
        immutable_xy_trajectory(
            row,
            expected_steps=HORIZON_STEPS,
            expected_entities=11,
            name=f"prediction[{index}]",
        )
        for index, row in enumerate(prediction)
    )
    truth_rows = tuple(
        immutable_xy_trajectory(
            row,
            expected_steps=HORIZON_STEPS,
            expected_entities=11,
            name=f"truth[{index}]",
        )
        for index, row in enumerate(truth)
    )
    scores = tuple(
        population_standardized_relative_error(
            [predicted_rows[row][step][player][coordinate] for row in range(len(truth_rows))],
            [truth_rows[row][step][player][coordinate] for row in range(len(truth_rows))],
            zero_variance="rmse",
        )
        for step in range(HORIZON_STEPS)
        for player in range(11)
        for coordinate in range(2)
    )
    return RawDisplacementSRE(
        per_scalar_sre=scores,
        raw_sre=math.fsum(scores) / len(scores),
        population_rows=len(truth_rows),
    )


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
    "GeneratedCalibrationContract",
    "RAW_DISPLACEMENT_EVALUATOR",
    "RawDisplacementEvaluatorConfiguration",
    "RawDisplacementSRE",
    "DisplacementEvaluator",
    "DisplacementInputs",
    "evaluate_displacement",
    "evaluate_raw_displacement_sre",
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
        target_hz=HORIZON_HZ,
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
    data_state_binding="repaired_position_measurement_state",
    split_protocol_binding="match_grouped_public_and_cross_match_splits",
    evaluator_binding="origin_relative_displacement_raw_population_sre",
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
    direct_model_bindings=(HISTORICAL_FINAL_MODEL_ID,),
)
DISPLACEMENT_BENCHMARK = BENCHMARK
