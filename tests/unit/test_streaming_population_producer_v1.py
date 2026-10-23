"""Synthetic bounded-memory producer tests; no protected data or verifier is used."""

from __future__ import annotations

import copy
import hashlib
import json
import stat
import subprocess
import sys
import textwrap
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
    assert actual_receipt["storage_boundary"]["trust"] == (
        "SYNTHETIC_ONLY_NOT_TRUSTED_FOR_PROTECTED_DATA"
    )
    assert actual_receipt["storage_boundary"]["filesystem_type"]
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


def _assert_incomplete_receipt_parity(
    actual: dict[str, object],
    expected: dict[str, object],
) -> None:
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
        "status",
    ):
        assert actual[key] == expected[key]
    assert actual["storage_boundary"]["trust"] == ("SYNTHETIC_ONLY_NOT_TRUSTED_FOR_PROTECTED_DATA")


def _replace_first_source(sources, source):
    return (source, *sources[1:])


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


def test_missing_odd_frames_match_the_frozen_producer(tmp_path):
    sources = complete_10hz_sources(synthetic_sources())
    rows = _rows(sources[0].tracking_jsonl)
    changed = _replace_first_source(
        sources,
        replace(sources[0], tracking_jsonl=_lines([row for row in rows if row["frame"] != 101])),
    )
    inputs = _persist(tmp_path / "inputs", changed)
    result = streaming.produce_streaming_population_draft_v1(inputs, tmp_path / "output")
    _assert_scientific_parity(changed, result)
    receipt = json.loads((result.output_directory / "receipt.json").read_bytes())
    assert receipt["input_receipts"][0]["source_frame_count"] == 85
    assert receipt["input_receipts"][0]["retained_sample_count"] == 43


@pytest.mark.parametrize("missing_frames", ((160,), (160, 162), (150,)))
def test_missing_even_frames_sparse_support_and_missing_origins_match_incomplete_receipts(
    tmp_path,
    missing_frames,
):
    sources = complete_10hz_sources(synthetic_sources())
    if missing_frames == (150,):
        sources = synthetic_sources()
    rows = _rows(sources[0].tracking_jsonl)
    changed = _replace_first_source(
        sources,
        replace(
            sources[0],
            tracking_jsonl=_lines([row for row in rows if row["frame"] not in missing_frames]),
        ),
    )
    inputs = _persist(tmp_path / "inputs", changed)
    with pytest.raises(historical.IncompletePopulationV2) as expected_error:
        historical.produce_population_draft_v2(changed, input_kind="synthetic")
    output = tmp_path / "output"
    with pytest.raises(streaming.IncompleteStreamingPopulationV1) as actual_error:
        streaming.produce_streaming_population_draft_v1(inputs, output)
    assert actual_error.value.receipt_path == output / "receipt.json"
    expected_receipt = json.loads(expected_error.value.receipt_json)
    actual_receipt = json.loads((output / "receipt.json").read_bytes())
    _assert_incomplete_receipt_parity(actual_receipt, expected_receipt)
    first_match = actual_receipt["match_counts"][0]
    assert first_match["candidate_window_count"] == 0
    assert first_match["diagnostic_origin_count"] == 43
    assert first_match["diagnostic_exclusion_window_counts"].get("TEMPORAL_GAP", 0) > 0
    assert (output / "truth.jsonl").exists() is False
    assert (output / "manifest.json").exists() is False
    assert (output / ".incomplete").exists()


@pytest.mark.parametrize(("missing", "valid_positions", "passes"), ((2, 39, True), (3, 38, False)))
def test_streaming_parity_at_the_39_of_41_eligibility_threshold(
    tmp_path,
    missing,
    valid_positions,
    passes,
):
    sources = synthetic_sources()
    rows = _rows(sources[0].tracking_jsonl)
    for row in rows[:missing]:
        row["ball_data"] = {"x": None, "y": None, "z": None, "is_detected": None}
    changed = _replace_first_source(
        sources,
        replace(sources[0], tracking_jsonl=_lines(rows)),
    )
    inputs = _persist(tmp_path / "inputs", changed)
    result = streaming.produce_streaming_population_draft_v1(inputs, tmp_path / "output")
    _assert_scientific_parity(changed, result)
    diagnostic = next(
        row
        for row in _rows((tmp_path / "output" / "diagnostic-census.jsonl").read_bytes())
        if row["match_id"] == sources[0].match_id
        and row["origin_sample_id"] == "period_1/sample_75"
    )["diagnostic"]
    assert diagnostic["quality"]["ball_observations"]["valid_position_count"] == valid_positions
    assert diagnostic["candidate_rules_pass"] is passes


