import pytest

from fpdbench.benchmarks.multimodal_state_estimation import (
    SensorCandidateFamily,
    evaluate_sensor_state_channels,
    evaluate_sensor_state_gate,
    quality_from_sre,
)
from fpdbench.evaluation import (
    PITCH_SCALE_M,
    EvaluatorConfiguration,
    physical_trajectory_metrics,
    population_standardized_relative_error,
    rmse,
)
from fpdbench.evaluation.calibration import PiecewiseLinearTransform


def test_relative_error_uses_population_standard_deviation() -> None:
    assert population_standardized_relative_error([0.0, 1.0, 2.0], [0.0, 1.0, 2.0]) == 0.0
    # Truth [0, 2] has population SD 1 (ddof=0), so SRE equals RMSE here.
    assert population_standardized_relative_error([1.0, 2.0], [0.0, 2.0]) == pytest.approx(2**-0.5)
    assert rmse([1.0, 2.0], [0.0, 2.0]) == pytest.approx(2**-0.5)
    assert (
        population_standardized_relative_error([1.0, 3.0], [2.0, 2.0], zero_variance="rmse") == 1.0
    )
    with pytest.raises(ValueError, match="constant truth"):
        population_standardized_relative_error([1.0, 3.0], [2.0, 2.0])


def test_evaluator_configuration_ignores_description_and_provenance() -> None:
    state = {"formula": "RMSE", "ddof": "0"}
    first = EvaluatorConfiguration.from_state(
        "example.evaluator", "1.0.0", state, description="first", provenance=("source:a",)
    )
    second = EvaluatorConfiguration.from_state(
        "example.evaluator", "1.0.0", state, description="second", provenance=("source:b",)
    )
    changed = EvaluatorConfiguration.from_state(
        "example.evaluator", "1.0.0", {**state, "ddof": "1"}
    )

    assert first.scientific_config_sha256 == second.scientific_config_sha256
    assert first.scientific_config_sha256 != changed.scientific_config_sha256


@pytest.mark.parametrize("prediction,truth", [([], []), ([1.0], [0.0, 1.0])])
def test_vector_metrics_reject_empty_or_mismatched_shapes(
    prediction: list[float], truth: list[float]
) -> None:
    with pytest.raises(ValueError, match="same nonzero length"):
        rmse(prediction, truth)
    with pytest.raises(ValueError, match="same nonzero length"):
        population_standardized_relative_error(prediction, truth)


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
def test_vector_metrics_reject_nonfinite_inputs(bad_value: float) -> None:
    with pytest.raises(ValueError, match="must be finite"):
        rmse([bad_value], [0.0])
    with pytest.raises(ValueError, match="must be finite"):
        population_standardized_relative_error([0.0], [bad_value])


def test_physical_trajectory_metrics_use_metres_and_global_scalar_rmse() -> None:
    prediction = [[[[0.0, 0.0]], [[0.0, 0.0]]]]
    truth = [[[[3.0 / PITCH_SCALE_M[0], 4.0 / PITCH_SCALE_M[1]]], [[0.0, 2.0 / 34.0]]]]

    metrics = physical_trajectory_metrics(prediction, truth)

    assert metrics.ade_m == pytest.approx(3.5)
    assert metrics.fde_m == pytest.approx(2.0)
    assert metrics.xy_rmse_m == pytest.approx((29.0 / 4.0) ** 0.5)


def test_physical_trajectory_metrics_reject_bad_shapes_and_nonfinite_values() -> None:
    with pytest.raises(ValueError, match="same nonempty batch"):
        physical_trajectory_metrics([], [])
    with pytest.raises(ValueError, match="same nonempty batch"):
        physical_trajectory_metrics([[[[0.0, 0.0]]]], [])
    with pytest.raises(ValueError, match="matching nonempty horizons"):
        physical_trajectory_metrics([[[[0.0, 0.0]]]], [[[[0.0, 0.0]], [[0.0, 0.0]]]])
    with pytest.raises(ValueError, match="matching nonempty entities"):
        physical_trajectory_metrics([[[[0.0, 0.0]]]], [[[[0.0, 0.0], [0.0, 0.0]]]])
    with pytest.raises(ValueError, match="x and y components"):
        physical_trajectory_metrics([[[[0.0]]]], [[[[0.0]]]])
    with pytest.raises(ValueError, match="coordinates must be finite"):
        physical_trajectory_metrics([[[[float("nan"), 0.0]]]], [[[[0.0, 0.0]]]])
    with pytest.raises(ValueError, match="exactly two axes"):
        physical_trajectory_metrics([[[[0.0, 0.0]]]], [[[[0.0, 0.0]]]], (52.5,))


def test_sensor_state_sre_quality_gate_and_target_nonselection() -> None:
    perfect = evaluate_sensor_state_channels(
        {"position": [0.0, 1.0, 2.0]},
        {"position": [0.0, 1.0, 2.0]},
        SensorCandidateFamily.CLEAN_HORIZONTAL_MOTION,
    )
    assert perfect.per_channel_sre == (("position", 0.0),)
    assert perfect.per_channel_quality == (("position", 1.0),)
    assert perfect.mean_sre == 0.0 and perfect.mean_quality == 1.0
    assert perfect.benchmark_reward_emitted is False
    assert quality_from_sre(2.0) == 0.0
    assert quality_from_sre(-2.0) == 1.0
    assert evaluate_sensor_state_gate([0.2, 0.3]).passes
    assert not evaluate_sensor_state_gate([0.3, 0.300001]).passes
    with pytest.raises(ValueError, match="constant truth"):
        evaluate_sensor_state_channels(
            {"constant": [0.0, 0.0]},
            {"constant": [1.0, 1.0]},
            SensorCandidateFamily.CLEAN_HORIZONTAL_MOTION,
        )


def test_corruption_region_requires_256_validation_rows() -> None:
    values = list(float(index) for index in range(256))
    with pytest.raises(ValueError, match="256 rows"):
        evaluate_sensor_state_channels(
            {"imu": values},
            {"imu": values},
            SensorCandidateFamily.CORRUPTION_REGION,
            region_mask=[index < 255 for index in range(256)],
        )
    result = evaluate_sensor_state_channels(
        {"imu": values},
        {"imu": values},
        SensorCandidateFamily.CORRUPTION_REGION,
        region_mask=[True] * 256,
    )
    assert result.mean_sre == 0.0


def test_piecewise_linear_transform_interpolates_and_clamps() -> None:
    transform = PiecewiseLinearTransform(((0.0, 0.0), (0.5, 0.25), (1.0, 1.0)))
    assert transform.apply(-1.0) == 0.0
    assert transform.apply(0.25) == pytest.approx(0.125)
    assert transform.apply(2.0) == 1.0
    with pytest.raises(ValueError, match="x values must rise"):
        PiecewiseLinearTransform(((0.5, 0.0), (0.5, 1.0)))
