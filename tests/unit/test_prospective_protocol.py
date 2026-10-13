from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import cast

import pytest

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.prospective_protocol import (
    PROTOCOL_SHA256,
    load_prospective_protocol,
    validate_prospective_protocol_document,
)

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "src" / "fpdbench"


def _read(relative: str) -> dict[str, object]:
    return cast(dict[str, object], json.loads((BASE / relative).read_text()))


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _rehash(document: dict[str, object]) -> None:
    state = cast(dict[str, object], document["scientific_state"])
    identity = cast(dict[str, object], state["identity"])
    identity["research_question_sha256"] = _digest(identity["research_question"])
    for item in cast(list[dict[str, object]], state["benchmarks"]):
        item["benchmark_sha256"] = _digest(
            {key: value for key, value in item.items() if key != "benchmark_sha256"}
        )
    split = cast(dict[str, object], state["split"])
    roles = split["roles"]
    lomo = cast(dict[str, object], split["lomo"])
    folds = lomo["folds"]
    split["role_assignment_sha256"] = _digest(roles)
    split["lomo_assignment_sha256"] = _digest(folds)
    split["split_sha256"] = _digest({"roles": roles, "lomo_folds": folds})
    evaluation = cast(dict[str, object], state["evaluation"])
    evaluation["metric_contract_sha256"] = _digest(
        {key: value for key, value in evaluation.items() if key != "metric_contract_sha256"}
    )
    document["protocol_sha256"] = _digest(state)


def _authorities() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    return (
        _read("data_sources/skillcorner_open_data_v1.json"),
        _read("data_states/skillcorner_5hz_v1.json"),
        _read("eligibility/skillcorner_window_v1.json"),
    )


def _validate(document: dict[str, object]) -> None:
    validate_prospective_protocol_document(document, *_authorities())


def test_prospective_protocol_is_stable_pinned_and_uses_the_exact_population() -> None:
    document = load_prospective_protocol()

    assert document["protocol_sha256"] == PROTOCOL_SHA256
    _validate(document)


def test_protocol_hash_detects_unreviewed_identity_drift() -> None:
    document = copy.deepcopy(load_prospective_protocol())
    document["protocol_id"] = "different.protocol"

    with pytest.raises(ValueError, match="protocol_id"):
        _validate(document)


def test_protocol_rejects_wrong_data_and_eligibility_hashes_even_when_rehashed() -> None:
    document = copy.deepcopy(load_prospective_protocol())
    state = cast(dict[str, object], document["scientific_state"])
    authorities = cast(dict[str, object], state["authorities"])
    authorities["measurement_state_hash"] = "0" * 64
    _rehash(document)
    with pytest.raises(ValueError, match="measurement state hash"):
        _validate(document)

    document = copy.deepcopy(load_prospective_protocol())
    state = cast(dict[str, object], document["scientific_state"])
    authorities = cast(dict[str, object], state["authorities"])
    authorities["eligibility_policy_hash"] = "0" * 64
    _rehash(document)
    with pytest.raises(ValueError, match="eligibility policy hash"):
        _validate(document)


def test_protocol_rejects_future_feature_leakage_even_when_rehashed() -> None:
    document = copy.deepcopy(load_prospective_protocol())
    state = cast(dict[str, object], document["scientific_state"])
    regimes = cast(list[dict[str, object]], state["information_regimes"])
    future_ball = next(item for item in regimes if item["regime_id"] == "future_ball")
    features = cast(list[object], future_ball["model_visible_features"])
    features.append("future.phase.label")
    _rehash(document)

    with pytest.raises(ValueError, match="information boundary"):
        _validate(document)


def test_protocol_rejects_cross_role_overlap_and_target_mask_ambiguity() -> None:
    document = copy.deepcopy(load_prospective_protocol())
    state = cast(dict[str, object], document["scientific_state"])
    split = cast(dict[str, object], state["split"])
    roles = cast(dict[str, list[object]], split["roles"])
    roles["evaluation"].append(roles["training"][0])
    _rehash(document)
    with pytest.raises(ValueError, match="match role assignment"):
        _validate(document)

    document = copy.deepcopy(load_prospective_protocol())
    state = cast(dict[str, object], document["scientific_state"])
    targets = cast(dict[str, object], state["target_panel"])
    targets["target_truth_mask"] = "mask each coordinate independently"
    _rehash(document)
    with pytest.raises(ValueError, match="target mask"):
        _validate(document)


def test_protocol_rejects_incompatible_metrics_and_missing_delegated_decisions() -> None:
    document = copy.deepcopy(load_prospective_protocol())
    state = cast(dict[str, object], document["scientific_state"])
    evaluation = cast(dict[str, object], state["evaluation"])
    primary = cast(dict[str, object], evaluation["primary_metric"])
    primary["metric_id"] = "sre.rmse_over_population_std.v1"
    _rehash(document)
    with pytest.raises(ValueError, match="primary metric compatibility"):
        _validate(document)

    document = copy.deepcopy(load_prospective_protocol())
    state = cast(dict[str, object], document["scientific_state"])
    selection = cast(dict[str, object], state["selection_and_execution"])
    compute_budget = cast(dict[str, object], selection["compute_budget"])
    compute_budget.pop("exact_per_run_and_campaign_ceilings_owner")
    _rehash(document)
    with pytest.raises(ValueError, match="compute_budget"):
        _validate(document)


def test_protocol_rejects_four_match_confirmatory_inference_even_when_rehashed() -> None:
    changes = (
        ("confirmatory_scope", "four directional confirmatory hypotheses"),
        ("method", "paired one-sided Student t test on four match-level contrasts"),
        ("confidence_interval", "two-sided 95% Student t interval"),
        ("multiplicity", "Holm step-down familywise alpha 0.05"),
    )
    for key, value in changes:
        document = copy.deepcopy(load_prospective_protocol())
        state = cast(dict[str, object], document["scientific_state"])
        analysis = cast(dict[str, object], state["analysis"])
        if key == "confirmatory_scope":
            analysis[key] = value
        else:
            uncertainty = cast(dict[str, object], analysis["uncertainty"])
            uncertainty[key] = value
        _rehash(document)

        with pytest.raises(ValueError):
            _validate(document)


def test_protocol_rejects_authority_manifest_hash_drift() -> None:
    source, measurement, eligibility = _authorities()
    measurement["data_state_hash"] = "0" * 64

    with pytest.raises(ValueError, match="measurement authority hash"):
        validate_prospective_protocol_document(
            load_prospective_protocol(), source, measurement, eligibility
        )
