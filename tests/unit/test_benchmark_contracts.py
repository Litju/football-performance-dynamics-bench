from dataclasses import fields, replace

import pytest

from fpdbench import __version__
from fpdbench.benchmarks import (
    UNKNOWN,
    BenchmarkDefinition,
    BenchmarkIdentity,
    CanonicalSampling,
    ExecutionStatus,
    ResearchObjectDefinition,
    ResearchObjectIdentity,
    ResearchObjectType,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    ABSOLUTE_POSITION_BENCHMARK,
    DISPLACEMENT_BENCHMARK,
    HISTORY_HZ,
    HISTORY_STEPS,
    ORIGINAL_POSITION_DATA_STATE,
    REPAIRED_POSITION_DATA_STATE,
    TARGET_SHAPE,
    AbsolutePositionInputs,
    DisplacementInputs,
    ForecastOrigin,
    absolute_position_to_physical,
    evaluate_absolute_position_trajectories,
    evaluate_displacement,
    invert_origin_relative_displacement,
    make_absolute_position_target,
    make_origin_relative_displacement_target,
    normalized_displacement_to_physical,
    validate_information_boundary,
)
from fpdbench.benchmarks.future_response_forecasting import RESEARCH_OBJECT as FORECASTING
from fpdbench.benchmarks.multimodal_state_estimation import (
    CANDIDATE_TARGET_FAMILIES,
    MODALITIES,
    SELECTED_TARGET_FAMILY,
    TEMPORAL_ALIGNMENT,
    NativeSensorStream,
    TimestampedObservation,
)
from fpdbench.benchmarks.multimodal_state_estimation import RESEARCH_OBJECT as SENSOR_STATE
from fpdbench.benchmarks.registry import default_registry
from fpdbench.benchmarks.workload_performance_state import (
    DOCUMENTED_RMSE_INTERVAL_M_S2,
    SIGNED_TANGENTIAL_ACCELERATION_RESEARCH_OBJECT,
    WHOLE_SESSION_RESEARCH_OBJECT,
    evaluate_signed_tangential_acceleration,
)


def _frame(value: float) -> list[list[float]]:
    return [[value, value] for _ in range(11)]


def _trajectory(steps: int, value: float) -> list[list[list[float]]]:
    return [_frame(value) for _ in range(steps)]


def test_package_import_and_registry_discovery() -> None:
    assert __version__ == "0.1.0"
    registry = default_registry()
    assert len(registry.discover()) == 2
    assert len(registry.research_objects()) == 6
    assert (
        registry.lookup(ABSOLUTE_POSITION_BENCHMARK.identity.scientific_id)
        is ABSOLUTE_POSITION_BENCHMARK
    )
    assert len(registry.families()) == 4
    assert registry.discover("future_response_forecasting") == ()


def test_historical_alias_is_not_a_primary_identifier() -> None:
    registry = default_registry()
    alias = registry.aliases()[0]
    assert registry.resolve_alias(alias.value) == alias
    with pytest.raises(ValueError, match="provenance aliases"):
        registry.lookup(alias.value)
    assert (
        alias.canonical_id
        == registry.lookup_research_object(alias.canonical_id).identity.scientific_id
    )


