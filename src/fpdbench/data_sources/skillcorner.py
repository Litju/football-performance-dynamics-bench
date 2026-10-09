"""Verify the immutable SkillCorner Open Data source authority."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from typing import cast

MANIFEST_PATH = Path(__file__).with_name("skillcorner_open_data_v1.json")
_HEX_40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_LFS_POINTER = re.compile(
    rb"version https://git-lfs\.github\.com/spec/v1\noid sha256:([0-9a-f]{64})\nsize ([0-9]+)\n?\Z"
)


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def source_population_hash(match_ids: Sequence[object]) -> str:
    ids = [_match_id(value) for value in match_ids]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate source match ID")
    return _digest(sorted(ids))


def _match_id(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"invalid source match ID: {value!r}")
    return value


def source_release_hash(manifest: Mapping[str, object]) -> str:
    upstream = cast(dict[str, object], manifest["upstream"])
    selected = sorted(
        _match_id(value) for value in cast(list[object], manifest["selected_source_matches"])
    )
    available = {
        _match_id(cast(dict[str, object], match)["match_id"]): cast(dict[str, object], match)
        for match in cast(list[object], manifest["available_matches"])
    }
    files: list[dict[str, object]] = []
    for match_id in selected:
        match = available[match_id]
        for file in cast(list[object], match["files"]):
            entry = cast(dict[str, object], file)
            identity: dict[str, object] = {
                field: entry[field]
                for field in (
                    "identity_type",
                    "git_blob_sha",
                    "byte_size",
                    "raw_sha256",
                    "lfs_oid_sha256",
                    "lfs_payload_size",
                )
                if field in entry
            }
            files.append(
                {
                    "match_id": match_id,
                    "repository_path": entry["repository_path"],
                    "identity": identity,
                }
            )
    files.sort(key=lambda item: str(item["repository_path"]))
    return _digest(
        {
            "schema_id": "fpdbench.source-release",
            "schema_version": "1.0.0",
            "source_id": manifest["source_id"],
            "repository": upstream["repository"],
            "pinned_commit": upstream["pinned_commit"],
            "selected_match_ids": selected,
            "files": files,
        }
    )


def manifest_hash(manifest: Mapping[str, object]) -> str:
    content = dict(manifest)
    content.pop("manifest_sha256", None)
    return _digest(content)


def _required_map(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    typed_value = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in typed_value):
        raise ValueError(f"{label} must be a JSON object")
    return cast(dict[str, object], typed_value)


def _required_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a JSON array")
    return cast(list[object], value)


def _safe_repository_path(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("repository path must be a string")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {".", ".."} for part in path.parts):
        raise ValueError(f"unsafe repository path: {value!r}")
    return value


def validate_manifest(manifest: Mapping[str, object]) -> tuple[str, ...]:
    errors: list[str] = []
    try:
        if manifest.get("schema_id") != "fpdbench.skillcorner-source-authority":
            errors.append("unexpected SkillCorner source-authority schema_id")
        if manifest.get("schema_version") != "1.0.0":
            errors.append("unsupported SkillCorner source-authority schema_version")
        upstream = _required_map(manifest.get("upstream"), "upstream")
        repository = upstream.get("repository")
        commit = upstream.get("pinned_commit")
        if repository != "SkillCorner/opendata":
            errors.append("unexpected upstream repository")
        if not isinstance(commit, str) or not _HEX_40.fullmatch(commit):
            errors.append("pinned upstream commit must be a full Git SHA")

        available = _required_list(manifest.get("available_matches"), "available_matches")
        selected = [
            _match_id(value)
            for value in _required_list(
                manifest.get("selected_source_matches"), "selected_source_matches"
            )
        ]
        excluded = _required_list(
            manifest.get("excluded_source_matches"), "excluded_source_matches"
        )
        available_by_id: dict[int, dict[str, object]] = {}
        for raw_match in available:
            match = _required_map(raw_match, "available match")
            match_id = _match_id(match.get("match_id"))
            if match_id in available_by_id:
                errors.append(f"duplicate available match: {match_id}")
                continue
            available_by_id[match_id] = match
        if len(selected) != len(set(selected)):
            errors.append("duplicate selected source match")
        excluded_by_id: dict[int, str] = {}
        for raw_exclusion in excluded:
            exclusion = _required_map(raw_exclusion, "excluded source match")
            match_id = _match_id(exclusion.get("match_id"))
            reason = exclusion.get("reason")
            if match_id in excluded_by_id:
                errors.append(f"duplicate excluded source match: {match_id}")
            elif not isinstance(reason, str) or not reason.strip():
                errors.append(f"excluded match {match_id} requires a precise reason")
            else:
                excluded_by_id[match_id] = reason
        if set(available_by_id) != set(selected) | set(excluded_by_id):
            errors.append("available matches must be partitioned by selected and excluded matches")
        if set(selected) & set(excluded_by_id):
            errors.append("a source match cannot be both selected and excluded")

        file_paths: set[str] = set()
        for match_id in selected:
            match = available_by_id.get(match_id)
            if match is None:
                continue
            for field in (
                "directory_present",
                "match_metadata_present",
                "tracking_path_present",
                "dynamic_events_present",
                "phases_of_play_present",
            ):
                if match.get(field) is not True:
                    errors.append(f"selected match {match_id} is missing {field}")
            files = _required_list(match.get("files"), f"match {match_id} files")
            by_path: dict[str, dict[str, object]] = {}
            for raw_file in files:
                entry = _required_map(raw_file, f"match {match_id} file")
                path = _safe_repository_path(entry.get("repository_path"))
                if path in file_paths:
                    errors.append(f"duplicate source file path: {path}")
                file_paths.add(path)
                by_path[path] = entry
                sha = entry.get("git_blob_sha")
                size = entry.get("byte_size")
                if not isinstance(sha, str) or not _HEX_40.fullmatch(sha):
                    errors.append(f"invalid Git blob SHA for {path}")
                if isinstance(size, bool) or not isinstance(size, int) or size < 0:
                    errors.append(f"invalid byte size for {path}")
                raw_sha = entry.get("raw_sha256")
                if raw_sha is not None and (
                    not isinstance(raw_sha, str) or not _HEX_64.fullmatch(raw_sha)
                ):
                    errors.append(f"invalid raw SHA-256 for {path}")
                is_tracking = path.endswith("_tracking_extrapolated.jsonl")
                if is_tracking:
                    if entry.get("identity_type") != "git_lfs_pointer":
                        errors.append(
                            f"tracking identity must distinguish the Git LFS pointer: {path}"
                        )
                    oid = entry.get("lfs_oid_sha256")
                    payload_size = entry.get("lfs_payload_size")
                    if not isinstance(oid, str) or not _HEX_64.fullmatch(oid):
                        errors.append(f"invalid Git LFS payload OID for {path}")
                    if (
                        isinstance(payload_size, bool)
                        or not isinstance(payload_size, int)
                        or payload_size <= 0
                    ):
                        errors.append(f"invalid Git LFS payload size for {path}")
                elif entry.get("identity_type") != "git_blob":
                    errors.append(f"ordinary source file must use Git blob identity: {path}")
            expected_paths = {
                f"data/matches/{match_id}/{match_id}_match.json",
                f"data/matches/{match_id}/{match_id}_tracking_extrapolated.jsonl",
                f"data/matches/{match_id}/{match_id}_dynamic_events.csv",
                f"data/matches/{match_id}/{match_id}_phases_of_play.csv",
            }
            if set(by_path) != expected_paths:
                errors.append(f"match {match_id} file inventory is incomplete or unexpected")

        general_files: list[object] = [manifest.get("source_index")]
        general_files.extend(
            _required_list(manifest.get("repository_context_files"), "repository_context_files")
        )
        general_files.extend(
            _required_list(
                manifest.get("non_selected_repository_artifacts"),
                "non_selected_repository_artifacts",
            )
        )
        body_pose = _required_map(
            manifest.get("optional_body_pose_source"), "optional_body_pose_source"
        )
        for key in ("github_manifest", "github_readme", "github_sample"):
            if body_pose.get(key) is not None:
                general_files.append(body_pose[key])
        for raw_file in general_files:
            entry = _required_map(raw_file, "repository source file")
            path = _safe_repository_path(entry.get("repository_path"))
            sha = entry.get("git_blob_sha")
            size = entry.get("byte_size")
            if not isinstance(sha, str) or not _HEX_40.fullmatch(sha):
                errors.append(f"invalid Git blob SHA for {path}")
            if isinstance(size, bool) or not isinstance(size, int) or size < 0:
                errors.append(f"invalid byte size for {path}")
            if entry.get("identity_type") != "git_blob":
                errors.append(f"repository artifact must use Git blob identity: {path}")
            raw_sha = entry.get("raw_sha256")
            if raw_sha is not None and (
                not isinstance(raw_sha, str) or not _HEX_64.fullmatch(raw_sha)
            ):
                errors.append(f"invalid raw SHA-256 for {path}")
        hf_revision = body_pose.get("pinned_hf_revision")
        if not isinstance(hf_revision, str) or not _HEX_40.fullmatch(hf_revision):
            errors.append("pinned Body Pose revision must be a full immutable SHA")
        for raw_archive in _required_list(body_pose.get("archives"), "Body Pose archives"):
            archive = _required_map(raw_archive, "Body Pose archive")
            path = archive.get("path")
            sha = archive.get("sha256")
            size = archive.get("byte_size")
            if (
                not isinstance(path, str)
                or PurePosixPath(path).is_absolute()
                or ".." in path.split("/")
            ):
                errors.append("invalid Body Pose archive path")
            if not isinstance(sha, str) or not _HEX_64.fullmatch(sha):
                errors.append(f"invalid Body Pose archive SHA-256: {path}")
            if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
                errors.append(f"invalid Body Pose archive size: {path}")

        expected_population_hash = source_population_hash(selected)
        if manifest.get("source_population_hash") != expected_population_hash:
            errors.append("source_population_hash does not match selected source matches")
        expected_release_hash = source_release_hash(manifest)
        if manifest.get("source_release_hash") != expected_release_hash:
            errors.append("source_release_hash does not match selected files and identities")
        if (
            manifest.get("source_release_id")
            != f"skillcorner_open_data_v1:sha256:{expected_release_hash}"
        ):
            errors.append("source_release_id does not match source_release_hash")
        expected_manifest_hash = manifest_hash(manifest)
        if manifest.get("manifest_sha256") != expected_manifest_hash:
            errors.append("manifest_sha256 does not match manifest content")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))
    return tuple(sorted(set(errors)))


def parse_lfs_pointer(pointer: bytes) -> tuple[str, int]:
    match = _LFS_POINTER.fullmatch(pointer)
    if match is None:
        raise ValueError("invalid Git LFS pointer")
    return match.group(1).decode(), int(match.group(2))


def validate_lfs_pointer(
    pointer: bytes, expected: Mapping[str, object], path: str
) -> tuple[str, ...]:
    try:
        oid, size = parse_lfs_pointer(pointer)
    except ValueError as exc:
        return (f"invalid Git LFS pointer for {path}: {exc}",)
    errors: list[str] = []
    if git_blob_sha(pointer) != expected.get("git_blob_sha"):
        errors.append(f"Git LFS pointer Git blob SHA mismatch: {path}")
    if len(pointer) != expected.get("byte_size"):
        errors.append(f"Git LFS pointer byte size mismatch: {path}")
    if oid != expected.get("lfs_oid_sha256"):
        errors.append(f"Git LFS payload OID mismatch: {path}")
    if size != expected.get("lfs_payload_size"):
        errors.append(f"Git LFS payload size mismatch: {path}")
    return tuple(errors)


def validate_lfs_payload(
    payload: bytes, expected: Mapping[str, object], path: str
) -> tuple[str, ...]:
    errors: list[str] = []
    if hashlib.sha256(payload).hexdigest() != expected.get("lfs_oid_sha256"):
        errors.append(f"Git LFS payload OID mismatch: {path}")
    if len(payload) != expected.get("lfs_payload_size"):
        errors.append(f"Git LFS payload size mismatch: {path}")
    return tuple(errors)


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _match_inventory_paths(manifest: Mapping[str, object]) -> tuple[set[str], set[str]]:
    ids = [
        _match_id(value)
        for value in _required_list(
            manifest.get("selected_source_matches"), "selected_source_matches"
        )
    ]
    directories = {f"data/matches/{match_id}" for match_id in ids}
    paths = {
        _safe_repository_path(cast(dict[str, object], file)["repository_path"])
        for raw_match in _required_list(manifest.get("available_matches"), "available_matches")
        if _match_id(cast(dict[str, object], raw_match)["match_id"]) in set(ids)
        for file in _required_list(cast(dict[str, object], raw_match).get("files"), "match files")
    }
    return directories, paths


def validate_tree_inventory(
    manifest: Mapping[str, object], tree_entries: Sequence[Mapping[str, object]]
) -> tuple[str, ...]:
    directories, file_paths = _match_inventory_paths(manifest)
    expected = {"data/matches", *directories, *file_paths}
    entries: dict[str, Mapping[str, object]] = {}
    errors: list[str] = []
    for entry in tree_entries:
        path_value = entry.get("path")
        if not isinstance(path_value, str) or not (
            path_value == "data/matches" or path_value.startswith("data/matches/")
        ):
            continue
        if path_value in entries:
            errors.append(f"duplicate upstream tree path: {path_value}")
        entries[path_value] = entry
    missing = expected - set(entries)
    unexpected = set(entries) - expected
    errors.extend(f"missing upstream source path: {path}" for path in sorted(missing))
    errors.extend(f"unexpected upstream source path: {path}" for path in sorted(unexpected))
    for path in sorted(directories):
        if path in entries and entries[path].get("type") != "tree":
            errors.append(f"upstream match directory is not a tree: {path}")
    for path in sorted(file_paths):
        if path in entries and entries[path].get("type") != "blob":
            errors.append(f"upstream match file is not a blob: {path}")

    identities: dict[str, dict[str, object]] = {}
    for raw_match in _required_list(manifest.get("available_matches"), "available_matches"):
        match = _required_map(raw_match, "available match")
        for raw_file in _required_list(match.get("files"), "match files"):
            file = _required_map(raw_file, "match file")
            identities[str(file["repository_path"])] = file
    for raw_file in _required_list(
        manifest.get("repository_context_files"), "repository_context_files"
    ):
        file = _required_map(raw_file, "repository context file")
        identities[str(file["repository_path"])] = file
    source_index = _required_map(manifest.get("source_index"), "source_index")
    identities[str(source_index["repository_path"])] = source_index
    for raw_file in _required_list(
        manifest.get("non_selected_repository_artifacts"), "non_selected_repository_artifacts"
    ):
        file = _required_map(raw_file, "non-selected repository artifact")
        identities[str(file["repository_path"])] = file
    expected_aggregate_paths = {path for path in identities if path.startswith("data/aggregates/")}
    actual_aggregate_paths = {
        str(entry["path"])
        for entry in tree_entries
        if str(entry.get("path", "")).startswith("data/aggregates/") and entry.get("type") == "blob"
    }
    errors.extend(
        f"missing upstream source path: {path}"
        for path in sorted(expected_aggregate_paths - actual_aggregate_paths)
    )
    errors.extend(
        f"unexpected upstream source path: {path}"
        for path in sorted(actual_aggregate_paths - expected_aggregate_paths)
    )
    body_pose = _required_map(
        manifest.get("optional_body_pose_source"), "optional_body_pose_source"
    )
    for key in ("github_manifest", "github_readme", "github_sample"):
        file = body_pose.get(key)
        if isinstance(file, dict):
            item = cast(dict[str, object], file)
            identities[str(item["repository_path"])] = item
    for path, identity in identities.items():
        entry = entries.get(path)
        if entry is None:
            entry = next(
                (candidate for candidate in tree_entries if candidate.get("path") == path), None
            )
        if entry is None:
            errors.append(f"missing pinned upstream file: {path}")
            continue
        if entry.get("type") != "blob" or entry.get("sha") != identity.get("git_blob_sha"):
            errors.append(f"upstream Git blob identity mismatch: {path}")
        if entry.get("size") != identity.get("byte_size"):
            errors.append(f"upstream byte size mismatch: {path}")
    return tuple(sorted(set(errors)))


def master_drift_error(pinned_commit: str, observed_master: str) -> str | None:
    return revision_drift_error(pinned_commit, observed_master, "upstream master")


def revision_drift_error(expected: str, observed: str, label: str) -> str | None:
    if observed != expected:
        return f"{label} drift: pinned {expected}, current {observed}"
    return None


def _get_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "fpdbench-source-authority"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def _get_json(url: str) -> dict[str, object]:
    value = json.loads(_get_bytes(url))
    return _required_map(value, f"JSON response from {url}")


def _identity_records(manifest: Mapping[str, object]) -> dict[str, dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    for raw_match in _required_list(manifest.get("available_matches"), "available_matches"):
        for raw_file in _required_list(
            _required_map(raw_match, "available match").get("files"), "match files"
        ):
            file = _required_map(raw_file, "match file")
            records[str(file["repository_path"])] = file
    for raw_file in _required_list(
        manifest.get("repository_context_files"), "repository_context_files"
    ):
        file = _required_map(raw_file, "repository context file")
        records[str(file["repository_path"])] = file
    records[str(_required_map(manifest.get("source_index"), "source_index")["repository_path"])] = (
        _required_map(manifest.get("source_index"), "source_index")
    )
    for raw_file in _required_list(
        manifest.get("non_selected_repository_artifacts"), "non_selected_repository_artifacts"
    ):
        file = _required_map(raw_file, "non-selected repository artifact")
        records[str(file["repository_path"])] = file
    body_pose = _required_map(
        manifest.get("optional_body_pose_source"), "optional_body_pose_source"
    )
    for key in ("github_manifest", "github_readme", "github_sample"):
        file = body_pose.get(key)
        if isinstance(file, dict):
            item = cast(dict[str, object], file)
            records[str(item["repository_path"])] = item
    return records


def verify_live(manifest: Mapping[str, object]) -> dict[str, object]:
    """Compare the immutable authority with official live GitHub/Hugging Face metadata."""
    upstream = _required_map(manifest.get("upstream"), "upstream")
    repository = str(upstream["repository"])
    pinned = str(upstream["pinned_commit"])
    base = f"https://api.github.com/repos/{repository}"
    repo_info = _get_json(base)
    branch = str(upstream["default_branch"])
    branch_info = _get_json(f"{base}/branches/{branch}")
    head_value = cast(dict[str, object], branch_info.get("commit", {})).get("sha")
    if not isinstance(head_value, str):
        raise ValueError("GitHub branch response has no commit SHA")
    commit_info = _get_json(f"{base}/commits/{pinned}")
    if commit_info.get("sha") != pinned:
        raise ValueError("pinned SkillCorner commit does not exist")
    tree_sha_value = cast(dict[str, object], commit_info.get("commit", {})).get("tree")
    if not isinstance(tree_sha_value, dict):
        raise ValueError("pinned SkillCorner commit response has no tree SHA")
    tree_sha = cast(dict[str, object], tree_sha_value)
    if not isinstance(tree_sha.get("sha"), str):
        raise ValueError("pinned SkillCorner commit response has no tree SHA")
    if tree_sha.get("sha") != upstream.get("commit_tree_sha"):
        raise ValueError("pinned SkillCorner commit tree SHA differs from the authority")
    tree_info = _get_json(f"{base}/git/trees/{tree_sha['sha']}?recursive=1")
    entries = cast(
        list[dict[str, object]], _required_list(tree_info.get("tree"), "GitHub recursive tree")
    )
    errors = list(validate_tree_inventory(manifest, entries))
    if repo_info.get("full_name") != repository:
        errors.append("GitHub returned a different repository identity")
    if repo_info.get("default_branch") != branch:
        errors.append("upstream default branch changed")
    license_value = repo_info.get("license")
    license_info = cast(dict[str, object], license_value) if isinstance(license_value, dict) else {}
    license_spdx = license_info.get("spdx_id")
    if license_spdx != upstream.get("repository_license_spdx"):
        errors.append("upstream repository license metadata changed")
    if tree_info.get("truncated") is not False:
        errors.append("upstream recursive Git tree was truncated")
    if len(entries) != upstream.get("recursive_tree_entry_count"):
        errors.append("pinned recursive Git tree entry count differs from the authority")
    drift = master_drift_error(pinned, head_value)
    if drift is not None:
        errors.append(drift)

    index = _required_map(manifest.get("source_index"), "source_index")
    raw_base = f"https://raw.githubusercontent.com/{repository}/{pinned}/"
    raw_targets = [(index, "index")]
    raw_targets.extend(
        (file, "match")
        for file in _identity_records(manifest).values()
        if str(file.get("repository_path", "")).endswith("_match.json")
    )
    raw_targets.extend(
        (file, "pointer")
        for file in _identity_records(manifest).values()
        if str(file.get("repository_path", "")).endswith("_tracking_extrapolated.jsonl")
    )

    def check_raw(target: tuple[dict[str, object], str]) -> list[str]:
        file, kind = target
        path = str(file["repository_path"])
        try:
            data = _get_bytes(raw_base + path)
            failures: list[str] = []
            if len(data) != file.get("byte_size") and kind != "pointer":
                failures.append(f"pinned raw byte size mismatch: {path}")
            expected_sha = file.get("raw_sha256")
            if expected_sha is not None and hashlib.sha256(data).hexdigest() != expected_sha:
                failures.append(f"pinned raw SHA-256 mismatch: {path}")
            if kind == "pointer":
                failures.extend(validate_lfs_pointer(data, file, path))
            if kind == "match":
                parsed = json.loads(data)
                record = _required_map(parsed, "match metadata")
                match_id = int(PurePosixPath(path).parts[2])
                match = next(
                    item
                    for item in _required_list(
                        manifest.get("available_matches"), "available_matches"
                    )
                    if _match_id(_required_map(item, "available match")["match_id"]) == match_id
                )
                expected = _required_map(match, "match metadata")
                if record.get("id") != match_id:
                    failures.append(f"match metadata ID mismatch: {path}")
                if record.get("date_time") != expected.get("date"):
                    failures.append(f"match metadata date mismatch: {path}")
                home = _required_map(record.get("home_team"), "match home team")
                away = _required_map(record.get("away_team"), "match away team")
                if home.get("id") != expected.get("home_team_id"):
                    failures.append(f"match metadata home team mismatch: {path}")
                if away.get("id") != expected.get("away_team_id"):
                    failures.append(f"match metadata away team mismatch: {path}")
                edition = _required_map(
                    record.get("competition_edition"), "match competition edition"
                )
                if edition.get("id") != expected.get("competition_edition_id"):
                    failures.append(f"match metadata competition edition mismatch: {path}")
            return failures
        except (OSError, ValueError, TypeError, json.JSONDecodeError, urllib.error.URLError) as exc:
            return [f"cannot verify pinned upstream file {path}: {exc}"]

    with ThreadPoolExecutor(max_workers=8) as pool:
        for failures in pool.map(check_raw, raw_targets):
            errors.extend(failures)

    body_pose = _required_map(
        manifest.get("optional_body_pose_source"), "optional_body_pose_source"
    )
    hf_dataset = str(body_pose["hf_dataset"])
    hf_revision = str(body_pose["pinned_hf_revision"])
    hf_base = f"https://huggingface.co/api/datasets/{hf_dataset}"
    current_hf = _get_json(hf_base)
    pinned_hf = _get_json(f"{hf_base}/revision/{hf_revision}")
    if pinned_hf.get("sha") != hf_revision:
        errors.append("pinned Body Pose Hugging Face revision does not exist")
    if current_hf.get("gated") is not False or pinned_hf.get("gated") is not False:
        errors.append("Body Pose source is gated")
    observed_hf = current_hf.get("sha")
    if isinstance(observed_hf, str):
        hf_drift = revision_drift_error(hf_revision, observed_hf, "Body Pose main")
        if hf_drift is not None:
            errors.append(hf_drift)
    else:
        errors.append("Body Pose API returned no current main revision")
    pinned_files = {
        str(cast(dict[str, object], item).get("rfilename"))
        for item in _required_list(pinned_hf.get("siblings"), "pinned Hugging Face files")
    }
    expected_hf_files = {
        str(item["path"]) for item in cast(list[dict[str, object]], body_pose["archives"])
    }
    if not expected_hf_files <= pinned_files:
        errors.append("pinned Body Pose revision is missing an official archive")
    return {
        "status": "passed" if not errors else "failed",
        "repository": repository,
        "default_branch": branch,
        "pinned_commit": pinned,
        "current_default_branch_head": head_value,
        "recursive_tree_entries": len(entries),
        "recursive_tree_truncated": tree_info.get("truncated"),
        "body_pose_pinned_revision": hf_revision,
        "body_pose_current_main_head": current_hf.get("sha"),
        "errors": sorted(set(errors)),
    }


def verify_local_checkout(manifest: Mapping[str, object], root: Path) -> tuple[str, ...]:
    """Check an external SkillCorner checkout/cache without copying its bytes into FPD."""
    errors: list[str] = []
    index = _required_map(manifest.get("source_index"), "source_index")
    index_path = root / str(index["repository_path"])
    try:
        data = index_path.read_bytes()
        if git_blob_sha(data) != index.get("git_blob_sha"):
            errors.append("local matches.json Git blob identity mismatch")
        if hashlib.sha256(data).hexdigest() != index.get("raw_sha256"):
            errors.append("local matches.json SHA-256 mismatch")
        rows = json.loads(data)
        if not isinstance(rows, list):
            errors.append("local matches.json is not an array")
        else:
            row_ids = [
                _match_id(_required_map(row, "match index row").get("id"))
                for row in cast(list[object], rows)
            ]
            if len(row_ids) != len(set(row_ids)):
                errors.append("duplicate match ID in local matches.json")
            selected = {
                _match_id(value)
                for value in _required_list(
                    manifest.get("selected_source_matches"), "selected_source_matches"
                )
            }
            if set(row_ids) != selected:
                errors.append("local matches.json population differs from selected source matches")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        errors.append(f"cannot verify local matches.json: {exc}")

    directories, file_paths = _match_inventory_paths(manifest)
    match_root = root / "data/matches"
    actual_paths: set[str] = set()
    actual_dirs: set[str] = set()
    if match_root.exists():
        actual_paths = {
            path.relative_to(root).as_posix() for path in match_root.rglob("*") if path.is_file()
        }
        actual_dirs = {
            path.relative_to(root).as_posix() for path in match_root.rglob("*") if path.is_dir()
        }
    expected_dirs = directories
    errors.extend(
        f"missing local match directory: {path}" for path in sorted(expected_dirs - actual_dirs)
    )
    errors.extend(
        f"unexpected local match directory: {path}" for path in sorted(actual_dirs - expected_dirs)
    )
    errors.extend(
        f"missing local source file: {path}" for path in sorted(file_paths - actual_paths)
    )
    errors.extend(
        f"unexpected local source file: {path}" for path in sorted(actual_paths - file_paths)
    )

    for path in sorted(file_paths & actual_paths):
        entry = next(
            cast(dict[str, object], file)
            for raw_match in cast(list[object], manifest["available_matches"])
            for file in cast(list[object], cast(dict[str, object], raw_match)["files"])
            if cast(dict[str, object], file)["repository_path"] == path
        )
        try:
            data = (root / path).read_bytes()
            if path.endswith("_tracking_extrapolated.jsonl"):
                if data.startswith(b"version https://git-lfs.github.com/spec/v1"):
                    errors.extend(validate_lfs_pointer(data, entry, path))
                else:
                    errors.extend(validate_lfs_payload(data, entry, path))
            else:
                if git_blob_sha(data) != entry.get("git_blob_sha"):
                    errors.append(f"local Git blob SHA mismatch: {path}")
                if len(data) != entry.get("byte_size"):
                    errors.append(f"local Git blob size mismatch: {path}")
                raw_sha = entry.get("raw_sha256")
                if raw_sha is not None and hashlib.sha256(data).hexdigest() != raw_sha:
                    errors.append(f"local raw SHA-256 mismatch: {path}")
        except (OSError, ValueError) as exc:
            errors.append(f"cannot verify local source file {path}: {exc}")
    return tuple(sorted(set(errors)))


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return _required_map(value, "SkillCorner source manifest")
