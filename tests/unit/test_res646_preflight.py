"""Gate 5 tests use invented metadata only."""

import hashlib
from pathlib import Path

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
    seals: list[str] = []
    scope = "e" * 64
    for receipt in receipts:
        receipt["scope_sha256"] = scope
        receipt["previous_sha256"] = seals[-1] if seals else "0" * 64
        seals.append(scorer.digest(receipt))
    assert verification.verify_real_receipts(receipts, scope, seals) == result
    with pytest.raises(ValueError, match="receipt identity"):
        verification.verify_real_receipts(receipts, scope, list(reversed(seals)))
    with pytest.raises(ValueError, match="incomplete"):
        verification.verify_real_receipts(receipts[:-1], scope, seals[:-1])
    with pytest.raises(ValueError, match="invalid scope"):
        verification.verify_real_receipts(receipts, preflight.CONSUMED_SCOPE, seals)
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


def test_private_admission_reader_rejects_aliases_and_historical_paths(tmp_path: Path) -> None:
    directory = tmp_path / "fpdbench-private" / "research"
    directory.mkdir(parents=True, mode=0o700)
    path = directory / "research-admission.json"
    path.write_bytes(b"{}")
    path.chmod(0o600)
    assert preflight._read_admission(path) == b"{}"
    alias = tmp_path / "alias"
    alias.symlink_to(directory, target_is_directory=True)
    with pytest.raises(OSError):
        preflight._read_admission(alias / path.name)
    with pytest.raises(PermissionError):
        preflight._read_admission(tmp_path / "res594" / path.name)


def test_private_preflight_reuses_evidence_and_treats_empty_paths_as_missing(
    tmp_path: Path,
) -> None:
    config = tmp_path / "res646.env"
    config.write_text("SOURCE_INVENTORY=\nLEDGER_ROOT=''\nOUTPUT_DIRECTORY=\"\"\n")
    config.chmod(0o600)
    evidence = tmp_path / "existing-evidence.txt"
    evidence.write_text("Existing verified 18+18 checkpoint and receipt hashes; 81 source hashes.")
    evidence.chmod(0o600)
    report = preflight.private_preflight(config, evidence)
    assert report["status"] == "MISSING_OWNER_LOCAL_CONFIG"
    assert len(report["missing_fields"]) == 7
    assert report["prior_evidence_sha256"] == hashlib.sha256(evidence.read_bytes()).hexdigest()
    assert report["source_rows_opened"] is False
    assert report["models_loaded"] is False
    assert report["scope_consumed"] is False
    assert set(tmp_path.iterdir()) == {config, evidence}
