"""Linux source preflight. Never constructs or qualifies population membership."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from collections.abc import Generator, Iterator, Mapping
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import BinaryIO, cast

from fpdbench.data_sources.skillcorner import (
    MANIFEST_PATH,
    canonical_bytes,
    validate_lfs_pointer,
    validate_manifest,
)
from fpdbench.data_states.skillcorner import iter_skillcorner_5hz_v2, serialize_sample
from fpdbench.eligibility.skillcorner import (
    skillcorner_period_ranges,
    validate_ball_population_drift_v2,
)

REVISION = "4340d274572876239c154c90bc507a9b3250a656"
MANIFEST_SHA256 = "938cded522ee08f5de539976752fde51b2e858709574f3f63380bd72dd1af7fc"
SCHEMA = "fpdbench.protected-source-preflight"
VERSION = "1.0.0"
NAMESPACE = "fpdbench-res501-source-v1"
# Bounds are resource limits, not permission to truncate or omit any source rows.
MAX_ROW = 1024 * 1024
MAX_DOCUMENT = 16 * 1024 * 1024


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return cast(dict[str, object], value)


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _invalid_constant(_: str) -> object:
    raise ValueError("nonfinite JSON value")


def _json(payload: bytes) -> object:
    return cast(
        object, json.loads(payload, object_pairs_hook=_unique, parse_constant=_invalid_constant)
    )


def _parts(path: str) -> list[str]:
    parts = path.split("/")
    if not parts or any(part in {"", ".", ".."} or "\\" in part for part in parts):
        raise ValueError("unsafe relative path")
    return parts


def _check_directory(fd: int, *, private: bool) -> None:
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid not in {0, os.getuid()}:
        raise ValueError("unsafe directory owner or type")
    if private:
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("private directory requires user ownership and 0700")
    elif info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX:
        raise ValueError("unsafe writable ancestor")


def _file_identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _git_environment() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(LC_ALL="C", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null")
    return env


@contextmanager
def private_directory(path: Path) -> Generator[int]:
    """PR #16's boundary, strengthened with component-wise no-follow directory FDs."""
    if sys.platform != "linux" or not path.is_absolute() or ".." in path.parts:
        raise ValueError("absolute Linux storage path required")
    if path == Path("/mnt") or Path("/mnt") in path.parents:
        raise ValueError("Windows-mounted storage is forbidden")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        _check_directory(fd, private=False)
        for index, part in enumerate(path.parts[1:]):
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            _check_directory(fd, private=index == len(path.parts) - 2)
            try:
                os.stat(".git", dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ValueError("storage is inside a Git worktree")
        _check_directory(fd, private=True)
        # Reject Windows/network filesystems even when mounted outside /mnt.
        filesystem = subprocess.run(
            ["stat", "-f", "-c", "%T", f"/proc/self/fd/{fd}"],
            pass_fds=(fd,),
            capture_output=True,
            check=True,
            text=True,
        ).stdout.strip()
        if filesystem not in {"ext2/ext3", "btrfs", "xfs", "tmpfs", "overlayfs"}:
            raise ValueError("unsupported protected-storage filesystem")
        git = subprocess.run(
            ["git", "-C", f"/proc/self/fd/{fd}", "rev-parse", "--is-inside-work-tree"],
            pass_fds=(fd,),
            capture_output=True,
            env=_git_environment(),
            check=False,
        )
        if git.returncode == 0 or b"not a git repository" not in git.stderr:
            raise ValueError("cannot establish non-Git storage")
        yield fd
    finally:
        os.close(fd)


@contextmanager
def _open_file(root: int, relative: str) -> Generator[BinaryIO]:
    parts = _parts(relative)
    directory = os.dup(root)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
            _check_directory(directory, private=True)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_nlink != 1
            ):
                raise ValueError("source files require exclusive user-owned regular 0600 files")
            yield stream
            if _file_identity(os.fstat(stream.fileno())) != _file_identity(info):
                raise ValueError("source changed while open")
    finally:
        os.close(directory)


