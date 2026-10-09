import copy
import hashlib
import json
from pathlib import Path
from typing import cast

import pytest

from fpdbench.data_sources.skillcorner import (
    MANIFEST_PATH,
    git_blob_sha,
    load_manifest,
    manifest_hash,
    master_drift_error,
    revision_drift_error,
    source_population_hash,
    source_release_hash,
    validate_lfs_payload,
    validate_lfs_pointer,
    validate_manifest,
    validate_tree_inventory,
    verify_local_checkout,
)
from fpdbench.validation.artifacts import validate_artifacts


def _tree_entries(manifest: dict[str, object]) -> list[dict[str, object]]:
    entries = [{"path": "data/matches", "type": "tree"}]
    matches = cast(list[dict[str, object]], manifest["available_matches"])
    for match in matches:
        match_id = match["match_id"]
        entries.append({"path": f"data/matches/{match_id}", "type": "tree"})
        for file in cast(list[dict[str, object]], match["files"]):
            entries.append(
                {
                    "path": file["repository_path"],
                    "type": "blob",
                    "sha": file["git_blob_sha"],
                    "size": file["byte_size"],
                }
            )
    other_files = [
        cast(dict[str, object], manifest["source_index"]),
        *cast(list[dict[str, object]], manifest["repository_context_files"]),
        *cast(list[dict[str, object]], manifest["non_selected_repository_artifacts"]),
    ]
    body_pose = cast(dict[str, object], manifest["optional_body_pose_source"])
    other_files.extend(
        cast(dict[str, object], body_pose[key])
        for key in ("github_manifest", "github_readme", "github_sample")
    )
    entries.extend(
        {
            "path": file["repository_path"],
            "type": "blob",
            "sha": file["git_blob_sha"],
            "size": file["byte_size"],
        }
        for file in other_files
    )
    return entries


def _refresh_hashes(manifest: dict[str, object]) -> None:
    manifest["source_population_hash"] = source_population_hash(
        cast(list[object], manifest["selected_source_matches"])
    )
    manifest["source_release_hash"] = source_release_hash(manifest)
    manifest["source_release_id"] = (
        f"skillcorner_open_data_v1:sha256:{manifest['source_release_hash']}"
    )
    manifest["manifest_sha256"] = manifest_hash(manifest)


def test_checked_in_source_manifest_is_deterministic_and_valid() -> None:
    manifest = load_manifest()
    assert validate_manifest(manifest) == ()
    assert (
        MANIFEST_PATH.read_text()
        == json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )
    assert manifest["manifest_sha256"] == manifest_hash(manifest)


def test_set_order_and_descriptive_metadata_do_not_churn_source_identity() -> None:
    manifest = load_manifest()
    baseline = source_release_hash(manifest)
    baseline_population = source_population_hash(
        cast(list[object], manifest["selected_source_matches"])
    )
    reordered = copy.deepcopy(manifest)
    cast(list[object], reordered["available_matches"]).reverse()
    cast(list[object], reordered["selected_source_matches"]).reverse()
    for raw_match in cast(list[object], reordered["available_matches"]):
        cast(list[object], cast(dict[str, object], raw_match)["files"]).reverse()
    assert source_release_hash(reordered) == baseline
    assert source_population_hash(cast(list[object], reordered["selected_source_matches"])) == (
        baseline_population
    )

    first = cast(dict[str, object], cast(list[object], reordered["available_matches"])[0])
    first["home_team"] = "descriptive change"
    context = cast(list[dict[str, object]], reordered["repository_context_files"])
    readme = next(item for item in context if item["repository_path"] == "README.md")
    readme["claimed_match_count"] = 10
    assert len(cast(list[object], reordered["selected_source_matches"])) == 20
    assert source_release_hash(reordered) == baseline


