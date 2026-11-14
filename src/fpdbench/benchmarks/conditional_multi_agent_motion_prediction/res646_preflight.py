# pyright: reportPrivateUsage=false
"""Non-consuming research admission metadata checks; never opens source rows or models."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shlex
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from . import res645_paths as paths
from . import res645_source_stream as source
from .empirical_experiment_plan import protocol_split_v2

ADMISSION_SHA256 = "a8c82bfa09ac792d6c4ae779d4b28158c33ed3c2500f8548f3e94d48197f4fd1"
CONSUMED_SCOPE = "d359751e969767f30ed6e90c65b13d0eec49f11c9e33e1d2319b19530d28f2e0"


def _validate_admission(document: object, expected_sha256: str) -> dict[str, int]:
    if not isinstance(document, dict):
        raise ValueError("admission must be an object")
    document = cast(dict[str, Any], document)
    encoded = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()
    if hashlib.sha256(encoded).hexdigest() != expected_sha256:
        raise ValueError("research admission identity differs")
    if (
        document.get("status") != "RESEARCH_RECONCILED"
        or document.get("protected_status") != "NOT_QUALIFIED"
        or document.get("source_release_hash")
        != "e92c417b7640b27399451134ee3fce4b1961b0c0dfc2e01175a8f3c906a9ae07"
        or document.get("source_population_hash")
        != "e9054b7ddc2dfeff4dd8425ea61a23ed0b326076a08899e47502484228fdbdf4"
    ):
        raise ValueError("research admission provenance differs")
    roles = cast(dict[str, list[str]], protocol_split_v2()["roles"])
    raw_matches: object = document.get("per_match")
    if not isinstance(raw_matches, dict):
        raise ValueError("research admission match inventory differs")
    matches = cast(dict[str, Any], raw_matches)
    if set(matches) != {mid for members in roles.values() for mid in members}:
        raise ValueError("research admission match inventory differs")
    for role, members in roles.items():
        if any(
            not isinstance(matches[mid], dict) or matches[mid].get("role") != role
            for mid in members
        ):
            raise ValueError("research admission match role differs")
    counts: dict[str, int] = {}
    for mid in roles["evaluation"]:
        match_counts: object = matches[mid].get("counts")
        if not isinstance(match_counts, dict):
            raise ValueError("evaluation scoreable-window count missing")
        count: object = cast(dict[str, object], match_counts).get("scoreable_windows")
        if type(count) is not int or count <= 0:
            raise ValueError("evaluation scoreable-window count missing")
        counts[mid] = count
    return counts


def verify_admission(path: Path) -> dict[str, int]:
    """Verify the pinned admission and declared evaluation counts without reading truth."""
    raw = _read_admission(path)
    return _validate_admission(source.parse_json(raw), ADMISSION_SHA256)


def _private_fd(path: Path, *, directory: bool = False, identity_only: bool = False) -> int:
    if (
        not path.is_absolute()
        or ".." in path.parts
        or any(part in str(path).lower() for part in ("res594", "heldout", "held-out"))
    ):
        raise PermissionError("unsafe private metadata path")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in path.parts[1:-1]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd
            )
            os.close(fd)
            fd = child
        parent = os.fstat(fd)
        if parent.st_uid != os.geteuid() or parent.st_mode & 0o022:
            raise PermissionError("private metadata parent must be owner-controlled")
        flags = os.O_PATH if identity_only else os.O_RDONLY | os.O_NONBLOCK
        if directory:
            flags |= os.O_DIRECTORY
        child = os.open(path.name, flags | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
    finally:
        os.close(fd)
    return child


def _read_admission(path: Path, *, admission_only: bool = True) -> bytes:
    if admission_only and path.name != "research-admission.json":
        raise PermissionError("unsafe research admission path")
    with os.fdopen(_private_fd(path), "rb") as stream:
        before = os.fstat(stream.fileno())
        paths.check_regular(before, max_bytes=16 * 1024 * 1024, require_private=True)
        data = stream.read(16 * 1024 * 1024 + 1)
        after = os.fstat(stream.fileno())
    if len(data) != before.st_size or paths.stat_key(before) != paths.stat_key(after):
        raise ValueError("research admission changed while reading")
    return data


def proposed_scope(identities: dict[str, str]) -> str:
    """Hash prospective bindings only; this cannot authorize or reserve a campaign."""
    required = {
        "source_sha256",
        "scorer_sha256",
        "verifier_sha256",
        "runtime_sha256",
        "ledger_sha256",
        "output_sha256",
        "independent_report_sha256",
    }
    if set(identities) != required or any(
        re.fullmatch(r"[0-9a-f]{64}", value) is None or value == CONSUMED_SCOPE
        for value in identities.values()
    ):
        raise ValueError("incomplete or forbidden scope bindings")
    if identities["ledger_sha256"] == identities["output_sha256"]:
        raise ValueError("ledger and output identities must differ")
    body = {
        "study": "fpdbench.public-skillcorner-post-failure-descriptive-heldout/1.0.0",
        "protocol_sha256": "ac931391ecb0afcb68974e1765f65fbff17071ade2bcaab93bdadd22f84a0305",
        "manifest_sha256": "770f1d9bbca3020237992181a56e4f5be4adaae7aab07f5f1313aa699d8693e0",
        "admission_sha256": ADMISSION_SHA256,
        "matches": ["1874553", "1925299", "2006229", "2010085"],
        "cpu_seconds": 14400,
        "wall_seconds": 21600,
        "rss_bytes": 2147483648,
        "disk_bytes": 2147483648,
        "identities": identities,
    }
    data = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    digest = hashlib.sha256(data).hexdigest()
    if digest == CONSUMED_SCOPE:
        raise ValueError("historical scope is permanently forbidden")
    return digest


TRUST_DIRECTORY = Path("/etc/fpdbench/protected-executor")
TRUST_FILES = ("res646-owner-signers", "res646-ledger-key")


def production_trust_status() -> dict[str, Any]:
    """Existence-only probe of the protected trust files; never reads key material."""
    present = {name: (TRUST_DIRECTORY / name).is_file() for name in TRUST_FILES}
    return {
        "status": "PROVISIONED_UNVERIFIED"
        if all(present.values())
        else "PRODUCTION_TRUST_KEY_NOT_YET_PROVISIONED",
        "files_present": present,
        "policy": "real execution fails closed until both are provisioned and verified (Gate 6)",
    }


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _metadata(path: Path) -> bytes:
    # The same no-follow/private reader as admission; metadata names are scope-bound below.
    return _read_admission(path, admission_only=False)


def _directory(path: Path) -> dict[str, int | str]:
    # Opening a directory reads no evaluation rows or checkpoint bytes.
    fd = _private_fd(path, directory=True)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise PermissionError("directory must be owner-private")
        return {
            "path": str(path),
            "device": info.st_dev,
            "inode": info.st_ino,
            "uid": info.st_uid,
            "mode": info.st_mode,
        }
    finally:
        os.close(fd)


def _file_identity(path: Path) -> dict[str, int]:
    # O_PATH inspects the inode without opening file contents (including tensors/trajectories).
    fd = _private_fd(path, identity_only=True)
    try:
        info = os.fstat(fd)
        paths.check_regular(info, max_bytes=8 * 1024**3, require_private=True)
        return dict(
            zip(
                ("device", "inode", "size", "mtime_ns", "ctime_ns"),
                paths.stat_key(info),
                strict=True,
            )
        )
    finally:
        os.close(fd)


def resource_observations(ledger: Path, output: Path) -> dict[str, Any]:
    """Observe this process's effective cgroup hierarchy and actual target filesystems."""
    from .res645_evidence import CgroupEvidence

    provider = CgroupEvidence()
    snapshot = provider.snapshot(os.getpid())
    # Read every ancestor: a child reporting 'max' cannot override its parent's limit.
    location = provider.root / provider._relative(os.getpid()).lstrip("/")
    if not snapshot["available"]:
        raise ValueError("actual cgroup observations unavailable")
    memory: list[int] = []
    cpus: list[float] = []
    hierarchy: list[dict[str, Any]] = []
    for parent in (location, *location.parents):
        if not parent.is_relative_to(Path("/sys/fs/cgroup")):
            break
        row: dict[str, Any] = {"path": str(parent)}
        for name in ("memory.max", "cpu.max"):
            path = parent / name
            if not path.is_file():
                continue
            value = path.read_text().strip()
            row[name] = value
            if name == "memory.max" and value != "max":
                memory.append(int(value))
            elif name == "cpu.max" and not value.startswith("max"):
                quota, period = map(int, value.split())
                cpus.append(quota / period)
        hierarchy.append(row)
    if not any("memory.max" in r and "cpu.max" in r for r in hierarchy):
        raise ValueError("actual cgroup CPU/memory limits unavailable")
    filesystems = {}
    for name, path in (("ledger", ledger), ("output", output)):
        stat = os.statvfs(path)
        filesystems[name] = {
            "device": path.stat().st_dev,
            "available_bytes": stat.f_bavail * stat.f_frsize,
            "available_inodes": stat.f_favail,
            "read_only": bool(stat.f_flag & os.ST_RDONLY),
        }
    return {
        "mountinfo_sha256": hashlib.sha256(Path("/proc/self/mountinfo").read_bytes()).hexdigest(),
        "cgroup": snapshot,
        "hierarchy": hierarchy,
        "memory_limit_bytes": min(memory) if memory else None,
        "cpu_capacity": min([float(len(os.sched_getaffinity(0))), *cpus]),
        "filesystems": filesystems,
    }


