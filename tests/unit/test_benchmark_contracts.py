from dataclasses import fields

import pytest

from fpdbench import __version__
from fpdbench.benchmarks import ExecutionStatus, TemporalContract
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    ABSOLUTE_POSITION_BENCHMARK,
    DISPLACEMENT_BENCHMARK,
    ORIGINAL_POSITION_DATA_STATE,
    REPAIRED_POSITION_DATA_STATE,
    TARGET_SHAPE,
    AbsolutePositionInputs,
    ForecastOrigin,
    absolute_position_to_physical,
    evaluate_absolute_position_trajectories,
    evaluate_displacement,
    invert_origin_relative_displacement,
    make_absolute_position_target,
    make_origin_relative_displacement_target,
    validate_information_boundary,
)
from fpdbench.benchmarks.future_response_forecasting import BENCHMARK as FORECASTING
from fpdbench.benchmarks.multimodal_state_estimation import (
    BENCHMARK as SENSOR_STATE,
)
from fpdbench.benchmarks.multimodal_state_estimation import (
    CANDIDATE_TARGET_FAMILIES,
    MODALITIES,
    SELECTED_TARGET_FAMILY,
    TEMPORAL_ALIGNMENT,
    NativeSensorStream,
    TimestampedObservation,
)
from fpdbench.benchmarks.registry import default_registry
from fpdbench.benchmarks.workload_performance_state import (
    DOCUMENTED_RMSE_INTERVAL_M_S2,
    SIGNED_TANGENTIAL_ACCELERATION_BENCHMARK,
    WHOLE_SESSION_BENCHMARK,
    evaluate_signed_tangential_acceleration,
)


def _frame(value: float) -> list[list[float]]:
    return [[value, value] for _ in range(11)]


def _trajectory(steps: int, value: float) -> list[list[list[float]]]:
    return [_frame(value) for _ in range(steps)]


def test_package_import_and_registry_discovery() -> None:
    assert __version__ == "0.1.0"
    registry = default_registry()
    assert len(registry.discover()) == 6
    assert (
        registry.lookup(ABSOLUTE_POSITION_BENCHMARK.identity.scientific_id)
        is ABSOLUTE_POSITION_BENCHMARK
    )
    assert set(registry.families()) == {
        "workload_performance_state",
        "multimodal_state_estimation",
        "future_response_forecasting",
        "conditional_multi_agent_motion_prediction",
    }


def test_historical_alias_is_not_a_primary_identifier() -> None:
    registry = default_registry()
    alias = registry.aliases()[0]
    assert registry.resolve_alias(alias.value) == alias
    with pytest.raises(ValueError, match="provenance aliases"):
        registry.lookup(alias.value)
    assert alias.canonical_id == registry.lookup(alias.canonical_id).identity.scientific_id


def test_unavailable_and_unrecovered_benchmarks_are_explicit() -> None:
    assert WHOLE_SESSION_BENCHMARK.task.execution_status is ExecutionStatus.NON_EXECUTABLE
    assert WHOLE_SESSION_BENCHMARK.task.reconstruction_blockers
    assert FORECASTING.identity.task_id is None
    assert FORECASTING.task.execution_status is ExecutionStatus.UNRECOVERABLE
    assert FORECASTING.task.targets == ()
    assert SENSOR_STATE.task.scientific_maturity.value == "negative"
    assert SELECTED_TARGET_FAMILY is None
    assert len(CANDIDATE_TARGET_FAMILIES) == 4
    assert SIGNED_TANGENTIAL_ACCELERATION_BENCHMARK.task.scientific_maturity.value == "invalidated"
    assert SIGNED_TANGENTIAL_ACCELERATION_BENCHMARK.task.temporal.target_hz == 10.0
    assert SENSOR_STATE.task.temporal.target_hz == 10.0


def test_signed_acceleration_uses_full_row_rmse_for_supported_vectors() -> None:
    first = evaluate_signed_tangential_acceleration([0.0, 1.0, 2.0], [0.0, 0.0, 0.0])
    second = evaluate_signed_tangential_acceleration([0.0, 1.0], [0.0, 0.0])
    assert first.rmse_m_s2 == pytest.approx(5**0.5 / 3**0.5)
    assert first.scored_samples == 3
    assert second.rmse_m_s2 == pytest.approx(2**-0.5)
    assert DOCUMENTED_RMSE_INTERVAL_M_S2 == (0.04, 0.075)


def test_absolute_position_contract_shapes_scaling_and_future_exclusion() -> None:
    physical = _trajectory(15, 0.0)
    physical[0][0] = [52.5, 34.0]
    target = make_absolute_position_target(physical)
    assert len(target) == 15 and len(target[0]) == 11 and len(target[0][0]) == 2
    assert target[0][0] == (1.0, 1.0)
    assert TARGET_SHAPE == (15, 11, 2)
    assert absolute_position_to_physical(target)[0][0] == pytest.approx((52.5, 34.0))
    assert ABSOLUTE_POSITION_BENCHMARK.task.temporal.history_seconds == 5.0
    assert ABSOLUTE_POSITION_BENCHMARK.task.temporal.history_hz == 5.0
    assert ABSOLUTE_POSITION_BENCHMARK.task.temporal.history_steps == 25
    assert ABSOLUTE_POSITION_BENCHMARK.task.temporal.horizon_seconds == 3.0
    assert ABSOLUTE_POSITION_BENCHMARK.task.temporal.horizon_hz == 5.0
    assert ABSOLUTE_POSITION_BENCHMARK.task.temporal.horizon_steps == 15
    assert ABSOLUTE_POSITION_BENCHMARK.task.information_boundary.conditional_future_context == (
        "realized future opponent-team XY",
        "realized future ball XY",
    )
    with pytest.raises(ValueError, match="15 time steps"):
        make_absolute_position_target(_trajectory(14, 0.0))
    assert "future_target_team_xy_m" not in {field.name for field in fields(AbsolutePositionInputs)}
    validate_information_boundary(("history_target_team_xy", "realized_future_opponent_xy"))
    with pytest.raises(ValueError, match="information-boundary"):
        validate_information_boundary(("future_target_team_xy",))


