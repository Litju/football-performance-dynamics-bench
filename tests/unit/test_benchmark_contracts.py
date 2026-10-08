import hashlib
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
    TransitionStatus,
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
    DISPLACEMENT_GENERATED_CALIBRATION,
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
    LOMO_RAW_SCIENTIFIC_LOCK,
    LOMO_RAW_SCIENTIFIC_LOCK_HASH,
    LOMO_SPLIT,
    ORIGINAL_POSITION_DATA_STATE,
    PARITY_FIELDS,
    POSITION_MEASUREMENT_EVIDENCE,
    POSITION_MEASUREMENT_SEMANTICS,
    PREDECESSOR_PARITY,
    PRIVATE_RESULT_RECORDS,
    PUBLIC_TRAIN,
    PUBLIC_VALIDATION,
    PUBLIC_VALIDATION_PHYSICAL_RESULT,
    PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK,
    PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK_HASH,
    PUBLIC_VALIDATION_RAW_RESULT,
    PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK,
    PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK_HASH,
    RAW_DISPLACEMENT_EVALUATOR,
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
    GeneratedCalibrationContract,
    RawDisplacementEvaluatorConfiguration,
    absolute_position_to_physical,
    build_lomo_raw_scientific_lock,
    build_public_validation_raw_scientific_lock,
    evaluate_absolute_position_trajectories,
    evaluate_displacement,
    evaluate_raw_displacement_sre,
    invert_origin_relative_displacement,
    make_absolute_position_target,
    make_origin_relative_displacement_target,
    normalized_displacement_to_physical,
    raw_evaluator_hash,
    validate_information_boundary,
)
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
from fpdbench.provenance.scientific_lock import (
    build_scientific_lock,
    canonical_scientific_bytes,
    validate_scientific_lock_provenance,
    verify_scientific_lock,
)
from fpdbench.validation.artifacts import validate_artifacts


def _frame(value: float) -> list[list[float]]:
    return [[value, value] for _ in range(11)]


def _trajectory(steps: int, value: float) -> list[list[list[float]]]:
    return [_frame(value) for _ in range(steps)]


def _raw_lock_hashes_for(evaluator: RawDisplacementEvaluatorConfiguration) -> tuple[str, str]:
    public_lock = build_public_validation_raw_scientific_lock(evaluator=evaluator)
    lomo_lock = build_lomo_raw_scientific_lock(evaluator=evaluator)
    return str(public_lock["scientific_lock_hash"]), str(lomo_lock["scientific_lock_hash"])


