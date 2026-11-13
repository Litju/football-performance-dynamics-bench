"""Gate 5 tests use invented metadata only."""

import hashlib

import pytest

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    empirical_experiment_plan as plan,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    res635_post_failure_evaluation as scorer,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    res635_verification as verification,
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


def test_real_match_aggregation_requires_complete_records_without_inference() -> None:
    receipts = [
        {
            "match": match,
            "records": [
                {
                    "cell": list(cell),
                    "strata": {
                        "all": {"metrics": {metric: float(i + 1) for metric in scorer.METRICS}}
                    },
                }
                for cell in scorer.CELLS
            ],
        }
        for i, match in enumerate(verification.EVALUATION_MATCHES)
    ]
    result = verification.aggregate(receipts, matches=verification.EVALUATION_MATCHES)
    assert result["records"] == 72
    assert all(values["ade_m"] == 2.5 for values in result["equal_match_means"].values())
    receipts[0]["records"][0]["strata"]["all"]["metrics"]["ade_m"] = float("nan")
    with pytest.raises(ValueError, match="invalid aggregate metric"):
        verification.aggregate(receipts, matches=verification.EVALUATION_MATCHES)
    receipts[0]["records"][0]["strata"]["all"]["metrics"]["ade_m"] = 1.0
    receipts[0]["records"].pop()
    with pytest.raises(ValueError, match="18 unique"):
        verification.aggregate(receipts, matches=verification.EVALUATION_MATCHES)


def test_proposed_scope_is_deterministic_and_never_accepts_consumed_scope() -> None:
    bindings = {
        f"{name}_sha256": "a" * 64
        for name in ("source", "scorer", "verifier", "runtime", "ledger", "output")
    }
    bindings["independent_report_sha256"] = "b" * 64
    bindings["ledger_sha256"] = "d" * 64
    original = preflight.proposed_scope(bindings)
    assert (
        len(original) == 64
        and preflight.proposed_scope(dict(reversed(list(bindings.items())))) == original
    )
    bindings["output_sha256"] = "c" * 64
    assert preflight.proposed_scope(bindings) != original
    bindings["output_sha256"] = preflight.CONSUMED_SCOPE
    with pytest.raises(ValueError, match="forbidden"):
        preflight.proposed_scope(bindings)