def test_historical_negative_and_invalidated_objects_are_not_benchmarks() -> None:
    registry = default_registry()
    assert WHOLE_SESSION_RESEARCH_OBJECT.task.execution_status is ExecutionStatus.NON_EXECUTABLE
    assert WHOLE_SESSION_RESEARCH_OBJECT.task.reconstruction_blockers
    assert WHOLE_SESSION_RESEARCH_OBJECT.descriptor.research_object_type is (
        ResearchObjectType.HISTORICAL_STUDY
    )
    assert WHOLE_SESSION_RESEARCH_OBJECT.direct_model_bindings == ()
    assert isinstance(WHOLE_SESSION_RESEARCH_OBJECT.identity, ResearchObjectIdentity)
    assert not isinstance(WHOLE_SESSION_RESEARCH_OBJECT.identity, BenchmarkIdentity)
    assert FORECASTING.identity.task_id is None
    assert FORECASTING.descriptor.research_object_type is ResearchObjectType.RESEARCH_FAMILY
    assert FORECASTING.task.execution_status is ExecutionStatus.UNRECOVERABLE
    assert FORECASTING.task.targets == ()
    assert SENSOR_STATE.descriptor.research_object_type is ResearchObjectType.NEGATIVE_RESULT
    assert SENSOR_STATE.task.scientific_maturity.value == "negative"
    assert SELECTED_TARGET_FAMILY is None
    assert len(CANDIDATE_TARGET_FAMILIES) == 4
    assert (
        SIGNED_TANGENTIAL_ACCELERATION_RESEARCH_OBJECT.descriptor.research_object_type
        is ResearchObjectType.INVALIDATED_FORMULATION
    )
    assert SIGNED_TANGENTIAL_ACCELERATION_RESEARCH_OBJECT.task.scientific_maturity.value == (
        "invalidated"
    )
    for object_id in (
        WHOLE_SESSION_RESEARCH_OBJECT.identity.scientific_id,
        SENSOR_STATE.identity.scientific_id,
        SIGNED_TANGENTIAL_ACCELERATION_RESEARCH_OBJECT.identity.scientific_id,
        FORECASTING.identity.scientific_id,
    ):
        with pytest.raises(KeyError, match="not a benchmark"):
            registry.lookup(object_id)
    assert isinstance(ABSOLUTE_POSITION_BENCHMARK, BenchmarkDefinition)
    assert isinstance(DISPLACEMENT_BENCHMARK, BenchmarkDefinition)
    assert isinstance(ABSOLUTE_POSITION_BENCHMARK.identity, BenchmarkIdentity)
    assert len(registry.discover("conditional_multi_agent_motion_prediction")) == 2
    assert all(
        item.descriptor.research_object_type is ResearchObjectType.BENCHMARK
        for item in registry.discover()
    )
    assert SIGNED_TANGENTIAL_ACCELERATION_RESEARCH_OBJECT.task.temporal.target_hz == 10.0
    assert SENSOR_STATE.task.temporal.target_hz == 10.0
    assert SENSOR_STATE.descriptor.canonical_sampling.target_hz == 10.0
    with pytest.raises(ValueError, match="classification and definition type"):
        ResearchObjectDefinition(
            ABSOLUTE_POSITION_BENCHMARK.identity,
            ABSOLUTE_POSITION_BENCHMARK.descriptor,
            ABSOLUTE_POSITION_BENCHMARK.task,
        )
    with pytest.raises(ValueError, match="classification and definition type"):
        BenchmarkDefinition(
            WHOLE_SESSION_RESEARCH_OBJECT.identity,  # type: ignore[arg-type]
            WHOLE_SESSION_RESEARCH_OBJECT.descriptor,
            WHOLE_SESSION_RESEARCH_OBJECT.task,
        )