def test_membership_and_selected_file_identity_mutations_change_release_identity() -> None:
    manifest = load_manifest()
    baseline = source_release_hash(manifest)
    changed_membership = copy.deepcopy(manifest)
    cast(list[object], changed_membership["selected_source_matches"]).pop()
    assert source_release_hash(changed_membership) != baseline

    changed_file = copy.deepcopy(manifest)
    first_match = cast(dict[str, object], cast(list[object], changed_file["available_matches"])[0])
    first_file = cast(dict[str, object], cast(list[object], first_match["files"])[0])
    first_file["git_blob_sha"] = "0" * 40
    assert source_release_hash(changed_file) != baseline


def test_stale_readme_match_count_does_not_define_source_population() -> None:
    manifest = load_manifest()
    assert cast(dict[str, object], manifest["source_index"])["repository_path"] == (
        "data/matches.json"
    )
    assert len(cast(list[object], manifest["available_matches"])) == 20
    assert manifest["selected_source_matches"] == [
        cast(dict[str, object], match)["match_id"]
        for match in sorted(
            cast(list[object], manifest["available_matches"]),
            key=lambda item: cast(dict[str, object], item)["match_id"],
        )
    ]
    assert cast(list[object], manifest["excluded_source_matches"]) == []
    baseline = source_release_hash(manifest)
    readme = next(
        item
        for item in cast(list[dict[str, object]], manifest["repository_context_files"])
        if item["repository_path"] == "README.md"
    )
    readme["claimed_match_count"] = 10
    assert len(cast(list[object], manifest["selected_source_matches"])) == 20
    assert source_release_hash(manifest) == baseline


def test_current_master_and_body_pose_revision_drift_are_detectable() -> None:
    pin = cast(dict[str, object], load_manifest()["upstream"])["pinned_commit"]
    assert master_drift_error(str(pin), str(pin)) is None
    assert master_drift_error(str(pin), "f" * 40) is not None
    assert revision_drift_error("a" * 40, "a" * 40, "Body Pose main") is None
    assert revision_drift_error("a" * 40, "b" * 40, "Body Pose main") == (
        f"Body Pose main drift: pinned {'a' * 40}, current {'b' * 40}"
    )


@pytest.mark.parametrize(
    "path", ["data/matches/2017461", "data/matches/2017461/2017461_match.json"]
)
def test_missing_match_directory_or_expected_file_fails(path: str) -> None:
    manifest = load_manifest()
    entries = [entry for entry in _tree_entries(manifest) if entry["path"] != path]
    assert any(
        "missing upstream source path" in error
        for error in validate_tree_inventory(manifest, entries)
    )


def test_duplicate_match_and_unexpected_source_paths_fail() -> None:
    manifest = load_manifest()
    duplicate = copy.deepcopy(manifest)
    available = cast(list[object], duplicate["available_matches"])
    available.append(copy.deepcopy(available[0]))
    assert any("duplicate available match" in error for error in validate_manifest(duplicate))

    entries = _tree_entries(manifest)
    entries.extend(
        [
            {"path": "data/matches/9999999", "type": "tree"},
            {"path": "data/matches/9999999/extra.csv", "type": "blob", "sha": "0" * 40, "size": 1},
            {
                "path": "data/matches/2017461/unexpected.csv",
                "type": "blob",
                "sha": "0" * 40,
                "size": 1,
            },
        ]
    )
    errors = validate_tree_inventory(manifest, entries)
    assert any("unexpected upstream source path: data/matches/9999999" in error for error in errors)
    assert any(
        "unexpected upstream source path: data/matches/2017461/unexpected.csv" in error
        for error in errors
    )


