from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
from res338_cuda_qualification import (  # noqa: E402
    INFORMATION_REGIMES,
    TARGET_PLAYERS,
    _inputs,
    _truth_and_mask,
)


def test_cuda_qualification_uses_one_directed_scene_panel() -> None:
    for regime in INFORMATION_REGIMES:
        inputs = _inputs(np.random.default_rng(1729), 4, regime)
        assert inputs.target_history.shape == (4, TARGET_PLAYERS, 78)
        assert inputs.target_side.shape == (4,)

    truth, mask = _truth_and_mask(np.random.default_rng(2718), 4)
    assert truth.shape == (4, TARGET_PLAYERS, 15, 2)
    assert mask.shape == (4, TARGET_PLAYERS, 15)
