"""Pack and verify one private research match cache without exposing row data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tarfile
from pathlib import Path, PurePosixPath
from typing import cast

import train_res338_final_fits as trainer

SCHEMA = "fpdbench.res338.content-addressed-cache-archive"
ARRAYS = set((*trainer._FEATURE_ARRAYS, *trainer._LABEL_ARRAYS))
SHA256 = re.compile(r"[0-9a-f]{64}")
DEFAULT_CHUNK_BYTES = 64 * 1024**2


def _safe_member(name: str) -> tuple[str, str]:
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("archive contains an unsafe path")
    if len(path.parts) != 3 or path.parts[0] not in {"training", "validation"}:
        raise ValueError("archive path must be role/match/file")
    if path.parts[2] != "cache.json" and path.parts[2] not in {f"{name}.npy" for name in ARRAYS}:
        raise ValueError("archive contains an unexpected cache file")
    return path.parts[0], path.parts[1]


def _hash(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError("cache files must be exclusive regular files")
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
        after = os.fstat(stream.fileno())
        if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ValueError("cache file changed while hashing")
    return digest.hexdigest(), before.st_size


def pack(
    cache_directory: Path, output_directory: Path, role: str, match_id: str
) -> dict[str, object]:
    if role not in {"training", "validation"}:
        raise ValueError("only training and validation caches may be archived")
    with trainer.source.private_directory(cache_directory.parent.parent):
        pass
    if cache_directory.name != match_id or cache_directory.parent.name != role:
        raise ValueError("cache directory does not match its role and match identity")
    cache_path = cache_directory / "cache.json"
    cache_sha, _ = _hash(cache_path)
    cache = trainer._read_private_json(cache_path)
    arrays = cast(dict[str, str], cache.get("arrays", {}))
    expected_names = {f"{name}.npy" for name in ARRAYS}
    if (
        cache.get("role") != role
        or cache.get("match_id") != match_id
        or set(arrays) != expected_names
    ):
        raise ValueError("cache identity does not match its directory")
    files = [{"name": "cache.json", "sha256": cache_sha, "size_bytes": cache_path.stat().st_size}]
    for name in sorted(expected_names):
        path = cache_directory / name
        digest, size = _hash(path)
        if digest != arrays[name]:
            raise ValueError("cache array differs from cache.json")
        files.append({"name": name, "sha256": digest, "size_bytes": size})

    output_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    archive_tmp = output_directory / f".{role}-{match_id}.{os.getpid()}.partial"
    fd = os.open(archive_tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as raw:
        with tarfile.open(fileobj=raw, mode="w") as archive:
            for entry in files:
                path = cache_directory / str(entry["name"])
                info = archive.gettarinfo(str(path), arcname=f"{role}/{match_id}/{path.name}")
                info.mtime = 0
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                with path.open("rb") as stream:
                    archive.addfile(info, stream)
        raw.flush()
        os.fsync(raw.fileno())
    archive_sha, archive_size = _hash(archive_tmp)
    archive_path = output_directory / f"{archive_sha}.tar"
    if archive_path.exists():
        if _hash(archive_path) != (archive_sha, archive_size):
            raise ValueError("content-addressed archive path contains different bytes")
        archive_tmp.unlink()
    else:
        os.replace(archive_tmp, archive_path)
    trainer._fsync_directory(output_directory)
    manifest = {
        "schema_id": SCHEMA,
        "schema_version": "1.0.0",
        "role": role,
        "match_id": match_id,
        "cache_metadata_sha256": cache_sha,
        "archive_sha256": archive_sha,
        "archive_size_bytes": archive_size,
        "files": files,
    }
    trainer._atomic_json(output_directory / f"{archive_sha}.json", manifest)
    return manifest


def extract(archive_path: Path, manifest_path: Path, cache_root: Path) -> dict[str, object]:
    manifest = trainer._read_private_json(manifest_path)
    archive_sha, archive_size = _hash(archive_path)
    if (
        manifest.get("schema_id") != SCHEMA
        or manifest.get("schema_version") != "1.0.0"
        or manifest.get("archive_sha256") != archive_sha
        or manifest.get("archive_size_bytes") != archive_size
    ):
        raise ValueError("cache archive does not match its content-addressed manifest")
    role, match_id = str(manifest["role"]), str(manifest["match_id"])
    if role not in {"training", "validation"}:
        raise ValueError("evaluation cache archives are forbidden")
    expected_files = cast(list[dict[str, object]], manifest["files"])
    expected = {f"{role}/{match_id}/{row['name']}": row for row in expected_files}
    if len(expected) != len(expected_files) or {str(row["name"]) for row in expected_files} != {
        "cache.json",
        *(f"{name}.npy" for name in ARRAYS),
    }:
        raise ValueError("cache archive manifest has duplicate or missing files")
    target = cache_root / role / match_id
    if target.exists():
        raise FileExistsError("cache extraction target already exists")
    cache_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    cache_root.chmod(0o700)
    with trainer.source.private_directory(cache_root):
        pass
    role_root = cache_root / role
    role_root.mkdir(mode=0o700, exist_ok=True)
    target.mkdir(mode=0o700)
    seen: set[str] = set()
    try:
        with tarfile.open(archive_path, mode="r:") as archive:
            for member in archive:
                member_role, member_match = _safe_member(member.name)
                if member_role != role or member_match != match_id or member.name not in expected:
                    raise ValueError("cache archive contains an out-of-scope member")
                if not member.isfile() or member.issym() or member.islnk() or member.name in seen:
                    raise ValueError("cache archive contains a nonregular or duplicate member")
                seen.add(member.name)
                row = expected[member.name]
                if member.size != int(row["size_bytes"]):
                    raise ValueError("cache archive member size differs from its manifest")
                output = target / str(row["name"])
                source_stream = archive.extractfile(member)
                if source_stream is None:
                    raise ValueError("cache archive member is unreadable")
                fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                digest = hashlib.sha256()
                count = 0
                with os.fdopen(fd, "wb") as destination, source_stream:
                    while block := source_stream.read(1024 * 1024):
                        count += len(block)
                        digest.update(block)
                        destination.write(block)
                    destination.flush()
                    os.fsync(destination.fileno())
                if count != member.size or digest.hexdigest() != row["sha256"]:
                    raise ValueError("cache archive member SHA-256 differs")
        if seen != set(expected):
            raise ValueError("cache archive is missing required files")
        cache = trainer._read_private_json(target / "cache.json")
        if (
            hashlib.sha256((target / "cache.json").read_bytes()).hexdigest()
            != manifest["cache_metadata_sha256"]
            or cache.get("match_id") != match_id
            or cache.get("role") != role
        ):
            raise ValueError("extracted cache metadata differs from its archive manifest")
        extracted_arrays = {
            str(row["name"]): str(row["sha256"])
            for row in expected_files
            if str(row["name"]).endswith(".npy")
        }
        if cache.get("arrays") != extracted_arrays:
            raise ValueError("cache.json array identities differ from the archive manifest")
        trainer._fsync_directory(target)
        trainer._fsync_directory(role_root)
        return manifest
    except Exception:
        for path in target.iterdir():
            if path.is_file() and not path.is_symlink():
                path.unlink()
        target.rmdir()
        trainer._fsync_directory(role_root)
        raise


def build_index(
    archive_directory: Path,
    reference_path: Path,
    reference_sha256: str,
    scope: str,
) -> tuple[Path, dict[str, object]]:
    reference_bytes = reference_path.read_bytes()
    if hashlib.sha256(reference_bytes).hexdigest() != reference_sha256:
        raise ValueError("cache archive index reference SHA-256 differs")
    reference = cast(
        dict[str, object],
        json.loads(reference_bytes, object_pairs_hook=trainer._unique_json_object),
    )
    roles = cast(dict[str, list[str]], reference["roles"])
    selected = set(roles["training"]) | set(roles["validation"])
    preloaded = set(cast(dict[str, object], reference["preloaded_cache_identities"]))
    if scope not in {"preloaded", "all"}:
        raise ValueError("cache archive index scope must be preloaded or all")
    expected_matches = preloaded if scope == "preloaded" else selected
    entries = []
    for manifest_path in sorted(archive_directory.glob("*.json")):
        if manifest_path.name == "archive-index.json" or not SHA256.fullmatch(manifest_path.stem):
            continue
        manifest = trainer._read_private_json(manifest_path)
        archive_path = archive_directory / f"{manifest_path.stem}.tar"
        archive_sha, archive_size = _hash(archive_path)
        role, match_id = str(manifest["role"]), str(manifest["match_id"])
        if (
            manifest.get("schema_id") != SCHEMA
            or manifest.get("archive_sha256") != manifest_path.stem
            or archive_sha != manifest_path.stem
            or archive_size != manifest.get("archive_size_bytes")
            or role not in {"training", "validation"}
            or match_id not in expected_matches
            or (role == "training" and match_id not in roles["training"])
            or (role == "validation" and match_id not in roles["validation"])
        ):
            raise ValueError(
                "cache archive does not match the projected role and content identities"
            )
        entries.append(
            {
                "role": role,
                "match_id": match_id,
                "archive_sha256": archive_sha,
                "archive_size_bytes": archive_size,
                "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                "manifest": manifest,
            }
        )
    if {str(item["match_id"]) for item in entries} != expected_matches:
        raise ValueError("cache archive index is missing or adding out-of-scope matches")
    index = {
        "schema_id": "fpdbench.res338.cache-archive-index",
        "schema_version": "1.0.0",
        "scope": scope,
        "parent_reference_sha256": reference_sha256,
        "cache_count": len(entries),
        "archives": entries,
    }
    payload = trainer._canonical(index)
    index_sha = hashlib.sha256(payload).hexdigest()
    output_path = archive_directory / f"cache-archive-index-{index_sha}.json"
    if not output_path.exists():
        trainer._atomic_write(output_path, payload)
    elif hashlib.sha256(output_path.read_bytes()).hexdigest() != index_sha:
        raise ValueError("content-addressed cache index path contains different bytes")
    return output_path, index


def restore_manifests(index_path: Path, output_directory: Path) -> list[Path]:
    index_bytes = index_path.read_bytes()
    index_sha = hashlib.sha256(index_bytes).hexdigest()
    if index_path.stem != f"cache-archive-index-{index_sha}":
        raise ValueError("cache archive index filename differs from its content SHA-256")
    index = cast(
        dict[str, object], json.loads(index_bytes, object_pairs_hook=trainer._unique_json_object)
    )
    if index.get("schema_id") != "fpdbench.res338.cache-archive-index":
        raise ValueError("unknown cache archive index schema")
    output_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    output_directory.chmod(0o700)
    restored = []
    for entry in cast(list[dict[str, object]], index["archives"]):
        archive_sha = str(entry["archive_sha256"])
        manifest = cast(dict[str, object], entry["manifest"])
        payload = trainer._canonical(manifest)
        if (
            hashlib.sha256(payload).hexdigest() != entry["manifest_sha256"]
            or manifest.get("archive_sha256") != archive_sha
            or manifest.get("role") not in {"training", "validation"}
        ):
            raise ValueError("embedded cache archive manifest differs from its frozen index")
        path = output_directory / f"{archive_sha}.json"
        if path.exists():
            if path.read_bytes() != payload:
                raise ValueError("restored archive manifest conflicts with existing content")
        else:
            trainer._atomic_write(path, payload)
        restored.append(path)
    return restored


def split_archive(
    archive_path: Path,
    manifest_path: Path,
    chunk_directory: Path,
    chunk_size_bytes: int = DEFAULT_CHUNK_BYTES,
) -> tuple[Path, dict[str, object]]:
    if chunk_size_bytes <= 0 or chunk_size_bytes > 64 * 1024**2:
        raise ValueError("Drive upload chunks must be between one byte and 64 MiB")
    manifest = trainer._read_private_json(manifest_path)
    archive_sha, archive_size = _hash(archive_path)
    if (
        manifest.get("archive_sha256") != archive_sha
        or manifest.get("archive_size_bytes") != archive_size
    ):
        raise ValueError("cache archive differs from its match manifest")
    chunk_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    chunk_directory.chmod(0o700)
    chunks = []
    with archive_path.open("rb") as source_stream:
        ordinal = 0
        while payload := source_stream.read(chunk_size_bytes):
            digest = hashlib.sha256(payload).hexdigest()
            chunk_path = chunk_directory / f"{digest}.chunk"
            if chunk_path.exists():
                if _hash(chunk_path) != (digest, len(payload)):
                    raise ValueError("content-addressed upload chunk contains different bytes")
            else:
                temporary = chunk_path.with_name(f".{chunk_path.name}.{os.getpid()}.tmp")
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, chunk_path)
                trainer._fsync_directory(chunk_directory)
            chunks.append(
                {
                    "ordinal": ordinal,
                    "sha256": digest,
                    "size_bytes": len(payload),
                    "file_name": chunk_path.name,
                }
            )
            ordinal += 1
    descriptor: dict[str, object] = {
        "schema_id": "fpdbench.res338.cache-archive-chunks",
        "schema_version": "1.0.0",
        "role": manifest["role"],
        "match_id": manifest["match_id"],
        "archive_sha256": archive_sha,
        "archive_size_bytes": archive_size,
        "chunk_size_bytes": chunk_size_bytes,
        "cache_manifest_sha256": hashlib.sha256(trainer._canonical(manifest)).hexdigest(),
        "cache_manifest": manifest,
        "chunks": chunks,
    }
    descriptor_path = chunk_directory / f"{archive_sha}.chunks.json"
    trainer._atomic_json(descriptor_path, descriptor)
    return descriptor_path, descriptor


def pack_training_validation_caches(
    cache_root: Path,
    archive_directory: Path,
    reference_path: Path,
    reference_sha256: str,
) -> dict[str, object]:
    reference_bytes = reference_path.read_bytes()
    if hashlib.sha256(reference_bytes).hexdigest() != reference_sha256:
        raise ValueError("cache packing reference SHA-256 differs")
    reference = cast(
        dict[str, object],
        json.loads(reference_bytes, object_pairs_hook=trainer._unique_json_object),
    )
    roles = cast(dict[str, list[str]], reference["roles"])
    chunk_directory = archive_directory / "chunks"
    total_archive_bytes = 0
    for role in ("training", "validation"):
        for match_id in roles[role]:
            manifest = pack(cache_root / role / match_id, archive_directory, role, match_id)
            archive_sha = str(manifest["archive_sha256"])
            split_archive(
                archive_directory / f"{archive_sha}.tar",
                archive_directory / f"{archive_sha}.json",
                chunk_directory,
            )
            total_archive_bytes += int(manifest["archive_size_bytes"])
    archive_index_path, archive_index = build_index(
        archive_directory, reference_path, reference_sha256, "all"
    )
    chunk_index_path, chunk_index = build_chunk_index(
        chunk_directory, reference_path, reference_sha256, "all"
    )
    return {
        "status": "PACKED",
        "cache_archive_count": int(archive_index["cache_count"]),
        "total_archive_bytes": total_archive_bytes,
        "chunk_count": len(list(chunk_directory.glob("*.chunk"))),
        "archive_index_path": str(archive_index_path),
        "archive_index_sha256": hashlib.sha256(archive_index_path.read_bytes()).hexdigest(),
        "chunk_index_path": str(chunk_index_path),
        "chunk_index_sha256": hashlib.sha256(chunk_index_path.read_bytes()).hexdigest(),
        "chunk_archive_count": int(chunk_index["archive_count"]),
    }


def build_chunk_index(
    chunk_directory: Path,
    reference_path: Path,
    reference_sha256: str,
    scope: str,
) -> tuple[Path, dict[str, object]]:
    reference_bytes = reference_path.read_bytes()
    if hashlib.sha256(reference_bytes).hexdigest() != reference_sha256:
        raise ValueError("chunk index reference SHA-256 differs")
    reference = cast(
        dict[str, object],
        json.loads(reference_bytes, object_pairs_hook=trainer._unique_json_object),
    )
    roles = cast(dict[str, list[str]], reference["roles"])
    selected = set(roles["training"]) | set(roles["validation"])
    expected = (
        set(cast(dict[str, object], reference["preloaded_cache_identities"]))
        if scope == "preloaded"
        else selected
        if scope == "all"
        else None
    )
    if expected is None:
        raise ValueError("chunk index scope must be preloaded or all")
    archives = []
    seen_matches: set[str] = set()
    for path in sorted(chunk_directory.glob("*.chunks.json")):
        descriptor = trainer._read_private_json(path)
        role, match_id = str(descriptor["role"]), str(descriptor["match_id"])
        if (
            descriptor.get("schema_id") != "fpdbench.res338.cache-archive-chunks"
            or match_id not in expected
            or (role == "training" and match_id not in roles["training"])
            or (role == "validation" and match_id not in roles["validation"])
            or match_id in seen_matches
        ):
            raise ValueError("chunk descriptor is duplicate or outside the selected roles")
        seen_matches.add(match_id)
        for chunk in cast(list[dict[str, object]], descriptor["chunks"]):
            chunk_path = chunk_directory / str(chunk["file_name"])
            if _hash(chunk_path) != (str(chunk["sha256"]), int(chunk["size_bytes"])):
                raise ValueError("chunk identity differs from its descriptor")
        descriptor_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        archives.append(
            {
                "role": role,
                "match_id": match_id,
                "archive_sha256": descriptor["archive_sha256"],
                "archive_size_bytes": descriptor["archive_size_bytes"],
                "descriptor_sha256": descriptor_sha256,
                "descriptor_file_name": path.name,
                "descriptor": descriptor,
                "chunks": descriptor["chunks"],
            }
        )
    if seen_matches != expected:
        raise ValueError("chunk index is missing or adding out-of-scope matches")
    index: dict[str, object] = {
        "schema_id": "fpdbench.res338.cache-chunk-index",
        "schema_version": "1.0.0",
        "scope": scope,
        "parent_reference_sha256": reference_sha256,
        "archive_count": len(archives),
        "archives": archives,
    }
    payload = trainer._canonical(index)
    digest = hashlib.sha256(payload).hexdigest()
    path = chunk_directory / f"cache-chunk-index-{digest}.json"
    if not path.exists():
        trainer._atomic_write(path, payload)
    elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError("content-addressed chunk-index path contains different bytes")
    return path, index


def restore_chunk_descriptors(index_path: Path, output_directory: Path) -> list[Path]:
    index_bytes = index_path.read_bytes()
    index_sha = hashlib.sha256(index_bytes).hexdigest()
    if index_path.stem != f"cache-chunk-index-{index_sha}":
        raise ValueError("content-addressed chunk index filename differs from its bytes")
    index = cast(
        dict[str, object], json.loads(index_bytes, object_pairs_hook=trainer._unique_json_object)
    )
    if index.get("schema_id") != "fpdbench.res338.cache-chunk-index":
        raise ValueError("unknown cache chunk index schema")
    output_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    output_directory.chmod(0o700)
    restored = []
    for entry in cast(list[dict[str, object]], index["archives"]):
        descriptor = cast(dict[str, object], entry["descriptor"])
        payload = trainer._canonical(descriptor)
        digest = hashlib.sha256(payload).hexdigest()
        if (
            digest != entry["descriptor_sha256"]
            or descriptor.get("archive_sha256") != entry.get("archive_sha256")
            or descriptor.get("match_id") != entry.get("match_id")
        ):
            raise ValueError("embedded chunk descriptor differs from its frozen index")
        path = output_directory / str(entry["descriptor_file_name"])
        if path.exists():
            if path.read_bytes() != payload:
                raise ValueError("restored chunk descriptor conflicts with existing content")
        else:
            trainer._atomic_write(path, payload)
        restored.append(path)
    return restored


def assemble_chunks(
    descriptor_path: Path,
    chunk_directory: Path,
    output_directory: Path,
    cache_root: Path | None = None,
) -> dict[str, object]:
    descriptor = trainer._read_private_json(descriptor_path)
    archive_sha = str(descriptor["archive_sha256"])
    manifest = cast(dict[str, object], descriptor["cache_manifest"])
    if (
        descriptor.get("schema_id") != "fpdbench.res338.cache-archive-chunks"
        or hashlib.sha256(trainer._canonical(manifest)).hexdigest()
        != descriptor.get("cache_manifest_sha256")
        or manifest.get("archive_sha256") != archive_sha
    ):
        raise ValueError("chunk descriptor or embedded archive manifest is invalid")
    output_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    output_directory.chmod(0o700)
    target = output_directory / f"{archive_sha}.tar"
    if target.exists():
        if _hash(target) != (archive_sha, int(descriptor["archive_size_bytes"])):
            raise ValueError("existing assembled archive differs from its content identity")
    else:
        temporary = target.with_name(f".{target.name}.{os.getpid()}.partial")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        total_sha = hashlib.sha256()
        total_size = 0
        with os.fdopen(fd, "wb") as output:
            for ordinal, item in enumerate(cast(list[dict[str, object]], descriptor["chunks"])):
                if int(item["ordinal"]) != ordinal:
                    raise ValueError("chunk order differs from the frozen archive descriptor")
                chunk_path = chunk_directory / str(item["file_name"])
                chunk_sha, chunk_size = _hash(chunk_path)
                if (chunk_sha, chunk_size) != (item["sha256"], int(item["size_bytes"])):
                    raise ValueError("uploaded chunk differs from its content identity")
                with chunk_path.open("rb") as stream:
                    while block := stream.read(1024 * 1024):
                        output.write(block)
                        total_sha.update(block)
                        total_size += len(block)
            output.flush()
            os.fsync(output.fileno())
        if (total_sha.hexdigest(), total_size) != (
            archive_sha,
            int(descriptor["archive_size_bytes"]),
        ):
            temporary.unlink(missing_ok=True)
            raise ValueError("assembled archive differs from its content-addressed identity")
        os.replace(temporary, target)
        trainer._fsync_directory(output_directory)
    sidecar = output_directory / f"{archive_sha}.json"
    sidecar_payload = trainer._canonical(manifest)
    if not sidecar.exists():
        trainer._atomic_write(sidecar, sidecar_payload)
    elif sidecar.read_bytes() != sidecar_payload:
        raise ValueError("assembled archive sidecar differs from its embedded manifest")
    result = {"archive": str(target), "archive_sha256": archive_sha}
    if cache_root is not None:
        result["cache_manifest"] = extract(target, sidecar, cache_root)
    return result


def stage_preloaded_chunks(
    index_path: Path,
    expected_index_sha256: str,
    reference_path: Path,
    reference_sha256: str,
    chunk_directory: Path,
    archive_directory: Path,
    cache_root: Path,
) -> dict[str, object]:
    index_bytes = index_path.read_bytes()
    reference_bytes = reference_path.read_bytes()
    if (
        hashlib.sha256(index_bytes).hexdigest() != expected_index_sha256
        or hashlib.sha256(reference_bytes).hexdigest() != reference_sha256
    ):
        raise ValueError("preloaded cache index or reference SHA-256 differs")
    index = cast(
        dict[str, object], json.loads(index_bytes, object_pairs_hook=trainer._unique_json_object)
    )
    reference = cast(
        dict[str, object],
        json.loads(reference_bytes, object_pairs_hook=trainer._unique_json_object),
    )
    preloaded = cast(dict[str, dict[str, object]], reference["preloaded_cache_identities"])
    expected = set(preloaded)
    entries = cast(list[dict[str, object]], index["archives"])
    if (
        index.get("schema_id") != "fpdbench.res338.cache-chunk-index"
        or index.get("scope") != "preloaded"
        or index.get("parent_reference_sha256") != reference_sha256
        or int(index.get("archive_count", -1)) != len(expected)
        or len(entries) != len(expected)
        or {(str(entry["role"]), str(entry["match_id"])) for entry in entries}
        != {("training", match_id) for match_id in expected}
    ):
        raise ValueError("preloaded cache index differs from the six frozen training caches")
    descriptors = restore_chunk_descriptors(index_path, archive_directory / "descriptors")
    for descriptor_path in descriptors:
        descriptor = trainer._read_private_json(descriptor_path)
        match_id = str(descriptor["match_id"])
        if descriptor.get("role") != "training" or match_id not in expected:
            raise ValueError("preloaded cache descriptor contains an out-of-scope role")
        target = cache_root / "training" / match_id
        if target.exists():
            trainer._verified_preloaded_cache(target, match_id, "training", preloaded[match_id])
            assemble_chunks(descriptor_path, chunk_directory, archive_directory)
        else:
            assemble_chunks(descriptor_path, chunk_directory, archive_directory, cache_root)
            trainer._verified_preloaded_cache(target, match_id, "training", preloaded[match_id])
    return {"status": "STAGED", "cache_count": len(descriptors), "role": "training"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    pack_parser = modes.add_parser("pack")
    pack_parser.add_argument("cache_directory", type=Path)
    pack_parser.add_argument("output_directory", type=Path)
    pack_parser.add_argument("role", choices=("training", "validation"))
    pack_parser.add_argument("match_id")
    unpack_parser = modes.add_parser("extract")
    unpack_parser.add_argument("archive", type=Path)
    unpack_parser.add_argument("manifest", type=Path)
    unpack_parser.add_argument("cache_root", type=Path)
    index_parser = modes.add_parser("index")
    index_parser.add_argument("archive_directory", type=Path)
    index_parser.add_argument("reference", type=Path)
    index_parser.add_argument("reference_sha256")
    index_parser.add_argument("scope", choices=("preloaded", "all"))
    restore_parser = modes.add_parser("restore-manifests")
    restore_parser.add_argument("index", type=Path)
    restore_parser.add_argument("output_directory", type=Path)
    restore_chunks_parser = modes.add_parser("restore-chunk-descriptors")
    restore_chunks_parser.add_argument("index", type=Path)
    restore_chunks_parser.add_argument("output_directory", type=Path)
    stage_parser = modes.add_parser("stage-preloaded")
    stage_parser.add_argument("index", type=Path)
    stage_parser.add_argument("index_sha256")
    stage_parser.add_argument("reference", type=Path)
    stage_parser.add_argument("reference_sha256")
    stage_parser.add_argument("chunk_directory", type=Path)
    stage_parser.add_argument("archive_directory", type=Path)
    stage_parser.add_argument("cache_root", type=Path)
    args = parser.parse_args()
    if args.mode == "pack":
        result: object = pack(args.cache_directory, args.output_directory, args.role, args.match_id)
    elif args.mode == "extract":
        result = extract(args.archive, args.manifest, args.cache_root)
    elif args.mode == "index":
        path, index = build_index(
            args.archive_directory, args.reference, args.reference_sha256, args.scope
        )
        result = {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            **index,
        }
    elif args.mode == "restore-manifests":
        result = {
            "restored_manifest_count": len(restore_manifests(args.index, args.output_directory))
        }
    elif args.mode == "restore-chunk-descriptors":
        result = {
            "restored_descriptor_count": len(
                restore_chunk_descriptors(args.index, args.output_directory)
            )
        }
    else:
        result = stage_preloaded_chunks(
            args.index,
            args.index_sha256,
            args.reference,
            args.reference_sha256,
            args.chunk_directory,
            args.archive_directory,
            args.cache_root,
        )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
