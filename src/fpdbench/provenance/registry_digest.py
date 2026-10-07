"""Compute the canonical read-only content digest for an evidence registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import unicodedata
from dataclasses import dataclass
from pathlib import Path


def _normalized_path(path: Path, root: Path) -> str:
    value = unicodedata.normalize("NFC", path.relative_to(root).as_posix())
    value.encode("utf-8", errors="strict")
    return value


def _raise_walk_error(error: OSError) -> None:
    raise error


@dataclass(frozen=True, slots=True)
class RegistryManifestEntry:
    path: str
    kind: str
    sha256: str


def registry_content_manifest(root: Path) -> tuple[RegistryManifestEntry, ...]:
    """Return the canonical file and symlink records used by the registry digest."""
    if root.is_symlink():
        raise ValueError("registry root must not be a symlink")
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("registry root must be a directory")

    records: list[tuple[bytes, RegistryManifestEntry]] = []
    for base, directories, filenames in os.walk(root, followlinks=False, onerror=_raise_walk_error):
        base_path = Path(base)
        retained_directories: list[str] = []
        for name in directories:
            path = base_path / name
            relative = path.relative_to(root)
            if ".git" in relative.parts:
                continue
            if path.is_symlink():
                target = os.fsencode(os.readlink(path))
                normalized = _normalized_path(path, root)
                records.append(
                    (
                        normalized.encode("utf-8"),
                        RegistryManifestEntry(
                            normalized, "symlink", hashlib.sha256(target).hexdigest()
                        ),
                    )
                )
            else:
                retained_directories.append(name)
        directories[:] = retained_directories

        for name in filenames:
            path = base_path / name
            relative = path.relative_to(root)
            if ".git" in relative.parts:
                continue
            normalized = _normalized_path(path, root)
            file_stat = path.lstat()
            if stat.S_ISREG(file_stat.st_mode):
                digest = hashlib.sha256()
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                kind = "file"
            elif stat.S_ISLNK(file_stat.st_mode):
                digest = hashlib.sha256(os.fsencode(os.readlink(path)))
                kind = "symlink"
            else:
                raise ValueError(f"unsupported registry filesystem node: {normalized}")
            records.append(
                (
                    normalized.encode("utf-8"),
                    RegistryManifestEntry(normalized, kind, digest.hexdigest()),
                )
            )

    records.sort(key=lambda item: item[0])
    normalized_paths = [record.path for _, record in records]
    if len(normalized_paths) != len(set(normalized_paths)):
        raise ValueError("registry paths collide after NFC normalization")
    return tuple(record for _, record in records)


def registry_content_digest(root: Path) -> tuple[str, int]:
    """Hash regular files and symlink targets, excluding every ``.git`` path."""
    entries = registry_content_manifest(root)

    aggregate = hashlib.sha256()
    for entry in entries:
        aggregate.update(
            (
                json.dumps(
                    {"kind": entry.kind, "path": entry.path, "sha256": entry.sha256},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
        )
    return aggregate.hexdigest(), len(entries)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    digest, count = registry_content_digest(args.root)
    print(json.dumps({"path_count": count, "sha256": digest}, sort_keys=True))
    return 0