def test_absolute_position_inputs_validate_history_and_realized_context_shapes() -> None:
    inputs = AbsolutePositionInputs(
        history_target_team_xy_m=tuple(_trajectory(25, 0.0)),
        history_opponent_team_xy_m=tuple(_trajectory(25, 0.0)),
        history_ball_xy_m=tuple((0.0, 0.0) for _ in range(25)),
        realized_future_opponent_xy_m=tuple(_trajectory(15, 0.0)),
        realized_future_ball_xy_m=tuple((0.0, 0.0) for _ in range(15)),
    )
    assert len(inputs.history_target_team_xy_m) == 25
    assert len(inputs.realized_future_opponent_xy_m) == 15
    with pytest.raises(ValueError, match="25 time steps"):
        AbsolutePositionInputs(
            history_target_team_xy_m=tuple(_trajectory(24, 0.0)),
            history_opponent_team_xy_m=tuple(_trajectory(25, 0.0)),
            history_ball_xy_m=tuple((0.0, 0.0) for _ in range(25)),
            realized_future_opponent_xy_m=tuple(_trajectory(15, 0.0)),
            realized_future_ball_xy_m=tuple((0.0, 0.0) for _ in range(15)),
        )


def test_physical_trajectory_metrics_are_global_and_pitch_scaled() -> None:
    prediction = _trajectory(15, 0.0)
    truth = _trajectory(15, 0.0)
    prediction[0][0][0] = 0.01
    metrics = evaluate_absolute_position_trajectories([prediction], [truth])
    assert metrics.ade_m == pytest.approx(0.525 / (15 * 11))
    assert metrics.fde_m == pytest.approx(0.0)
    assert metrics.xy_rmse_m == pytest.approx(0.525 / (15 * 11 * 2) ** 0.5)
    prediction = _trajectory(15, 0.0)
    truth = _trajectory(15, 0.0)
    prediction[-1][0][0] = 0.01
    metrics = evaluate_absolute_position_trajectories([prediction], [truth])
    assert metrics.fde_m == pytest.approx(0.525 / 11)


def test_original_and_repaired_data_states_are_separate() -> None:
    assert ORIGINAL_POSITION_DATA_STATE.state_id != REPAIRED_POSITION_DATA_STATE.state_id
    assert "every fifth" in ORIGINAL_POSITION_DATA_STATE.transformation
    assert "causal endpoint" in REPAIRED_POSITION_DATA_STATE.transformation


def test_displacement_target_round_trip_and_causal_origin() -> None:
    origin_positions = _frame(3.0)
    future_positions = _trajectory(2, 0.0)
    for frame in future_positions:
        for point in frame:
            point[:] = [4.0, 5.0]
    displacement = make_origin_relative_displacement_target(future_positions, origin_positions)
    assert displacement[0][0] == (1.0, 2.0)
    assert invert_origin_relative_displacement(displacement, origin_positions)[0][0] == (4.0, 5.0)
    origin = ForecastOrigin.from_observations(
        10.0,
        [9.0, 9.5, 10.0],
        ["observed_history", "origin_target_positions"],
        target_origin_positions_m=origin_positions,
    )
    seen: dict[str, object] = {}

    def evaluator(prediction: object, truth: object) -> dict[str, float]:
        seen["prediction"] = prediction
        seen["truth"] = truth
        return {"rows": float(len(prediction))}  # type: ignore[arg-type]

    result = evaluate_displacement(displacement, displacement, origin, evaluator)
    assert result == {"rows": 2.0}
    assert seen["prediction"] == invert_origin_relative_displacement(displacement, origin_positions)
    assert DISPLACEMENT_BENCHMARK.identity.task_id == "origin_relative_displacement_prediction"


def test_forecast_origin_rejects_future_information_and_target_leakage() -> None:
    with pytest.raises(ValueError, match="cross the causal"):
        ForecastOrigin.from_observations(1.0, [0.0, 1.1], ["observed_history"])
    with pytest.raises(ValueError, match="information-boundary"):
        ForecastOrigin.from_observations(1.0, [0.0, 1.0], ["future_target_team_xy"])
    with pytest.raises(ValueError, match="strictly increasing"):
        ForecastOrigin.from_observations(1.0, [0.0, 0.0], ["observed_history"])


def test_sensor_modalities_and_causal_alignment_prefix() -> None:
    assert len(MODALITIES) == 4
    assert TEMPORAL_ALIGNMENT.candidate_target_hz == 10.0
    assert TEMPORAL_ALIGNMENT.representation_selected is False
    stream = NativeSensorStream(
        "IMU",
        (
            TimestampedObservation(0.0, (1.0,)),
            TimestampedObservation(0.1, (2.0,)),
            TimestampedObservation(0.2, (3.0,)),
        ),
    )
    assert tuple(item.timestamp_s for item in stream.causal_prefix(0.1)) == (0.0, 0.1)
    assert stream.causal_prefix(-1.0) == ()


def test_temporal_grid_change_is_not_compatible() -> None:
    original = TemporalContract(history_seconds=5.0, history_hz=5.0, history_steps=25)
    changed = TemporalContract(history_seconds=5.0, history_hz=10.0, history_steps=50)
    assert original.canonical_grid_compatible_with(original)
    assert not original.canonical_grid_compatible_with(changed)