def test_all_registered_research_objects_have_typed_complete_descriptors() -> None:
    required_fields = (
        "public_name",
        "technical_name",
        "research_question",
        "scientific_task_type",
        "prediction_or_inference_target",
        "input_modalities",
        "conditioning_information",
        "information_boundary",
        "target_representation",
        "reference_frame",
        "history_contract",
        "horizon_contract",
        "canonical_sampling",
        "population_semantics",
        "unit_of_evaluation",
        "causal_status",
        "scientific_metric_family",
        "known_non_claims",
        "scientific_maturity",
        "research_object_type",
        "release_status",
    )
    for research_object in default_registry().research_objects():
        descriptor = research_object.descriptor
        assert descriptor.technical_name
        for name in required_fields:
            assert getattr(descriptor, name) is not None
    assert FORECASTING.descriptor.prediction_or_inference_target is UNKNOWN
    assert FORECASTING.descriptor.history_contract.duration_seconds is UNKNOWN
    classifications = {
        research_object.descriptor.research_object_type
        for research_object in default_registry().research_objects()
    }
    assert classifications == {
        ResearchObjectType.RESEARCH_FAMILY,
        ResearchObjectType.HISTORICAL_STUDY,
        ResearchObjectType.INVALIDATED_FORMULATION,
        ResearchObjectType.NEGATIVE_RESULT,
        ResearchObjectType.BENCHMARK,
    }


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
    future_positions = _trajectory(15, 0.0)
    for frame in future_positions:
        for point in frame:
            point[:] = [55.5, 37.0]
    history_times = [
        10.0 - (HISTORY_STEPS - 1 - index) / HISTORY_HZ for index in range(HISTORY_STEPS)
    ]
    origin = ForecastOrigin.from_observations(
        10.0,
        history_times,
        [
            "history_target_team_xy",
            "history_opponent_team_xy",
            "history_ball_xy",
            "realized_future_opponent_xy",
            "realized_future_ball_xy",
        ],
        target_origin_positions_m=origin_positions,
    )
    displacement = make_origin_relative_displacement_target(future_positions, origin)
    assert TARGET_SHAPE == (15, 11, 2)
    assert len(displacement) == 15 and len(displacement[0]) == 11
    assert displacement[0][0] == pytest.approx((1.0, 1.0))
    physical_displacement = normalized_displacement_to_physical(displacement)
    assert physical_displacement[0][0] == pytest.approx((52.5, 34.0))
    recovered_absolute = invert_origin_relative_displacement(displacement, origin)
    assert recovered_absolute[0][0] == pytest.approx((55.5, 37.0))
    assert recovered_absolute == tuple(
        tuple(tuple(point) for point in frame) for frame in future_positions
    )
    with pytest.raises(ValueError, match="15 time steps"):
        make_origin_relative_displacement_target(_trajectory(14, 0.0), origin)
    inputs = DisplacementInputs(
        history_target_team_xy_m=tuple(_trajectory(25, 3.0)),
        history_opponent_team_xy_m=tuple(_trajectory(25, 1.0)),
        history_ball_xy_m=tuple((0.0, 0.0) for _ in range(25)),
        realized_future_opponent_xy_m=tuple(_trajectory(15, 2.0)),
        realized_future_ball_xy_m=tuple((0.0, 0.0) for _ in range(15)),
        forecast_origin=origin,
    )
    assert len(inputs.history_target_team_xy_m) == 25
    assert len(inputs.realized_future_opponent_xy_m) == 15
    assert {field.name for field in fields(DisplacementInputs)}.isdisjoint(
        {"future_target_team_xy_m", "future_target_team_features"}
    )
    descriptor = DISPLACEMENT_BENCHMARK.descriptor
    assert descriptor.history_contract.duration_seconds == 5.0
    assert descriptor.horizon_contract.duration_seconds == 3.0
    assert descriptor.canonical_sampling.history_hz == 5.0
    assert descriptor.canonical_sampling.history_steps == 25
    assert descriptor.canonical_sampling.horizon_hz == 5.0
    assert descriptor.canonical_sampling.horizon_steps == 15
    assert descriptor.reference_frame == (
        "Per-player future displacement relative to the same player's exact observed position "
        "at the causal forecast origin."
    )
    seen: dict[str, object] = {}

    def evaluator(prediction: object, truth: object) -> dict[str, float]:
        seen["prediction"] = prediction
        seen["truth"] = truth
        return {"rows": float(len(prediction))}  # type: ignore[arg-type]

    result = evaluate_displacement(displacement, displacement, origin, evaluator)
    assert result == {"rows": 15.0}
    assert seen["prediction"] == invert_origin_relative_displacement(displacement, origin)
    assert DISPLACEMENT_BENCHMARK.identity.task_id == "origin_relative_displacement_prediction"

    wrong_origin = ForecastOrigin.from_observations(
        10.0,
        history_times,
        ["history_target_team_xy"],
        target_origin_positions_m=_frame(4.0),
    )
    with pytest.raises(ValueError, match="final observed target-team history frame"):
        DisplacementInputs(
            history_target_team_xy_m=tuple(_trajectory(25, 3.0)),
            history_opponent_team_xy_m=tuple(_trajectory(25, 1.0)),
            history_ball_xy_m=tuple((0.0, 0.0) for _ in range(25)),
            realized_future_opponent_xy_m=tuple(_trajectory(15, 2.0)),
            realized_future_ball_xy_m=tuple((0.0, 0.0) for _ in range(15)),
            forecast_origin=wrong_origin,
        )