def test_package_import_and_registry_discovery() -> None:
    assert __version__ == "0.1.0.dev0"
    assert version("football-performance-dynamics-bench") == __version__
    registry = default_registry()
    assert len(registry.discover()) == 2
    assert {item.identity.scientific_id for item in registry.discover()} == {
        "conditional_multi_agent_motion_prediction/absolute_position_prediction",
        "conditional_multi_agent_motion_prediction/origin_relative_displacement_prediction",
    }
    assert len(registry.research_objects()) == 5
    assert (
        registry.lookup(ABSOLUTE_POSITION_BENCHMARK.identity.scientific_id)
        is ABSOLUTE_POSITION_BENCHMARK
    )
    assert len(registry.families()) == 4
    assert registry.discover("future_response_forecasting") == ()
    assert all(
        item.identity.scientific_id
        not in {
            WHOLE_SESSION_RESEARCH_OBJECT.identity.scientific_id,
            SIGNED_TANGENTIAL_ACCELERATION_RESEARCH_OBJECT.identity.scientific_id,
            SENSOR_STATE.identity.scientific_id,
        }
        for item in registry.discover()
    )


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
    classifications = {
        research_object.descriptor.research_object_type
        for research_object in default_registry().research_objects()
    }
    assert classifications == {
        ResearchObjectType.HISTORICAL_STUDY,
        ResearchObjectType.INVALIDATED_FORMULATION,
        ResearchObjectType.NEGATIVE_RESULT,
        ResearchObjectType.BENCHMARK,
    }
    assert WHOLE_SESSION_RESEARCH_OBJECT.direct_model_bindings == ()
    assert len(SIGNED_TANGENTIAL_ACCELERATION_RESEARCH_OBJECT.direct_model_bindings) == 7


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

    truth_zero = _trajectory(15, 0.0)
    truth_two = _trajectory(15, 2.0)
    prediction_zero = _trajectory(15, 0.0)
    prediction_two = _trajectory(15, 2.0)
    for scalar_index in range(165):
        step, offset = divmod(scalar_index, 22)
        player, coordinate = divmod(offset, 2)
        prediction_zero[step][player][coordinate] = 5.0
        prediction_two[step][player][coordinate] = 5.0
    mixed = evaluate_raw_displacement_sre(
        (tuple(prediction_zero), tuple(prediction_two)),
        (tuple(truth_zero), tuple(truth_two)),
    )
    assert len(mixed.per_scalar_sre) == 330
    assert mixed.per_scalar_sre[:165] == pytest.approx((17**0.5,) * 165)
    assert mixed.per_scalar_sre[165:] == (0.0,) * 165
    assert mixed.raw_sre == pytest.approx((17**0.5) / 2)

    with pytest.raises(ValueError, match="same nonempty population"):
        evaluate_raw_displacement_sre((), ())
    with pytest.raises(ValueError, match="same nonempty population"):
        evaluate_raw_displacement_sre((tuple(truth_zero),), ())
    nonfinite = _trajectory(15, 0.0)
    nonfinite[-1][0][0] = float("inf")
    with pytest.raises(ValueError, match="finite XY pairs"):
        evaluate_raw_displacement_sre((tuple(nonfinite),), (tuple(truth_zero),))

    assert RAW_DISPLACEMENT_EVALUATOR.metric_id == "sre.rmse_over_population_std.v1"
    assert RAW_DISPLACEMENT_EVALUATOR.target_type == "PopulationSRETarget"
    assert RAW_DISPLACEMENT_EVALUATOR.target_count == 330
    assert RAW_DISPLACEMENT_EVALUATOR.per_target_weight == 1.0
    assert RAW_DISPLACEMENT_EVALUATOR.raw_clipping is None
    assert RAW_DISPLACEMENT_EVALUATOR.zero_variance_policy == "rmse"
    assert RAW_DISPLACEMENT_EVALUATOR.population_mean_predictor_sre == 1.0
    assert RAW_DISPLACEMENT_EVALUATOR.aggregation == "equal arithmetic mean across scalar targets"
    assert RAW_DISPLACEMENT_EVALUATOR.lower_is_better
    assert DISPLACEMENT_GENERATED_CALIBRATION.floor == 1.0
    assert DISPLACEMENT_GENERATED_CALIBRATION.perfect == 0.0
    assert DISPLACEMENT_GENERATED_CALIBRATION.lower_is_better
    assert DISPLACEMENT_GENERATED_CALIBRATION.target_weight == 1.0
    assert DISPLACEMENT_GENERATED_CALIBRATION.quality_floor_mode == "effective_no_info"
    assert DISPLACEMENT_GENERATED_CALIBRATION.naive_score_bounds == (1e-6, 0.10)
    assert DISPLACEMENT_GENERATED_CALIBRATION.calibration_lock_state is UNKNOWN
    assert DISPLACEMENT_GENERATED_CALIBRATION.reference_vector is UNKNOWN
    assert DISPLACEMENT_GENERATED_CALIBRATION.no_information_ceiling_vector is UNKNOWN
    assert DISPLACEMENT_GENERATED_CALIBRATION.x_ref is UNKNOWN
    assert DISPLACEMENT_GENERATED_CALIBRATION.calibrated_reward is UNKNOWN
    with pytest.raises(ValueError, match="requires a known calibration lock"):
        replace(DISPLACEMENT_GENERATED_CALIBRATION, calibrated_reward=0.6)
    assert not hasattr(score, "calibrated_reward")


