import pytest

from fpdbench.benchmarks.multimodal_state_estimation import (
    SensorCandidateFamily,
)
from fpdbench.benchmarks.multimodal_state_estimation import (
    evaluate_sensor_state_channels as evaluate_sensor_wrapper,
)
from fpdbench.benchmarks.multimodal_state_estimation import (
    evaluate_sensor_state_gate as evaluate_gate_wrapper,
)
from fpdbench.benchmarks.workload_performance_state import (
    evaluate_signed_tangential_acceleration as evaluate_signed_wrapper,
)
from fpdbench.evaluation import (
    ABSOLUTE_POSITION_CALIBRATION,
    ABSOLUTE_POSITION_CALIBRATION_LOCK_SHA256,
    ABSOLUTE_POSITION_EVALUATOR_SOURCE_SHA256,
    ABSOLUTE_POSITION_HISTORICAL_SCORER,
    ABSOLUTE_POSITION_RAW_EVALUATOR,
    ABSOLUTE_POSITION_TARGET_IDS,
    DISPLACEMENT_GENERATED_CALIBRATION,
    RAW_DISPLACEMENT_EVALUATOR,
    AbsolutePositionRawEvaluation,
    absolute_position_progress,
    evaluate_absolute_position_population_sre,
    evaluate_raw_displacement_sre,
    evaluate_sensor_state_channels,
    evaluate_sensor_state_gate,
    evaluate_signed_tangential_acceleration,
    raw_evaluator_hash,
    score_absolute_position,
)
from fpdbench.unknown import UNKNOWN


def _trajectory(value: float) -> tuple[tuple[tuple[float, float], ...], ...]:
    return tuple(tuple((value, value) for _ in range(11)) for _ in range(15))


def test_signed_acceleration_compatibility_wrapper() -> None:
    prediction, truth = [0.0, 1.0, 2.0], [0.0, 0.0, 0.0]
    assert evaluate_signed_wrapper(prediction, truth) == evaluate_signed_tangential_acceleration(
        prediction, truth
    )
    assert evaluate_signed_wrapper(prediction, truth).aggregation == "global full-row RMSE"


def test_sensor_diagnostic_wrapper_equal_channel_q_and_gate() -> None:
    predictions = {"b": [1.0, 2.0], "a": [0.0, 1.0]}
    truths = {"b": [0.0, 2.0], "a": [0.0, 1.0]}
    generic = evaluate_sensor_state_channels(predictions, truths)
    compatible = evaluate_sensor_wrapper(
        predictions, truths, SensorCandidateFamily.CLEAN_HORIZONTAL_MOTION
    )
    assert (
        generic.per_channel_sre
        == compatible.per_channel_sre
        == (
            ("a", 0.0),
            ("b", 2**-0.5),
        )
    )
    assert generic.mean_sre == pytest.approx(2**-1.5)
    assert generic.mean_quality == pytest.approx((1.0 + 1.0 - 2**-0.5) / 2)
    assert evaluate_sensor_state_gate([0.3]).passes
    assert evaluate_gate_wrapper([0.3]).passes
    assert not evaluate_sensor_state_gate([0.300001]).passes
    with pytest.raises(ValueError, match="constant truth"):
        evaluate_sensor_state_channels({"x": [1.0, 1.0]}, {"x": [0.0, 0.0]})
    with pytest.raises(ValueError, match="256 rows"):
        evaluate_sensor_state_channels(
            {"x": [0.0] * 256}, {"x": [1.0] * 256}, region_mask=[True] * 255 + [False]
        )


def test_standalone_displacement_raw_330_target_aggregation() -> None:
    truth_targets = ((0.0, 2.0),) * 330
    mean_prediction = ((1.0, 1.0),) * 330
    result = evaluate_raw_displacement_sre(mean_prediction, truth_targets)
    assert result.per_scalar_sre == (1.0,) * 330
    assert result.raw_sre == 1.0
    assert result.population_rows == 2
    assert raw_evaluator_hash() == (
        "e7ae84ae81bf25cfc121fcb1e00bcb27804adcd4bfa349c1e6117ecf0176275b"
    )
    assert DISPLACEMENT_GENERATED_CALIBRATION.calibrated_reward is UNKNOWN
    assert not hasattr(RAW_DISPLACEMENT_EVALUATOR, "generated_calibration")


def test_absolute_historical_scorer_reference_no_information_and_order() -> None:
    calibration = ABSOLUTE_POSITION_CALIBRATION
    assert calibration.source_sha256 == ABSOLUTE_POSITION_CALIBRATION_LOCK_SHA256
    assert len(calibration.targets) == 330
    assert ABSOLUTE_POSITION_HISTORICAL_SCORER.calibration_sha256 == (
        ABSOLUTE_POSITION_CALIBRATION_LOCK_SHA256
    )
    assert ABSOLUTE_POSITION_RAW_EVALUATOR.calibration_sha256 is None
    assert ABSOLUTE_POSITION_HISTORICAL_SCORER.provenance == (
        f"registry://sha256/{ABSOLUTE_POSITION_EVALUATOR_SOURCE_SHA256}",
        f"registry://sha256/{ABSOLUTE_POSITION_CALIBRATION_LOCK_SHA256}",
    )

    reference_raw = AbsolutePositionRawEvaluation(
        tuple((target.target_id, target.reference_sre) for target in calibration.targets), 1
    )
    reference_progress = absolute_position_progress(reference_raw)
    reference_result = score_absolute_position(reference_progress)
    assert reference_progress.aggregate_progress == pytest.approx(calibration.x_ref)
    assert reference_result.score == pytest.approx(calibration.reference_score)
    assert (
        score_absolute_position(
            absolute_position_progress(
                AbsolutePositionRawEvaluation(tuple(reversed(reference_raw.per_target_sre)), 1)
            )
        )
        == reference_result
    )

    no_information = AbsolutePositionRawEvaluation(
        tuple((target.target_id, target.no_information_ceiling) for target in calibration.targets),
        1,
    )
    perfect = AbsolutePositionRawEvaluation(
        tuple((target_id, 0.0) for target_id in ABSOLUTE_POSITION_TARGET_IDS), 1
    )
    assert score_absolute_position(absolute_position_progress(no_information)).score == 0.0
    assert score_absolute_position(absolute_position_progress(perfect)).score == 1.0


def test_absolute_position_raw_target_geometry_and_order() -> None:
    truth = _trajectory(0.0)
    prediction = [list(map(list, step)) for step in truth]
    prediction[0][0][0] = 0.25
    raw = evaluate_absolute_position_population_sre([prediction, truth], [truth, truth])
    assert raw.population_rows == 2
    assert raw.per_target_sre[0][0] == ABSOLUTE_POSITION_TARGET_IDS[0]
    assert raw.per_target_sre[0][1] == pytest.approx(0.25 / 2**0.5)
    assert len(raw.per_target_sre) == 330
