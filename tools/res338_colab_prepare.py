"""Download only pinned training/validation source files and reconcile them in Colab."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import urllib.parse
import urllib.request
from pathlib import Path
from typing import cast

import research_population_v1
import train_res338_final_fits as trainer

from fpdbench.data_sources import protected_skillcorner as source


def _identity(path: Path, record: dict[str, object]) -> tuple[str, int]:
    digest = hashlib.sha256()
    blob = hashlib.sha1()
    size_expected = int(record.get("lfs_payload_size", record["byte_size"]))
    blob.update(b"blob " + str(size_expected).encode() + b"\0")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_size != size_expected
        ):
            raise ValueError("downloaded source type or size differs from its pinned identity")
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
            blob.update(block)
        after = os.fstat(stream.fileno())
        if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ValueError("source changed while hashing")
    sha = digest.hexdigest()
    if "lfs_oid_sha256" in record:
        if sha != record["lfs_oid_sha256"]:
            raise ValueError("tracking source SHA-256 differs from the pinned LFS identity")
    elif blob.hexdigest() != record["git_blob_sha"]:
        raise ValueError("source Git blob identity differs")
    if "raw_sha256" in record and sha != record["raw_sha256"]:
        raise ValueError("source raw SHA-256 differs")
    return sha, size_expected


def _download(record: dict[str, object], source_root: Path, commit: str) -> dict[str, object]:
    relative = str(record["repository_path"])
    parts = Path(relative).parts
    if len(parts) != 4 or parts[:2] != ("data", "matches"):
        raise ValueError("unexpected path in training-validation source manifest")
    match_id = parts[2]
    if not parts[3].startswith(f"{match_id}_"):
        raise ValueError("source filename differs from its match directory")
    if record.get("identity_type") == "git_lfs_pointer":
        url = f"https://media.githubusercontent.com/media/SkillCorner/opendata/{commit}/{relative}"
    elif str(record.get("pinned_source_url", "")).startswith(
        f"https://raw.githubusercontent.com/SkillCorner/opendata/{commit}/"
    ):
        url = str(record["pinned_source_url"])
    else:
        raise ValueError("source URL is not the official pinned SkillCorner release")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {
        "raw.githubusercontent.com",
        "media.githubusercontent.com",
    }:
        raise ValueError("source download must come from the pinned official SkillCorner host")
    target = source_root / relative
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if target.exists():
        sha, size = _identity(target, record)
        return {"path": relative, "sha256": sha, "bytes": size, "status": "verified_existing"}
    temporary = target.with_name(f".{target.name}.{os.getpid()}.partial")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    digest = hashlib.sha256()
    blob = hashlib.sha1()
    expected_size = int(record.get("lfs_payload_size", record["byte_size"]))
    blob.update(b"blob " + str(expected_size).encode() + b"\0")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "FPD-RES338-Colab"})
        with os.fdopen(fd, "wb") as stream:
            with urllib.request.urlopen(request, timeout=120) as response:
                final_host = urllib.parse.urlparse(response.geturl()).hostname or ""
                if response.status != 200 or not (
                    final_host.endswith("githubusercontent.com") or final_host == "github.com"
                ):
                    raise ValueError(
                        "pinned source download redirected outside GitHub content hosts"
                    )
                count = 0
                while block := response.read(1024 * 1024):
                    count += len(block)
                    if count > expected_size:
                        raise ValueError("source download exceeded its pinned byte size")
                    digest.update(block)
                    blob.update(block)
                    stream.write(block)
                if count != expected_size:
                    raise ValueError("source download was truncated")
                stream.flush()
                os.fsync(stream.fileno())
        sha = digest.hexdigest()
        if "lfs_oid_sha256" in record:
            if sha != record["lfs_oid_sha256"]:
                raise ValueError("tracking source SHA-256 differs from the pinned LFS identity")
        elif blob.hexdigest() != record["git_blob_sha"]:
            raise ValueError("source Git blob identity differs")
        if "raw_sha256" in record and sha != record["raw_sha256"]:
            raise ValueError("source raw SHA-256 differs")
        os.replace(temporary, target)
        trainer._fsync_directory(target.parent)
        return {
            "path": relative,
            "sha256": sha,
            "bytes": count,
            "status": "downloaded_and_verified",
        }
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def prepare(
    *,
    reference_path: Path,
    reference_sha256: str,
    source_root: Path,
    research_root: Path,
    repo_root: Path,
) -> dict[str, object]:
    os.umask(0o077)
    if reference_path.is_symlink():
        raise ValueError("training-validation reference cannot be a symlink")
    reference_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    reference_path.parent.chmod(0o700)
    reference_path.chmod(0o600)
    ref_bytes = reference_path.read_bytes()
    if hashlib.sha256(ref_bytes).hexdigest() != reference_sha256:
        raise ValueError("training-validation reference SHA-256 differs")
    reference = cast(
        dict[str, object], json.loads(ref_bytes, object_pairs_hook=trainer._unique_json_object)
    )
    if (
        reference.get("schema_id") != "fpdbench.res338.training-validation-reference"
        or reference.get("parent_research_manifest_sha256") != trainer.RESEARCH_MANIFEST_SHA256
        or len(reference.get("roles", {}).get("training", [])) != 12
        or len(reference.get("roles", {}).get("validation", [])) != 4
        or "evaluation" in reference.get("roles", {})
    ):
        raise ValueError("reference is not a training/validation-only projection")
    expected_scope = set(reference["roles"]["training"]) | set(reference["roles"]["validation"])
    if set(reference["source_match_order"]) != expected_scope or len(expected_scope) != 16:
        raise ValueError("source manifest contains missing or out-of-scope matches")
    source_manifest = cast(list[dict[str, object]], reference["source_manifest"])
    if len(source_manifest) != 64:
        raise ValueError("exactly 64 pinned source files for the 16 selected matches are required")
    expected_paths = {str(row["path"]) for row in reference["source_files"]}
    if {str(row["repository_path"]) for row in source_manifest} != expected_paths or any(
        len(Path(str(row["repository_path"])).parts) != 4
        or Path(str(row["repository_path"])).parts[2] not in expected_scope
        for row in source_manifest
    ):
        raise ValueError("source manifest contains a missing or evaluation-role path")
    if source_root.is_symlink() or research_root.is_symlink():
        raise ValueError("Colab staging roots cannot be symlinks")
    source_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    source_root.chmod(0o700)
    research_root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    research_root.parent.chmod(0o700)
    with source.private_directory(source_root):
        pass
    downloads = [
        _download(row, source_root, str(reference["source_commit"])) for row in source_manifest
    ]
    if {item["path"] for item in downloads} != {item["path"] for item in reference["source_files"]}:
        raise ValueError("downloaded source paths differ from the frozen source projection")
    if research_root.exists():
        existing_admission = research_root / "research-admission.json"
        if not existing_admission.is_file():
            raise FileExistsError(
                "partial research root is preserved; use a fresh Colab session path"
            )
        plan, _, roles = trainer._frozen_split_and_authorities()
        _, rehash = trainer.verify_training_validation_population(
            research_root, source_root, reference_path, reference_sha256, plan, roles
        )
        print(
            json.dumps(
                {
                    "status": "PREPARED",
                    "population_rehash": rehash,
                    "research_admission_sha256": hashlib.sha256(
                        existing_admission.read_bytes()
                    ).hexdigest(),
                    "source_file_count": len(downloads),
                    "source_bytes": sum(int(item["bytes"]) for item in downloads),
                    "match_count": 16,
                    "evaluation_files_downloaded": 0,
                    "evaluation_labels_loaded": 0,
                },
                sort_keys=True,
            )
        )
        return {"status": "PREPARED", "population_rehash": rehash}
    manifest_dir = research_root.parent / "manifests"
    manifest_dir.mkdir(mode=0o700, exist_ok=True)
    source_manifest_out = {
        "schema_id": "fpdbench.res338.colab-source-download",
        "schema_version": "1.0.0",
        "parent_research_manifest_sha256": trainer.RESEARCH_MANIFEST_SHA256,
        "source_commit": reference["source_commit"],
        "scope": "training-validation",
        "match_count": 16,
        "files": downloads,
    }
    trainer._atomic_json(manifest_dir / "source-download-manifest.json", source_manifest_out)
    research_population_v1.run(
        source_root,
        research_root,
        None,
        scope="training-validation",
        reference_path=reference_path,
        reference_sha256=reference_sha256,
    )
    plan, _, roles = trainer._frozen_split_and_authorities()
    _, rehash = trainer.verify_training_validation_population(
        research_root, source_root, reference_path, reference_sha256, plan, roles
    )
    report = {
        "status": "PREPARED",
        "source_manifest_sha256": hashlib.sha256(
            (manifest_dir / "source-download-manifest.json").read_bytes()
        ).hexdigest(),
        "research_admission_sha256": hashlib.sha256(
            (research_root / "research-admission.json").read_bytes()
        ).hexdigest(),
        "source_file_count": len(downloads),
        "source_bytes": sum(int(item["bytes"]) for item in downloads),
        "match_count": len(expected_scope),
        "roles": {role: len(ids) for role, ids in reference["roles"].items()},
        "evaluation_files_downloaded": 0,
        "evaluation_labels_loaded": 0,
        "raw_source_persisted_to_drive": False,
    }
    print(json.dumps(report, sort_keys=True))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=Path("/content/res338/reference.json"))
    parser.add_argument("--reference-sha256", required=True)
    parser.add_argument("--source-root", type=Path, default=Path("/content/res338/source"))
    parser.add_argument("--research-root", type=Path, default=Path("/content/res338/research"))
    parser.add_argument("--repo-root", type=Path, default=Path("/content/res338/repo"))
    args = parser.parse_args()
    os.chdir(args.repo_root)
    prepare(
        reference_path=args.reference,
        reference_sha256=args.reference_sha256,
        source_root=args.source_root,
        research_root=args.research_root,
        repo_root=args.repo_root,
    )


if __name__ == "__main__":
    main()