def _qualify(values: dict[str, str], prior: bytes) -> dict[str, Any]:
    from . import res635_post_failure_evaluation as scorer
    from . import res645_checkpoints as ck
    from . import res645_pipeline as pipeline

    evidence = json.loads(prior)
    if evidence.get("schema") != "fpdbench.res646.gate5-evidence/1":
        raise ValueError(
            "incomplete independent evidence: structured metadata attestation required"
        )
    scope = evidence["read_scope"]
    if (
        values["GATE5_READ_SCOPE"] != _digest(scope)
        or scope["policy"] != "metadata-only-no-source-or-model-bytes"
        or scope["paths"] != {k: v for k, v in values.items() if k != "GATE5_READ_SCOPE"}
    ):
        raise ValueError("configured paths differ from independently declared read scope")
    for name in ("evidence_id", "verification_method", "verified_at_utc"):
        if not isinstance(evidence.get(name), str) or not evidence[name]:
            raise ValueError("incomplete independent evidence identifiers")
    provenance = pipeline.provenance([], "")
    ck.frozen_manifest()
    if (
        evidence["protocol_sha256"] != scorer.PROTOCOL_SHA256
        or evidence["manifest_sha256"] != ck.FROZEN_MANIFEST_SHA256
        or evidence["admission_sha256"] != ADMISSION_SHA256
    ):
        raise ValueError("frozen protocol, manifest or admission identity differs")
    code = provenance["code_sha256"]
    verifier = {k: code[k] for k in ("res645_independent.py", "res635_verification.py")}
    if evidence["code_sha256"] != code:
        raise ValueError("scorer or verifier code identity differs")
    runtime = provenance["runtime"]
    if (runtime["python"], runtime["numpy"], runtime["torch"]) != ("3.12.8", "2.2.4", "2.6.0+cpu"):
        raise ValueError("invalid execution runtime")
    if evidence["runtime"] != runtime:
        raise ValueError("runtime evidence differs")
    if (
        Path(values["SOURCE_INVENTORY"]).name != "source-inventory.json"
        or Path(values["RESEARCH_ADMISSION"]).name != "research-admission.json"
        or Path(scope["resource_report"]).suffix != ".json"
        or Path(scope["independent_source"]).name != "independent-source.json"
    ):
        raise ValueError("configured metadata paths have unexpected names")
    verified_at = datetime.fromisoformat(evidence["verified_at_utc"].replace("Z", "+00:00"))
    if verified_at.tzinfo is None or not timedelta(0) <= datetime.now(
        UTC
    ) - verified_at < timedelta(days=1):
        raise ValueError("independent resource/quota evidence is stale or future-dated")
    admission = json.loads(_metadata(Path(values["RESEARCH_ADMISSION"])))
    counts = _validate_admission(admission, ADMISSION_SHA256)
    inventory_bytes = _metadata(Path(values["SOURCE_INVENTORY"]))
    inventory = json.loads(inventory_bytes)
    inventory_sha = hashlib.sha256(inventory_bytes).hexdigest()
    if (
        inventory_sha != evidence["source_inventory_sha256"]
        or inventory_sha != admission["source_inventory_sha256"]
    ):
        raise ValueError("wrong source inventory")
    independent_bytes = _metadata(Path(scope["independent_source"]))
    if hashlib.sha256(independent_bytes).hexdigest() != admission["independent_source_sha256"]:
        raise ValueError("independent source metadata differs from frozen admission")
    independent_source = json.loads(independent_bytes)
    independent_files = independent_source["source_files"]
    expected_readback = {r["path"]: (r["bytes"], r["sha256"]) for r in inventory}
    observed_readback = {r["path"]: (r["bytes"], r["sha256"]) for r in independent_files}
    if (
        len(independent_files) != 81
        or len(observed_readback) != 81
        or observed_readback != expected_readback
    ):
        raise ValueError("independent source inventory differs")
    normalization = {str(r["match_id"]): r for r in independent_source["normalization_receipts"]}
    checked: dict[str, Any] = {}
    entries = evidence["files"]
    if len(entries) != 117 or len({r["path"] for r in entries}) != 117:
        raise ValueError("incomplete independent evidence: 81+18+18 unique files required")
    checkpoint_dir = Path(values["CHECKPOINT_DIRECTORY"])
    receipt_dir = Path(values["FIT_RECEIPTS_DIRECTORY"])

    def names_in(directory: Path) -> list[str]:
        fd = _private_fd(directory, directory=True)
        try:
            return sorted(os.listdir(fd))
        finally:
            os.close(fd)

    checkpoint_names = names_in(checkpoint_dir)
    receipt_names = names_in(receipt_dir)
    checkpoint_files, receipt_files = ck.artifact_file_maps(
        ck.frozen_manifest(), checkpoint_names, receipt_names
    )
    expected_models = {
        str(checkpoint_dir / filename): digest for digest, filename in checkpoint_files.items()
    }
    expected_receipts = {
        str(receipt_dir / filename): digest for digest, filename in receipt_files.items()
    }
    # Inventory is metadata only; prior independently checked byte hashes stay bound to stat IDs.
    expected_sources = {str(Path(scope["source_root"]) / r["path"]): r["sha256"] for r in inventory}
    if len(expected_sources) != 81:
        raise ValueError("wrong source inventory: 81 files required")
    expected = {**expected_sources, **expected_models, **expected_receipts}
    if len(expected) != 117 or {r["path"]: r["sha256"] for r in entries} != expected:
        raise ValueError("independent file evidence differs from frozen inventory")
    identities: list[tuple[int, int]] = []
    observed_stat: dict[str, dict[str, int]] = {}
    for entry in entries:
        identity = _file_identity(Path(entry["path"]))
        recorded = entry.get("identity")
        if recorded is not None and identity != recorded:
            raise ValueError("filesystem identity differs from previously recorded stat")
        observed_stat[entry["path"]] = identity
        identities.append((identity["device"], identity["inode"]))
    if len(set(identities)) != 117:
        raise ValueError("aliased input identities")
    if evidence["fit_receipt_bindings_verified"] is not True:
        raise ValueError("incomplete independent fit receipt verification")
    matches = evidence["matches"]
    if matches != scope["matches"] or [m["match_id"] for m in matches] != list(counts):
        raise ValueError("intended scoring matches differ from approved scope or admission")
    expected_scoring: dict[str, str] = {}
    originals = {r["path"]: r["sha256"] for r in inventory}
    for match in matches:
        mid = match["match_id"]
        if (
            set(match) != {"match_id", "directory", "locked_path", "eligible_windows", "sha256"}
            or match["eligible_windows"] != counts[mid]
            or set(match["sha256"])
            != {"metadata_sha256", "phases_sha256", "tracking_raw_sha256", "locked_sha256"}
        ):
            raise ValueError("incomplete intended scoring match binding")
        for key, raw_name in (
            ("metadata_sha256", "match.json"),
            ("tracking_raw_sha256", "tracking_extrapolated.jsonl"),
        ):
            if match["sha256"][key] != originals[f"data/matches/{mid}/{mid}_{raw_name}"]:
                raise ValueError("normalized scoring source differs from frozen source inventory")
        normalized = normalization[mid]
        if (
            match["sha256"]["phases_sha256"] != normalized["phases_sha256"]
            or match["sha256"]["metadata_sha256"] != normalized["metadata_sha256"]
            or normalized["raw_csv_sha256"]
            != originals[f"data/matches/{mid}/{mid}_phases_of_play.csv"]
        ):
            raise ValueError("normalized phases differ from frozen independent source evidence")
        lock_hash = match["sha256"]["locked_sha256"]
        if (
            admission["artifacts"][mid]["producer_sha256"] != lock_hash
            or admission["artifacts"][mid]["verifier_sha256"] != lock_hash
        ):
            raise ValueError("scoring population lock differs from frozen admission")
        directory = Path(match["directory"])
        checked[f"SOURCE_{mid}"] = _directory(directory)
        checked[f"LOCK_{mid}"] = _directory(Path(match["locked_path"]).parent)
        expected_scoring.update(
            {
                str(directory / name): match["sha256"][key]
                for name, key in (
                    ("metadata.json", "metadata_sha256"),
                    ("phases.json", "phases_sha256"),
                    ("tracking.jsonl", "tracking_raw_sha256"),
                )
            }
        )
        expected_scoring[match["locked_path"]] = lock_hash
    if any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in expected_scoring.values()):
        raise ValueError("scoring input byte identity must be SHA-256")
    scoring_files = evidence["scoring_files"]
    if (
        len(expected_scoring) != 16
        or len(scoring_files) != 16
        or {r["path"]: r["sha256"] for r in scoring_files} != expected_scoring
    ):
        raise ValueError("incomplete independent scoring input/lock evidence")
    for entry in scoring_files:
        identity = _file_identity(Path(entry["path"]))
        recorded = entry.get("identity")
        if recorded is not None and identity != recorded:
            raise ValueError("scoring input identity differs from previously recorded stat")
        observed_stat[entry["path"]] = identity
        identities.append((identity["device"], identity["inode"]))
    if len(set(identities)) != 133:
        raise ValueError("aliased scoring input identities")
    ledger, output = Path(values["LEDGER_ROOT"]), Path(values["OUTPUT_DIRECTORY"])
    for name, expected_files in (
        ("CHECKPOINT_DIRECTORY", expected_models),
        ("FIT_RECEIPTS_DIRECTORY", expected_receipts),
    ):
        directory = Path(values[name])
        checked[name] = _directory(directory)
        fd = _private_fd(directory, directory=True)
        try:
            names = sorted(os.listdir(fd))
            selected = {Path(name).name for name in expected_files}
            if not selected.issubset(names):
                raise ValueError("selected frozen artifact missing")
            if name == "CHECKPOINT_DIRECTORY" and set(names) != selected:
                raise ValueError("unexpected checkpoint files")
            if name == "FIT_RECEIPTS_DIRECTORY" and any(
                (
                    entry.startswith("fit-receipt-")
                    or re.fullmatch(r"[0-9a-f]{64}\.json", entry) is not None
                )
                and entry not in selected
                for entry in names
            ):
                raise ValueError("unexpected additional fit receipts")
        finally:
            os.close(fd)
    checked["LEDGER_ROOT"], checked["OUTPUT_DIRECTORY"] = _directory(ledger), _directory(output)
    if any(checked[name]["mode"] & 0o7777 != 0o700 for name in ("LEDGER_ROOT", "OUTPUT_DIRECTORY")):
        raise PermissionError("ledger/output must have executor-required owner mode 0700")
    if (
        ledger == output
        or ledger in output.parents
        or output in ledger.parents
        or (checked["LEDGER_ROOT"]["device"], checked["LEDGER_ROOT"]["inode"])
        == (checked["OUTPUT_DIRECTORY"]["device"], checked["OUTPUT_DIRECTORY"]["inode"])
    ):
        raise ValueError("ledger/output identity collision")
    for entry in [*entries, *scoring_files]:
        p = Path(entry["path"])
        if ledger == p or output == p or ledger in p.parents or output in p.parents:
            raise ValueError("ledger/output must be isolated from input evidence")
    for path in (ledger, output):
        fd = _private_fd(path, directory=True)
        try:
            if os.listdir(fd):
                raise ValueError("proposed ledger/output must be empty")
        finally:
            os.close(fd)
    resources = resource_observations(ledger, output)
    if resources["memory_limit_bytes"] is not None and resources["memory_limit_bytes"] < 2**31:
        raise ValueError("insufficient cgroup memory")
    quota_status: dict[str, str] = {}
    for name, observed in resources["filesystems"].items():
        if observed["read_only"]:
            raise ValueError("ledger/output filesystem is read-only")
        if observed["available_bytes"] < 2**31 or observed["available_inodes"] < 16:
            raise ValueError("insufficient target filesystem capacity")
        quotas = evidence.get("quotas", {})
        quota = quotas.get(name) if isinstance(quotas, dict) else None
        if quota is None:
            quota_status[name] = "QUOTA_UNKNOWN"
            continue
        if (
            not isinstance(quota, dict)
            or quota.get("device") != observed["device"]
            or quota.get("uid") != os.geteuid()
            or quota.get("mountinfo_sha256") != resources["mountinfo_sha256"]
            or not quota.get("evidence_id")
        ):
            raise ValueError("untrusted or mismatched filesystem quota evidence")
        status = quota.get("status", "QUOTA_VERIFIED_SUFFICIENT")
        if status == "NO_ENFORCED_QUOTA_VERIFIED":
            if quota.get("verified_absence") is not True or not quota.get("verification_method"):
                raise ValueError("missing independent evidence of unenforced quotas")
        elif status == "QUOTA_VERIFIED_SUFFICIENT":
            if type(quota.get("available_bytes")) is not int or quota["available_bytes"] < 2**31:
                raise ValueError("insufficient enforced filesystem quota")
        else:
            quota_status[name] = "QUOTA_UNKNOWN"
            continue
        quota_status[name] = status
    qualification_raw = _metadata(Path(scope["resource_report"]))
    if hashlib.sha256(qualification_raw).hexdigest() != evidence["resource_report_sha256"]:
        raise ValueError("synthetic resource report identity differs")
    qualification = json.loads(qualification_raw)
    if (
        qualification["code_sha256"] != code
        or qualification["runtime"] != runtime
        or qualification["synthetic_only"] is not True
    ):
        raise ValueError("incomplete final-code synthetic resource evidence")
    measurements = qualification["measurements"]
    if not measurements or any(r["records"] != 72 or r["windows"] <= 0 for r in measurements):
        raise ValueError("incomplete synthetic campaign measurements")
    row = max(measurements, key=lambda r: r["windows"])
    windows = sum(counts.values())
    # The frozen protocol imposes execution-time limits, not a 2x synthetic admission rule.
    # Keep a direct observation check and a baseline wall-feasibility check; disclose the
    # doubled synthetic sensitivity scenario without treating it as a proven upper bound.
    capacity = resources["cpu_capacity"]
    if type(capacity) not in (float, int) or not math.isfinite(capacity) or capacity <= 0:
        raise ValueError("invalid effective CPU capacity")
    measured = {
        "cpu_s": row["cpu_s"],
        "wall_s": row["wall_s"],
        "rss_bytes": row["combined_peak_rss_bytes"],
        "disk_bytes": row["transient_disk_bytes"],
    }
    ceilings = {"cpu_s": 14400, "wall_s": 21600, "rss_bytes": 2**31, "disk_bytes": 2**31}
    for key, ceiling in ceilings.items():
        value = measured[key]
        if type(value) not in (float, int) or not math.isfinite(value) or not 0 < value <= ceiling:
            raise ValueError("observed synthetic campaign exceeds frozen execution limits")
    linear_projection = {
        "cpu_s": measured["cpu_s"] * windows / row["windows"],
        "wall_s": max(measured["wall_s"], measured["cpu_s"] / capacity) * windows / row["windows"],
        "rss_bytes": measured["rss_bytes"],
        "disk_bytes": measured["disk_bytes"],
    }
    projection = {
        "cpu_s": 2 * linear_projection["cpu_s"],
        "wall_s": 2 * linear_projection["wall_s"],
        "rss_bytes": measured["rss_bytes"],
        "disk_bytes": measured["disk_bytes"],
    }
    if linear_projection["wall_s"] > ceilings["wall_s"]:
        raise ValueError(
            "measured-throughput wall projection incompatible with effective CPU quota"
        )
    campaign_configuration = {
        "schema": "fpdbench.res646.campaign/1",
        "namespace": "RES646-REAL-v1",
        "matches": matches,
        "checkpoint_directory": values["CHECKPOINT_DIRECTORY"],
        "receipt_directory": values["FIT_RECEIPTS_DIRECTORY"],
        "checkpoint_files": checkpoint_files,
        "receipt_files": receipt_files,
        "admission": values["RESEARCH_ADMISSION"],
        "ledger_root": str(ledger),
        "output": str(output),
        "independent_report_sha256": hashlib.sha256(prior).hexdigest(),
    }
    bindings = {
        "source_sha256": scorer.digest({"config": campaign_configuration, "fixture_sha256": None}),
        "scorer_sha256": _digest(code),
        "verifier_sha256": _digest(verifier),
        "runtime_sha256": _digest(runtime),
        "ledger_sha256": _digest(checked["LEDGER_ROOT"]),
        "output_sha256": _digest(checked["OUTPUT_DIRECTORY"]),
        "independent_report_sha256": hashlib.sha256(prior).hexdigest(),
    }
    return {
        "checked_directories": checked,
        "campaign_configuration": campaign_configuration,
        "identities": bindings,
        "proposed_scope_sha256": proposed_scope(bindings),
        "resources": resources,
        "resource_report_sha256": evidence["resource_report_sha256"],
        "resource_linear_projection": linear_projection,
        "resource_sensitivity_scenario": projection,
        "resource_scenario_exceeds_frozen_budget": any(
            projection[name] > limit for name, limit in ceilings.items()
        ),
        "resource_scenario_policy": (
            "2x linear synthetic cost is a disclosure-only sensitivity, not a frozen admission gate"
        ),
        "evaluation_role_counts": counts,
        "independent_evidence": evidence,
        "current_file_stat_sha256": _digest(observed_stat),
        "historical_byte_continuity": (
            "UNVERIFIED_PENDING_AUTHORIZED_READ: current stat is not retrospective byte proof"
        ),
        "quota_status": quota_status,
        "limitations": [
            "Past SHA-256 readbacks establish expected contents at the time of readback; "
            "current stat observations do not retroactively prove unchanged bytes.",
            "Current bytes must match all frozen digests at the separately authorized "
            "Gate 6 read boundary, before the first learned forward pass.",
            "Real-source execution time remains unverified; the 2x scenario is a warning.",
            "Unknown quota status must be explicitly considered by the owner before Gate 6; "
            "the executor's frozen disk/RSS limits remain mandatory.",
        ],
    }