def test_lfs_pointer_oid_and_size_are_distinct_from_pointer_blob_identity() -> None:
    manifest = load_manifest()
    match = cast(dict[str, object], cast(list[object], manifest["available_matches"])[0])
    tracking = next(
        cast(dict[str, object], item)
        for item in cast(list[object], match["files"])
        if str(cast(dict[str, object], item)["repository_path"]).endswith(
            "_tracking_extrapolated.jsonl"
        )
    )
    pointer = (
        "version https://git-lfs.github.com/spec/v1\n"
        f"oid sha256:{tracking['lfs_oid_sha256']}\n"
        f"size {tracking['lfs_payload_size']}\n"
    ).encode()
    assert validate_lfs_pointer(pointer, tracking, str(tracking["repository_path"])) == ()
    assert any(
        "payload OID mismatch" in error
        for error in validate_lfs_pointer(
            pointer.replace(str(tracking["lfs_oid_sha256"]).encode(), b"0" * 64),
            tracking,
            str(tracking["repository_path"]),
        )
    )
    assert any(
        "payload size mismatch" in error
        for error in validate_lfs_pointer(
            pointer.replace(str(tracking["lfs_payload_size"]).encode(), b"1"),
            tracking,
            str(tracking["repository_path"]),
        )
    )
    assert any(
        "payload OID mismatch" in error
        for error in validate_lfs_payload(
            b"not the tracking payload", tracking, str(tracking["repository_path"])
        )
    )
    assert any(
        "payload size mismatch" in error
        for error in validate_lfs_payload(
            b"not the tracking payload", tracking, str(tracking["repository_path"])
        )
    )


def test_local_paths_and_runtime_timestamps_do_not_affect_source_identity() -> None:
    manifest = load_manifest()
    baseline = source_release_hash(manifest)
    manifest["local_path"] = "/tmp/skillcorner"
    manifest["retrieved_at"] = "2099-01-01T00:00:00Z"
    manifest["hostname"] = "local-machine"
    assert source_release_hash(manifest) == baseline


def test_artifact_guard_rejects_raw_source_payload_paths(tmp_path: Path) -> None:
    source = tmp_path / "data" / "matches" / "2017461" / "2017461_dynamic_events.csv"
    source.parent.mkdir(parents=True)
    source.write_text("source rows are not fixtures\n")
    errors = validate_artifacts(tmp_path)
    assert any("SkillCorner source or derived data is not allowed" in error for error in errors)


def test_local_checkout_verifies_git_files_lfs_pointer_and_acquired_payload(
    tmp_path: Path,
) -> None:
    payload = b"synthetic local tracking payload"
    lfs_oid = hashlib.sha256(payload).hexdigest()
    pointer = (
        f"version https://git-lfs.github.com/spec/v1\noid sha256:{lfs_oid}\nsize {len(payload)}\n"
    ).encode()
    index_bytes = json.dumps([{"id": 42}]).encode()
    source_files = {
        "data/matches/42/42_match.json": b'{"id":42}',
        "data/matches/42/42_tracking_extrapolated.jsonl": pointer,
        "data/matches/42/42_dynamic_events.csv": b"synthetic,event\n",
        "data/matches/42/42_phases_of_play.csv": b"synthetic,phase\n",
    }
    entries = []
    for path, content in source_files.items():
        entry: dict[str, object] = {
            "repository_path": path,
            "git_blob_sha": git_blob_sha(content),
            "byte_size": len(content),
        }
        if path.endswith("_tracking_extrapolated.jsonl"):
            entry.update(
                identity_type="git_lfs_pointer",
                lfs_oid_sha256=lfs_oid,
                lfs_payload_size=len(payload),
            )
        else:
            entry["identity_type"] = "git_blob"
            if path.endswith("_match.json"):
                entry["raw_sha256"] = hashlib.sha256(content).hexdigest()
        entries.append(entry)
    index = {
        "repository_path": "data/matches.json",
        "git_blob_sha": git_blob_sha(index_bytes),
        "raw_sha256": hashlib.sha256(index_bytes).hexdigest(),
    }
    manifest: dict[str, object] = {
        "source_index": index,
        "selected_source_matches": [42],
        "available_matches": [{"match_id": 42, "files": entries}],
    }
    (tmp_path / "data").mkdir()
    (tmp_path / "data/matches.json").write_bytes(index_bytes)
    for path, content in source_files.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    assert verify_local_checkout(manifest, tmp_path) == ()
    (tmp_path / "data/matches/42/42_tracking_extrapolated.jsonl").write_bytes(payload)
    assert verify_local_checkout(manifest, tmp_path) == ()
