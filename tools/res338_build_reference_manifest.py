"""Build a private 16-match identity projection without evaluation records."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import cast

import train_res338_final_fits as trainer

from fpdbench.data_sources import protected_skillcorner as source


def _read_json(root: Path, name: str, digest: str) -> object:
    return json.loads(
        trainer.read_private_file(root / name, digest),
        object_pairs_hook=trainer._unique_json_object,
    )


def build(
    research_root: Path, source_root: Path, cache_root: Path | None = None
) -> dict[str, object]:
    manifest = trainer._read_pinned_manifest(research_root)
    plan, protocol, roles = trainer._frozen_split_and_authorities()
    selected_roles = {role: list(roles[role]) for role in ("training", "validation")}
    source_authority = source._authority()
    selected = {mid for values in selected_roles.values() for mid in values}
    source_match_order = [
        str(mid) for mid in source_authority["selected_source_matches"] if str(mid) in selected
    ]
    if len(selected) != 16 or set(source_match_order) != selected:
        raise ValueError(
            "the frozen training/validation projection must contain exactly 16 matches"
        )

    source_inventory = cast(
        list[dict[str, object]],
        _read_json(
            research_root, "source-inventory.json", str(manifest["source_inventory_sha256"])
        ),
    )
    independent = cast(
        dict[str, object],
        _read_json(
            research_root,
            "independent-source.json",
            str(manifest["independent_source_sha256"]),
        ),
    )
    source_files = [
        item
        for item in source_inventory
        if any(str(item["path"]).startswith(f"data/matches/{mid}/") for mid in selected)
    ]
    independent_files = [
        item
        for item in cast(list[dict[str, object]], independent["source_files"])
        if any(str(item["path"]).startswith(f"data/matches/{mid}/") for mid in selected)
    ]
    normalization = [
        item
        for item in cast(list[dict[str, object]], independent["normalization_receipts"])
        if str(item["match_id"]) in selected
    ]
    authority_records = [
        record
        for record in source._records(source_authority)
        if any(
            str(record["repository_path"]).startswith(f"data/matches/{mid}/") for mid in selected
        )
    ]
    if len(source_files) != 64 or len(independent_files) != 64 or len(authority_records) != 64:
        raise ValueError("expected exactly four pinned source files for each of 16 matches")

    source_by_path = {str(item["repository_path"]): item for item in authority_records}
    if set(source_by_path) != {str(item["path"]) for item in source_files}:
        raise ValueError("source inventory paths differ from the pinned SkillCorner authority")
    source_manifest = [
        {
            key: record[key]
            for key in (
                "repository_path",
                "pinned_source_url",
                "identity_type",
                "byte_size",
                "git_blob_sha",
                "raw_sha256",
                "lfs_oid_sha256",
                "lfs_payload_size",
            )
            if key in record
        }
        for record in authority_records
    ]

    # Verify only the 16 permitted source files; evaluation-role source files are not opened.
    with source.private_directory(source_root) as root_fd:
        for row in source_files:
            relative = str(row["path"])
            authority_row = source_by_path[relative]
            size = int(row["bytes"])
            digest = hashlib.sha256()
            blob = hashlib.sha1(b"blob " + str(size).encode() + b"\0")
            with source._open_file(root_fd, relative) as stream:
                before = os.fstat(stream.fileno())
                if (
                    before.st_size != size
                    or int(authority_row.get("lfs_payload_size", size)) != size
                ):
                    raise ValueError("local source size differs from its pinned identity")
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
                    blob.update(block)
                after = os.fstat(stream.fileno())
                if source._file_identity(before) != source._file_identity(after):
                    raise ValueError("source changed while verifying its identity")
            actual_sha = digest.hexdigest()
            if actual_sha != row["sha256"]:
                raise ValueError("local source differs from the reconciled source inventory")
            if "lfs_oid_sha256" in authority_row:
                if actual_sha != authority_row["lfs_oid_sha256"]:
                    raise ValueError("tracking source differs from its pinned LFS SHA-256")
            elif blob.hexdigest() != authority_row["git_blob_sha"]:
                raise ValueError("Git blob identity differs from the pinned SkillCorner source")

    per_match = cast(dict[str, dict[str, object]], manifest["per_match"])
    artifacts = cast(dict[str, dict[str, object]], manifest["artifacts"])
    projected_per_match = {mid: per_match[mid] for mid in sorted(selected)}
    projected_artifacts = {mid: artifacts[mid] for mid in sorted(selected)}
    if set(projected_per_match) != selected or set(projected_artifacts) != selected:
        raise ValueError("research admission is missing a training or validation match")
    theoretical = sum(
        int(cast(dict[str, object], projected_per_match[mid]["counts"])["theoretical"])
        for mid in selected
    )
    scoreable_scenes = sum(
        int(cast(dict[str, object], projected_per_match[mid]["counts"])["home_scenes"])
        + int(cast(dict[str, object], projected_per_match[mid]["counts"])["away_scenes"])
        for mid in selected
    )
    preloaded_caches: dict[str, dict[str, object]] = {}
    if cache_root is not None:
        training_ids = set(selected_roles["training"])
        source_sha = {str(item["path"]): str(item["sha256"]) for item in source_files}
        for match_id in sorted(training_ids):
            cache_dir = cache_root / "training" / match_id
            cache_path = cache_dir / "cache.json"
            if not cache_path.is_file():
                continue
            cache = cast(
                dict[str, object],
                json.loads(cache_path.read_bytes(), object_pairs_hook=trainer._unique_json_object),
            )
            arrays = cast(dict[str, str], cache["arrays"])
            expected_arrays = {
                f"{name}.npy" for name in (*trainer._FEATURE_ARRAYS, *trainer._LABEL_ARRAYS)
            }
            if (
                cache.get("match_id") != match_id
                or cache.get("role") != "training"
                or cache.get("population_stream_sha256")
                != projected_artifacts[match_id]["producer_sha256"]
                or set(arrays) != expected_arrays
                or cache.get("tracking_sha256")
                != source_sha[f"data/matches/{match_id}/{match_id}_tracking_extrapolated.jsonl"]
            ):
                raise ValueError(
                    "completed local cache does not bind to the frozen source projection"
                )
            for filename, digest in arrays.items():
                if trainer._sha256_file(cache_dir / filename) != digest:
                    raise ValueError("completed local feature cache array hash differs")
            preloaded_caches[match_id] = {
                **cache,
                "cache_metadata_sha256": hashlib.sha256(cache_path.read_bytes()).hexdigest(),
            }
    return {
        "schema_id": "fpdbench.res338.training-validation-reference",
        "schema_version": "1.0.0",
        "parent_research_manifest_sha256": trainer.RESEARCH_MANIFEST_SHA256,
        "parent_source_inventory_sha256": manifest["source_inventory_sha256"],
        "parent_independent_source_sha256": manifest["independent_source_sha256"],
        "source_release_hash": manifest["source_release_hash"],
        "source_population_hash": manifest["source_population_hash"],
        "source_commit": source_authority["upstream"]["pinned_commit"],
        "plan_sha256": plan["plan_sha256"],
        "protocol_sha256": protocol["protocol_sha256"],
        "roles": selected_roles,
        "source_match_order": source_match_order,
        "source_manifest": source_manifest,
        "per_match": projected_per_match,
        "artifacts": projected_artifacts,
        "preloaded_cache_identities": preloaded_caches,
        "source_files": source_files,
        "independent_source": {
            "source_files": independent_files,
            "normalization_receipts": normalization,
        },
        "resource_census": {
            "total": {
                "C": {
                    "theoretical": theoretical,
                    "scoreable_scenes": scoreable_scenes,
                }
            }
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("research_root", type=Path)
    parser.add_argument("source_root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=Path("/srv/fpdbench-private/evidence/res338-final-fits-v1/feature-cache"),
    )
    args = parser.parse_args()
    os.umask(0o077)
    payload = trainer._canonical(build(args.research_root, args.source_root, args.cache_root))
    trainer._atomic_write(args.output, payload)
    digest = hashlib.sha256(payload).hexdigest()
    trainer._atomic_write(
        args.output.with_suffix(args.output.suffix + ".sha256"), f"{digest}\n".encode()
    )
    print(json.dumps({"sha256": digest, "bytes": len(payload)}))


if __name__ == "__main__":
    main()
