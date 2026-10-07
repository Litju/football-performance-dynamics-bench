"""Recovered conditional absolute-position target and input contracts."""

import math
from collections.abc import Sequence
from dataclasses import dataclass

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
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.geometry import (
    XY,
    PositionTrajectory,
    immutable_xy_trajectory,
    immutable_xy_vector,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.information import (
    validate_information_boundary,
)
from fpdbench.data import DataStateDescriptor
from fpdbench.evaluation.metrics import (
    PITCH_SCALE_M,
    TrajectoryMetrics,
    physical_trajectory_metrics,
)

BENCHMARK_ID = "conditional_multi_agent_motion_prediction/absolute_position_prediction"
HISTORY_SECONDS = 5.0
HISTORY_HZ = 5.0
HISTORY_STEPS = 25
HORIZON_SECONDS = 3.0
HORIZON_HZ = 5.0
HORIZON_STEPS = 15
TARGET_SHAPE = (HORIZON_STEPS, 11, 2)


@dataclass(frozen=True, slots=True)
class AbsolutePositionInputs:
    history_target_team_xy_m: PositionTrajectory
    history_opponent_team_xy_m: PositionTrajectory
    history_ball_xy_m: tuple[XY, ...]
    realized_future_opponent_xy_m: PositionTrajectory
    realized_future_ball_xy_m: tuple[XY, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "history_target_team_xy_m",
            immutable_xy_trajectory(
                self.history_target_team_xy_m,
                expected_steps=HISTORY_STEPS,
                expected_entities=11,
                name="history target-team XY",
            ),
        )
        object.__setattr__(
            self,
            "history_opponent_team_xy_m",
            immutable_xy_trajectory(
                self.history_opponent_team_xy_m,
                expected_steps=HISTORY_STEPS,
                expected_entities=11,
                name="history opponent-team XY",
            ),
        )
        history_ball = tuple(
            immutable_xy_vector(point, name="history ball XY") for point in self.history_ball_xy_m
        )
        if len(history_ball) != HISTORY_STEPS:
            raise ValueError("history ball XY must contain 25 time steps")
        object.__setattr__(self, "history_ball_xy_m", history_ball)
        object.__setattr__(
            self,
            "realized_future_opponent_xy_m",
            immutable_xy_trajectory(
                self.realized_future_opponent_xy_m,
                expected_steps=HORIZON_STEPS,
                expected_entities=11,
                name="realized future opponent-team XY",
            ),
        )
        future_ball = tuple(
            immutable_xy_vector(point, name="realized future ball XY")
            for point in self.realized_future_ball_xy_m
        )
        if len(future_ball) != HORIZON_STEPS:
            raise ValueError("realized future ball XY must contain 15 time steps")
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


def make_absolute_position_target(
    future_target_team_xy_m: Sequence[Sequence[Sequence[float]]],
    scale_xy_m: tuple[float, float] = PITCH_SCALE_M,
) -> PositionTrajectory:
    """Validate [15, 11, 2] and return pitch-normalized absolute future XY."""
    if any(not math.isfinite(value) or value <= 0 for value in scale_xy_m):
        raise ValueError("pitch scales must be finite and positive")
    physical = immutable_xy_trajectory(
        future_target_team_xy_m,
        expected_steps=HORIZON_STEPS,
        expected_entities=11,
        name="absolute-position target",
    )
    return tuple(
        tuple((x / scale_xy_m[0], y / scale_xy_m[1]) for x, y in step) for step in physical
    )


def absolute_position_to_physical(
    target_normalized: Sequence[Sequence[Sequence[float]]],
    scale_xy_m: tuple[float, float] = PITCH_SCALE_M,
) -> PositionTrajectory:
    normalized = immutable_xy_trajectory(
        target_normalized,
        expected_steps=HORIZON_STEPS,
        expected_entities=11,
        name="normalized absolute-position target",
    )
    if any(not math.isfinite(value) or value <= 0 for value in scale_xy_m):
        raise ValueError("pitch scales must be finite and positive")
    return tuple(
        tuple((x * scale_xy_m[0], y * scale_xy_m[1]) for x, y in step) for step in normalized
    )


def evaluate_absolute_position_trajectories(
    prediction_normalized: Sequence[PositionTrajectory],
    truth_normalized: Sequence[PositionTrajectory],
) -> TrajectoryMetrics:
    for name, batch in (("prediction", prediction_normalized), ("truth", truth_normalized)):
        if not batch:
            raise ValueError(f"{name} batch must be nonempty")
        for trajectory in batch:
            immutable_xy_trajectory(
                trajectory,
                expected_steps=HORIZON_STEPS,
                expected_entities=11,
                name=f"{name} target",
            )
    return physical_trajectory_metrics(
        prediction_normalized,
        truth_normalized,
        scale_xy_m=PITCH_SCALE_M,
    )


ORIGINAL_POSITION_DATA_STATE = DataStateDescriptor(
    state_id="original_position_measurement_state",
    version="historical",
    transformation="Select every fifth 25 Hz XY observation without interpolation.",
)
REPAIRED_POSITION_DATA_STATE = DataStateDescriptor(
    state_id="repaired_position_measurement_state",
    version="historical",
    transformation=(
        "Retain exact 25-to-5 Hz position selection and use causal endpoint velocity estimates."
    ),
)

_TASK = TechnicalTaskContract(
    inputs=(
        "25 observed scene steps at 5 Hz",
        "realized future opponent-team XY",
        "realized future ball XY",
    ),
    targets=("future target-team absolute pitch XY with shape [15, 11, 2]",),
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
        withheld_targets=(
            "future target-team XY",
            "future target-team-derived features",
        ),
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
    evaluator_binding="ADE, FDE, XY-RMSE in metres; population SRE is separately defined",
    execution_status=ExecutionStatus.PARTIAL,
    scientific_maturity=ScientificMaturity.PARTIAL,
    reconstruction_blockers=(
        (
            "The repaired and original data states are represented separately; "
            "data bytes are absent."
        ),
        "Private challenge data and checkpoints are not included or recomputed.",
        "No new scientific lock or public release is asserted.",
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
        task_id="absolute_position_prediction",
    ),
    descriptor=ScientificDescriptor.from_task(
        _TASK,
        public_name="Conditional multi-agent absolute-position prediction",
        technical_name="absolute_position_prediction",
        research_question=(
            "Given observed scene history and realized future opponent and ball positions, "
            "what are the target-team players' future positions?"
        ),
        scientific_task_type=ScientificTaskType.CONDITIONAL_RESPONSE_PREDICTION,
        prediction_or_inference_target=(
            "Future XY positions of 11 target-team players over 3 seconds."
        ),
        input_modalities=("player tracking XY", "ball tracking XY"),
        conditioning_information=(
            "observed target-team history",
            "observed opponent-team history",
            "observed ball history",
            "realized future opponent-team XY",
            "realized future ball XY",
        ),
        target_representation="Pitch-normalized absolute XY with shape [15, 11, 2].",
        reference_frame="Absolute pitch XY normalized by [52.5, 34.0] metres.",
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

ABSOLUTE_POSITION_BENCHMARK = BENCHMARK
