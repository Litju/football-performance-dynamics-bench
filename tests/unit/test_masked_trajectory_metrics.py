from __future__ import annotations

import math

import pytest

from fpdbench.evaluation.metrics import masked_physical_trajectory_metrics


def test_masked_physical_metrics_support_variable_target_counts_and_null_xy_masks() -> None:
    metrics = masked_physical_trajectory_metrics(
        prediction=(
            (((1.0, 0.0), (2.0, 0.0)), ((1.0, 1.0), (3.0, 0.0))),
            (((0.0, 0.0),), ((0.0, 0.0),)),
        ),
        truth=(
            (((0.0, 0.0), None), ((0.0, 1.0), (3.0, 0.0))),
            (((0.0, 0.0),), ((0.0, 0.0),)),
        ),
    )

    assert metrics.ade_m == pytest.approx(2.0 / 5.0)
    assert metrics.fde_m == pytest.approx(1.0 / 3.0)
    assert metrics.xy_rmse_m == pytest.approx(math.sqrt(2.0 / 10.0))
    assert metrics.scored_points == 5
    assert metrics.final_targets == 3


def test_masked_physical_metrics_reject_partial_or_empty_truth_masks() -> None:
    with pytest.raises(ValueError, match="finite XY pairs or a null XY mask"):
        masked_physical_trajectory_metrics(
            ((((0.0, 0.0),),),),
            ((((1.0, None),),),),  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="final-horizon targets"):
        masked_physical_trajectory_metrics(
            ((((0.0, 0.0),), ((0.0, 0.0),)),),
            ((((0.0, 0.0),), (None,)),),  # type: ignore[arg-type]
        )
