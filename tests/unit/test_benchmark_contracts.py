import json
from dataclasses import fields, replace
from importlib.metadata import version
from pathlib import Path

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
    CORRECTED_AGGREGATION,
    CORRECTED_LOMO_AGGREGATE,
    CORRECTED_LOMO_GRAND_MEAN_RAW_SRE,
    DISPLACEMENT_BENCHMARK,
    DISPLACEMENT_DATA_STATE,
    DISPLACEMENT_DATA_STATE_EVIDENCE,
    DISPLACEMENT_FEATURE_COUNT,
    DISPLACEMENT_SPLIT,
    DISPLACEMENT_TARGET_COUNT,
    FINAL_PUBLIC_MODEL,
    FIRST_LOMO_AGGREGATE,
    FIRST_LOMO_CAMPAIGN,
    HISTORICAL_FINAL_MODEL_ID,
    HISTORICAL_PRIVATE,
    HISTORICAL_RESULTS,
    HISTORY_HZ,
    HISTORY_STEPS,
    INVALIDATED_SECOND_CAMPAIGN_AGGREGATE,
    LOMO_FOLD_RESULTS,
    ORIGINAL_POSITION_DATA_STATE,
    PARITY_FIELDS,
    POSITION_MEASUREMENT_EVIDENCE,
    POSITION_MEASUREMENT_SEMANTICS,
    PREDECESSOR_PARITY,
    PRIVATE_RESULT_RECORDS,
    PUBLIC_TRAIN,
    PUBLIC_VALIDATION,
    PUBLIC_VALIDATION_PHYSICAL_RESULT,
    PUBLIC_VALIDATION_RAW_RESULT,
    RAW_DISPLACEMENT_EVALUATOR,
    RAW_SCIENTIFIC_LOCK,
    RAW_SCIENTIFIC_LOCK_HASH,
    REPAIRED_POSITION_DATA_STATE,
    SECOND_LOMO_CAMPAIGN,
    SYSTEM_VALIDATION_EVIDENCE,
    TARGET_SHAPE,
    TARGET_TEAM_ORIENTATION_EVIDENCE,
    TARGET_TEAM_ORIENTATION_SEMANTICS,
    TRAINING_REEXECUTED_DURING_RECONSTRUCTION,
    AbsolutePositionInputs,
    DisplacementInputs,
    ForecastOrigin,
    ParityStatus,
    absolute_position_to_physical,
    evaluate_absolute_position_trajectories,
    evaluate_displacement,
    evaluate_raw_displacement_sre,
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
from fpdbench.experiments import EvaluatorState, ResultPopulation, ResultValidity
from fpdbench.provenance.aliases import DISPLACEMENT_HISTORICAL_ALIASES
from fpdbench.provenance.scientific_lock import verify_scientific_lock
from fpdbench.validation.artifacts import validate_artifacts


def _frame(value: float) -> list[list[float]]:
    return [[value, value] for _ in range(11)]


def _trajectory(steps: int, value: float) -> list[list[list[float]]]:
    return [_frame(value) for _ in range(steps)]


