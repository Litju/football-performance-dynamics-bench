"""Gate 5 tests use invented metadata only."""

import hashlib

import pytest

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    empirical_experiment_plan as plan,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import res645_checkpoints as ck
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    res646_preflight as preflight,
)


def test_admission_requires_identity_roles_and_positive_counts() -> None:
    roles = plan.protocol_split_v2()["roles"]
    document = {
        "status": "RESEARCH_RECONCILED",
        "protected_status": "NOT_QUALIFIED",
        "source_release_hash": "e92c417b7640b27399451134ee3fce4b1961b0c0dfc2e01175a8f3c906a9ae07",
        "source_population_hash": (
            "e9054b7ddc2dfeff4dd8425ea61a23ed0b326076a08899e47502484228fdbdf4"
        ),
        "per_match": {
            mid: {"role": role, "counts": {"scoreable_windows": 2}}
            for role, matches in roles.items()
            for mid in matches
        },
    }
    digest = hashlib.sha256(ck.canonical(document)).hexdigest()
    assert preflight._validate_admission(document, digest) == dict.fromkeys(roles["evaluation"], 2)
    document["per_match"][roles["evaluation"][0]]["role"] = "training"
    with pytest.raises(ValueError, match="identity"):
        preflight._validate_admission(document, digest)
    digest = hashlib.sha256(ck.canonical(document)).hexdigest()
    with pytest.raises(ValueError, match="role"):
        preflight._validate_admission(document, digest)
    document["per_match"][roles["evaluation"][0]]["role"] = "evaluation"
    document["per_match"][roles["evaluation"][0]]["counts"]["scoreable_windows"] = 0
    digest = hashlib.sha256(ck.canonical(document)).hexdigest()
    with pytest.raises(ValueError, match="scoreable-window"):
        preflight._validate_admission(document, digest)
