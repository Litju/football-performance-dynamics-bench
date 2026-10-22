"""Synthetic bounded-memory producer tests; no protected data or verifier is used."""

from __future__ import annotations

import copy
import gc
import hashlib
import json
import stat
import sys
import tracemalloc
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_population_producer_v2 import (  # noqa: E402
    complete_10hz_sources,
    synthetic_sources,
)

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (  # noqa: E402
    population_producer_v2 as historical,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (  # noqa: E402
    streaming_population_producer_v1 as streaming,
)
from fpdbench.data_sources.skillcorner import canonical_bytes  # noqa: E402
from fpdbench.eligibility.skillcorner import BallPopulationQualificationStop  # noqa: E402


def _lines(values: list[object]) -> bytes:
    return b"".join(canonical_bytes(value) + b"\n" for value in values)


def _rows(payload: bytes) -> list[dict[str, object]]:
    return [json.loads(line) for line in payload.splitlines()]


def _persist(
    root: Path,
    sources: tuple[historical.PopulationMatchInputV2, ...],
) -> tuple[streaming.StreamingPopulationMatchInputV1, ...]:
    root.mkdir(mode=0o700)
    result = []
    for source in sources:
        match_dir = root / source.match_id
        match_dir.mkdir(mode=0o700)
        paths = (
            match_dir / "metadata.json",
            match_dir / "tracking.jsonl",
            match_dir / "phases.json",
        )
        for path, payload in zip(
            paths,
            (
                source.metadata_json,
                source.tracking_jsonl,
                source.phase_intervals_json,
            ),
            strict=True,
        ):
            with path.open("xb") as stream:
                stream.write(payload)
            path.chmod(0o600)
        result.append(
            streaming.StreamingPopulationMatchInputV1(
                source.match_id,
                paths[0],
                paths[1],
                paths[2],
            )
        )
    return tuple(result)


def _artifacts(result: streaming.StreamingPopulationResultV1) -> dict[str, bytes]:
    directory = result.output_directory
    return {
        "manifest_json": (directory / "manifest.json").read_bytes(),
        "candidates_jsonl": (directory / "candidates.jsonl").read_bytes(),
        "diagnostic_census_jsonl": (directory / "diagnostic-census.jsonl").read_bytes(),
        "truth_jsonl": (directory / "truth.jsonl").read_bytes(),
    }


def _assert_scientific_parity(
    sources: tuple[historical.PopulationMatchInputV2, ...],
    result: streaming.StreamingPopulationResultV1,
) -> None:
    old = historical.produce_population_draft_v2(sources, input_kind="synthetic")
    actual = _artifacts(result)
    assert actual == {
        "manifest_json": old.manifest_json,
        "candidates_jsonl": old.candidates_jsonl,
        "diagnostic_census_jsonl": old.diagnostic_census_jsonl,
        "truth_jsonl": old.truth_jsonl,
    }
    actual_receipt = json.loads((result.output_directory / "receipt.json").read_bytes())
    old_receipt = json.loads(old.receipt_json)
    for key in (
        "authority_bindings",
        "source_byte_qualified",
        "independent_verification",
        "input_receipts",
        "match_counts",
        "candidate_origin_population_sha256",
        "diagnostic_origin_census_count",
        "diagnostic_origin_census_sha256",
        "candidates_jsonl_sha256",
        "diagnostic_census_jsonl_sha256",
        "drift_scan",
    ):
        assert actual_receipt[key] == old_receipt[key]
    assert actual_receipt["status"] == old_receipt["status"] == "UNQUALIFIED"
    assert actual_receipt["worker_version"] == streaming.WORKER_VERSION
    assert actual_receipt["worker_package_identity"]["executable_runtime_attestation"] == (
        "NOT_PROVIDED"
    )
    assert "producer_executable_fingerprint" not in actual_receipt
    assert (
        actual_receipt["receipt_sha256"]
        == hashlib.sha256(
            canonical_bytes(
                {key: value for key, value in actual_receipt.items() if key != "receipt_sha256"}
            )
        ).hexdigest()
    )
    manifest = json.loads(actual["manifest_json"])
    assert historical.validate_evaluation_population_authority_v2_document(manifest)
    assert (result.output_directory / ".incomplete").exists() is False
    assert stat.S_IMODE(result.output_directory.stat().st_mode) == 0o700
    for artifact in result.output_directory.iterdir():
        assert stat.S_IMODE(artifact.stat().st_mode) == 0o600


def _missing_support_sources():
    incomplete = []
    for source in synthetic_sources():
        metadata = json.loads(source.metadata_json)
        metadata["match_periods"][0]["end_frame"] = 106
        for player in metadata["players"]:
            player["playing_time"]["by_period"][0]["end_frame"] = 106
        frames = [
            row
            for row in _rows(source.tracking_jsonl)
            if row["frame"] < 106 and row["frame"] != 102
        ]
        incomplete.append(
            replace(
                source,
                metadata_json=canonical_bytes(metadata),
                tracking_jsonl=_lines(frames),
                phase_intervals_json=canonical_bytes(
                    [{"period": 1, "frame_start": 100, "frame_end": 106}]
                ),
            )
        )
    return tuple(incomplete)


def test_synthetic_and_complete_10hz_scientific_parity(tmp_path):
    sources = complete_10hz_sources(synthetic_sources())
    inputs = _persist(tmp_path / "inputs", sources)
    result = streaming.produce_streaming_population_draft_v1(
        inputs,
        (tmp_path / "output").resolve(),
    )
    _assert_scientific_parity(sources, result)
    ten_hz_receipt = json.loads((tmp_path / "output" / "receipt.json").read_bytes())
    assert all(row["source_frame_count"] == 86 for row in ten_hz_receipt["input_receipts"])
    assert all(row["retained_sample_count"] == 43 for row in ten_hz_receipt["input_receipts"])


def test_missing_match_fails_before_creating_output(tmp_path):
    inputs = _persist(tmp_path / "inputs", synthetic_sources())
    output = (tmp_path / "output").resolve()
    with pytest.raises(ValueError, match="exactly the pinned 20 matches"):
        streaming.produce_streaming_population_draft_v1(inputs[:-1], output)
    assert not output.exists()


def test_missing_support_leaves_an_incomplete_receipt_without_truth_or_manifest(tmp_path):
    incomplete_sources = _missing_support_sources()
    inputs = _persist(tmp_path / "inputs", incomplete_sources)
    output = (tmp_path / "output").resolve()
    with pytest.raises(streaming.IncompleteStreamingPopulationV1) as error:
        streaming.produce_streaming_population_draft_v1(inputs, output)
    assert error.value.receipt_path == output / "receipt.json"
    receipt = json.loads((output / "receipt.json").read_bytes())
    assert receipt["status"] == "INCOMPLETE"
    assert receipt["match_counts"][0]["diagnostic_origin_count"] == 3
    assert receipt["match_counts"][0]["candidate_window_count"] == 0
    first_match_diagnostics = [
        row
        for row in _rows((output / "diagnostic-census.jsonl").read_bytes())
        if row["match_id"] == inputs[0].match_id
    ]
    assert [row["origin_sample_id"] for row in first_match_diagnostics] == [
        "period_1/sample_50",
        "period_1/sample_51",
        "period_1/sample_52",
    ]
    assert receipt["match_counts"][0]["scoreable_window_count"] == 0
    assert (output / ".incomplete").exists()
    assert (output / "manifest.json").exists() is False
    assert (output / "truth.jsonl").exists() is False


@pytest.mark.parametrize("malformation", ("duplicate_key", "unsupported_field", "nonfinite"))
def test_malformed_or_unsupported_tracking_rows_fail_closed(tmp_path, malformation):
    sources = synthetic_sources()
    source = sources[0]
    lines = source.tracking_jsonl.splitlines()
    if malformation == "duplicate_key":
        lines[0] = b'{"frame":100,"frame":100}'
    else:
        row = json.loads(lines[0])
        if malformation == "unsupported_field":
            row["unreviewed"] = True
            lines[0] = canonical_bytes(row)
        else:
            row["ball_data"]["x"] = float("nan")
            lines[0] = canonical_bytes(row)
    malformed = (replace(source, tracking_jsonl=b"\n".join(lines) + b"\n"), *sources[1:])
    inputs = _persist(tmp_path / "inputs", malformed)
    output = (tmp_path / "output").resolve()
    with pytest.raises(ValueError):
        streaming.produce_streaming_population_draft_v1(inputs, output)
    assert (output / ".incomplete").exists()
    assert (output / "receipt.json").exists() is False


def test_late_nullable_ball_drift_is_scanned_before_population_construction(tmp_path):
    sources = synthetic_sources()
    first = sources[0]
    frames = _rows(first.tracking_jsonl)
    late = copy.deepcopy(frames[-1])
    late.update(
        frame=186,
        timestamp="00:00:18.60",
        ball_data={"x": 1.0, "y": 2.0, "z": None, "is_detected": None},
    )
    drifted = (replace(first, tracking_jsonl=first.tracking_jsonl + _lines([late])), *sources[1:])
    inputs = _persist(tmp_path / "inputs", drifted)
    output = (tmp_path / "output").resolve()
    with pytest.raises(streaming.IncompleteStreamingPopulationV1):
        streaming.produce_streaming_population_draft_v1(inputs, output)
    receipt = json.loads((output / "receipt.json").read_bytes())
    assert receipt["drift_scan"]["checked_sample_count"] == 20 * 43 + 1
    assert receipt["drift_scan"]["null_flag_finite_xy_count"] == 1
    assert (output / "candidates.jsonl").exists() is False
    assert (output / "truth.jsonl").exists() is False
    assert (output / ".incomplete").exists()
    with pytest.raises(BallPopulationQualificationStop):
        historical.produce_population_draft_v2(drifted, input_kind="synthetic")


def test_source_mutation_after_drift_scan_is_rejected(tmp_path, monkeypatch):
    inputs = _persist(tmp_path / "inputs", synthetic_sources())
    output = (tmp_path / "output").resolve()
    original = streaming._snapshots_and_drift

    def mutate_after_scan(input_map, roles, release_id):
        snapshots, scan = original(input_map, roles, release_id)
        tracking = input_map[roles[0][1]].tracking_jsonl_path
        rows = _rows(tracking.read_bytes())
        rows[0]["ball_data"]["x"] = 1.5
        tracking.write_bytes(_lines(rows))
        return snapshots, scan

    monkeypatch.setattr(streaming, "_snapshots_and_drift", mutate_after_scan)
    with pytest.raises(ValueError, match="changed after the mandatory drift scan"):
        streaming.produce_streaming_population_draft_v1(inputs, output)
    assert (output / ".incomplete").exists()
    assert (output / "receipt.json").exists() is False


def test_interrupted_artifact_write_keeps_the_incomplete_marker(tmp_path, monkeypatch):
    inputs = _persist(tmp_path / "inputs", synthetic_sources())
    output = (tmp_path / "output").resolve()
    original = streaming._ArtifactWriter.write
    writes = 0

    def fail_after_some_rows(writer, payload):
        nonlocal writes
        writes += 1
        if writes == 50:
            raise OSError("injected interrupted write")
        original(writer, payload)

    monkeypatch.setattr(streaming._ArtifactWriter, "write", fail_after_some_rows)
    with pytest.raises(OSError, match="interrupted"):
        streaming.produce_streaming_population_draft_v1(inputs, output)
    assert (output / ".incomplete").exists()
    assert (output / "receipt.json").exists() is False
    assert (output / "manifest.json").exists() is False


def test_corrupted_candidate_artifact_is_not_receipted(tmp_path, monkeypatch):
    inputs = _persist(tmp_path / "inputs", _missing_support_sources())
    output = (tmp_path / "output").resolve()
    original = streaming._verify_output_digest
    corrupted = False

    def corrupt_then_verify(path, expected):
        nonlocal corrupted
        if path.name == "candidates.jsonl" and not corrupted:
            corrupted = True
            with path.open("ab") as stream:
                stream.write(b"{}\n")
        return original(path, expected)

    monkeypatch.setattr(streaming, "_verify_output_digest", corrupt_then_verify)
    with pytest.raises(ValueError, match="changed while being written"):
        streaming.produce_streaming_population_draft_v1(inputs, output)
    assert corrupted
    assert (output / ".incomplete").exists()
    assert (output / "receipt.json").exists() is False


def test_preexisting_output_directory_is_never_overwritten(tmp_path):
    inputs = _persist(tmp_path / "inputs", synthetic_sources())
    output = tmp_path / "output"
    output.mkdir()
    sentinel = output / "sentinel"
    sentinel.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        streaming.produce_streaming_population_draft_v1(inputs, output.resolve())
    assert sentinel.read_bytes() == b"keep"


def _extended_inputs(root: Path, end_frame: int):
    root.mkdir(mode=0o700)
    result = []
    for source in synthetic_sources():
        match_dir = root / source.match_id
        match_dir.mkdir(mode=0o700)
        metadata = json.loads(source.metadata_json)
        metadata["match_periods"][0]["end_frame"] = end_frame
        for player in metadata["players"]:
            player["playing_time"]["by_period"][0]["end_frame"] = end_frame
        metadata_path = match_dir / "metadata.json"
        metadata_path.write_bytes(canonical_bytes(metadata))
        metadata_path.chmod(0o600)
        phase_path = match_dir / "phases.json"
        phase_path.write_bytes(
            canonical_bytes([{"period": 1, "frame_start": 100, "frame_end": end_frame}])
        )
        phase_path.chmod(0o600)
        tracking_path = match_dir / "tracking.jsonl"
        template = json.loads(source.tracking_jsonl.splitlines()[0])
        with tracking_path.open("xb") as stream:
            for frame_number in range(100, end_frame):
                frame = copy.deepcopy(template)
                frame["frame"] = frame_number
                frame["timestamp"] = f"00:00:{frame_number // 10:02d}.{frame_number % 10}0"
                for player in frame["player_data"]:
                    player["x"] = player["player_id"] % 20 + frame_number / 100
                stream.write(canonical_bytes(frame) + b"\n")
        tracking_path.chmod(0o600)
        result.append(
            streaming.StreamingPopulationMatchInputV1(
                source.match_id,
                metadata_path,
                tracking_path,
                phase_path,
            )
        )
    return tuple(result)


def _measure(inputs, output: Path) -> tuple[int, bool, int]:
    gc.collect()
    tracemalloc.start()
    result = streaming.produce_streaming_population_draft_v1(inputs, output.resolve())
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    receipt = json.loads((result.output_directory / "receipt.json").read_bytes())
    output_size = sum(path.stat().st_size for path in result.output_directory.iterdir())
    return peak, receipt["candidate_origin_population_sha256"] != "", output_size


def test_peak_memory_does_not_scale_with_frames_candidates_or_output(tmp_path):
    small = _persist(tmp_path / "small-input", complete_10hz_sources(synthetic_sources()))
    large = _extended_inputs(tmp_path / "large-input", 212)
    small_peak, small_has_candidates, small_size = _measure(small, tmp_path / "small-output")
    large_peak, large_has_candidates, large_size = _measure(large, tmp_path / "large-output")
    large_receipt = json.loads((tmp_path / "large-output" / "receipt.json").read_bytes())
    large_candidates = json.loads((tmp_path / "large-output" / "manifest.json").read_bytes())[
        "candidate_window_count"
    ]
    small_receipt = json.loads((tmp_path / "small-output" / "receipt.json").read_bytes())
    print(
        "streaming-memory "
        f"small_peak_bytes={small_peak} large_peak_bytes={large_peak} "
        f"candidate_count={large_candidates} "
        f"output_bytes={small_size}->{large_size}"
    )
    assert small_has_candidates and large_has_candidates
    assert large_candidates == 20 * 16
    assert large_size > small_size * 1.9
    assert large_peak <= small_peak + 1_000_000
    assert sum(row["source_frame_count"] for row in small_receipt["input_receipts"]) == 20 * 86
    assert sum(row["source_frame_count"] for row in large_receipt["input_receipts"]) == 20 * 112
    assert large_receipt["status"] == "UNQUALIFIED"