def test_generated_calibration_metadata_does_not_churn_raw_scientific_lock() -> None:
    calibration_a = DISPLACEMENT_GENERATED_CALIBRATION
    # Hypothetical mutation fixture only; these values are not historical calibration facts.
    calibration_b = replace(
        calibration_a,
        calibration_lock_state="hypothetical",
        lower_is_better=False,
        target_weight=2.0,
        floor=0.75,
        perfect=0.25,
        quality_floor_mode="mutation_fixture",
        naive_score_bounds=(0.2, 0.8),
        reference_vector=(0.1, 0.2),
        no_information_ceiling_vector=(0.3, 0.4),
        x_ref=0.5,
        calibrated_reward=0.6,
    )
    evaluator_a = RAW_DISPLACEMENT_EVALUATOR

    assert isinstance(calibration_a, GeneratedCalibrationContract)
    assert calibration_a.reference_vector is UNKNOWN
    assert calibration_a.no_information_ceiling_vector is UNKNOWN
    assert calibration_a.x_ref is UNKNOWN
    assert calibration_a.calibrated_reward is UNKNOWN
    assert calibration_b.calibration_lock_state == "hypothetical"
    assert calibration_b != calibration_a
    assert not hasattr(evaluator_a, "generated_calibration")
    assert "calibrated_reward" not in evaluator_a.scientific_state()
    assert raw_evaluator_hash(evaluator_a) == (
        "e7ae84ae81bf25cfc121fcb1e00bcb27804adcd4bfa349c1e6117ecf0176275b"
    )
    expected = (PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK_HASH, LOMO_RAW_SCIENTIFIC_LOCK_HASH)
    assert _raw_lock_hashes_for(evaluator_a) == expected


@pytest.mark.parametrize(
    "changed",
    [
        replace(RAW_DISPLACEMENT_EVALUATOR, degrees_of_freedom=1),
        replace(RAW_DISPLACEMENT_EVALUATOR, zero_variance_policy="error"),
        replace(RAW_DISPLACEMENT_EVALUATOR, per_target_weight=2.0),
        replace(RAW_DISPLACEMENT_EVALUATOR, aggregation="weighted arithmetic mean"),
        replace(RAW_DISPLACEMENT_EVALUATOR, raw_clipping=(0.0, 1.0)),
        replace(RAW_DISPLACEMENT_EVALUATOR, target_count=331),
        replace(RAW_DISPLACEMENT_EVALUATOR, metric_id="sre.alternate.v1"),
        replace(RAW_DISPLACEMENT_EVALUATOR, lower_is_better=False),
    ],
)
def test_raw_evaluator_scientific_changes_churn_raw_lock(
    changed: RawDisplacementEvaluatorConfiguration,
) -> None:
    assert raw_evaluator_hash(changed) != raw_evaluator_hash(RAW_DISPLACEMENT_EVALUATOR)
    public_hash, lomo_hash = _raw_lock_hashes_for(changed)
    assert public_hash != PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK_HASH
    assert lomo_hash != LOMO_RAW_SCIENTIFIC_LOCK_HASH


def test_raw_locks_bind_only_their_own_split() -> None:
    changed_lomo = replace(LOMO_SPLIT, assignment_sha256="a" * 64)
    changed_public = replace(DISPLACEMENT_SPLIT, assignment_sha256="b" * 64)

    lomo_changed_lock = build_lomo_raw_scientific_lock(changed_lomo)
    public_unchanged_lock = build_public_validation_raw_scientific_lock(DISPLACEMENT_SPLIT)
    public_changed_lock = build_public_validation_raw_scientific_lock(changed_public)
    lomo_unchanged_lock = build_lomo_raw_scientific_lock(LOMO_SPLIT)

    assert lomo_changed_lock["scientific_lock_hash"] != LOMO_RAW_SCIENTIFIC_LOCK_HASH
    assert public_unchanged_lock["scientific_lock_hash"] == (
        PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK_HASH
    )
    assert public_changed_lock["scientific_lock_hash"] != (
        PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK_HASH
    )
    assert lomo_unchanged_lock["scientific_lock_hash"] == LOMO_RAW_SCIENTIFIC_LOCK_HASH


