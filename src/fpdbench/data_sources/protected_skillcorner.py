"""Linux source preflight. Never constructs or qualifies population membership."""

from __future__ import annotations

import base64
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

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    empirical_experiment_plan as experiment_plan,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.prospective_protocol import (
    EXPECTED_ELIGIBILITY_POLICY_V2_HASH,
    EXPECTED_MEASUREMENT_STATE_V2_HASH,
    EXPECTED_SOURCE_POPULATION_HASH,
    EXPECTED_SOURCE_RELEASE_HASH,
    PROTOCOL_V2_SHA256,
)
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
TRUST_DIRECTORY = Path("/etc/fpdbench/protected-executor")
TRUST_OWNER_UID = 0
TRUST_POLICY_NAMESPACE = "fpdbench-res544-trust-policy-v1"
TRUST_POLICY_PRINCIPAL = "fpdbench-policy-owner"
TRUST_POLICY_SCHEMA = "fpdbench.protected-execution-trust-policy"
TRUST_POLICY_VERSION = "1.0.0"
PRODUCER_REVISION = "6644dba8c945ca86be72b54792db30cbe488e5d0"
PRODUCER_INVENTORY_SHA256 = "153bc67c532b8eddba90a98994d60f656526e71961f17c9d1f2454a72dd2e1a4"
VERIFIER_REVISION = "ef1a22583cdd52bb63509a13bfc480a313ea69d4"
VERIFIER_INVENTORY_SHA256 = "c61851dd0b930694a960d8cf79046258ea92a8c2cc19db60d33fdbb12f4b6b09"
POPULATION_SCHEMA_SHA256 = "27da86b7355c311a65c68ab9b2bd3ae86e27779ed48641c23181ffe2f9adc224"
RESULT_SCHEMA_SHA256 = "d0d7dbf4a14cade66d1e0ce7282441d8f035a68de8a192ad8e4d70210be18f7f"
# Bounds are resource limits, not permission to truncate or omit any source rows.
MAX_ROW = 1024 * 1024
MAX_DOCUMENT = 16 * 1024 * 1024
MAX_TRUST_POLICY = 1024 * 1024
PLAN_V2_SHA256 = experiment_plan.PLAN_V2_SHA256


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
            implementation = installed_adapter_inventory()
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


@contextmanager
def _trusted_directory() -> Generator[int]:
    path = TRUST_DIRECTORY
    if sys.platform != "linux" or not path.is_absolute() or ".." in path.parts:
        raise ValueError("Linux system trust directory required")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for index, part in enumerate(path.parts[1:]):
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            final = index == len(path.parts) - 2
            allowed_owners = {0, TRUST_OWNER_UID}
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid not in allowed_owners
                or (final and info.st_uid != TRUST_OWNER_UID)
                or (info.st_mode & 0o022 and (final or not info.st_mode & stat.S_ISVTX))
            ):
                raise ValueError("unsafe system trust directory")
            try:
                os.stat(".git", dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ValueError("system trust directory is inside a Git worktree")
        if not path.parts[1:]:
            raise ValueError("system trust directory must not be root")
        yield fd
    finally:
        os.close(fd)


def _trusted_file(directory: int, name: str, *, limit: int = MAX_TRUST_POLICY) -> bytes:
    if len(_parts(name)) != 1:
        raise ValueError("unsafe trust filename")
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != TRUST_OWNER_UID
            or info.st_mode & 0o022
            or info.st_nlink != 1
            or info.st_size > limit
        ):
            raise ValueError("unsafe system trust file")
        payload = stream.read(limit + 1)
        if (
            len(payload) != info.st_size
            or len(payload) > limit
            or _file_identity(os.fstat(stream.fileno())) != _file_identity(info)
        ):
            raise ValueError("system trust file changed while open")
        return payload


def _hash(value: object, label: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"invalid {label}")
    return value


def _fingerprint(public_key: bytes) -> str:
    return "SHA256:" + base64.b64encode(hashlib.sha256(public_key).digest()).decode().rstrip("=")


def _signer_fingerprints(payload: bytes, principal: str) -> frozenset[str]:
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        raise ValueError("invalid allowed-signers file") from None
    fingerprints: list[str] = []
    for line in lines:
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if (
            len(fields) not in {3, 4}
            or fields[0] != principal
            or fields[1] not in {"ssh-ed25519", "ecdsa-sha2-nistp256", "ssh-rsa"}
        ):
            raise ValueError("allowed-signers file must contain only the pinned principal")
        try:
            public_key = base64.b64decode(fields[2], validate=True)
        except ValueError:
            raise ValueError("invalid allowed-signers public key") from None
        if not public_key:
            raise ValueError("empty allowed-signers public key")
        fingerprints.append(_fingerprint(public_key))
    if not fingerprints or len(fingerprints) != len(set(fingerprints)):
        raise ValueError("allowed-signers file is empty or duplicated")
    return frozenset(fingerprints)


