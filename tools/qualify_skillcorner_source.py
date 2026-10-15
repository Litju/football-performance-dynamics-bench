"""Fail-closed source qualification; receipts belong outside Git and public CI."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import platform
import stat
import subprocess
import traceback
from collections import Counter
from pathlib import Path

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    load_empirical_experiment_plan,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.prospective_protocol import (
    load_prospective_protocol,
)
from fpdbench.data_sources.skillcorner import (
    canonical_bytes,
    load_manifest,
    validate_lfs_pointer,
    validate_manifest,
    verify_local_checkout,
)
from fpdbench.data_states.skillcorner import iter_skillcorner_5hz


def _has_symlink_component(path):
    path = Path(path)
    if not path.is_absolute():
        path = Path.cwd() / path
    current = Path(path.anchor)
    for part in path.parts[1:]:
        if part in {"", "."}:
            continue
        current /= part
        if current.is_symlink():
            return True
    return False


def private_directory(path):
    if _has_symlink_component(path):
        raise ValueError("restricted directory path must not contain symlinks")
    path = path.resolve(strict=True)
    repo = Path(__file__).resolve().parents[1]
    if path == repo or repo in path.parents:
        raise ValueError("restricted storage must be outside the repository")
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("restricted directory must exist with mode 0700")
    if info.st_uid != os.getuid():
        raise ValueError("restricted directory must belong to the current user")
    for parent in path.parents:
        parent_info = parent.stat()
        if parent_info.st_mode & 0o022 and not parent_info.st_mode & stat.S_ISVTX:
            raise ValueError("restricted directory has an unsafe writable parent")
    return path


def validate_storage_boundary(source_root, destination):
    repo = Path(__file__).resolve().parents[1]
    if (
        source_root in destination.parents
        or destination in source_root.parents
        or source_root == destination
    ):
        raise ValueError("restricted source and output directories must not overlap")

    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env["LC_ALL"] = "C"
    result = subprocess.run(
        ["git", "-C", str(destination), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )
    if result.returncode == 0:
        if result.stdout.strip() == "true":
            raise ValueError("restricted storage must be outside every Git worktree")
        if result.stdout.strip() != "false":
            raise ValueError("could not verify restricted storage is outside Git worktrees")
    elif "not a git repository" not in result.stderr:
        raise ValueError("could not verify restricted storage is outside Git worktrees")

    if destination == repo or repo in destination.parents:
        raise ValueError("restricted storage must be outside the repository")


def write_private(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(canonical_bytes(value))


def verify_payload(payload, entry):
    if payload.startswith(b"version https://git-lfs.github.com/spec/v1"):
        raise ValueError("unresolved tracking LFS pointer")
    if len(payload) != entry["lfs_payload_size"]:
        raise ValueError("tracking payload size mismatch")
    if hashlib.sha256(payload).hexdigest() != entry["lfs_oid_sha256"]:
        raise ValueError("tracking payload SHA-256 mismatch")


def source_preflight(root):
    """Strengthen the pointer-or-payload check to require actual tracking bytes."""
    manifest = load_manifest()
    if validate_manifest(manifest):
        raise ValueError("invalid pinned source authority")
    revision = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != manifest["upstream"]["pinned_commit"]:
        raise ValueError("source revision mismatch")
    if verify_local_checkout(manifest, root):
        raise ValueError("source inventory or byte identity mismatch")
    receipts = []
    records = [manifest["source_index"]] + [
        entry for match in manifest["available_matches"] for entry in match["files"]
    ]
    for entry in records:
        path = root / entry["repository_path"]
        if path.is_symlink() or root.resolve() not in path.resolve().parents:
            raise ValueError("source file escapes restricted checkout")
        payload = path.read_bytes()
        if entry.get("identity_type") == "git_lfs_pointer":
            verify_payload(payload, entry)
            pointer = subprocess.check_output(
                ["git", "-C", str(root), "show", f"{revision}:{entry['repository_path']}"]
            )
            if validate_lfs_pointer(pointer, entry, entry["repository_path"]):
                raise ValueError("pinned LFS tracking object mismatch")
        receipt = {
            "path": entry["repository_path"],
            "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
        }
        if entry.get("identity_type") == "git_lfs_pointer":
            receipt["pointer_sha256"] = hashlib.sha256(pointer).hexdigest()
            receipt["pointer_git_blob_sha"] = entry["git_blob_sha"]
        receipts.append(receipt)
    return receipts


def read_frames(path):
    with path.open() as stream:
        for line in stream:
            yield json.loads(line)


def raw_schema_scan(frames):
    """Independent raw-byte pass: no canonicalizer, producer, or eligibility output."""
    counts = Counter()
    violations = []
    previous = -1
    for row_number, frame in enumerate(frames, start=1):
        counts["source_rows"] += 1
        number = frame["frame"]
        if isinstance(number, bool) or not isinstance(number, int) or number <= previous:
            raise ValueError("source frame order or type invalid")
        previous = number
        if number % 2:
            continue
        counts["even_source_rows"] += 1
        ball = frame["ball_data"]
        if ball is not None and not isinstance(ball.get("is_detected"), bool):
            counts["ball_detection_not_boolean"] += 1
            violations.append(
                {
                    "row_number": row_number,
                    "source_frame": number,
                    "field": "ball_data.is_detected",
                    "value_type": type(ball.get("is_detected")).__name__,
                    "coordinate_pair_missing": ball.get("x") is None or ball.get("y") is None,
                }
            )
        for player in frame["player_data"]:
            if not isinstance(player.get("is_detected"), bool):
                counts["player_detection_not_boolean"] += 1
                violations.append(
                    {
                        "row_number": row_number,
                        "source_frame": number,
                        "field": "player_data.is_detected",
                        "value_type": type(player.get("is_detected")).__name__,
                    }
                )
    # This is NOT a qualified candidate count: canonicalization may reject these rows.
    counts["retained_row_support_count_upper_bound"] = max(0, counts["even_source_rows"] - 40)
    return dict(counts), violations


def qualify(root, destination):
    inputs = source_preflight(root)
    source = load_manifest()
    protocol = load_prospective_protocol()
    plan = load_empirical_experiment_plan()
    results = []
    for match_id in source["selected_source_matches"]:
        directory = root / "data/matches" / str(match_id)
        tracking = directory / f"{match_id}_tracking_extrapolated.jsonl"
        counts, violations = raw_schema_scan(read_frames(tracking))
        canonical_count = 0
        error = None
        try:
            metadata = json.loads((directory / f"{match_id}_match.json").read_bytes())
            for _ in iter_skillcorner_5hz(
                read_frames(tracking), metadata, source_release_id=source["source_release_id"]
            ):
                canonical_count += 1
        except (ValueError, TypeError, KeyError) as exc:
            error = str(exc)
        result = {
            "match_id": match_id,
            "raw_scan_counts": counts,
            "raw_schema_violations": violations,
            "canonical_rows_before_failure": canonical_count,
            "canonicalization_error": error,
        }
        write_private(destination / f"source-match-{len(results) + 1:02}.json", result)
        results.append(result)
    if source_preflight(root) != inputs:
        raise ValueError("source changed during qualification")
    failed = any(r["canonicalization_error"] or r["raw_schema_violations"] for r in results)
    receipt = {
        "schema_id": "fpdbench.skillcorner-source-qualification",
        "schema_version": "1.0.0",
        "status": "FAIL" if failed else "PASS",
        "stage": "source_preflight_only",
        "source_inputs": inputs,
        "source_revision": source["upstream"]["pinned_commit"],
        "authorities": protocol["scientific_state"]["authorities"],
        "protocol_sha256": protocol["protocol_sha256"],
        "plan_sha256": plan["plan_sha256"],
        "verifier_id": "qualify_skillcorner_source.raw_schema_scan/v1",
        "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "canonicalizer_sha256": hashlib.sha256(
            Path(inspect.getfile(iter_skillcorner_5hz)).read_bytes()
        ).hexdigest(),
        "implementation_git_revision": subprocess.check_output(
            ["git", "-C", str(Path(__file__).resolve().parents[1]), "rev-parse", "HEAD"],
            text=True,
        ).strip(),
        "runtime_python": platform.python_version(),
        "match_receipt_sha256": [hashlib.sha256(canonical_bytes(r)).hexdigest() for r in results],
        "match_count": len(results),
        "failed_match_count": sum(r["canonicalization_error"] is not None for r in results),
        "candidate_window_count": None,
        "eligible_window_count": None,
        "population_manifest_sha256": None,
        "limitation": "Source preflight only; no eligibility replay or population authority sealed",
    }
    receipt["receipt_sha256"] = hashlib.sha256(canonical_bytes(receipt)).hexdigest()
    write_private(destination / "source-qualification.json", receipt)
    return not failed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--restricted-output", required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        destination = private_directory(args.restricted_output)
        root = private_directory(args.source_root)
        validate_storage_boundary(root, destination)
        if any(destination.iterdir()):
            raise ValueError("use an empty receipt directory to preserve previous receipts")
    except (ValueError, OSError):
        raise SystemExit("FAIL: restricted storage requirements not met") from None
    try:
        passed = qualify(root, destination)
    except Exception:
        try:
            write_private(
                destination / "failure.json",
                {
                    "status": "FAIL",
                    "stage": "source_preflight",
                    "diagnostic": traceback.format_exc(),
                },
            )
        except Exception:
            raise SystemExit("FAIL: source preflight; restricted diagnostics unavailable") from None
        raise SystemExit("FAIL: source preflight; diagnostics remain restricted") from None
    if not passed:
        raise SystemExit(
            "FAIL: frozen measurement contract rejects source; receipts remain restricted"
        )
    print("PASS: source preflight only; population remains unqualified")


if __name__ == "__main__":
    main()