def _private_preflight(owner_config: Path, evidence: Path) -> dict[str, Any]:
    """Reconcile existing owner-local evidence without source/model opens or reservation.

    Old textual readback evidence is retained as evidence, not promoted to a new attestation.
    Missing local bindings and target quotas remain blockers regardless of old hash checks.
    """
    raw = _metadata(owner_config)
    prior = _metadata(evidence)
    names = {
        "SOURCE_INVENTORY",
        "CHECKPOINT_DIRECTORY",
        "FIT_RECEIPTS_DIRECTORY",
        "RESEARCH_ADMISSION",
        "LEDGER_ROOT",
        "OUTPUT_DIRECTORY",
        "GATE5_READ_SCOPE",
    }
    values: dict[str, str] = {}
    for line in raw.decode().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key not in names or key in values:
            raise ValueError("invalid or duplicate owner-local configuration field")
        parsed = shlex.split(value, comments=True)
        if len(parsed) > 1:
            raise ValueError("owner-local values must be single literal paths or scope IDs")
        values[key] = parsed[0] if parsed else ""
    missing = sorted(name for name in names if not values.get(name))
    result: dict[str, Any] = {
        "schema": "fpdbench.res646.nonconsuming-preflight/2",
        "status": "MISSING_OWNER_LOCAL_CONFIG" if missing else "RES646_GATE5_BLOCKED",
        "missing_fields": missing,
        "prior_evidence_sha256": hashlib.sha256(prior).hexdigest(),
        "prior_evidence_bytes": len(prior),
        "prior_evidence_policy": "preserved; no repeated source or checkpoint byte readback",
        "protocol_sha256": "ac931391ecb0afcb68974e1765f65fbff17071ade2bcaab93bdadd22f84a0305",
        "manifest_sha256": "770f1d9bbca3020237992181a56e4f5be4adaae7aab07f5f1313aa699d8693e0",
        "admission_sha256": ADMISSION_SHA256,
        "production_trust": production_trust_status(),
        "source_rows_opened": False,
        "models_loaded": False,
        "scope_consumed": False,
        "target_resource_qualification": "not established by prior host free-space observations",
        "separate_owner_go": "not requested or provisioned",
        "remaining_gate6_conditions": [
            "Independent review and acceptance of this Gate 5 evidence.",
            "Owner confirms target execution host, quotas and resource assumptions.",
            "Protected production signer trust and ledger integrity key provisioning.",
            "Separate signed, unexpired owner GO bound to exact scope and code identities.",
            "Fresh single-use reservation and supervised worker capability.",
        ],
        "independent_review_accepted": False,
        "blockers": [],
    }
    if not missing:
        try:
            result.update(_qualify(values, prior))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            # Detailed diagnostics stay in the owner-private report, never the CLI log.
            result["blockers"] = [f"{type(exc).__name__}: {exc}"]
        else:
            result["status"] = "RES646_GATE5_READY_FOR_INDEPENDENT_REVIEW"
            result["target_resource_qualification"] = (
                "observed metadata; projections require review"
            )
    return result


