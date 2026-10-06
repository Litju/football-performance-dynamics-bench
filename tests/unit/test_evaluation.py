import pytest

from fpdbench.benchmarks.multimodal_state_estimation import (
    SensorCandidateFamily,
    evaluate_sensor_state_channels,
    evaluate_sensor_state_gate,
    quality_from_sre,
)
from fpdbench.evaluation.calibration import PiecewiseLinearTransform
from fpdbench.evaluation.metrics import population_standardized_relative_error, rmse


def test_relative_error_uses_population_standard_deviation() -> None:
    assert population_standardized_relative_error([0.0, 1.0, 2.0], [0.0, 1.0, 2.0]) == 0.0
    assert population_standardized_relative_error([1.0, 2.0], [0.0, 2.0]) == pytest.approx(2**-0.5)
    assert rmse([1.0, 2.0], [0.0, 2.0]) == pytest.approx(2**-0.5)
    assert (
        population_standardized_relative_error([1.0, 3.0], [2.0, 2.0], zero_variance="rmse") == 1.0
    )
    with pytest.raises(ValueError, match="constant truth"):
        population_standardized_relative_error([1.0, 3.0], [2.0, 2.0])


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