def test_streaming_parity_for_warnings_nonzero_anchors_and_truth_masks(tmp_path):
    sources = complete_10hz_sources(synthetic_sources())
    rows = _rows(sources[0].tracking_jsonl)
    partial_ball = next(row for row in rows if row["frame"] == 152)
    partial_ball["ball_data"]["y"] = None
    missing_player = next(row for row in rows if row["frame"] == 160)
    player = next(item for item in missing_player["player_data"] if item["player_id"] == 1001)
    player.update(x=None, y=None)
    changed = _replace_first_source(
        sources,
        replace(sources[0], tracking_jsonl=_lines(rows)),
    )
    inputs = _persist(tmp_path / "inputs", changed)
    result = streaming.produce_streaming_population_draft_v1(inputs, tmp_path / "output")
    _assert_scientific_parity(changed, result)
    census = _rows((tmp_path / "output" / "diagnostic-census.jsonl").read_bytes())
    diagnostic = next(
        row["diagnostic"]
        for row in census
        if row["match_id"] == sources[0].match_id
        and row["origin_sample_id"] == "period_1/sample_75"
    )
    assert "BALL_COORDINATES_PARTIAL" in {item["code"] for item in diagnostic["warnings"]}
    truth = next(
        row
        for row in _rows((tmp_path / "output" / "truth.jsonl").read_bytes())
        if row["match_id"] == sources[0].match_id
        and row["origin_sample_id"] == "period_1/sample_75"
        and row["scene_id"] == "home"
    )
    assert truth["origin_xy"][0] == [1.25, -4.0]
    assert truth["absolute_xy"][4][0] is None
    assert truth["origin_relative_displacement"][4][0] is None
    assert truth["truth_mask"][4][0] is False
    assert truth["absolute_xy"][0][0] is not None
    assert truth["origin_relative_displacement"][0][0] is not None
    assert all(
        valid == (xy is not None) == (delta is not None)
        for xy_row, delta_row, mask_row in zip(
            truth["absolute_xy"],
            truth["origin_relative_displacement"],
            truth["truth_mask"],
            strict=True,
        )
        for xy, delta, valid in zip(xy_row, delta_row, mask_row, strict=True)
    )


def test_streaming_parity_resets_window_support_at_period_boundaries(tmp_path):
    sources = synthetic_sources()
    metadata = json.loads(sources[0].metadata_json)
    metadata["match_periods"].append({"period": 2, "start_frame": 300, "end_frame": 386})
    for player in metadata["players"]:
        player["playing_time"]["by_period"].append(
            {"name": "period_2", "start_frame": 300, "end_frame": 386}
        )
    first_period = _rows(sources[0].tracking_jsonl)
    second_period = copy.deepcopy(first_period)
    for frame in second_period:
        frame["frame"] += 200
        frame["period"] = 2
        frame["timestamp"] = f"00:00:{frame['frame'] // 10:02d}.{frame['frame'] % 10}0"
    changed = _replace_first_source(
        sources,
        replace(
            sources[0],
            metadata_json=canonical_bytes(metadata),
            tracking_jsonl=_lines(first_period + second_period),
            phase_intervals_json=canonical_bytes(
                [
                    {"period": 1, "frame_start": 100, "frame_end": 186},
                    {"period": 2, "frame_start": 300, "frame_end": 386},
                ]
            ),
        ),
    )
    inputs = _persist(tmp_path / "inputs", changed)
    result = streaming.produce_streaming_population_draft_v1(inputs, tmp_path / "output")
    _assert_scientific_parity(changed, result)
    manifest = json.loads((tmp_path / "output" / "manifest.json").read_bytes())
    windows = manifest["matches"][0]["windows"]
    assert [window["origin_sample_id"] for window in windows] == [
        "period_1/sample_75",
        "period_1/sample_76",
        "period_1/sample_77",
        "period_2/sample_175",
        "period_2/sample_176",
        "period_2/sample_177",
    ]


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


def test_output_rejects_symlinked_ancestor_without_redirecting_writes(tmp_path):
    inputs = _persist(tmp_path / "inputs", synthetic_sources())
    target = tmp_path / "target"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(OSError):
        streaming.produce_streaming_population_draft_v1(inputs, alias / "output")
    assert not (target / "output").exists()


def test_input_rejects_symlinked_ancestor(tmp_path):
    root = tmp_path / "inputs"
    inputs = _persist(root, synthetic_sources())
    alias = tmp_path / "input-alias"
    alias.symlink_to(root, target_is_directory=True)
    linked_inputs = tuple(
        replace(
            item,
            metadata_path=alias / item.match_id / item.metadata_path.name,
            tracking_jsonl_path=alias / item.match_id / item.tracking_jsonl_path.name,
            phase_intervals_path=alias / item.match_id / item.phase_intervals_path.name,
        )
        for item in inputs
    )
    output = tmp_path / "output"
    with pytest.raises(OSError):
        streaming.produce_streaming_population_draft_v1(linked_inputs, output)
    assert (output / ".incomplete").exists()
    assert (output / "receipt.json").exists() is False


def test_output_must_be_separate_from_input_tree(tmp_path):
    inputs_root = tmp_path / "inputs"
    inputs = _persist(inputs_root, synthetic_sources())
    with pytest.raises(ValueError, match="input directory tree"):
        streaming.produce_streaming_population_draft_v1(inputs, inputs_root / "output")
    assert (inputs_root / "output").exists() is False