def test_result_values_and_output_hashes_do_not_change_raw_locks() -> None:
    changed_fold_metric = replace(LOMO_FOLD_RESULTS[0].result, metrics=(("raw_sre", 0.9),))
    changed_aggregate_metric = replace(
        CORRECTED_LOMO_AGGREGATE, metrics=(("grand_mean_raw_sre", 0.9),)
    )
    changed_fold_output = replace(LOMO_FOLD_RESULTS[0].result, output_sha256="c" * 64)
    changed_public_metric = replace(PUBLIC_VALIDATION_RAW_RESULT, metrics=(("raw_sre", 0.9),))
    changed_public_output = replace(PUBLIC_VALIDATION_RAW_RESULT, output_sha256="d" * 64)
    mutated_results = (
        changed_fold_metric,
        changed_aggregate_metric,
        changed_fold_output,
        changed_public_metric,
        changed_public_output,
    )
    assert changed_fold_metric.metrics != LOMO_FOLD_RESULTS[0].result.metrics
    assert changed_aggregate_metric.metrics != CORRECTED_LOMO_AGGREGATE.metrics
    assert changed_fold_output.output_sha256 == "c" * 64
    assert changed_public_metric.metrics != PUBLIC_VALIDATION_RAW_RESULT.metrics
    assert changed_public_output.output_sha256 == "d" * 64
    assert all(
        result.scientific_lock_hash == LOMO_RAW_SCIENTIFIC_LOCK_HASH
        for result in mutated_results[:3]
    )
    assert all(
        result.scientific_lock_hash == PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK_HASH
        for result in mutated_results[3:]
    )
    assert _raw_lock_hashes_for(RAW_DISPLACEMENT_EVALUATOR) == (
        PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK_HASH,
        LOMO_RAW_SCIENTIFIC_LOCK_HASH,
    )
    result_output_hashes = tuple(
        result.output_sha256 for result in HISTORICAL_RESULTS if result.output_sha256 is not None
    ) + ("c" * 64, "d" * 64)
    assert all(
        validate_scientific_lock_provenance(lock, result_output_hashes) == ()
        for lock in (PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK, LOMO_RAW_SCIENTIFIC_LOCK)
    )


def test_lock_provenance_validator_rejects_result_output_citations() -> None:
    result_output_sha256 = "e" * 64
    state = {
        key: value
        for key, value in PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK.items()
        if key != "scientific_lock_hash"
    }
    snapshot = dict(state["scientific_provenance_snapshot"])
    citations = list(snapshot["citations"])
    citations.append(f"registry://sha256/{result_output_sha256}")
    snapshot_id = str(snapshot["snapshot_id"])
    snapshot["citations"] = citations
    snapshot["snapshot_hash"] = hashlib.sha256(
        canonical_scientific_bytes({"citations": "\n".join(citations), "snapshot_id": snapshot_id})
    ).hexdigest()
    state["scientific_provenance_snapshot"] = snapshot

    lock_with_result_citation = build_scientific_lock(state)
    assert validate_scientific_lock_provenance(
        lock_with_result_citation, (result_output_sha256,)
    ) == (f"scientific provenance cites result output SHA-256 {result_output_sha256}",)


