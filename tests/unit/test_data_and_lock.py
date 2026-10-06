from pathlib import Path

import pytest

from fpdbench.data import (
    ArtifactReference,
    DatasetMembership,
    DataStateDescriptor,
    PopulationSemantics,
    SplitProtocolDescriptor,
    membership_digest,
)
from fpdbench.provenance.scientific_lock import (
    LOCK_SCHEMA_VERSION,
    build_scientific_lock,
    canonical_scientific_bytes,
    compute_scientific_lock_hash,
    verify_scientific_lock,
)


def _digest(char: str) -> str:
    return char * 64


def _scientific_state() -> dict[str, object]:
    return {
        "lock_schema_version": LOCK_SCHEMA_VERSION,
        "benchmark_id": "conditional_multi_agent_motion_prediction/absolute_position_prediction",
        "benchmark_definition_hash": _digest("a"),
        "data_release_id": "position-data",
        "data_release_version": "1.0.0",
        "data_manifest_hash": _digest("b"),
        "data_state_id": "repaired_position_measurement_state",
        "split_protocol_id": "match_grouped_split",
        "split_protocol_version": "1.0.0",
        "split_protocol_hash": _digest("c"),
        "evaluator_id": "physical_trajectory_metrics",
        "evaluator_version": "1.0.0",
        "evaluator_hash": _digest("d"),
        "schema_version": "1.0.0",
        "schema_hash": _digest("e"),
        "fixture_manifest_hash": _digest("f"),
        "scientific_provenance_snapshot": {
            "snapshot_id": "evidence-snapshot",
            "snapshot_hash": _digest("1"),
            "citations": ["registry://r2/conditional_team_response_absolute_position"],
        },
    }


def test_artifact_sha256_verification_and_immutable_descriptors(tmp_path: Path) -> None:
    artifact_path = tmp_path / "artifact.bin"
    artifact_path.write_bytes(b"scientific artifact")
    import hashlib

    reference = ArtifactReference(
        "artifact://fixture",
        hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
        size_bytes=artifact_path.stat().st_size,
    )
    assert reference.verify(artifact_path)
    state = DataStateDescriptor("state", "1.0.0", "fixed transform", [reference])
    assert isinstance(state.artifacts, tuple)
    assert state.artifacts[0] == reference
    population = PopulationSemantics("target_population", "all eligible target entities")
    membership = DatasetMembership("study_membership", 1, membership_digest(["sample-1"]))
    split = SplitProtocolDescriptor("grouped", "1.0.0", _digest("c"), "match", "public")
    assert population.population_id != membership.membership_id
    assert split.protocol_id == "grouped"


def test_membership_digest_is_length_delimited_and_ordered() -> None:
    assert membership_digest(["a", "bc"]) != membership_digest(["ab", "c"])
    assert membership_digest(["a", "b"]) != membership_digest(["b", "a"])


def test_scientific_lock_is_deterministic_and_excludes_governance() -> None:
    base = _scientific_state()
    first = build_scientific_lock(base)
    second = build_scientific_lock(base)
    assert first == second
    assert verify_scientific_lock(first)
    governed = dict(base)
    governed.update(
        {
            "legal_status": "not_assessed",
            "publication_status": "private",
            "hosting_provider": "local",
            "release_timestamp": "2099-01-01T00:00:00Z",
        }
    )
    assert compute_scientific_lock_hash(governed) == first["scientific_lock_hash"]
    assert "hosting_provider" not in first


def test_scientific_lock_changes_when_scientific_state_changes() -> None:
    base = _scientific_state()
    original = compute_scientific_lock_hash(base)
    changed = dict(base)
    changed["data_manifest_hash"] = _digest("9")
    assert compute_scientific_lock_hash(changed) != original
    lock = build_scientific_lock(base)
    lock["scientific_lock_hash"] = _digest("0")
    assert not verify_scientific_lock(lock)


def test_lock_canonical_json_and_rejects_non_string_leaves() -> None:
    assert (
        canonical_scientific_bytes({"z": "last", "a": ["first"]}) == b'{"a":["first"],"z":"last"}'
    )
    assert canonical_scientific_bytes({"\U0001f600": "astral", "\ue000": "bmp"}) == (
        '{"😀":"astral","\ue000":"bmp"}'.encode()
    )
    with pytest.raises(ValueError, match="only strings"):
        canonical_scientific_bytes({"count": 2})
    changed = _scientific_state()
    changed["schema_hash"] = "not-a-digest"
    with pytest.raises(ValueError, match="SHA-256"):
        compute_scientific_lock_hash(changed)
