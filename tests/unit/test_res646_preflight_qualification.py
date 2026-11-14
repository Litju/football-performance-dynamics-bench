"""Gate 5 qualification uses invented files and prior metadata evidence, never real weights."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shlex
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import res635_execution as e
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    res635_post_failure_evaluation as scorer,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import res645_checkpoints as ck
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    res645_pipeline as pipeline,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import res646_preflight as p


def write(path: Path, value: object) -> bytes:
    data = ck.canonical(value)
    path.write_bytes(data)
    path.chmod(0o600)
    return data


@dataclass
class LocalEvidence:
    config: Path
    prior: Path
    values: dict[str, str]
    document: dict[str, Any]
    resources: dict[str, Any]
    resource_report: Path

    def save(self, *, refresh_scope: bool = True) -> None:
        if refresh_scope:
            self.document["read_scope"]["paths"] = {
                key: value for key, value in self.values.items() if key != "GATE5_READ_SCOPE"
            }
            self.values["GATE5_READ_SCOPE"] = p._digest(self.document["read_scope"])
        self.config.write_text(
            "".join(f"{key}={shlex.quote(value)}\n" for key, value in self.values.items())
        )
        self.config.chmod(0o600)
        write(self.prior, self.document)

    def check(self) -> dict[str, Any]:
        return p.private_preflight(self.config, self.prior)


@pytest.fixture
def local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LocalEvidence:
    directories = {}
    for name in ("source", "checkpoints", "receipts", "ledger", "output"):
        path = tmp_path / name
        path.mkdir(mode=0o700)
        directories[name] = path
    entries = []
    inventory = []
    matches = []
    scoring_files = []
    normalization = []
    artifacts = {}
    roles = p.protocol_split_v2()["roles"]
    inputs, producer = tmp_path / "inputs", tmp_path / "producer"
    inputs.mkdir(mode=0o700)
    producer.mkdir(mode=0o700)
    for mid in roles["evaluation"]:
        raw_directory = directories["source"] / "data" / "matches" / mid
        raw_directory.mkdir(parents=True, mode=0o700)
        # Every ancestor is owner-controlled; the actual file parents are owner-private.
        directory = inputs / mid
        directory.mkdir(mode=0o700)
        hashes = {}
        for raw_name, normalized_name, key in (
            ("match.json", "metadata.json", "metadata_sha256"),
            ("phases_of_play.csv", "phases.json", "phases_sha256"),
            ("tracking_extrapolated.jsonl", "tracking.jsonl", "tracking_raw_sha256"),
        ):
            original = raw_directory / f"{mid}_{raw_name}"
            original_bytes = write(original, {"invented": f"{mid}/{raw_name}"})
            original_sha = hashlib.sha256(original_bytes).hexdigest()
            inventory.append(
                {
                    "path": str(original.relative_to(directories["source"])),
                    "bytes": len(original_bytes),
                    "sha256": original_sha,
                    "git_blob_sha": "b" * 40,
                }
            )
            entries.append(
                {
                    "path": str(original),
                    "sha256": original_sha,
                    "identity": p._file_identity(original),
                }
            )
            normalized = directory / normalized_name
            if key == "phases_sha256":
                normalized_bytes = write(normalized, {"invented_normalized_phases": mid})
                raw_csv_sha = original_sha
            else:
                normalized.write_bytes(original_bytes)
                normalized.chmod(0o600)
                normalized_bytes = original_bytes
            hashes[key] = hashlib.sha256(normalized_bytes).hexdigest()
            scoring_files.append(
                {
                    "path": str(normalized),
                    "sha256": hashes[key],
                    "identity": p._file_identity(normalized),
                }
            )
        locked = producer / f"{mid}.jsonl"
        hashes["locked_sha256"] = hashlib.sha256(write(locked, {"invented_lock": mid})).hexdigest()
        scoring_files.append(
            {
                "path": str(locked),
                "sha256": hashes["locked_sha256"],
                "identity": p._file_identity(locked),
            }
        )
        artifacts[mid] = {
            "producer_sha256": hashes["locked_sha256"],
            "verifier_sha256": hashes["locked_sha256"],
        }
        normalization.append(
            {
                "match_id": mid,
                "metadata_sha256": hashes["metadata_sha256"],
                "phases_sha256": hashes["phases_sha256"],
                "raw_csv_sha256": raw_csv_sha,
                "lineage_sha256": "c" * 64,
            }
        )
        matches.append(
            {
                "match_id": mid,
                "directory": str(directory),
                "locked_path": str(locked),
                "eligible_windows": 1000,
                "sha256": hashes,
            }
        )
    for index in range(69):
        path = directories["source"] / f"invented-{index}.bin"
        data = write(path, {"invented": index})
        sha = hashlib.sha256(data).hexdigest()
        inventory.append(
            {"path": path.name, "bytes": len(data), "sha256": sha, "git_blob_sha": "b" * 40}
        )
        entries.append({"path": str(path), "sha256": sha, "identity": p._file_identity(path)})
    inventory_path = tmp_path / "source-inventory.json"
    inventory_sha = hashlib.sha256(write(inventory_path, inventory)).hexdigest()
    independent_source = tmp_path / "independent-source.json"
    independent_sha = hashlib.sha256(
        write(
            independent_source,
            {
                "source_files": [
                    {key: row[key] for key in ("path", "bytes", "sha256")} for row in inventory
                ],
                "normalization_receipts": normalization,
            },
        )
    ).hexdigest()
    admission = {
        "status": "RESEARCH_RECONCILED",
        "protected_status": "NOT_QUALIFIED",
        "source_release_hash": "e92c417b7640b27399451134ee3fce4b1961b0c0dfc2e01175a8f3c906a9ae07",
        "source_population_hash": (
            "e9054b7ddc2dfeff4dd8425ea61a23ed0b326076a08899e47502484228fdbdf4"
        ),
        "source_inventory_sha256": inventory_sha,
        "independent_source_sha256": independent_sha,
        "artifacts": artifacts,
        "per_match": {
            match: {"role": role, "counts": {"scoreable_windows": 1000}}
            for role, members in roles.items()
            for match in members
        },
    }
    admission_path = tmp_path / "research-admission.json"
    admission_sha = hashlib.sha256(write(admission_path, admission)).hexdigest()
    monkeypatch.setattr(p, "ADMISSION_SHA256", admission_sha)
    for record in ck.frozen_manifest()["checkpoints"]:
        for directory, key, extension in (
            ("checkpoints", "checkpoint_sha256", "pt"),
            ("receipts", "receipt_sha256", "json"),
        ):
            path = directories[directory] / f"{record[key]}.{extension}"
            # Hash labels describe invented prior evidence; no real tensor bytes exist here.
            write(path, {"invented_prior_readback_fixture": record[key]})
            entries.append(
                {"path": str(path), "sha256": record[key], "identity": p._file_identity(path)}
            )
    provenance = pipeline.provenance([], "")
    provenance["runtime"].update(python="3.12.8", numpy="2.2.4", torch="2.6.0+cpu")
    # Invented qualification models the frozen runtime even when CI uses a newer patch version.
    monkeypatch.setattr(pipeline, "provenance", lambda *_: copy.deepcopy(provenance))
    resource_report = tmp_path / "synthetic-resource-report.json"
    report_bytes = write(
        resource_report,
        {
            "synthetic_only": True,
            "code_sha256": provenance["code_sha256"],
            "runtime": provenance["runtime"],
            "measurements": [
                {
                    "records": 72,
                    "windows": 800,
                    "cpu_s": 90,
                    "wall_s": 93,
                    "combined_peak_rss_bytes": 450000000,
                    "transient_disk_bytes": 200000,
                }
            ],
        },
    )
    values = {
        "SOURCE_INVENTORY": str(inventory_path),
        "CHECKPOINT_DIRECTORY": str(directories["checkpoints"]),
        "FIT_RECEIPTS_DIRECTORY": str(directories["receipts"]),
        "RESEARCH_ADMISSION": str(admission_path),
        "LEDGER_ROOT": str(directories["ledger"]),
        "OUTPUT_DIRECTORY": str(directories["output"]),
    }
    resources = {
        "memory_limit_bytes": 2**32,
        "mountinfo_sha256": "a" * 64,
        "cpu_capacity": 2,
        "filesystems": {
            name: {
                "device": directories[name].stat().st_dev,
                "available_bytes": 2**40,
                "available_inodes": 100,
                "read_only": False,
            }
            for name in ("ledger", "output")
        },
    }
    document = {
        "schema": "fpdbench.res646.gate5-evidence/1",
        "read_scope": {
            "policy": "metadata-only-no-source-or-model-bytes",
            "paths": values.copy(),
            "source_root": str(directories["source"]),
            "resource_report": str(resource_report),
            "independent_source": str(independent_source),
            "matches": copy.deepcopy(matches),
        },
        "evidence_id": "invented-independent-readback-001",
        "verification_method": "invented independent byte-readback fixture",
        "verified_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "protocol_sha256": scorer.PROTOCOL_SHA256,
        "manifest_sha256": ck.FROZEN_MANIFEST_SHA256,
        "admission_sha256": admission_sha,
        "code_sha256": provenance["code_sha256"],
        "runtime": provenance["runtime"],
        "source_inventory_sha256": inventory_sha,
        "files": entries,
        "scoring_files": scoring_files,
        "matches": matches,
        "fit_receipt_bindings_verified": True,
        "quotas": {
            name: {
                "device": directories[name].stat().st_dev,
                "evidence_id": f"invented-quota-{name}",
                "uid": os.geteuid(),
                "mountinfo_sha256": "a" * 64,
                "available_bytes": 2**40,
            }
            for name in ("ledger", "output")
        },
        "resource_report_sha256": hashlib.sha256(report_bytes).hexdigest(),
    }
    result = LocalEvidence(
        tmp_path / "res646.env",
        tmp_path / "independent-evidence.json",
        values,
        document,
        resources,
        resource_report,
    )
    result.save()
    monkeypatch.setattr(p, "resource_observations", lambda *_: copy.deepcopy(result.resources))
    return result


def test_doubled_cpu_sensitivity_is_disclosed_not_a_new_admission_gate(
    local: LocalEvidence,
) -> None:
    # Four invented matches x 1000 windows; 800-window observation fits the true
    # ceilings but the arbitrary 2x projection exceeds the 14,400-second CPU cap.
    report = json.loads(local.resource_report.read_bytes())
    report["measurements"][0]["cpu_s"] = 2160
    local.document["resource_report_sha256"] = hashlib.sha256(
        write(local.resource_report, report)
    ).hexdigest()
    local.save()
    result = local.check()
    assert result["status"] == "RES646_GATE5_READY_FOR_INDEPENDENT_REVIEW"
    assert result["resource_linear_projection"]["cpu_s"] == 10800
    assert result["resource_sensitivity_scenario"]["cpu_s"] == 21600
    assert result["resource_scenario_exceeds_frozen_budget"] is True
    assert result["scope_consumed"] is False


def test_complete_configuration_qualifies_without_input_bytes_or_scope_consumption(
    local: LocalEvidence,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    protected = {
        row["path"] for row in [*local.document["files"], *local.document["scoring_files"]]
    }
    original_open = os.open
    inspected = []

    def metadata_open(path: str | bytes | Path, flags: int, *args: Any, **kwargs: Any) -> int:
        # The final component is opened relative to its already checked parent descriptor.
        if str(path) in {Path(name).name for name in protected}:
            assert flags & os.O_PATH, "preflight attempted to open input contents"
            inspected.append(str(path))
        return original_open(path, flags, *args, **kwargs)

    loaded = Mock(side_effect=AssertionError("preflight deserialized tensors"))
    forward = Mock(side_effect=AssertionError("preflight ran model inference"))
    reserved = Mock(side_effect=AssertionError("preflight consumed a scope"))
    monkeypatch.setattr(os, "open", metadata_open)
    monkeypatch.setattr(ck.torch, "load", loaded)
    monkeypatch.setattr(ck.lds.PerTargetContextDeepSetsMLP, "forward", forward)
    monkeypatch.setattr(e, "reserve", reserved)
    first = local.check()
    second = local.check()
    assert first["status"] == "RES646_GATE5_READY_FOR_INDEPENDENT_REVIEW", first
    assert first["proposed_scope_sha256"] == second["proposed_scope_sha256"]
    assert len(first["evaluation_role_counts"]) == 4
    assert len(inspected) == 266
    assert first["independent_review_accepted"] is False
    assert first["remaining_gate6_conditions"]
    assert first["limitations"]
    assert not first["models_loaded"] and not first["scope_consumed"]
    assert not first["source_rows_opened"]
    assert list(Path(local.values["LEDGER_ROOT"]).iterdir()) == []
    assert list(Path(local.values["OUTPUT_DIRECTORY"]).iterdir()) == []
    loaded.assert_not_called()
    forward.assert_not_called()
    reserved.assert_not_called()


@pytest.mark.parametrize(
    "field",
    [
        "SOURCE_INVENTORY",
        "CHECKPOINT_DIRECTORY",
        "FIT_RECEIPTS_DIRECTORY",
        "RESEARCH_ADMISSION",
        "LEDGER_ROOT",
        "OUTPUT_DIRECTORY",
        "GATE5_READ_SCOPE",
    ],
)
def test_each_missing_field_is_reported(local: LocalEvidence, field: str) -> None:
    local.values[field] = ""
    local.save(refresh_scope=False)
    report = local.check()
    assert report["status"] == "MISSING_OWNER_LOCAL_CONFIG"
    assert report["missing_fields"] == [field]


@pytest.mark.parametrize(
    "field", ["SOURCE_INVENTORY", "RESEARCH_ADMISSION", "CHECKPOINT_DIRECTORY"]
)
def test_mismatched_paths_are_blocked(local: LocalEvidence, field: str) -> None:
    local.values[field] += "-unapproved"
    local.save(refresh_scope=False)
    report = local.check()
    assert report["status"] == "RES646_GATE5_BLOCKED"
    assert "read scope" in str(report["blockers"])


@pytest.mark.parametrize("alias", ["symlink", "hardlink", "directory-symlink"])
def test_input_aliases_are_blocked(local: LocalEvidence, alias: str, tmp_path: Path) -> None:
    path = Path(local.document["files"][0]["path"])
    if alias == "directory-symlink":
        source = path.parent
        renamed = tmp_path / "renamed-source"
        source.rename(renamed)
        source.symlink_to(renamed, target_is_directory=True)
    else:
        renamed = tmp_path / "invented-original"
        path.rename(renamed)
        path.symlink_to(renamed) if alias == "symlink" else os.link(renamed, path)
    assert local.check()["status"] == "RES646_GATE5_BLOCKED"


@pytest.mark.parametrize("target", ["input", "ledger", "output", "checkpoint-directory"])
def test_unsafe_permissions_are_blocked(local: LocalEvidence, target: str) -> None:
    path = {
        "input": Path(local.document["files"][0]["path"]),
        "ledger": Path(local.values["LEDGER_ROOT"]),
        "output": Path(local.values["OUTPUT_DIRECTORY"]),
        "checkpoint-directory": Path(local.values["CHECKPOINT_DIRECTORY"]),
    }[target]
    path.chmod(0o644 if target == "input" else 0o755)
    assert local.check()["status"] == "RES646_GATE5_BLOCKED"


@pytest.mark.parametrize(
    "identity", ["admission_sha256", "manifest_sha256", "source_inventory_sha256"]
)
def test_wrong_frozen_identity_is_blocked(local: LocalEvidence, identity: str) -> None:
    local.document[identity] = "0" * 64
    local.save()
    assert local.check()["status"] == "RES646_GATE5_BLOCKED"


def test_changed_admission_bytes_are_blocked(local: LocalEvidence) -> None:
    path = Path(local.values["RESEARCH_ADMISSION"])
    admission = json.loads(path.read_bytes())
    admission["protected_status"] = "QUALIFIED"
    write(path, admission)
    assert local.check()["status"] == "RES646_GATE5_BLOCKED"


@pytest.mark.parametrize("limit", ["memory", "quota", "disk", "inodes", "cpu"])
def test_insufficient_resources_are_blocked(local: LocalEvidence, limit: str) -> None:
    if limit == "memory":
        local.resources["memory_limit_bytes"] = 2**30
    elif limit == "quota":
        local.document["quotas"]["output"]["available_bytes"] = 2**30
        local.save()
    elif limit == "cpu":
        local.resources["cpu_capacity"] = 0.001
    else:
        name = "available_bytes" if limit == "disk" else "available_inodes"
        local.resources["filesystems"]["output"][name] = 1
    assert local.check()["status"] == "RES646_GATE5_BLOCKED"


def test_invalid_execution_runtime_is_blocked(
    local: LocalEvidence,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provenance = pipeline.provenance([], "")
    provenance["runtime"]["python"] = "3.12.9"
    monkeypatch.setattr(pipeline, "provenance", lambda *_: provenance)
    assert local.check()["status"] == "RES646_GATE5_BLOCKED"


def test_ledger_output_identity_collision_is_blocked(local: LocalEvidence) -> None:
    local.values["OUTPUT_DIRECTORY"] = local.values["LEDGER_ROOT"]
    local.save()
    report = local.check()
    assert report["status"] == "RES646_GATE5_BLOCKED"
    assert "collision" in str(report["blockers"])


@pytest.mark.parametrize("missing", ["file", "receipt-binding", "evidence-id", "resource-code"])
def test_incomplete_independent_evidence_is_blocked(local: LocalEvidence, missing: str) -> None:
    if missing == "file":
        local.document["files"].pop()
    elif missing == "receipt-binding":
        local.document["fit_receipt_bindings_verified"] = False
    elif missing == "evidence-id":
        local.document["evidence_id"] = ""
    else:
        report = json.loads(local.resource_report.read_bytes())
        report["code_sha256"] = {}
        data = write(local.resource_report, report)
        local.document["resource_report_sha256"] = hashlib.sha256(data).hexdigest()
    local.save()
    assert local.check()["status"] == "RES646_GATE5_BLOCKED"


def test_success_cli_exits_zero_and_writes_private_report(
    local: LocalEvidence,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    report = tmp_path / "gate5-report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "preflight",
            "--owner-config",
            str(local.config),
            "--evidence",
            str(local.prior),
            "--report",
            str(report),
        ],
    )
    assert p.main() == 0
    saved = json.loads(report.read_bytes())
    assert saved["status"] == "RES646_GATE5_READY_FOR_INDEPENDENT_REVIEW"
    assert report.stat().st_mode & 0o077 == 0
    assert str(tmp_path) not in capsys.readouterr().out


@pytest.mark.parametrize("target", ["ledger", "output", "input"])
def test_unsafe_ownership_is_blocked(
    local: LocalEvidence,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    path = Path(
        {
            "input": local.document["files"][0]["path"],
            "ledger": local.values["LEDGER_ROOT"],
            "output": local.values["OUTPUT_DIRECTORY"],
        }[target]
    )
    inode = path.stat().st_ino
    original = os.fstat

    def wrong_owner(fd: int) -> os.stat_result:
        result = original(fd)
        if result.st_ino == inode:
            parts = list(result)
            parts[4] = result.st_uid + 1
            return os.stat_result(parts)
        return result

    monkeypatch.setattr(os, "fstat", wrong_owner)
    assert local.check()["status"] == "RES646_GATE5_BLOCKED"


@pytest.mark.parametrize("field", ["uid", "mountinfo_sha256"])
def test_quota_evidence_must_belong_to_current_user_and_mount(
    local: LocalEvidence,
    field: str,
) -> None:
    local.document["quotas"]["output"][field] = -1 if field == "uid" else "f" * 64
    local.save()
    assert local.check()["status"] == "RES646_GATE5_BLOCKED"


@pytest.mark.parametrize("when", ["stale", "future"])
def test_resource_attestation_must_be_recent(local: LocalEvidence, when: str) -> None:
    from datetime import timedelta

    offset = timedelta(days=-2 if when == "stale" else 2)
    local.document["verified_at_utc"] = (datetime.now(UTC) + offset).isoformat()
    local.save()
    assert local.check()["status"] == "RES646_GATE5_BLOCKED"


@pytest.mark.parametrize(
    "field,value",
    [
        ("cpu_s", 2**31),
        ("wall_s", 2**31),
        ("combined_peak_rss_bytes", 2**31 + 1),
        ("transient_disk_bytes", 2**31 + 1),
    ],
)
def test_measurements_cannot_exceed_frozen_budgets(
    local: LocalEvidence,
    field: str,
    value: int,
) -> None:
    report = json.loads(local.resource_report.read_bytes())
    report["measurements"][0][field] = value
    local.document["resource_report_sha256"] = hashlib.sha256(
        write(local.resource_report, report)
    ).hexdigest()
    local.save()
    assert local.check()["status"] == "RES646_GATE5_BLOCKED"


@pytest.mark.parametrize("target", ["LEDGER_ROOT", "OUTPUT_DIRECTORY"])
def test_proposed_execution_directories_must_be_empty(local: LocalEvidence, target: str) -> None:
    write(Path(local.values[target]) / "unrelated-artifact.json", {"invented": True})
    assert local.check()["status"] == "RES646_GATE5_BLOCKED"


@pytest.mark.parametrize("kind", ["duplicate", "bad-quote", "config-symlink", "config-hardlink"])
def test_malformed_or_aliased_configuration_returns_blocked_report(
    local: LocalEvidence,
    kind: str,
    tmp_path: Path,
) -> None:
    if kind == "duplicate":
        with local.config.open("a") as stream:
            stream.write("SOURCE_INVENTORY=duplicate\n")
    elif kind == "bad-quote":
        local.config.write_text("SOURCE_INVENTORY='unterminated\n")
    else:
        original = tmp_path / "original-config.env"
        local.config.rename(original)
        if kind == "config-symlink":
            local.config.symlink_to(original)
        else:
            os.link(original, local.config)
    result = local.check()
    assert result["status"] == "RES646_GATE5_BLOCKED"
    assert result["scope_consumed"] is False


def test_blocked_cli_exits_two_without_leaking_private_paths(
    local: LocalEvidence,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    local.values["SOURCE_INVENTORY"] = ""
    local.save(refresh_scope=False)
    report = tmp_path / "blocked-report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "preflight",
            "--owner-config",
            str(local.config),
            "--evidence",
            str(local.prior),
            "--report",
            str(report),
        ],
    )
    assert p.main() == 2
    assert json.loads(report.read_bytes())["status"] == "MISSING_OWNER_LOCAL_CONFIG"
    assert str(tmp_path) not in capsys.readouterr().out


@pytest.mark.parametrize("value", [-1.0, 0.0, float("inf"), float("nan")])
def test_invalid_measurements_fail_closed(local: LocalEvidence, value: float) -> None:
    report = json.loads(local.resource_report.read_bytes())
    report["measurements"][0]["cpu_s"] = value
    data = json.dumps(report).encode()
    local.resource_report.write_bytes(data)
    local.document["resource_report_sha256"] = hashlib.sha256(data).hexdigest()
    local.save()
    assert local.check()["status"] == "RES646_GATE5_BLOCKED"


def test_resource_report_hash_mismatch_is_blocked(local: LocalEvidence) -> None:
    local.document["resource_report_sha256"] = "0" * 64
    local.save()
    assert local.check()["status"] == "RES646_GATE5_BLOCKED"


@pytest.mark.parametrize("available", [True, False])
def test_effective_cgroup_limits_include_ancestors_and_never_guess_unlimited(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    available: bool,
) -> None:
    from types import SimpleNamespace

    from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
        res645_evidence as infrastructure,
    )

    root = Path("/sys/fs/cgroup")
    controls = (
        {
            root / "parent/leaf/memory.max": "max",
            root / "parent/leaf/cpu.max": "50000 100000",
            root / "parent/memory.max": str(2**31),
            root / "parent/cpu.max": "100000 100000",
            root / "memory.max": "max",
            root / "cpu.max": "max 100000",
        }
        if available
        else {}
    )
    provider = SimpleNamespace(
        root=root,
        _relative=lambda _: "/parent/leaf",
        snapshot=lambda _: {"available": True, "cgroup": "/parent/leaf", "oom_kill": 0},
    )
    monkeypatch.setattr(infrastructure, "CgroupEvidence", lambda: provider)
    original_file, original_text = Path.is_file, Path.read_text

    def is_file(path: Path) -> bool:
        return path in controls if path.is_relative_to(root) else original_file(path)

    def read_text(path: Path, *args: Any, **kwargs: Any) -> str:
        return controls[path] if path in controls else original_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "is_file", is_file)
    monkeypatch.setattr(Path, "read_text", read_text)
    monkeypatch.setattr(os, "sched_getaffinity", lambda _: set(range(8)))
    if not available:
        with pytest.raises(ValueError, match="CPU/memory limits unavailable"):
            p.resource_observations(tmp_path, tmp_path)
        return
    observed = p.resource_observations(tmp_path, tmp_path)
    assert observed["memory_limit_bytes"] == 2**31
    assert observed["cpu_capacity"] == 0.5
    assert observed["filesystems"]["output"]["device"] == tmp_path.stat().st_dev
    assert observed["filesystems"]["output"]["available_bytes"] > 0
    assert observed["hierarchy"][1]["memory.max"] == str(2**31)


def test_success_emits_the_exact_campaign_plan_identity(
    local: LocalEvidence, tmp_path: Path
) -> None:
    from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
        res646_authorization as authorization,
    )

    result = local.check()
    assert result["status"] == "RES646_GATE5_READY_FOR_INDEPENDENT_REVIEW", result["blockers"]
    campaign_path = tmp_path / "proposed-campaign.json"
    write(campaign_path, result["campaign_configuration"])
    plan = authorization.CampaignPlan(campaign_path)
    assert plan.identities == result["identities"]
    assert plan.scope == result["proposed_scope_sha256"]
    assert list(plan.root.iterdir()) == []
    assert list(plan.output.iterdir()) == []


@pytest.mark.parametrize("directory", ["CHECKPOINT_DIRECTORY", "FIT_RECEIPTS_DIRECTORY"])
def test_checkpoint_and_receipt_directories_reject_extra_files(
    local: LocalEvidence,
    directory: str,
) -> None:
    write(Path(local.values[directory]) / "extra-invented-file.json", {"invented": True})
    result = local.check()
    assert result["status"] == "RES646_GATE5_BLOCKED"
    assert "directory inventory" in str(result["blockers"])


@pytest.mark.parametrize(
    "key", ["metadata_sha256", "tracking_raw_sha256", "phases_sha256", "locked_sha256"]
)
def test_scoring_input_bindings_must_match_frozen_source_and_admission(
    local: LocalEvidence,
    key: str,
) -> None:
    local.document["matches"][0]["sha256"][key] = "f" * 64
    local.document["read_scope"]["matches"] = copy.deepcopy(local.document["matches"])
    local.save()
    result = local.check()
    assert result["status"] == "RES646_GATE5_BLOCKED"
    assert "frozen" in str(result["blockers"])


@pytest.mark.parametrize(
    "kind", ["missing", "changed-normalized", "changed-lock", "hardlink", "symlink"]
)
def test_normalized_scoring_and_lock_evidence_is_complete_and_alias_free(
    local: LocalEvidence,
    kind: str,
    tmp_path: Path,
) -> None:
    if kind == "missing":
        local.document["scoring_files"].pop()
        local.save()
    else:
        row = local.document["scoring_files"][3 if kind == "changed-lock" else 0]
        path = Path(row["path"])
        if kind in ("changed-normalized", "changed-lock"):
            write(path, {"invented_substitution": True})
        else:
            original = tmp_path / "invented-original-scoring"
            path.rename(original)
            path.symlink_to(original) if kind == "symlink" else os.link(original, path)
    assert local.check()["status"] == "RES646_GATE5_BLOCKED"


@pytest.mark.parametrize("field", ["bytes", "sha256", "normalization-phases"])
def test_pinned_independent_source_must_agree_with_inventory_and_normalization(
    local: LocalEvidence,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    independent_path = Path(local.document["read_scope"]["independent_source"])
    independent = json.loads(independent_path.read_bytes())
    if field == "normalization-phases":
        independent["normalization_receipts"][0]["phases_sha256"] = "f" * 64
    else:
        independent["source_files"][0][field] = -1 if field == "bytes" else "f" * 64
    independent_sha = hashlib.sha256(write(independent_path, independent)).hexdigest()
    admission_path = Path(local.values["RESEARCH_ADMISSION"])
    admission = json.loads(admission_path.read_bytes())
    admission["independent_source_sha256"] = independent_sha
    admission_sha = hashlib.sha256(write(admission_path, admission)).hexdigest()
    # Pin the deliberately inconsistent invented admission so this tests reconciliation,
    # rather than stopping at an ordinary metadata hash mismatch.
    monkeypatch.setattr(p, "ADMISSION_SHA256", admission_sha)
    local.document["admission_sha256"] = admission_sha
    local.save()
    result = local.check()
    assert result["status"] == "RES646_GATE5_BLOCKED"
    expected = "normalized phases" if field == "normalization-phases" else "source inventory"
    assert expected in str(result["blockers"])


@pytest.mark.parametrize("target", ["LEDGER_ROOT", "OUTPUT_DIRECTORY"])
@pytest.mark.parametrize("mode", [0o500, 0o1700])
def test_target_modes_must_match_executor_exactly(
    local: LocalEvidence, target: str, mode: int
) -> None:
    Path(local.values[target]).chmod(mode)
    report = local.check()
    assert report["status"] == "RES646_GATE5_BLOCKED"
    assert "0700" in str(report["blockers"])


@pytest.mark.parametrize("target", ["ledger", "output"])
def test_read_only_target_filesystem_is_blocked(local: LocalEvidence, target: str) -> None:
    local.resources["filesystems"][target]["read_only"] = True
    report = local.check()
    assert report["status"] == "RES646_GATE5_BLOCKED"
    assert "read-only" in str(report["blockers"])