def test_displacement_parity_contract_is_complete_and_distinct() -> None:
    assert {entry.layer for entry in PREDECESSOR_PARITY} == set(PARITY_FIELDS)
    assert len(PREDECESSOR_PARITY) == len(PARITY_FIELDS)
    assert {entry.status for entry in PREDECESSOR_PARITY} <= set(TransitionStatus)
    assert all(entry.evidence for entry in PREDECESSOR_PARITY)
    assert ABSOLUTE_POSITION_BENCHMARK.identity.scientific_id != (
        DISPLACEMENT_BENCHMARK.identity.scientific_id
    )
    assert {
        entry.status
        for entry in PREDECESSOR_PARITY
        if entry.layer in {"target_representation", "reference_frame", "benchmark_identity"}
    } == {TransitionStatus.CHANGED}
    assert any(
        entry.layer == "calibration" and entry.status is TransitionStatus.UNKNOWN
        for entry in PREDECESSOR_PARITY
    )
    assert all(
        next(entry for entry in PREDECESSOR_PARITY if entry.layer == field).status
        is TransitionStatus.UNKNOWN
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
        fold.result.scientific_lock_hash == LOMO_RAW_SCIENTIFIC_LOCK_HASH
        for fold in LOMO_FOLD_RESULTS
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
    assert (
        PUBLIC_VALIDATION_RAW_RESULT.scientific_lock_hash
        == PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK_HASH
    )
    assert (
        PUBLIC_VALIDATION_PHYSICAL_RESULT.scientific_lock_hash
        == PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK_HASH
    )
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


def test_displacement_raw_scientific_locks_bind_exact_result_groups() -> None:
    assert verify_scientific_lock(PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK)
    assert verify_scientific_lock(LOMO_RAW_SCIENTIFIC_LOCK)
    assert verify_scientific_lock(PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK)
    assert (
        PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK["evaluator_id"]
        == "origin_relative_displacement_raw_population_sre"
    )
    assert PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK["split_protocol_id"] == (
        DISPLACEMENT_SPLIT.protocol_id
    )
    assert PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK["split_protocol_hash"] == (
        DISPLACEMENT_SPLIT.assignment_sha256
    )
    assert LOMO_RAW_SCIENTIFIC_LOCK["split_protocol_id"] == LOMO_SPLIT.protocol_id
    assert LOMO_RAW_SCIENTIFIC_LOCK["split_protocol_hash"] == LOMO_SPLIT.assignment_sha256
    assert "x_ref" not in PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK
    assert "calibrated_reward" not in PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK
    assert "x_ref" not in LOMO_RAW_SCIENTIFIC_LOCK
    assert "calibrated_reward" not in LOMO_RAW_SCIENTIFIC_LOCK

    raw_lomo_results = [
        result
        for result in HISTORICAL_RESULTS
        if result.population is ResultPopulation.LOMO_CROSS_MATCH
        and result.evaluator_state is EvaluatorState.RAW_EVALUATION
    ]
    raw_public_results = [
        result
        for result in HISTORICAL_RESULTS
        if result.population is ResultPopulation.PUBLIC_VALIDATION
        and result.evaluator_state is EvaluatorState.RAW_EVALUATION
    ]
    assert len(raw_lomo_results) == 17
    assert all(
        result.scientific_lock_hash == LOMO_RAW_SCIENTIFIC_LOCK_HASH for result in raw_lomo_results
    )
    assert len(raw_public_results) == 1
    assert raw_public_results[0] is PUBLIC_VALIDATION_RAW_RESULT
    assert raw_public_results[0].scientific_lock_hash == PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK_HASH
    assert (
        PUBLIC_VALIDATION_PHYSICAL_RESULT.scientific_lock_hash
        == PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK_HASH
    )
    assert PRIVATE_RESULT_RECORDS == ()

    result_output_hashes = tuple(
        result.output_sha256 for result in HISTORICAL_RESULTS if result.output_sha256 is not None
    )
    for lock in (
        PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK,
        LOMO_RAW_SCIENTIFIC_LOCK,
        PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK,
    ):
        assert validate_scientific_lock_provenance(lock, result_output_hashes) == ()
        citations = lock["scientific_provenance_snapshot"]["citations"]
        assert (
            "registry://sha256/eb83130616d3d77c6d0d49c7d9ebe89ed8099741fa5c6163b295a084d73ac527"
            not in citations
        )
        assert all(
            result.output_sha256 not in citations
            for result in HISTORICAL_RESULTS
            if result.output_sha256 is not None
        )

    public_citations = PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK["scientific_provenance_snapshot"][
        "citations"
    ]
    lomo_citations = LOMO_RAW_SCIENTIFIC_LOCK["scientific_provenance_snapshot"]["citations"]
    assert (
        "registry://sha256/134cfd7a6a3b5bcdf04d1d03772e8674c37b2da301e81245aabe2be5b11519b4"
        in public_citations
    )
    assert (
        "registry://sha256/5e060c84952cd4544fde6b80a93675c02c06036440ef9d2c97aa96eec618709c"
        in public_citations
    )
    assert (
        "registry://sha256/134cfd7a6a3b5bcdf04d1d03772e8674c37b2da301e81245aabe2be5b11519b4"
        not in lomo_citations
    )
    assert (
        "registry://sha256/5e060c84952cd4544fde6b80a93675c02c06036440ef9d2c97aa96eec618709c"
        not in lomo_citations
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
        / "public_validation_raw_displacement_scientific_lock.json"
    )
    lomo_lock_path = lock_path.with_name("lomo_raw_displacement_scientific_lock.json")
    assert json.loads(lock_path.read_text()) == PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK
    assert json.loads(lomo_lock_path.read_text()) == LOMO_RAW_SCIENTIFIC_LOCK
    assert not lock_path.with_name("raw_displacement_scientific_lock.json").exists()
    assert validate_artifacts(root) == ()