def private_preflight(owner_config: Path, evidence: Path) -> dict[str, Any]:
    """Return a fail-closed disposition even for malformed or aliased local metadata."""
    try:
        return _private_preflight(owner_config, evidence)
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
        return {
            "schema": "fpdbench.res646.nonconsuming-preflight/2",
            "status": "MISSING_OWNER_LOCAL_CONFIG"
            if not owner_config.exists()
            else "RES646_GATE5_BLOCKED",
            "missing_fields": [],
            "blockers": [f"{type(exc).__name__}: {exc}"],
            "source_rows_opened": False,
            "models_loaded": False,
            "scope_consumed": False,
            "independent_review_accepted": False,
            "production_trust": production_trust_status(),
            "remaining_gate6_conditions": [
                "Complete Gate 5 and independent review before provisioning or GO."
            ],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="RES646 metadata-only, non-consuming preflight")
    parser.add_argument("--owner-config", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = private_preflight(args.owner_config, args.evidence)
    from .res635_execution import atomic

    fd = _private_fd(args.report.parent, directory=True)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise PermissionError("report directory must be owner-private")
    finally:
        os.close(fd)
    atomic(args.report, result)
    print(json.dumps({"status": result["status"], "missing_fields": result["missing_fields"]}))
    return 0 if result["status"] == "RES646_GATE5_READY_FOR_INDEPENDENT_REVIEW" else 2


if __name__ == "__main__":
    raise SystemExit(main())