def test_output_rejects_shared_writable_ancestor(tmp_path):
    inputs = _persist(tmp_path / "inputs", synthetic_sources())
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o700)
    shared.chmod(0o777)
    try:
        with pytest.raises(ValueError, match="shared-writable"):
            streaming.produce_streaming_population_draft_v1(inputs, shared / "output")
        assert (shared / "output").exists() is False
    finally:
        shared.chmod(0o700)


def _extended_inputs(
    root: Path,
    end_frame: int,
    *,
    source_end_frame: int | None = None,
):
    source_end_frame = end_frame if source_end_frame is None else source_end_frame
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
            for frame_number in range(100, source_end_frame):
                frame = copy.deepcopy(template)
                frame["frame"] = frame_number
                frame["period"] = 1 if frame_number < end_frame else None
                frame["timestamp"] = (
                    f"{frame_number // 36000:02d}:"
                    f"{frame_number // 600 % 60:02d}:"
                    f"{frame_number // 10 % 60:02d}.{frame_number % 10}0"
                )
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


def _measure_in_worker_process(inputs, output: Path) -> dict[str, int | str]:
    worker = textwrap.dedent(
        """
        import gc
        import json
        import resource
        import sys
        import tracemalloc
        from pathlib import Path
        from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
            streaming_population_producer_v1 as streaming,
        )

        inputs = [
            streaming.StreamingPopulationMatchInputV1(
                item["match_id"],
                Path(item["metadata"]),
                Path(item["tracking"]),
                Path(item["phases"]),
            )
            for item in json.loads(sys.argv[1])
        ]
        output = Path(sys.argv[2])
        gc.collect()
        tracemalloc.start()
        result = streaming.produce_streaming_population_draft_v1(inputs, output)
        _, allocation_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        receipt = json.loads((result.output_directory / "receipt.json").read_bytes())
        candidate_count = sum(
            item["candidate_window_count"] for item in receipt["match_counts"]
        )
        output_bytes = sum(
            path.stat().st_size for path in result.output_directory.iterdir()
        )
        print(json.dumps({
            "source_rows": sum(item["source_frame_count"] for item in receipt["input_receipts"]),
            "candidate_count": candidate_count,
            "output_bytes": output_bytes,
            "tracemalloc_peak_bytes": allocation_peak,
            "rss_peak_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            "status": receipt["status"],
        }))
        """
    )
    serialized_inputs = json.dumps(
        [
            {
                "match_id": item.match_id,
                "metadata": str(item.metadata_path),
                "tracking": str(item.tracking_jsonl_path),
                "phases": str(item.phase_intervals_path),
            }
            for item in inputs
        ]
    )
    try:
        completed = subprocess.run(
            [sys.executable, "-c", worker, serialized_inputs, str(output)],
            check=True,
            capture_output=True,
            cwd=Path(__file__).resolve().parents[2],
            text=True,
        )
    except subprocess.CalledProcessError as error:
        raise AssertionError(f"separate measurement worker failed: {error.stderr}") from error
    return json.loads(completed.stdout.splitlines()[-1])


def test_separate_worker_memory_stays_bounded_at_10x_input_scale(tmp_path):
    small = _persist(tmp_path / "small-input", complete_10hz_sources(synthetic_sources()))
    large = _extended_inputs(
        tmp_path / "large-input",
        280,
        source_end_frame=960,
    )
    small_metrics = _measure_in_worker_process(small, tmp_path / "small-output")
    large_metrics = _measure_in_worker_process(large, tmp_path / "large-output")
    print(
        "streaming-memory "
        f"source_rows={small_metrics['source_rows']}->{large_metrics['source_rows']} "
        f"candidate_count={small_metrics['candidate_count']}->{large_metrics['candidate_count']} "
        f"output_bytes={small_metrics['output_bytes']}->{large_metrics['output_bytes']} "
        f"tracemalloc_peak_bytes={small_metrics['tracemalloc_peak_bytes']}"
        f"->{large_metrics['tracemalloc_peak_bytes']} "
        f"rss_peak_bytes={small_metrics['rss_peak_bytes']}->{large_metrics['rss_peak_bytes']}"
    )
    assert small_metrics["source_rows"] == 20 * 86
    assert large_metrics["source_rows"] >= small_metrics["source_rows"] * 10
    assert small_metrics["candidate_count"] == 20 * 3
    assert large_metrics["candidate_count"] == 20 * 65
    assert large_metrics["candidate_count"] >= small_metrics["candidate_count"] * 10
    assert large_metrics["output_bytes"] >= small_metrics["output_bytes"] * 3
    assert large_metrics["tracemalloc_peak_bytes"] <= (
        small_metrics["tracemalloc_peak_bytes"] + 1_000_000
    )
    assert large_metrics["rss_peak_bytes"] <= small_metrics["rss_peak_bytes"] + 32 * 1024 * 1024
    assert small_metrics["status"] == large_metrics["status"] == "UNQUALIFIED"
