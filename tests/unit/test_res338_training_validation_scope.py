from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
from research_population_verifier_v1 import _scoped_authorities  # noqa: E402


def test_training_validation_authorities_exclude_evaluation_matches() -> None:
    authorities = _scoped_authorities("training-validation")
    role_counts = {
        role: sum(actual_role == role for actual_role, _ in authorities.roles)
        for role in ("training", "validation", "evaluation")
    }
    selected = {str(match_id) for match_id in authorities.source["selected_source_matches"]}

    assert role_counts == {"training": 12, "validation": 4, "evaluation": 0}
    assert len(selected) == 16
    assert selected == set(authorities.match_order)
    assert len(authorities.match_order) == 16
