from __future__ import annotations

import hashlib
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))


def _job_module(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RES338_JOB_STATUS_PATH", "/tmp/res338-colab-job-test.json")
    monkeypatch.setenv("RES338_JOB_ID", "unit-test")
    sys.modules.pop("res338_colab_job", None)
    module = importlib.import_module("res338_colab_job")
    sys.modules.pop("res338_colab_job", None)
    return module


def _prepared_campaign(root: Path) -> None:
    training = [f"train-{index}" for index in range(12)]
    validation = [f"validation-{index}" for index in range(4)]
    freeze = {
        "schema_id": "fpdbench.res338-research-final-fit-campaign",
        "research_scope": "training-validation",
        "protected_status": "NOT_QUALIFIED",
        "research_roles": {"training": training, "validation": validation},
        "feature_cache": {match: {} for match in training + validation},
    }
    payload = json.dumps(freeze, sort_keys=True, separators=(",", ":")).encode()
    (root / "campaign").mkdir()
    (root / "campaign" / "reproducibility-manifest.json").write_bytes(payload)
    (root / "campaign" / "campaign.json").write_text(
        json.dumps(
            {
                "status": "PREPARED",
                "completed_fit_count": 0,
                "failed_fit_count": 0,
                "required_fit_count": 18,
                "frozen_manifest_sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    )


def test_cleanup_removes_only_verified_preparation_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = _job_module(monkeypatch)
    monkeypatch.setattr(job, "ROOT", tmp_path)
    monkeypatch.setattr(job, "CAMPAIGN", tmp_path / "campaign")
    temporary = (
        tmp_path / "source",
        tmp_path / "research",
        tmp_path / "preloaded-cache",
        tmp_path / "transfer" / "chunks",
    )
    for directory in temporary:
        directory.mkdir(parents=True)
        (directory / "private.tmp").write_text("private")
    monkeypatch.setattr(job, "SOURCE", temporary[0])
    monkeypatch.setattr(job, "RESEARCH", temporary[1])
    monkeypatch.setattr(job, "PRELOADED", temporary[2])
    monkeypatch.setattr(job, "TRANSFER_CHUNKS", temporary[3])
    _prepared_campaign(tmp_path)

    removed = job._remove_verified_preparation_inputs()

    assert set(removed) == {path.relative_to(tmp_path).as_posix() for path in temporary}
    assert all(not path.exists() for path in temporary)
    assert (tmp_path / "campaign" / "campaign.json").is_file()


def test_cleanup_preserves_inputs_when_campaign_is_not_prepared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = _job_module(monkeypatch)
    monkeypatch.setattr(job, "ROOT", tmp_path)
    monkeypatch.setattr(job, "CAMPAIGN", tmp_path / "campaign")
    (tmp_path / "source").mkdir()
    monkeypatch.setattr(job, "SOURCE", tmp_path / "source")
    monkeypatch.setattr(job, "RESEARCH", tmp_path / "research")
    monkeypatch.setattr(job, "PRELOADED", tmp_path / "preloaded-cache")
    monkeypatch.setattr(job, "TRANSFER_CHUNKS", tmp_path / "transfer" / "chunks")
    _prepared_campaign(tmp_path)
    ledger = json.loads((tmp_path / "campaign" / "campaign.json").read_bytes())
    ledger["status"] = "RUNNING"
    (tmp_path / "campaign" / "campaign.json").write_text(json.dumps(ledger))

    with pytest.raises(ValueError, match="before the exact 16-cache campaign is frozen"):
        job._remove_verified_preparation_inputs()

    assert (tmp_path / "source").is_dir()


def test_pack_caches_records_a_completed_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = _job_module(monkeypatch)
    status_path = tmp_path / "job.json"
    status_path.write_text(json.dumps({"job_id": "unit-test", "status": "STARTING"}))
    reference = tmp_path / "reference.json"
    reference.write_bytes(b"{}")
    repo = tmp_path / "repo"
    repo.mkdir()
    python = tmp_path / "venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("pinned runtime")
    monkeypatch.setattr(job, "STATUS_PATH", status_path)
    monkeypatch.setattr(job, "ROOT", tmp_path)
    monkeypatch.setattr(job, "REPO", repo)
    monkeypatch.setattr(job, "PYTHON", python)
    monkeypatch.setattr(job, "REFERENCE", reference)
    monkeypatch.setattr(job, "REFERENCE_SHA", hashlib.sha256(b"{}").hexdigest())
    monkeypatch.setenv("RES338_CODE_SHA", "frozen-code")
    monkeypatch.setattr(job.subprocess, "check_output", lambda *args, **kwargs: "frozen-code")
    calls: list[tuple[object, ...]] = []
    monkeypatch.setitem(
        sys.modules,
        "res338_cache_archive",
        SimpleNamespace(
            pack_training_validation_caches=lambda *args: calls.append(args) or {"packed": True}
        ),
    )

    result = job.run("pack-caches")
    status = json.loads(status_path.read_bytes())

    assert result == {"packed": True}
    assert len(calls) == 1
    assert status["status"] == "COMPLETED"
    assert status["exit_code"] == 0
    assert status["elapsed_seconds"] >= 0
    assert status["finished_at_utc"]