def test_forecast_origin_rejects_future_information_and_target_leakage() -> None:
    with pytest.raises(ValueError, match="cross the causal"):
        ForecastOrigin.from_observations(1.0, [0.0, 1.1], ["observed_history"])
    with pytest.raises(ValueError, match="information-boundary"):
        ForecastOrigin.from_observations(1.0, [0.0, 1.0], ["future_target_team_xy"])
    with pytest.raises(ValueError, match="strictly increasing"):
        ForecastOrigin.from_observations(1.0, [0.0, 0.0], ["observed_history"])
    with pytest.raises(ValueError, match="observed at the forecast origin"):
        ForecastOrigin.from_observations(
            1.0,
            [0.0, 0.8],
            ["observed_history"],
            target_origin_positions_m=_frame(3.0),
        )


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


def test_identity_and_release_temporal_compatibility_are_separate() -> None:
    descriptor = DISPLACEMENT_BENCHMARK.descriptor
    source_only = replace(descriptor, source_sampling_hz=50.0)
    assert descriptor.scientific_identity_compatible_with(source_only)
    assert descriptor.release_compatible_with(source_only)

    grid_only = replace(
        descriptor,
        canonical_sampling=CanonicalSampling(
            history_hz=10.0,
            history_steps=50,
            horizon_hz=10.0,
            horizon_steps=30,
            target_hz=UNKNOWN,
        ),
    )
    assert descriptor.scientific_identity_compatible_with(grid_only)
    assert not descriptor.release_compatible_with(grid_only)

    changed_boundary = replace(
        descriptor,
        information_boundary=replace(
            descriptor.information_boundary,
            conditional_future_context=(),
        ),
    )
    assert not descriptor.scientific_identity_compatible_with(changed_boundary)
    assert not descriptor.release_compatible_with(changed_boundary)


def test_displacement_input_rejects_future_target_leakage_and_incomplete_origin() -> None:
    with pytest.raises(ValueError, match="information-boundary"):
        validate_information_boundary(("history_target_team_xy", "future_target_team_xy"))
    with pytest.raises(ValueError, match="15 time steps"):
        normalized_displacement_to_physical(_trajectory(14, 0.0))

    times = [10.0 - (HISTORY_STEPS - 1 - index) / HISTORY_HZ for index in range(HISTORY_STEPS)]
    missing_position_origin = ForecastOrigin.from_observations(
        10.0,
        times,
        ["observed_target_team_history"],
    )
    with pytest.raises(ValueError, match="must include the observed target-team XY frame"):
        make_origin_relative_displacement_target(_trajectory(15, 0.0), missing_position_origin)
    incomplete = ForecastOrigin.from_observations(
        10.0,
        times[1:],
        ["history_target_team_xy"],
        target_origin_positions_m=_frame(3.0),
    )
    with pytest.raises(ValueError, match="25 history timestamps"):
        DisplacementInputs(
            history_target_team_xy_m=tuple(_trajectory(25, 3.0)),
            history_opponent_team_xy_m=tuple(_trajectory(25, 1.0)),
            history_ball_xy_m=tuple((0.0, 0.0) for _ in range(25)),
            realized_future_opponent_xy_m=tuple(_trajectory(15, 2.0)),
            realized_future_ball_xy_m=tuple((0.0, 0.0) for _ in range(15)),
            forecast_origin=incomplete,
        )