def test_package_import_and_registry_discovery() -> None:
    assert __version__ == "0.1.0.dev0"
    assert version("football-performance-dynamics-bench") == __version__
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
    for displacement_alias in DISPLACEMENT_HISTORICAL_ALIASES:
        assert registry.resolve_alias(displacement_alias.value) == displacement_alias
        with pytest.raises(ValueError, match="provenance aliases"):
            registry.lookup(displacement_alias.value)


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
    assert ABSOLUTE_POSITION_BENCHMARK.descriptor.canonical_sampling.target_hz == 5.0
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
    assert "realized_future_opponent_xy" in inputs.feature_names
    assert "realized_future_ball_xy" in inputs.feature_names
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
    assert "realized_future_opponent_xy" in inputs.feature_names
    assert "realized_future_ball_xy" in inputs.feature_names
    assert {field.name for field in fields(DisplacementInputs)}.isdisjoint(
        {"future_target_team_xy_m", "future_target_team_features"}
    )
    mismatched_origin = ForecastOrigin.from_observations(
        10.0,
        history_times,
        ["history_target_team_xy"],
        target_origin_positions_m=_frame(4.0),
    )
    with pytest.raises(ValueError, match="must equal the final observed target-team history frame"):
        DisplacementInputs(
            history_target_team_xy_m=tuple(_trajectory(25, 3.0)),
            history_opponent_team_xy_m=tuple(_trajectory(25, 1.0)),
            history_ball_xy_m=tuple((0.0, 0.0) for _ in range(25)),
            realized_future_opponent_xy_m=tuple(_trajectory(15, 2.0)),
            realized_future_ball_xy_m=tuple((0.0, 0.0) for _ in range(15)),
            forecast_origin=mismatched_origin,
        )
    descriptor = DISPLACEMENT_BENCHMARK.descriptor
    assert descriptor.history_contract.duration_seconds == 5.0
    assert descriptor.horizon_contract.duration_seconds == 3.0
    assert descriptor.canonical_sampling.history_hz == 5.0
    assert descriptor.canonical_sampling.history_steps == 25
    assert descriptor.canonical_sampling.horizon_hz == 5.0
    assert descriptor.canonical_sampling.horizon_steps == 15
    assert descriptor.canonical_sampling.target_hz == 5.0
    assert descriptor.scientific_maturity.value == "partial"
    assert descriptor.reference_frame == (
        "Per-player future displacement relative to the same player's exact observed position "
        "at the causal forecast origin."
    )
    assert DISPLACEMENT_BENCHMARK.task.data_state_binding == "repaired_position_measurement_state"
    assert DISPLACEMENT_BENCHMARK.task.split_protocol_binding == (
        "match_grouped_public_and_cross_match_splits"
    )
    assert DISPLACEMENT_BENCHMARK.task.evaluator_binding == (
        "origin_relative_displacement_raw_population_sre"
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
    for name in (
        "realized_future_opponent_xy",
        "realized_future_ball_xy",
        "future_opponent_xy",
        "future_ball_xy",
    ):
        with pytest.raises(ValueError, match="cannot appear in ForecastOrigin"):
            ForecastOrigin.from_observations(1.0, [0.0, 1.0], [name])
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
    changed_metric_family = replace(
        descriptor,
        scientific_metric_family=("independently versioned scorer",),
    )
    assert changed_metric_family.scientific_metric_family != descriptor.scientific_metric_family
    assert descriptor.scientific_identity_compatible_with(changed_metric_family)

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
    times = [10.0 - (HISTORY_STEPS - 1 - index) / HISTORY_HZ for index in range(HISTORY_STEPS)]
    with pytest.raises(ValueError, match="cannot appear in ForecastOrigin"):
        ForecastOrigin.from_observations(
            10.0,
            times,
            ["history_target_team_xy", "realized_future_ball_xy"],
            target_origin_positions_m=_frame(3.0),
        )
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


def test_displacement_raw_population_sre_is_scalar_weighted_and_uncalibrated() -> None:
    truth = (tuple(_trajectory(15, 0.0)), tuple(_trajectory(15, 2.0)))
    mean_prediction = (tuple(_trajectory(15, 1.0)), tuple(_trajectory(15, 1.0)))
    score = evaluate_raw_displacement_sre(mean_prediction, truth)
    assert score.population_rows == 2
    assert len(score.per_scalar_sre) == 330
    assert score.raw_sre == pytest.approx(1.0)

    perfect = evaluate_raw_displacement_sre(truth, truth)
    assert perfect.raw_sre == 0.0

    constant_truth = (tuple(_trajectory(15, 0.0)), tuple(_trajectory(15, 0.0)))
    nonzero_prediction = (tuple(_trajectory(15, 0.0)), tuple(_trajectory(15, 1.0)))
    zero_variance = evaluate_raw_displacement_sre(nonzero_prediction, constant_truth)
    assert zero_variance.raw_sre == pytest.approx(2**-0.5)
    assert RAW_DISPLACEMENT_EVALUATOR.metric_id == "sre.rmse_over_population_std.v1"
    assert RAW_DISPLACEMENT_EVALUATOR.target_type == "PopulationSRETarget"
    assert RAW_DISPLACEMENT_EVALUATOR.target_count == 330
    assert RAW_DISPLACEMENT_EVALUATOR.per_target_weight == 1.0
    assert RAW_DISPLACEMENT_EVALUATOR.raw_clipping is None
    assert RAW_DISPLACEMENT_EVALUATOR.zero_variance_policy == "rmse"
    assert RAW_DISPLACEMENT_EVALUATOR.population_mean_predictor_sre == 1.0
    assert RAW_DISPLACEMENT_EVALUATOR.generated_calibration.floor == 1.0
    assert RAW_DISPLACEMENT_EVALUATOR.generated_calibration.perfect == 0.0
    assert RAW_DISPLACEMENT_EVALUATOR.generated_calibration.lower_is_better
    assert RAW_DISPLACEMENT_EVALUATOR.generated_calibration.target_weight == 1.0
    assert (
        RAW_DISPLACEMENT_EVALUATOR.generated_calibration.quality_floor_mode == "effective_no_info"
    )
    assert RAW_DISPLACEMENT_EVALUATOR.generated_calibration.naive_score_bounds == (1e-6, 0.10)
    assert RAW_DISPLACEMENT_EVALUATOR.generated_calibration.calibration_lock_state is UNKNOWN
    assert RAW_DISPLACEMENT_EVALUATOR.generated_calibration.reference_vector is UNKNOWN
    assert RAW_DISPLACEMENT_EVALUATOR.generated_calibration.no_information_ceiling_vector is UNKNOWN
    assert RAW_DISPLACEMENT_EVALUATOR.generated_calibration.x_ref is UNKNOWN
    assert RAW_DISPLACEMENT_EVALUATOR.generated_calibration.calibrated_reward is UNKNOWN


def test_displacement_parity_contract_is_complete_and_distinct() -> None:
    assert {entry.field for entry in PREDECESSOR_PARITY} == set(PARITY_FIELDS)
    assert len(PREDECESSOR_PARITY) == len(PARITY_FIELDS)
    assert {entry.status for entry in PREDECESSOR_PARITY} <= set(ParityStatus)
    assert all(entry.evidence for entry in PREDECESSOR_PARITY)
    assert ABSOLUTE_POSITION_BENCHMARK.identity.scientific_id != (
        DISPLACEMENT_BENCHMARK.identity.scientific_id
    )
    assert {
        entry.status
        for entry in PREDECESSOR_PARITY
        if entry.field in {"target_representation", "reference_frame", "benchmark_identity"}
    } == {ParityStatus.CHANGED}
    assert any(
        entry.field == "calibration" and entry.status is ParityStatus.UNKNOWN
        for entry in PREDECESSOR_PARITY
    )
    assert all(
        next(entry for entry in PREDECESSOR_PARITY if entry.field == field).status
        is ParityStatus.UNKNOWN
        for field in ("baseline_ladder", "model_architecture", "model_selection_protocol")
    )


def test_displacement_data_split_lineage_preserves_private_boundary() -> None:
    assert DISPLACEMENT_DATA_STATE is REPAIRED_POSITION_DATA_STATE
    assert DISPLACEMENT_FEATURE_COUNT == 8_404
    assert DISPLACEMENT_TARGET_COUNT == 330
    assert PUBLIC_TRAIN.match_ids == ("J03WOH", "J03WOY", "J03WPY", "J03WQQ", "J03WR9")
    assert (PUBLIC_TRAIN.physical_windows, PUBLIC_TRAIN.directed_rows) == (17_386, 34_772)
    assert PUBLIC_VALIDATION.match_ids == ("J03WN1",)
    assert (PUBLIC_VALIDATION.physical_windows, PUBLIC_VALIDATION.directed_rows) == (215, 430)
    assert HISTORICAL_PRIVATE.match_ids == ("J03WMX",)
    assert (HISTORICAL_PRIVATE.physical_windows, HISTORICAL_PRIVATE.directed_rows) == (457, 914)
    assert HISTORICAL_PRIVATE.content_access.startswith("historical private metadata only")
    assert all(
        population.evidence for population in (PUBLIC_TRAIN, PUBLIC_VALIDATION, HISTORICAL_PRIVATE)
    )
    assert DISPLACEMENT_DATA_STATE_EVIDENCE
    assert POSITION_MEASUREMENT_EVIDENCE
    assert "xy[::5]" in POSITION_MEASUREMENT_SEMANTICS
    assert "only samples at or before t" in POSITION_MEASUREMENT_SEMANTICS
    assert "no separate team-relative" in TARGET_TEAM_ORIENTATION_SEMANTICS
    assert TARGET_TEAM_ORIENTATION_EVIDENCE
    assert DISPLACEMENT_SPLIT.assignment_sha256 == (
        "5e060c84952cd4544fde6b80a93675c02c06036440ef9d2c97aa96eec618709c"
    )


def test_lomo_campaigns_keep_invalid_aggregate_out_of_result_records() -> None:
    assert (FIRST_LOMO_CAMPAIGN.seeds, FIRST_LOMO_CAMPAIGN.fold_count) == ((20260911,), 5)
    assert (SECOND_LOMO_CAMPAIGN.seeds, SECOND_LOMO_CAMPAIGN.fold_count) == (
        (20260912, 20260913),
        10,
    )
    assert INVALIDATED_SECOND_CAMPAIGN_AGGREGATE.tuple_order_bug
    assert INVALIDATED_SECOND_CAMPAIGN_AGGREGATE.aggregate_validity is (ResultValidity.INVALIDATED)
    assert len(LOMO_FOLD_RESULTS) == 15
    assert len({fold.checkpoint_sha256 for fold in LOMO_FOLD_RESULTS}) == 15
    assert all(
        fold.result.output_sha256 == fold.result.evidence[0].sha256 for fold in LOMO_FOLD_RESULTS
    )
    assert all(
        fold.result.model_checkpoint_sha256 == fold.checkpoint_sha256 for fold in LOMO_FOLD_RESULTS
    )
    assert all(
        fold.result.scientific_lock_hash == RAW_SCIENTIFIC_LOCK_HASH for fold in LOMO_FOLD_RESULTS
    )
    assert not TRAINING_REEXECUTED_DURING_RECONSTRUCTION
    assert CORRECTED_AGGREGATION.aggregate_validity is ResultValidity.RECOMPUTED
    assert CORRECTED_LOMO_AGGREGATE.validity is ResultValidity.RECOMPUTED
    assert CORRECTED_LOMO_AGGREGATE.metrics == (
        ("grand_mean_raw_sre", CORRECTED_LOMO_GRAND_MEAN_RAW_SRE),
    )
    assert CORRECTED_LOMO_GRAND_MEAN_RAW_SRE == 0.27000500438140806
    assert sum(fold.result.metrics[0][1] for fold in LOMO_FOLD_RESULTS) / 15 == pytest.approx(
        CORRECTED_LOMO_GRAND_MEAN_RAW_SRE, abs=1e-15
    )
    assert FIRST_LOMO_AGGREGATE.metrics == (("mean_raw_sre", 0.2720811027147715),)


def test_selected_model_and_validation_results_keep_evidence_populations() -> None:
    assert FINAL_PUBLIC_MODEL.checkpoint_sha256 == (
        "3c5297b7c53f07e288c239d1f59b6df003ba349ea227c97377ba58d4cbac53c6"
    )
    assert FINAL_PUBLIC_MODEL.model_id == HISTORICAL_FINAL_MODEL_ID
    assert DISPLACEMENT_BENCHMARK.direct_model_bindings == (HISTORICAL_FINAL_MODEL_ID,)
    assert (
        FINAL_PUBLIC_MODEL.seed,
        FINAL_PUBLIC_MODEL.parameter_count,
        FINAL_PUBLIC_MODEL.epochs,
        FINAL_PUBLIC_MODEL.optimization_steps,
    ) == (20260912, 936_962, 42, 22_848)
    assert FINAL_PUBLIC_MODEL.training_matches == PUBLIC_TRAIN.match_ids
    assert FINAL_PUBLIC_MODEL.training_directed_rows == 34_772
    assert FINAL_PUBLIC_MODEL.public_validation_matches == PUBLIC_VALIDATION.match_ids
    assert FINAL_PUBLIC_MODEL.public_validation_directed_rows == 430
    assert not FINAL_PUBLIC_MODEL.scorer_calibration_reference
    assert FINAL_PUBLIC_MODEL.model_selection_protocol is UNKNOWN
    public_results = [
        result
        for result in HISTORICAL_RESULTS
        if result.population is ResultPopulation.PUBLIC_VALIDATION
    ]
    assert len(public_results) == 2
    assert {result.evaluator_state for result in public_results} == {
        EvaluatorState.RAW_EVALUATION,
        EvaluatorState.PHYSICAL_DIAGNOSTIC,
    }
    assert PUBLIC_VALIDATION_RAW_RESULT.scientific_lock_hash == RAW_SCIENTIFIC_LOCK_HASH
    assert PUBLIC_VALIDATION_PHYSICAL_RESULT.scientific_lock_hash is None
    assert PUBLIC_VALIDATION_RAW_RESULT.metrics == (("raw_sre", 0.25698394782524847),)
    assert PUBLIC_VALIDATION_PHYSICAL_RESULT.metrics == (
        ("ade_m", 0.7728278283223137),
        ("fde_m", 1.745128730406117),
        ("xy_rmse_m", 0.8841436584705827),
    )
    assert all(result.population is ResultPopulation.PUBLIC_VALIDATION for result in public_results)
    assert all(
        result.output_sha256 == "b29250984c897c1184cb1208a390c6fdeb2a4764cfe5ee530c73c0a1c9269528"
        for result in public_results
    )
    assert any(
        evidence.sha256 == PUBLIC_VALIDATION_RAW_RESULT.output_sha256
        for evidence in PUBLIC_VALIDATION_RAW_RESULT.evidence
    )
    assert not PRIVATE_RESULT_RECORDS
    assert len(SYSTEM_VALIDATION_EVIDENCE) == 3
    assert all(not item.quality_bearing for item in SYSTEM_VALIDATION_EVIDENCE)
    assert all(
        item.population is ResultPopulation.RELEASE_SYSTEM_VALIDATION
        and item.evaluator_state is EvaluatorState.RELEASE_ENGINEERING
        for item in SYSTEM_VALIDATION_EVIDENCE
    )


def test_displacement_raw_scientific_lock_is_scoped_and_aliases_stay_provenance() -> None:
    assert verify_scientific_lock(RAW_SCIENTIFIC_LOCK)
    assert RAW_SCIENTIFIC_LOCK["evaluator_id"] == "origin_relative_displacement_raw_population_sre"
    assert "x_ref" not in RAW_SCIENTIFIC_LOCK
    assert "calibrated_reward" not in RAW_SCIENTIFIC_LOCK
    citations = RAW_SCIENTIFIC_LOCK["scientific_provenance_snapshot"]["citations"]
    assert any(
        "raw-displacement" in citation and "private calibrated reward excluded" in citation
        for citation in citations
    )
    assert all(
        alias.canonical_id == DISPLACEMENT_BENCHMARK.identity.scientific_id
        for alias in DISPLACEMENT_HISTORICAL_ALIASES
    )
    assert all(alias.canonical_id != alias.value for alias in DISPLACEMENT_HISTORICAL_ALIASES)
    root = Path(__file__).resolve().parents[2]
    assert not tuple(root.rglob("*.pt"))
    lock_path = (
        root
        / "benchmarks"
        / "conditional_multi_agent_motion_prediction"
        / "raw_displacement_scientific_lock.json"
    )
    assert json.loads(lock_path.read_text()) == RAW_SCIENTIFIC_LOCK
    assert validate_artifacts(root) == ()
