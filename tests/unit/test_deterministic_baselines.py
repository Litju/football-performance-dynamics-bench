import pytest

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.deterministic_baselines import (
    predict_baseline,
    predict_displacement,
)


def test_persistence_and_velocity() -> None:
    history = [(2.0 + i * 0.2, -1.0 - i * 0.4) for i in range(6)]
    assert predict_baseline("origin_persistence_v1", history) == (history[-1],) * 15
    result = predict_baseline("constant_velocity_1s_v1", history)
    assert result[0] == pytest.approx((3.2, -3.4))
    assert result[-1] == pytest.approx((6.0, -9.0))
    displacement = predict_displacement("constant_velocity_1s_v1", history)
    assert displacement[-1] == pytest.approx((3.0, -6.0))
    assert predict_displacement("origin_persistence_v1", history) == ((0.0, 0.0),) * 15


def test_missing_history_falls_back_and_missing_origin_fails() -> None:
    history = [None, None, None, (float("nan"), 0.0), None, (2.0, 3.0)]
    assert predict_baseline("constant_velocity_1s_v1", history) == ((2.0, 3.0),) * 15
    with pytest.raises(ValueError):
        predict_baseline("constant_velocity_1s_v1", [None] * 6)


def test_sparse_velocity_uses_all_finite_observations() -> None:
    history = [(0.0, 0.0), None, (float("inf"), 0.0), None, None, (1.0, 2.0)]
    assert predict_baseline("constant_velocity_1s_v1", history)[-1] == pytest.approx((4.0, 8.0))
    with pytest.raises(ValueError):
        predict_baseline("other", history)