def write_private(directory: int, name: str, payload: bytes) -> None:
    if len(_parts(name)) != 1:
        raise ValueError("receipt name must be a basename")
    fd = os.open(
        name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory
    )
    with os.fdopen(fd, "wb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.fsync(directory)


def _authority() -> dict[str, object]:
    payload = MANIFEST_PATH.read_bytes()
    if hashlib.sha256(payload).hexdigest() != MANIFEST_SHA256:
        raise ValueError("unreviewed source authority")
    manifest = _object(_json(payload))
    if validate_manifest(manifest) or _object(manifest["upstream"])["pinned_commit"] != REVISION:
        raise ValueError("invalid pinned source authority")
    return manifest


def _records(manifest: Mapping[str, object]) -> list[dict[str, object]]:
    matches = cast(list[dict[str, object]], manifest["available_matches"])
    records = [_object(manifest["source_index"])] + [
        _object(entry) for match in matches for entry in cast(list[object], match["files"])
    ]
    paths = [str(entry["repository_path"]) for entry in records]
    if (
        len(matches) != 20
        or len(records) != 81
        or len(set(paths)) != 81
        or sum(r["identity_type"] == "git_lfs_pointer" for r in records) != 20
    ):
        raise ValueError("expected exactly 81 files and 20 LFS payloads")
    for path in paths:
        _parts(path)
    return sorted(records, key=lambda entry: str(entry["repository_path"]))


def _inventory(root: int, paths: list[str]) -> None:
    expected: dict[str, object] = {}
    for path in paths:
        tree = expected
        for part in _parts(path)[:-1]:
            tree = cast(dict[str, object], tree.setdefault(part, {}))
        tree[_parts(path)[-1]] = None

    def visit(fd: int, tree: dict[str, object]) -> None:
        # An unexpected entry fails immediately; no unbounded recursive walk.
        with os.scandir(fd) as entries:
            names: set[str] = set()
            for entry in entries:
                if entry.name not in tree:
                    raise ValueError("unexpected source inventory entry")
                names.add(entry.name)
        if names != set(tree):
            raise ValueError("missing source inventory entry")
        for name, child in tree.items():
            if child is not None:
                child_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    _check_directory(child_fd, private=True)
                    visit(child_fd, cast(dict[str, object], child))
                finally:
                    os.close(child_fd)

    visit(root, expected)


def _verify_sources(root: int, records: list[dict[str, object]]) -> list[dict[str, object]]:
    _inventory(root, [str(entry["repository_path"]) for entry in records])
    receipts: list[dict[str, object]] = []
    for entry in records:
        lfs = entry["identity_type"] == "git_lfs_pointer"
        size = cast(int, entry["lfs_payload_size"] if lfs else entry["byte_size"])
        path = str(entry["repository_path"])
        sha = hashlib.sha256()
        blob = hashlib.sha1(b"blob " + str(size).encode() + b"\0")
        with _open_file(root, path) as stream:
            if os.fstat(stream.fileno()).st_size != size:
                raise ValueError("source byte size mismatch")
            count = 0
            while chunk := stream.read(MAX_ROW):
                count += len(chunk)
                if count > size:
                    raise ValueError("source grew during verification")
                sha.update(chunk)
                blob.update(chunk)
        if count != size:
            raise ValueError("truncated source")
        if lfs:
            pointer = (
                f"version https://git-lfs.github.com/spec/v1\n"
                f"oid sha256:{entry['lfs_oid_sha256']}\nsize {size}\n"
            ).encode()
            if (
                validate_lfs_pointer(pointer, entry, path)
                or sha.hexdigest() != entry["lfs_oid_sha256"]
            ):
                raise ValueError("LFS pointer or resolved payload identity mismatch")
        elif blob.hexdigest() != entry["git_blob_sha"]:
            raise ValueError("Git blob identity mismatch")
        if "raw_sha256" in entry and sha.hexdigest() != entry["raw_sha256"]:
            raise ValueError("source SHA-256 mismatch")
        receipts.append(
            {
                "path": path,
                "bytes": size,
                "sha256": sha.hexdigest(),
                "git_blob_sha": entry["git_blob_sha"],
            }
        )
    return receipts


def _document(root: int, path: str) -> bytes:
    with _open_file(root, path) as stream:
        payload = stream.read(MAX_DOCUMENT + 1)
    if len(payload) > MAX_DOCUMENT:
        raise ValueError("document exceeds reviewed memory bound")
    return payload


def _rows(root: int, path: str, counts: dict[str, object]) -> Iterator[dict[str, object]]:
    raw_digest = hashlib.sha256()
    rows = 0
    even_rows = 0
    even_ids = hashlib.sha256()
    with _open_file(root, path) as stream:
        while line := stream.readline(MAX_ROW + 1):
            if len(line) > MAX_ROW or not line.strip():
                raise ValueError("oversized or empty tracking row")
            raw_digest.update(line)
            rows += 1
            row = _object(_json(line))
            frame = row.get("frame")
            if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
                raise ValueError("invalid source frame")
            if frame % 2 == 0:
                even_rows += 1
                even_ids.update(str(frame).encode() + b"\n")
            yield row
    counts.update(
        source_rows=rows,
        tracking_sha256=raw_digest.hexdigest(),
        even_source_rows=even_rows,
        even_frame_ids_sha256=even_ids.hexdigest(),
    )


def normalize_phases(payload: bytes, metadata: Mapping[str, object]) -> bytes:
    """Map positive CSV intervals to sorted half-open wire intervals; gaps stay gaps."""
    if len(payload) > MAX_DOCUMENT:
        raise ValueError("phase document exceeds reviewed memory bound")
    bounds, issues = skillcorner_period_ranges(metadata)
    if issues or not bounds:
        raise ValueError("invalid phase period bounds")
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8"), newline=""), strict=True)
    headers = reader.fieldnames
    if (
        not headers
        or len(headers) != len(set(headers))
        or not {"frame_start", "frame_end"} <= set(headers)
    ):
        raise ValueError("invalid phase CSV header")
    intervals: list[dict[str, int]] = []
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("ragged phase CSV row")
        values: list[int] = []
        for field in ("frame_start", "frame_end"):
            if not re.fullmatch(r"0|[1-9][0-9]*", row[field]):
                raise ValueError("phase frames must be exact nonnegative integers")
            values.append(int(row[field]))
        start, end = values
        periods = [
            period for period, (left, right) in bounds.items() if left <= start < end <= right
        ]
        if len(periods) != 1:
            raise ValueError("phase interval crosses or escapes period bounds")
        period = periods[0]
        if "period" in row and row["period"] != str(period):
            raise ValueError("phase period disagrees with metadata")
        if "duration" in row:
            try:
                duration = Decimal(row["duration"])
                if not duration.is_finite() or duration != Decimal(end - start) / 10:
                    raise ValueError("phase duration disagrees with half-open bounds")
            except InvalidOperation:
                raise ValueError("invalid phase duration") from None
        intervals.append({"period": period, "frame_start": start, "frame_end": end})
    intervals.sort(key=lambda row: (row["period"], row["frame_start"], row["frame_end"]))
    if not intervals:
        raise ValueError("empty phase CSV")
    # Opposing-team annotations may overlap; preserve rows and multiplicity, never fill gaps.
    return canonical_bytes(intervals)


def _scan(root: int, manifest: dict[str, object]) -> list[dict[str, object]]:
    counts: list[dict[str, object]] = []

    def samples() -> Iterator[dict[str, object]]:
        for match_id in cast(list[int], manifest["selected_source_matches"]):
            prefix = f"data/matches/{match_id}/{match_id}"
            metadata = _object(_json(_document(root, prefix + "_match.json")))
            if metadata.get("id") != match_id:
                raise ValueError("metadata identity mismatch")
            count: dict[str, object] = {"match_id": match_id}
            digest = hashlib.sha256()
            retained = 0
            retained_ids = hashlib.sha256()
            for sample in iter_skillcorner_5hz_v2(
                _rows(root, prefix + "_tracking_extrapolated.jsonl", count),
                metadata,
                source_release_id=str(manifest["source_release_id"]),
            ):
                retained += 1
                retained_ids.update(str(sample["source_frame"]).encode() + b"\n")
                digest.update(serialize_sample(sample) + b"\n")
                yield sample
            if (
                not retained
                or retained != count["even_source_rows"]
                or retained_ids.hexdigest() != count["even_frame_ids_sha256"]
            ):
                raise ValueError("incomplete retained-frame coverage")
            count.update(retained_rows=retained, retained_sha256=digest.hexdigest())
            counts.append(count)

    # This scan returns diagnostics only. Its result cannot authorize membership or truth.
    validate_ball_population_drift_v2(samples())
    return counts


def _ancestor_identities(directory: int) -> set[tuple[int, int]]:
    result: set[tuple[int, int]] = set()
    fd = os.dup(directory)
    try:
        while True:
            info = os.fstat(fd)
            identity = (info.st_dev, info.st_ino)
            if identity in result:
                return result
            result.add(identity)
            parent = os.open("..", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = parent
    finally:
        os.close(fd)


def source_preflight(source: Path, destination: Path) -> None:
    """Two-pass restricted preflight; fresh receipts only, no producer invocation."""
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("source and receipt directories must be disjoint")
    with private_directory(source) as root, private_directory(destination) as output:
        source_info, output_info = os.fstat(root), os.fstat(output)
        if (source_info.st_dev, source_info.st_ino) in _ancestor_identities(output) or (
            output_info.st_dev,
            output_info.st_ino,
        ) in _ancestor_identities(root):
            raise ValueError("source and receipt filesystem identities overlap")
        if os.listdir(output):
            raise ValueError("fresh empty receipt directory required; recovery never overwrites")
        write_private(output, "started.json", canonical_bytes({"status": "INCOMPLETE"}))
        try:
            manifest = _authority()
            records = _records(manifest)
            inventory = _verify_sources(root, records)
            counts = _scan(root, manifest)
            expected = {str(row["path"]): row["sha256"] for row in inventory}
            for count in counts:
                match_id = count["match_id"]
                path = f"data/matches/{match_id}/{match_id}_tracking_extrapolated.jsonl"
                if count["tracking_sha256"] != expected[path]:
                    raise ValueError("source changed during global scan")
            # Pass two begins only after the entire source-wide v2 drift scan completes.
            normalized: list[dict[str, object]] = []
            for match_id in cast(list[int], manifest["selected_source_matches"]):
                prefix = f"data/matches/{match_id}/{match_id}"
                metadata_bytes = _document(root, prefix + "_match.json")
                csv_bytes = _document(root, prefix + "_phases_of_play.csv")
                for suffix, payload in (
                    ("_match.json", metadata_bytes),
                    ("_phases_of_play.csv", csv_bytes),
                ):
                    if hashlib.sha256(payload).hexdigest() != expected[prefix + suffix]:
                        raise ValueError("normalization source changed")
                phases = normalize_phases(csv_bytes, _object(_json(metadata_bytes)))
                name = f"phases-{match_id}.json"
                write_private(output, name, phases)
                normalized.append(
                    {
                        "path": name,
                        "sha256": hashlib.sha256(phases).hexdigest(),
                        "source_sha256": hashlib.sha256(csv_bytes).hexdigest(),
                        "metadata_sha256": hashlib.sha256(metadata_bytes).hexdigest(),
                    }
                )
            if _verify_sources(root, records) != inventory:
                raise ValueError("source changed during preflight")
            package_root = Path(__file__).resolve().parents[1]
            implementation = [
                {
                    "path": path.relative_to(package_root).as_posix(),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
                for path in sorted(package_root.rglob("*"))
                if path.is_file() and path.suffix in {".py", ".json"}
            ]
            receipt = {
                "schema_id": SCHEMA,
                "schema_version": VERSION,
                "status": "SOURCE_PREFLIGHT",
                "qualification_status": "NOT_QUALIFIED",
                "source_revision": REVISION,
                "authority_sha256": MANIFEST_SHA256,
                "inputs": inventory,
                "scan": counts,
                "normalized_phases": normalized,
                "adapter_package": implementation,
                "authentication": "DETACHED_SSH_SIGNATURE_REQUIRED",
            }
            write_private(output, "source-preflight.json", canonical_bytes(receipt))
        except Exception:
            try:
                write_private(output, "failure.json", canonical_bytes({"status": "INCOMPLETE"}))
            except Exception:
                pass
            raise ValueError(
                "INCOMPLETE: protected preflight failed; use a fresh receipt directory"
            ) from None


def authenticate_receipt(
    receipt: bytes,
    signature: Path,
    allowed_signers: Path,
    *,
    trusted_signers_sha256: str,
    expected_package_sha256: str,
) -> dict[str, object]:
    """Independent reviewer pins trust file AND reviewed adapter inventory out of band."""
    if len(receipt) > MAX_DOCUMENT:
        raise ValueError("oversized receipt")
    with private_directory(allowed_signers.parent) as trusted_root:
        trusted = _document(trusted_root, allowed_signers.name)
    with private_directory(signature.parent) as signature_root:
        signed = _document(signature_root, signature.name)
    if hashlib.sha256(trusted).hexdigest() != trusted_signers_sha256:
        raise ValueError("untrusted signer configuration")
    with tempfile.TemporaryDirectory(prefix="res501-auth-") as temporary:
        with private_directory(Path(temporary)) as root:
            write_private(root, "signers", trusted)
            write_private(root, "signature", signed)
            result = subprocess.run(
                [
                    "ssh-keygen",
                    "-Y",
                    "verify",
                    "-f",
                    temporary + "/signers",
                    "-I",
                    "res501-source",
                    "-n",
                    NAMESPACE,
                    "-s",
                    temporary + "/signature",
                ],
                input=receipt,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
    if result.returncode:
        raise ValueError("source receipt signature not authenticated")
    value = _object(_json(receipt))
    if (
        value.get("schema_id") != SCHEMA
        or value.get("schema_version") != VERSION
        or value.get("status") != "SOURCE_PREFLIGHT"
        or value.get("qualification_status") != "NOT_QUALIFIED"
        or value.get("source_revision") != REVISION
        or value.get("authority_sha256") != MANIFEST_SHA256
        or hashlib.sha256(canonical_bytes(value.get("adapter_package"))).hexdigest()
        != expected_package_sha256
    ):
        raise ValueError("unreviewed receipt provenance contract")
    return value
