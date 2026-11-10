"""RES614: the historical scorer authority and the forensic evidence index stay intact."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INDEX = json.loads((REPO / "docs" / "res614" / "incident_evidence_index.json").read_text())
HEX64 = set("0123456789abcdef")


def _git_blob_id(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _utc(value: str) -> datetime:
    head, _, frac = value.rstrip("Z").partition(".")
    base = datetime.strptime(head, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)
    return base.replace(microsecond=int((frac + "000000")[:6])) if frac else base


def test_frozen_scorer_authority_is_byte_identical_to_the_frozen_commit() -> None:
    frozen = INDEX["frozen_identities"]
    assert frozen["commit"] == "7acc2c4e1174935efbe561e072f68c349af5e05f"
    for relative, blob in frozen["git_blob_ids_at_commit"].items():
        assert _git_blob_id(REPO / relative) == blob, relative


def test_frozen_sha256_identities_match_the_ratified_values() -> None:
    sha = INDEX["frozen_identities"]["sha256"]
    root = REPO / "src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction"
    assert (
        hashlib.sha256((root / "res593_amendment_v1.json").read_bytes()).hexdigest()
        == sha["amendment"]
        == "e54f067a07479b81c4625428e49e5a5b907c49987d4c5bd7982138e270e66913"
    )
    assert (
        hashlib.sha256((root / "res593_checkpoint_manifest_v1.json").read_bytes()).hexdigest()
        == sha["checkpoint_manifest"]
        == "770f1d9bbca3020237992181a56e4f5be4adaae7aab07f5f1313aa699d8693e0"
    )
    scorer = root / "amended_heldout_evaluation.py"
    assert hashlib.sha256(scorer.read_bytes()).hexdigest() == sha["scorer_module"]
    shim = REPO / "tools" / "score_res594_heldout.py"
    assert hashlib.sha256(shim.read_bytes()).hexdigest() == sha["entrypoint_shim"]


def test_evidence_index_declares_snapshot_access_and_marks_it_unverified() -> None:
    """Checks the recorded declaration only; it is not independent proof of no reads."""
    snapshot = INDEX["private_snapshot_metadata_only"]
    assert snapshot["content_opened"] is False
    assert snapshot["content_hashed"] is False
    assert snapshot["sha256"] is None
    assert snapshot["access_evidence"]["independently_verified"] is False
    assert snapshot["bytes"] == 6_815_838_287
    for source in INDEX["sources"]:
        assert "evaluation-input" not in source["display_path"]
        assert len(source["sha256"]) == 64 and set(source["sha256"]) <= HEX64
    assert INDEX["campaign_directory_listing"] == [
        ".started.json",
        "evaluation-input.private.jsonl",
    ]


def test_forensic_timeline_is_internally_consistent() -> None:
    session = INDEX["target_session"]
    snapshot = INDEX["private_snapshot_metadata_only"]
    start = _utc(session["exec_start_utc"])
    birth = _utc(snapshot["birth_utc"])
    mtime = _utc(snapshot["mtime_utc"])
    atime = _utc(snapshot["atime_utc"])
    alive = _utc(session["last_alive_sample_utc"])
    end = _utc(session["exec_end_utc"])
    dead = _utc(session["first_dead_sample_utc"])
    assert start < birth < mtime < atime < alive < end < dead
    assert (atime - mtime).total_seconds() < 1.0
    # Exec duration agrees with the bracketing timestamps to within the 1 s start rounding.
    assert abs((end - start).total_seconds() - session["exec_duration_s"]) < 1.0
    sample = session["last_alive_sample"]
    assert sample["etime"] == "30:27" and sample["cpu_time"] == "00:29:54"
    assert session["agent_kill_commands_issued"] == 0
    assert session["exit_code"] == 143


def test_no_fixed_thirty_minute_limit_in_the_command_census() -> None:
    census = INDEX["census"]
    assert census["sessions_ge_1800s_exit_0"] >= 21
    assert census["longest_exit_0_session_s"] > 3600
    assert min(census["exit_143_durations_s_range"]) < 100
    assert max(census["exit_143_durations_s_range"]) > 10_000


def test_new_diagnostics_do_not_name_private_data_or_the_scoring_entrypoint() -> None:
    for name in ("res614_synthetic_workload.py", "res614_resilient_runner.py"):
        text = (REPO / "tools" / name).read_text()
        assert "evaluation-input.private" not in text
        assert "score_res594_heldout" not in text
        assert "fpdbench-res594" not in text.replace('"res594"', "")
