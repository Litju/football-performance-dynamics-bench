from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
from res338_cache_archive import (  # noqa: E402
    assemble_chunks,
    build_chunk_index,
    build_index,
    extract,
    pack,
    pack_training_validation_caches,
    restore_chunk_descriptors,
    restore_manifests,
    split_archive,
    stage_preloaded_chunks,
    stage_training_validation_chunks,
)
from train_res338_final_fits import _FEATURE_ARRAYS, _LABEL_ARRAYS  # noqa: E402


def _cache(root: Path, role: str = "training", match_id: str = "match-1") -> Path:
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    directory = root / role / match_id
    directory.mkdir(mode=0o700, parents=True)
    arrays = {}
    for index, name in enumerate((*_FEATURE_ARRAYS, *_LABEL_ARRAYS)):
        path = directory / f"{name}.npy"
        with path.open("xb") as stream:
            np.save(stream, np.asarray([index], dtype=np.int64), allow_pickle=False)
        os.chmod(path, 0o400)
        arrays[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    payload = json.dumps(
        {
            "schema_id": "fpdbench.res338-feature-cache",
            "schema_version": "1.0.0",
            "match_id": match_id,
            "role": role,
            "arrays": arrays,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    metadata = directory / "cache.json"
    metadata.write_bytes(payload)
    os.chmod(metadata, 0o600)
    return directory


def test_cache_archive_roundtrips_and_verifies_every_member(tmp_path: Path) -> None:
    source = _cache(tmp_path / "source")
    archive_root = tmp_path / "archives"
    manifest = pack(source, archive_root, "training", "match-1")
    archive_path = archive_root / f"{manifest['archive_sha256']}.tar"
    manifest_path = archive_root / f"{manifest['archive_sha256']}.json"

    restored = extract(archive_path, manifest_path, tmp_path / "restored")
    assert restored["archive_sha256"] == manifest["archive_sha256"]
    assert len(restored["files"]) == 13
    for row in restored["files"]:
        path = tmp_path / "restored" / "training" / "match-1" / row["name"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]


def test_cache_archive_refuses_evaluation_role(tmp_path: Path) -> None:
    source = _cache(tmp_path / "source", role="training", match_id="match-1")
    with pytest.raises(ValueError, match="training and validation"):
        pack(source, tmp_path / "archives", "evaluation", "match-1")


def test_cache_archive_detects_readback_corruption(tmp_path: Path) -> None:
    source = _cache(tmp_path / "source")
    archive_root = tmp_path / "archives"
    manifest = pack(source, archive_root, "training", "match-1")
    archive_path = archive_root / f"{manifest['archive_sha256']}.tar"
    archive_path.write_bytes(archive_path.read_bytes() + b"corrupt")
    with pytest.raises(ValueError, match="content-addressed"):
        extract(
            archive_path,
            archive_root / f"{manifest['archive_sha256']}.json",
            tmp_path / "restored",
        )


def test_cache_index_binds_only_the_selected_scope(tmp_path: Path) -> None:
    source = _cache(tmp_path / "source")
    archive_root = tmp_path / "archives"
    pack(source, archive_root, "training", "match-1")
    reference_path = tmp_path / "reference.json"
    payload = json.dumps(
        {
            "roles": {"training": ["match-1"], "validation": [], "evaluation": ["eval"]},
            "preloaded_cache_identities": {"match-1": {}},
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    reference_path.write_bytes(payload)
    os.chmod(reference_path, 0o600)
    index_path, index = build_index(
        archive_root,
        reference_path,
        hashlib.sha256(payload).hexdigest(),
        "preloaded",
    )
    assert index["cache_count"] == 1
    assert index_path.exists()
    assert index["archives"][0]["role"] == "training"
    restored_manifests = restore_manifests(index_path, tmp_path / "restored-manifests")
    assert len(restored_manifests) == 1
    assert restored_manifests[0].name == f"{index['archives'][0]['archive_sha256']}.json"


def test_chunked_archive_reassembles_and_verifies(tmp_path: Path) -> None:
    source = _cache(tmp_path / "source")
    archive_root = tmp_path / "archives"
    archive = pack(source, archive_root, "training", "match-1")
    archive_path = archive_root / f"{archive['archive_sha256']}.tar"
    cache_manifest_path = archive_root / f"{archive['archive_sha256']}.json"
    chunk_root = tmp_path / "chunks"
    descriptor_path, descriptor = split_archive(
        archive_path, cache_manifest_path, chunk_root, chunk_size_bytes=1024
    )
    assert len(descriptor["chunks"]) > 1
    reference_path = tmp_path / "reference.json"
    cache = json.loads((source / "cache.json").read_text())
    reference = {
        "roles": {"training": ["match-1"], "validation": []},
        "preloaded_cache_identities": {
            "match-1": {
                **cache,
                "cache_metadata_sha256": hashlib.sha256(
                    (source / "cache.json").read_bytes()
                ).hexdigest(),
            }
        },
    }
    reference_payload = json.dumps(reference, sort_keys=True, separators=(",", ":")).encode()
    reference_path.write_bytes(reference_payload)
    os.chmod(reference_path, 0o600)
    chunk_index_path, chunk_index = build_chunk_index(
        chunk_root,
        reference_path,
        hashlib.sha256(reference_payload).hexdigest(),
        "preloaded",
    )
    assert chunk_index["archive_count"] == 1
    restored_descriptor_dir = tmp_path / "restored-descriptors"
    assert len(restore_chunk_descriptors(chunk_index_path, restored_descriptor_dir)) == 1
    result = assemble_chunks(
        restored_descriptor_dir / descriptor_path.name,
        chunk_root,
        tmp_path / "reassembled",
        tmp_path / "restored-cache",
    )
    assert result["archive_sha256"] == archive["archive_sha256"]
    staged = stage_preloaded_chunks(
        chunk_index_path,
        hashlib.sha256(chunk_index_path.read_bytes()).hexdigest(),
        reference_path,
        hashlib.sha256(reference_payload).hexdigest(),
        chunk_root,
        tmp_path / "reassembled",
        tmp_path / "restored-cache",
    )
    assert staged == {"status": "STAGED", "cache_count": 1, "role": "training"}
    with pytest.raises(ValueError, match="preloaded cache index or reference"):
        stage_preloaded_chunks(
            chunk_index_path,
            "0" * 64,
            reference_path,
            hashlib.sha256(reference_payload).hexdigest(),
            chunk_root,
            tmp_path / "reassembled",
            tmp_path / "restored-cache",
        )


def test_training_validation_cache_pack_creates_content_addressed_indexes(
    tmp_path: Path,
) -> None:
    cache_root = tmp_path / "feature-cache"
    training_matches = [f"train-{index}" for index in range(12)]
    validation_matches = [f"validation-{index}" for index in range(4)]
    for match_id in training_matches:
        _cache(cache_root, "training", match_id)
    for match_id in validation_matches:
        _cache(cache_root, "validation", match_id)
    training_cache_root = cache_root / "training"
    preloaded = {}
    for match_id in training_matches[:6]:
        cache_path = training_cache_root / match_id / "cache.json"
        preloaded[match_id] = {
            **json.loads(cache_path.read_text()),
            "cache_metadata_sha256": hashlib.sha256(cache_path.read_bytes()).hexdigest(),
        }
    reference = {
        "roles": {
            "training": training_matches,
            "validation": validation_matches,
        },
        "preloaded_cache_identities": preloaded,
    }
    reference_bytes = json.dumps(reference, sort_keys=True, separators=(",", ":")).encode()
    reference_path = tmp_path / "reference.json"
    reference_path.write_bytes(reference_bytes)
    os.chmod(reference_path, 0o600)

    result = pack_training_validation_caches(
        cache_root,
        tmp_path / "archives",
        reference_path,
        hashlib.sha256(reference_bytes).hexdigest(),
    )

    assert result["cache_archive_count"] == 16
    assert result["chunk_archive_count"] == 16
    assert result["chunk_count"] == 16
    archive_index = json.loads(Path(str(result["archive_index_path"])).read_bytes())
    chunk_index = json.loads(Path(str(result["chunk_index_path"])).read_bytes())
    assert {row["role"] for row in archive_index["archives"]} == {
        "training",
        "validation",
    }
    assert {row["role"] for row in chunk_index["archives"]} == {
        "training",
        "validation",
    }
    assert {row["match_id"] for row in chunk_index["archives"]} == set(
        training_matches + validation_matches
    )

    chunk_directory = Path(str(result["chunk_index_path"])).parent
    archive_directory = tmp_path / "restored-archives"
    restored_root = tmp_path / "restored-cache"
    for _ in range(2):
        staged = stage_training_validation_chunks(
            Path(str(result["chunk_index_path"])),
            str(result["chunk_index_sha256"]),
            reference_path,
            hashlib.sha256(reference_bytes).hexdigest(),
            chunk_directory,
            archive_directory,
            restored_root,
        )
        assert staged["cache_count"] == 16
        assert staged["recovered_partial_cache_count"] == 0

    corrupt = restored_root / "training" / training_matches[0] / "cache.json"
    corrupt.chmod(0o600)
    corrupt.write_text("corrupt")
    staged = stage_training_validation_chunks(
        Path(str(result["chunk_index_path"])),
        str(result["chunk_index_sha256"]),
        reference_path,
        hashlib.sha256(reference_bytes).hexdigest(),
        chunk_directory,
        archive_directory,
        restored_root,
    )
    assert staged["recovered_partial_cache_count"] == 1
    assert (restored_root / "training" / training_matches[0] / "cache.json").read_bytes() == (
        cache_root / "training" / training_matches[0] / "cache.json"
    ).read_bytes()
    assert len(list((restored_root.parent / "interrupted-cache-staging").iterdir())) == 1