def _verify_ssh_signature(
    payload: bytes, signature: bytes, allowed_signers: bytes, principal: str, namespace: str
) -> None:
    with tempfile.TemporaryDirectory(prefix="fpdbench-auth-", dir="/tmp") as temporary:
        root_path = Path(temporary)
        with private_directory(root_path) as root:
            write_private(root, "allowed_signers", allowed_signers)
            write_private(root, "signature", signature)
        try:
            result = subprocess.run(
                [
                    "/usr/bin/ssh-keygen",
                    "-Y",
                    "verify",
                    "-f",
                    temporary + "/allowed_signers",
                    "-I",
                    principal,
                    "-n",
                    namespace,
                    "-s",
                    temporary + "/signature",
                ],
                input=payload,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
                check=False,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise ValueError("detached signature verification unavailable") from None
        if result.returncode:
            raise ValueError("detached signature not authenticated")


def _authority_bindings() -> dict[str, str]:
    return {
        "source_authority_sha256": MANIFEST_SHA256,
        "source_release_sha256": EXPECTED_SOURCE_RELEASE_HASH,
        "source_population_sha256": EXPECTED_SOURCE_POPULATION_HASH,
        "measurement_state_sha256": EXPECTED_MEASUREMENT_STATE_V2_HASH,
        "eligibility_policy_sha256": EXPECTED_ELIGIBILITY_POLICY_V2_HASH,
        "protocol_sha256": PROTOCOL_V2_SHA256,
        "plan_sha256": PLAN_V2_SHA256,
        "population_schema_sha256": POPULATION_SCHEMA_SHA256,
        "result_schema_sha256": RESULT_SCHEMA_SHA256,
    }


def installed_adapter_inventory() -> list[dict[str, str]]:
    package_root = Path(__file__).resolve().parents[1]
    return [
        {
            "path": path.relative_to(package_root).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted(package_root.rglob("*"))
        if path.is_file() and path.suffix in {".py", ".json"} and not path.is_symlink()
    ]


def _inventory_digest(inventory: object) -> str:
    return hashlib.sha256(canonical_bytes(inventory)).hexdigest()


def _validate_trust_policy(payload: bytes, reviewer_signers: bytes) -> dict[str, object]:
    value = _object(_json(payload))
    if canonical_bytes(value) != payload or set(value) != {
        "schema_id",
        "schema_version",
        "generation",
        "status",
        "reviewer",
        "adapter_inventory_sha256",
        "producer",
        "verifier",
        "authority_bindings",
        "revoked_signer_key_fingerprints",
    }:
        raise ValueError("invalid trusted execution policy shape")
    generation = value.get("generation")
    if (
        value.get("schema_id") != TRUST_POLICY_SCHEMA
        or value.get("schema_version") != TRUST_POLICY_VERSION
        or value.get("status") != "ACTIVE"
        or isinstance(generation, bool)
        or not isinstance(generation, int)
        or generation < 1
    ):
        raise ValueError("invalid trusted execution policy identity")
    reviewer = _object(value.get("reviewer"))
    if set(reviewer) != {"principal", "namespace", "allowed_signers_sha256"}:
        raise ValueError("invalid reviewer policy")
    principal = reviewer.get("principal")
    if (
        not isinstance(principal, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._@-]{0,127}", principal) is None
        or reviewer.get("namespace") != NAMESPACE
        or _hash(reviewer.get("allowed_signers_sha256"), "reviewer key digest")
        != hashlib.sha256(reviewer_signers).hexdigest()
    ):
        raise ValueError("reviewer identity or allowed-signers digest mismatch")
    if _hash(value.get("adapter_inventory_sha256"), "adapter inventory digest") != (
        _inventory_digest(installed_adapter_inventory())
    ):
        raise ValueError("unreviewed protected adapter inventory")
    producer = _object(value.get("producer"))
    verifier = _object(value.get("verifier"))
    if producer != {
        "revision": PRODUCER_REVISION,
        "inventory_sha256": PRODUCER_INVENTORY_SHA256,
    } or verifier != {
        "revision": VERIFIER_REVISION,
        "inventory_sha256": VERIFIER_INVENTORY_SHA256,
    }:
        raise ValueError("producer or verifier pin differs from the reviewed historical packages")
    bindings = _object(value.get("authority_bindings"))
    if bindings != _authority_bindings():
        raise ValueError("trusted policy changes frozen scientific authority bindings")
    revoked = value.get("revoked_signer_key_fingerprints")
    if not isinstance(revoked, list):
        raise ValueError("invalid reviewer key revocation list")
    revoked_values: list[str] = []
    for item in cast(list[object], revoked):
        if not isinstance(item, str) or re.fullmatch(r"SHA256:[A-Za-z0-9+/]{43}", item) is None:
            raise ValueError("invalid reviewer key revocation list")
        revoked_values.append(item)
    if revoked_values != sorted(set(revoked_values)):
        raise ValueError("invalid reviewer key revocation list")
    current = _signer_fingerprints(reviewer_signers, principal)
    if current.intersection(revoked_values):
        raise ValueError("revoked reviewer key remains authorized")
    return value


def _load_trusted_policy() -> tuple[dict[str, object], bytes]:
    try:
        with _trusted_directory() as root:
            payload = _trusted_file(root, "policy.json")
            signature = _trusted_file(root, "policy.sig")
            root_signers = _trusted_file(root, "root.allowed_signers")
            reviewer_signers = _trusted_file(root, "reviewer.allowed_signers")
        _signer_fingerprints(root_signers, TRUST_POLICY_PRINCIPAL)
        _verify_ssh_signature(
            payload, signature, root_signers, TRUST_POLICY_PRINCIPAL, TRUST_POLICY_NAMESPACE
        )
        return _validate_trust_policy(payload, reviewer_signers), reviewer_signers
    except (OSError, ValueError, json.JSONDecodeError):
        raise ValueError("trusted protected-execution policy is unavailable or invalid") from None


def _validate_source_receipt(
    payload: bytes, value: dict[str, object], policy: Mapping[str, object]
) -> None:
    if canonical_bytes(value) != payload or set(value) != {
        "schema_id",
        "schema_version",
        "status",
        "qualification_status",
        "source_revision",
        "authority_sha256",
        "inputs",
        "scan",
        "normalized_phases",
        "adapter_package",
        "authentication",
    }:
        raise ValueError("invalid source-preflight receipt shape")
    if (
        value.get("schema_id") != SCHEMA
        or value.get("schema_version") != VERSION
        or value.get("status") != "SOURCE_PREFLIGHT"
        or value.get("qualification_status") != "NOT_QUALIFIED"
        or value.get("source_revision") != REVISION
        or value.get("authority_sha256") != MANIFEST_SHA256
        or value.get("authentication") != "DETACHED_SSH_SIGNATURE_REQUIRED"
    ):
        raise ValueError("receipt is not an unqualified v2 source preflight")
    inventory = installed_adapter_inventory()
    if value.get("adapter_package") != inventory or _inventory_digest(inventory) != policy.get(
        "adapter_inventory_sha256"
    ):
        raise ValueError("source receipt does not bind the reviewed adapter inventory")

    manifest = _authority()
    records = _records(manifest)
    raw_inputs = value.get("inputs")
    if not isinstance(raw_inputs, list):
        raise ValueError("source receipt does not cover the pinned source inventory")
    input_rows = cast(list[object], raw_inputs)
    if len(input_rows) != len(records):
        raise ValueError("source receipt does not cover the pinned source inventory")
    by_path: dict[str, dict[str, object]] = {}
    for record, raw in zip(records, input_rows, strict=True):
        row = _object(raw)
        path = str(record["repository_path"])
        is_lfs = record["identity_type"] == "git_lfs_pointer"
        expected_size = record["lfs_payload_size"] if is_lfs else record["byte_size"]
        sha256 = _hash(row.get("sha256"), "source digest")
        size = row.get("bytes")
        if (
            set(row) != {"path", "bytes", "sha256", "git_blob_sha"}
            or row.get("path") != path
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size != expected_size
            or row.get("git_blob_sha") != record["git_blob_sha"]
            or (is_lfs and sha256 != record["lfs_oid_sha256"])
            or (record.get("raw_sha256") is not None and sha256 != record["raw_sha256"])
        ):
            raise ValueError("source receipt differs from the pinned 81-file authority")
        by_path[path] = row

    selected = cast(list[int], manifest["selected_source_matches"])
    scans = value.get("scan")
    if not isinstance(scans, list):
        raise ValueError("source receipt has incomplete global scan coverage")
    scan_rows = cast(list[object], scans)
    if len(scan_rows) != len(selected):
        raise ValueError("source receipt has incomplete global scan coverage")
    for match_id, raw in zip(selected, scan_rows, strict=True):
        row = _object(raw)
        prefix = f"data/matches/{match_id}/{match_id}"
        tracking = by_path[prefix + "_tracking_extrapolated.jsonl"]
        source_rows = row.get("source_rows")
        even_rows = row.get("even_source_rows")
        retained_rows = row.get("retained_rows")
        if (
            set(row)
            != {
                "match_id",
                "source_rows",
                "tracking_sha256",
                "even_source_rows",
                "even_frame_ids_sha256",
                "retained_rows",
                "retained_sha256",
            }
            or type(row.get("match_id")) is not int
            or row.get("match_id") != match_id
            or isinstance(source_rows, bool)
            or not isinstance(source_rows, int)
            or source_rows < 1
            or isinstance(even_rows, bool)
            or not isinstance(even_rows, int)
            or not 1 <= even_rows <= source_rows
            or isinstance(retained_rows, bool)
            or not isinstance(retained_rows, int)
            or retained_rows != even_rows
            or row.get("tracking_sha256") != tracking["sha256"]
        ):
            raise ValueError("source receipt global scan is incomplete or inconsistent")
        _hash(row.get("even_frame_ids_sha256"), "retained frame identity digest")
        _hash(row.get("retained_sha256"), "retained sample digest")

    normalized = value.get("normalized_phases")
    if not isinstance(normalized, list):
        raise ValueError("source receipt has incomplete phase normalization")
    normalized_rows = cast(list[object], normalized)
    if len(normalized_rows) != len(selected):
        raise ValueError("source receipt has incomplete phase normalization")
    for match_id, raw in zip(selected, normalized_rows, strict=True):
        row = _object(raw)
        prefix = f"data/matches/{match_id}/{match_id}"
        expected = {
            "path": f"phases-{match_id}.json",
            "source_sha256": by_path[prefix + "_phases_of_play.csv"]["sha256"],
            "metadata_sha256": by_path[prefix + "_match.json"]["sha256"],
        }
        if set(row) != {"path", "sha256", "source_sha256", "metadata_sha256"} or any(
            row.get(key) != item for key, item in expected.items()
        ):
            raise ValueError("source receipt phase lineage differs from the pinned inputs")
        _hash(row.get("sha256"), "normalized phase digest")


def authenticate_receipt(receipt: bytes, signature: bytes) -> dict[str, object]:
    """Authenticate against the root-owned policy; no trust pin comes from the caller."""
    if len(receipt) > MAX_DOCUMENT or len(signature) > MAX_DOCUMENT:
        raise ValueError("oversized protected receipt or signature")
    policy, reviewer_signers = _load_trusted_policy()
    reviewer = _object(policy["reviewer"])
    _verify_ssh_signature(
        receipt,
        signature,
        reviewer_signers,
        cast(str, reviewer["principal"]),
        cast(str, reviewer["namespace"]),
    )
    value = _object(_json(receipt))
    _validate_source_receipt(receipt, value, policy)
    return value


def verify_source_snapshot(source: Path, receipt_directory: Path) -> None:
    """Reauthenticate and recheck the complete snapshot immediately before a later run."""
    try:
        with private_directory(source) as root, private_directory(receipt_directory) as output:
            source_info, output_info = os.fstat(root), os.fstat(output)
            if (
                source == receipt_directory
                or source in receipt_directory.parents
                or receipt_directory in source.parents
                or (source_info.st_dev, source_info.st_ino) in _ancestor_identities(output)
                or (output_info.st_dev, output_info.st_ino) in _ancestor_identities(root)
            ):
                raise ValueError("overlapping protected roots")
            receipt = _document(root=output, path="source-preflight.json")
            signature = _document(root=output, path="source-preflight.sig")
            value = authenticate_receipt(receipt, signature)
            manifest = _authority()
            records = _records(manifest)
            inventory = _verify_sources(root, records)
            if inventory != value["inputs"]:
                raise ValueError("source inventory changed")
            scan = _scan(root, manifest)
            if scan != value["scan"]:
                raise ValueError("source-wide scan changed")
            expected = {str(row["path"]): str(row["sha256"]) for row in inventory}
            expected_phases: list[dict[str, str]] = []
            for match_id in cast(list[int], manifest["selected_source_matches"]):
                prefix = f"data/matches/{match_id}/{match_id}"
                metadata = _document(root, prefix + "_match.json")
                csv_bytes = _document(root, prefix + "_phases_of_play.csv")
                if (
                    hashlib.sha256(metadata).hexdigest() != expected[prefix + "_match.json"]
                    or hashlib.sha256(csv_bytes).hexdigest()
                    != expected[prefix + "_phases_of_play.csv"]
                ):
                    raise ValueError("phase source changed")
                phases = normalize_phases(csv_bytes, _object(_json(metadata)))
                name = f"phases-{match_id}.json"
                expected_phases.append(
                    {
                        "path": name,
                        "sha256": hashlib.sha256(phases).hexdigest(),
                        "source_sha256": hashlib.sha256(csv_bytes).hexdigest(),
                        "metadata_sha256": hashlib.sha256(metadata).hexdigest(),
                    }
                )
                if _document(output, name) != phases:
                    raise ValueError("normalized phase snapshot changed")
            if expected_phases != value["normalized_phases"] or (
                _verify_sources(root, records) != inventory
            ):
                raise ValueError("protected source snapshot changed")
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        raise ValueError(
            "INCOMPLETE: authenticated protected source snapshot changed or is invalid"
        ) from None
