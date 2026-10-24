from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

import pytest

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    streaming_population_verifier_v1 as verifier,
)

MODULE = (
    "fpdbench.benchmarks.conditional_multi_agent_motion_prediction.streaming_population_verifier_v1"
)
FIXTURE_ARCHIVE = (
    Path(__file__).parents[1] / "fixtures/streaming-verifier-v1/pr25-synthetic-fixtures.zip"
)
FIXTURE_ARCHIVE_SHA256 = "86b1b82e2f14a586df17b18a180f6652bd269dfeaeb57f601ed9aee77bed7671"
PRODUCER_COMMIT = "aad8888eb6c7c046e4dfbce866886bf2ec8dd123"
PRODUCER_IDENTITY = "c3a81aa35599608711be85e3eacd9946bdd762937ef1bd08431a88ba415d20fc"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _rewrite_jsonl(path: Path, transform) -> None:
    temporary = path.with_name(f".{path.name}.mutation")
    with path.open("rb") as source, temporary.open("wb") as target:
        for line in source:
            value = transform(json.loads(line))
            if value is not None:
                target.write(_canonical(value) + b"\n")
    temporary.replace(path)


def _rewrite_receipt(artifact_root: Path, fields: dict[str, str]) -> None:
    path = artifact_root / "receipt.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    for field, filename in fields.items():
        receipt[field] = _sha256_file(artifact_root / filename)
    receipt.pop("receipt_sha256", None)
    receipt["receipt_sha256"] = hashlib.sha256(_canonical(receipt)).hexdigest()
    path.write_bytes(_canonical(receipt))


def _rewrite_receipt_values(artifact_root: Path, values: dict[str, object]) -> None:
    path = artifact_root / "receipt.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt.update(values)
    receipt.pop("receipt_sha256", None)
    receipt["receipt_sha256"] = hashlib.sha256(_canonical(receipt)).hexdigest()
    path.write_bytes(_canonical(receipt))


def _copy_artifacts(bundle, case: str, tmp_path: Path) -> Path:
    target = tmp_path / "artifacts"
    shutil.copytree(bundle.root / case / "artifacts", target)
    return target


def _run_verifier(
    bundle,
    case: str,
    tmp_path: Path,
    *,
    input_root: Path | None = None,
    artifact_root: Path | None = None,
    producer_root: Path | None = None,
) -> dict[str, object]:
    source = input_root or bundle.root / case / "inputs"
    artifacts = artifact_root or bundle.root / case / "artifacts"
    package = producer_root or bundle.producer_root
    report_path = tmp_path / "report.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            MODULE,
            "--input-root",
            str(source),
            "--artifact-root",
            str(artifacts),
            "--producer-package-root",
            str(package),
            "--report",
            str(report_path),
        ],
        capture_output=True,
        check=False,
        text=True,
        timeout=180,
    )
    assert result.returncode in {0, 1}, result.stderr
    return json.loads(report_path.read_text(encoding="utf-8"))


def _run_verifier_in_process(
    bundle,
    case: str,
    tmp_path: Path,
    *,
    input_root: Path,
) -> dict[str, object]:
    return verifier.verify_population(
        input_root,
        bundle.root / case / "artifacts",
        bundle.producer_root,
        tmp_path / "report.json",
    )


def _assert_report_entry(
    report: dict[str, object], category: str, *, record: bool = False
) -> dict[str, object]:
    counts = report["mismatch_counts_by_category"]
    assert isinstance(counts, dict) and counts.get(category, 0) > 0
    entries = report["mismatches"]
    assert isinstance(entries, list)
    entry = next(item for item in entries if item["category"] == category)
    assert entry["expected_sha256"] is None or len(entry["expected_sha256"]) == 64
    assert entry["actual_sha256"] is None or len(entry["actual_sha256"]) == 64
    if record:
        identity = entry["identity"]
        assert {"match_id", "origin_sample_id", "record_index"} <= set(identity)
    return entry


def _replace_file_with_same_bytes(path: Path) -> None:
    replacement = path.with_name(f".{path.name}.replacement")
    replacement.write_bytes(path.read_bytes())
    replacement.replace(path)


def _mutate_file_in_place(path: Path) -> None:
    with path.open("ab") as stream:
        stream.write(b"\n")


@pytest.fixture(scope="session")
def fixture_bundle(tmp_path_factory):
    assert _sha256_file(FIXTURE_ARCHIVE) == FIXTURE_ARCHIVE_SHA256
    producer_root_value = os.environ.get("FPDBENCH_PR25_PACKAGE_ROOT")
    assert producer_root_value, "CI must provide the pinned PR #25 source package"
    producer_root = Path(producer_root_value).resolve(strict=True)
    assert producer_root.is_dir()

    root = tmp_path_factory.mktemp("pr25-synthetic-fixtures")
    with zipfile.ZipFile(FIXTURE_ARCHIVE) as archive:
        for info in archive.infolist():
            relative = PurePosixPath(info.filename)
            mode = info.external_attr >> 16
            assert not relative.is_absolute() and ".." not in relative.parts
            assert not stat.S_ISLNK(mode)
            destination = root.joinpath(*relative.parts)
            if info.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)

    manifest = json.loads((root / "fixture-manifest.json").read_text(encoding="utf-8"))
    assert manifest["producer_commit"] == PRODUCER_COMMIT
    assert manifest["producer_source_package_identity_sha256"] == PRODUCER_IDENTITY
    assert (
        manifest["worker_execution"]
        == "separate isolated virtual environment with PR #25 wheel installed"
    )
    listed: set[str] = set()
    for case in manifest["cases"].values():
        for record in case["files"]:
            path = root / record["path"]
            listed.add(record["path"])
            assert path.stat().st_size == record["size"]
            assert _sha256_file(path) == record["sha256"]
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "fixture-manifest.json"
    }
    assert actual == listed
    return type(
        "FixtureBundle",
        (),
        {"root": root, "producer_root": producer_root, "manifest": manifest},
    )()


@pytest.mark.parametrize(
    "case",
    [
        "complete_10hz",
        "two_periods",
        "resource_scale",
        "missing_odd_frames",
        "missing_even_frame",
        "sparse_support",
        "eligibility_truth_edges",
        "incomplete_population",
    ],
)
def test_reconciles_isolated_pr25_outputs(fixture_bundle, tmp_path, case: str) -> None:
    report = _run_verifier(fixture_bundle, case, tmp_path)
    assert report["status"] == "RECONCILED_NON_AUTHORITATIVE"
    assert report["producer_source_package_verified"] is True
    assert report["producer_package_identity_sha256"] == PRODUCER_IDENTITY
    assert report["qualification"] == "NOT_PERFORMED"
    assert (
        report.get("producer_runtime_attestation", report.get("runtime_attestation"))
        == "NOT_PROVIDED"
    )
    assert report["runtime_gate"] == "BLOCKED"
    assert report["mismatch_count"] == 0


@pytest.mark.parametrize(
    ("filename", "mutation"),
    [("metadata.json", "replace"), ("phases.json", "mutate")],
)
def test_contract_snapshot_changes_after_initial_read_stop_before_membership(
    fixture_bundle, tmp_path, monkeypatch, filename: str, mutation: str
) -> None:
    input_root = tmp_path / "inputs"
    shutil.copytree(fixture_bundle.root / "complete_10hz/inputs", input_root)
    match_id = fixture_bundle.manifest["modified_match_id"]
    path = input_root / match_id / filename
    original_scan = verifier._global_drift_scan

    def mutate_then_scan(*args, **kwargs):
        if mutation == "replace":
            _replace_file_with_same_bytes(path)
        else:
            _mutate_file_in_place(path)
        return original_scan(*args, **kwargs)

    monkeypatch.setattr(verifier, "_global_drift_scan", mutate_then_scan)
    report = _run_verifier_in_process(
        fixture_bundle, "complete_10hz", tmp_path, input_root=input_root
    )
    assert report["status"] == "INPUT_SNAPSHOT_MISMATCH"
    assert report["membership_verification_started"] is False
    _assert_report_entry(report, "INPUT_SNAPSHOT_MISMATCH")


def test_tracking_replacement_after_drift_scan_stops_second_pass(
    fixture_bundle, tmp_path, monkeypatch
) -> None:
    input_root = tmp_path / "inputs"
    shutil.copytree(fixture_bundle.root / "complete_10hz/inputs", input_root)
    match_id = fixture_bundle.manifest["modified_match_id"]
    tracking = input_root / match_id / "tracking.jsonl"
    original_scan = verifier._global_drift_scan

    def scan_then_replace(*args, **kwargs):
        result = original_scan(*args, **kwargs)
        _replace_file_with_same_bytes(tracking)
        return result

    monkeypatch.setattr(verifier, "_global_drift_scan", scan_then_replace)
    report = _run_verifier_in_process(
        fixture_bundle, "complete_10hz", tmp_path, input_root=input_root
    )
    assert report["status"] == "INPUT_SNAPSHOT_MISMATCH"
    assert report["membership_verification_started"] is True
    _assert_report_entry(report, "INPUT_SNAPSHOT_MISMATCH")


@pytest.mark.parametrize("filename", ["metadata.json", "phases.json", "tracking.jsonl"])
def test_final_input_snapshot_rejects_changes_after_derivation(
    fixture_bundle, tmp_path, monkeypatch, filename: str
) -> None:
    input_root = tmp_path / "inputs"
    shutil.copytree(fixture_bundle.root / "complete_10hz/inputs", input_root)
    match_id = fixture_bundle.manifest["modified_match_id"]
    path = input_root / match_id / filename

    def mutate_after_derivation(*args, **kwargs):
        return object()

    def mutate_after_output_compare(*args, **kwargs):
        if filename == "phases.json":
            _mutate_file_in_place(path)
        else:
            _replace_file_with_same_bytes(path)
        return {}

    monkeypatch.setattr(verifier, "_build_expected_population", mutate_after_derivation)
    monkeypatch.setattr(verifier, "_compare_output_set", mutate_after_output_compare)
    report = _run_verifier_in_process(
        fixture_bundle, "complete_10hz", tmp_path, input_root=input_root
    )
    assert report["status"] == "INPUT_SNAPSHOT_MISMATCH"
    assert report["membership_verification_started"] is True
    _assert_report_entry(report, "INPUT_SNAPSHOT_MISMATCH")


def test_omitting_odd_frames_preserves_reconstructed_population(fixture_bundle) -> None:
    baseline = fixture_bundle.root / "complete_10hz" / "artifacts"
    without_odd = fixture_bundle.root / "missing_odd_frames" / "artifacts"
    for name in (
        "candidates.jsonl",
        "diagnostic-census.jsonl",
        "manifest.json",
        "truth.jsonl",
    ):
        assert _sha256_file(baseline / name) == _sha256_file(without_odd / name)
    assert _sha256_file(baseline / "receipt.json") != _sha256_file(without_odd / "receipt.json")


def test_threshold_warnings_masks_and_nonzero_anchors(fixture_bundle) -> None:
    case = fixture_bundle.root / "eligibility_truth_edges"
    match_id = fixture_bundle.manifest["modified_match_id"]
    valid_ball_counts: set[int] = set()
    exclusion_codes: set[str] = set()
    warning_codes: set[str] = set()
    threshold_states: set[bool] = set()
    for line in (case / "artifacts/candidates.jsonl").open(encoding="utf-8"):
        row = json.loads(line)
        if row["match_id"] != match_id:
            continue
        diagnostic = row["diagnostic"]
        valid_ball_counts.add(diagnostic["quality"]["ball_observations"]["valid_position_count"])
        exclusion_codes.update(item["code"] for item in diagnostic["exclusion_reasons"])
        warning_codes.update(item["code"] for item in diagnostic["warnings"])
        if diagnostic["quality"]["ball_observations"]["valid_position_count"] in {38, 39}:
            threshold_states.add(diagnostic["candidate_rules_pass"])
    assert {38, 39} <= valid_ball_counts
    assert threshold_states == {False, True}
    assert "BALL_COVERAGE_BELOW_MINIMUM" in exclusion_codes
    assert {
        "BALL_DISPLACEMENT_OUTLIER",
        "BALL_OUTSIDE_PITCH",
        "PLAYER_COORDINATES_MISSING",
    } <= warning_codes

    truth_path = case / "artifacts/truth.jsonl"
    partial_mask = False
    nonzero_anchor = False
    for line in truth_path.open(encoding="utf-8"):
        row = json.loads(line)
        if row["match_id"] == match_id and row["origin_sample_id"] == "period_1/sample_76":
            if row["scene_id"] == "home":
                partial_mask = row["truth_mask"][13][0] is False
                nonzero_anchor = row["origin_xy"][0][0] != 0
    assert partial_mask and nonzero_anchor


def test_two_periods_have_separate_grids_and_incomplete_support_is_reported(fixture_bundle) -> None:
    rows = [
        json.loads(line)
        for line in (fixture_bundle.root / "two_periods/artifacts/candidates.jsonl").open()
    ]
    origins = {row["origin_sample_id"].split("/")[0] for row in rows}
    assert origins == {"period_1", "period_2"}
    incomplete = fixture_bundle.root / "incomplete_population/artifacts"
    assert (incomplete / ".incomplete").is_file()
    assert not (incomplete / "manifest.json").exists()
    assert not (incomplete / "truth.jsonl").exists()
    receipt = json.loads((incomplete / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "INCOMPLETE"
    assert receipt["independent_verification"] == "NOT_PERFORMED"


def test_verifier_source_has_no_scientific_implementation_imports() -> None:
    source_path = (
        Path(__file__).parents[2]
        / "src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/"
        "streaming_population_verifier_v1.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported = {
        node.module.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imported.update(
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert "fpdbench" not in imported


def test_fabricated_self_hashed_receipt_cannot_replace_pinned_identity(
    fixture_bundle, tmp_path
) -> None:
    artifacts = _copy_artifacts(fixture_bundle, "complete_10hz", tmp_path)
    path = artifacts / "receipt.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt["worker_package_identity"]["sha256"] = "f" * 64
    receipt.pop("receipt_sha256")
    receipt["receipt_sha256"] = hashlib.sha256(_canonical(receipt)).hexdigest()
    path.write_bytes(_canonical(receipt))
    report = _run_verifier(fixture_bundle, "complete_10hz", tmp_path, artifact_root=artifacts)
    assert report["status"] == "MISMATCH"
    entry = _assert_report_entry(report, "PRODUCER_PROVENANCE_MISMATCH")
    assert entry["identity"]["field"].startswith("/worker_package_identity")
    assert report["producer_source_package_verified"] is True
    assert report["runtime_gate"] == "BLOCKED"


@pytest.mark.parametrize(
    ("artifact", "category", "mutation"),
    [
        ("truth.jsonl", "TRUTH_MASK_MISMATCH", "mask"),
        ("truth.jsonl", "PHYSICAL_TRUTH_MISMATCH", "physical"),
    ],
)
def test_rehashed_truth_mutations_still_fail_raw_reconstruction(
    fixture_bundle, tmp_path, artifact: str, category: str, mutation: str
) -> None:
    artifacts = _copy_artifacts(fixture_bundle, "complete_10hz", tmp_path)

    def alter(row):
        if row["scene_id"] == "home":
            if mutation == "mask":
                row["truth_mask"][0][0] = not row["truth_mask"][0][0]
            else:
                row["absolute_xy"][0][0][0] += 0.25
            return row
        return row

    _rewrite_jsonl(artifacts / artifact, alter)
    _rewrite_receipt(artifacts, {"truth_jsonl_sha256": artifact})
    report = _run_verifier(fixture_bundle, "complete_10hz", tmp_path, artifact_root=artifacts)
    assert report["status"] == "MISMATCH"
    _assert_report_entry(report, category, record=True)


def test_changed_manifest_role_is_detected_after_self_hash_recalculation(
    fixture_bundle, tmp_path
) -> None:
    artifacts = _copy_artifacts(fixture_bundle, "complete_10hz", tmp_path)
    path = artifacts / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["matches"][0]["role"] = "evaluation"
    manifest["manifest_sha256"] = hashlib.sha256(
        _canonical({key: value for key, value in manifest.items() if key != "manifest_sha256"})
    ).hexdigest()
    path.write_bytes(_canonical(manifest))
    _rewrite_receipt(
        artifacts,
        {"manifest_json_sha256": "manifest.json"},
    )
    _rewrite_receipt_values(artifacts, {"population_manifest_sha256": manifest["manifest_sha256"]})
    report = _run_verifier(fixture_bundle, "complete_10hz", tmp_path, artifact_root=artifacts)
    assert report["status"] == "MISMATCH"
    entry = _assert_report_entry(report, "MANIFEST_MATCH_ROLE_MISMATCH")
    assert entry["identity"]["match_id"]


def test_missing_and_reordered_rows_have_exact_record_reports(fixture_bundle, tmp_path) -> None:
    artifacts = _copy_artifacts(fixture_bundle, "complete_10hz", tmp_path)
    candidate_path = artifacts / "candidates.jsonl"
    lines = candidate_path.read_bytes().splitlines(keepends=True)
    candidate_path.write_bytes(b"".join(lines[:-1]))
    _rewrite_receipt(artifacts, {"candidates_jsonl_sha256": "candidates.jsonl"})
    report = _run_verifier(fixture_bundle, "complete_10hz", tmp_path, artifact_root=artifacts)
    assert report["status"] == "MISMATCH"
    _assert_report_entry(report, "MISSING_RECORD", record=True)

    reordered = _copy_artifacts(fixture_bundle, "complete_10hz", tmp_path / "reordered")
    candidate_path = reordered / "candidates.jsonl"
    with candidate_path.open("rb") as source:
        first, second, *rest = source.readlines()
    candidate_path.write_bytes(second + first + b"".join(rest))
    _rewrite_receipt(reordered, {"candidates_jsonl_sha256": "candidates.jsonl"})
    report = _run_verifier(
        fixture_bundle, "complete_10hz", tmp_path / "reordered", artifact_root=reordered
    )
    assert report["status"] == "MISMATCH"
    _assert_report_entry(report, "RECORD_ORDER_OR_IDENTITY_MISMATCH", record=True)


def test_malformed_source_and_artifact_and_period_boundary_mutations_fail(
    fixture_bundle, tmp_path
) -> None:
    malformed_inputs = tmp_path / "malformed-inputs"
    shutil.copytree(fixture_bundle.root / "complete_10hz/inputs", malformed_inputs)
    tracking = malformed_inputs / fixture_bundle.manifest["modified_match_id"] / "tracking.jsonl"
    with tracking.open("rb") as source:
        _, *remaining = source.readlines()
    tracking.write_bytes(b"not-json\n" + b"".join(remaining))
    report = _run_verifier(fixture_bundle, "complete_10hz", tmp_path, input_root=malformed_inputs)
    assert report["status"] == "INVALID_INPUT"
    assert report["membership_verification_started"] is False

    malformed_outputs = _copy_artifacts(fixture_bundle, "complete_10hz", tmp_path / "bad-output")
    path = malformed_outputs / "candidates.jsonl"
    with path.open("rb") as source:
        _, *remaining = source.readlines()
    path.write_bytes(b"not-json\n" + b"".join(remaining))
    report = _run_verifier(
        fixture_bundle, "complete_10hz", tmp_path / "bad-output", artifact_root=malformed_outputs
    )
    assert report["status"] == "MISMATCH"
    _assert_report_entry(report, "MALFORMED_ARTIFACT_RECORD", record=True)

    boundary_inputs = tmp_path / "period-boundary-inputs"
    shutil.copytree(fixture_bundle.root / "two_periods/inputs", boundary_inputs)
    tracking = boundary_inputs / fixture_bundle.manifest["modified_match_id"] / "tracking.jsonl"
    changed = False

    def alter_boundary(row):
        nonlocal changed
        if not changed and row["period"] == 2:
            row["period"] = 1
            changed = True
        return row

    _rewrite_jsonl(tracking, alter_boundary)
    assert changed
    report = _run_verifier(
        fixture_bundle,
        "two_periods",
        tmp_path / "period-boundary",
        input_root=boundary_inputs,
    )
    assert report["status"] == "MISMATCH"
    assert report["membership_verification_started"] is True


def test_global_nullable_ball_drift_stops_before_membership(fixture_bundle, tmp_path) -> None:
    drift_inputs = tmp_path / "drift-inputs"
    shutil.copytree(fixture_bundle.root / "complete_10hz/inputs", drift_inputs)
    tracking = drift_inputs / fixture_bundle.manifest["modified_match_id"] / "tracking.jsonl"
    changed = False

    def add_drift(row):
        nonlocal changed
        if not changed and row["frame"] % 2 == 0:
            row["ball_data"]["is_detected"] = None
            changed = True
        return row

    _rewrite_jsonl(tracking, add_drift)
    assert changed
    report = _run_verifier(fixture_bundle, "complete_10hz", tmp_path, input_root=drift_inputs)
    assert report["status"] == "GLOBAL_DRIFT_STOP"
    assert report["membership_verification_started"] is False
    entry = _assert_report_entry(report, "GLOBAL_NULL_FLAG_FINITE_XY_DRIFT")
    assert entry["identity"]["scope"] == "all-retained-v2-samples"


def test_modified_producer_source_is_rejected_before_reconciliation(
    fixture_bundle, tmp_path
) -> None:
    package = tmp_path / "producer-package"
    shutil.copytree(fixture_bundle.producer_root, package)
    producer_file = (
        package
        / "benchmarks/conditional_multi_agent_motion_prediction/streaming_population_producer_v1.py"
    )
    with producer_file.open("ab") as stream:
        stream.write(b"\n# mutation\n")
    report = _run_verifier(fixture_bundle, "complete_10hz", tmp_path, producer_root=package)
    assert report["status"] == "PRODUCER_PROVENANCE_MISMATCH"
    assert report["producer_source_package_verified"] is False
    assert report["membership_verification_started"] is False


def test_mismatch_report_caps_entries_without_losing_total_count(fixture_bundle, tmp_path) -> None:
    artifacts = _copy_artifacts(fixture_bundle, "resource_scale", tmp_path)

    def mutate(row):
        row["eligibility_result_sha256"] = "0" * 64
        return row

    _rewrite_jsonl(artifacts / "candidates.jsonl", mutate)
    _rewrite_receipt(artifacts, {"candidates_jsonl_sha256": "candidates.jsonl"})
    report = _run_verifier(fixture_bundle, "resource_scale", tmp_path, artifact_root=artifacts)
    assert report["status"] == "MISMATCH"
    assert report["mismatch_counts_by_category"]["CANDIDATE_RECORD_MISMATCH"] == 1300
    assert report["reported_mismatch_count"] == 1000
    assert report["suppressed_mismatch_count"] == report["mismatch_count"] - 1000


def _measure_separate_worker(bundle, case: str, tmp_path: Path) -> dict[str, object]:
    script = "\n".join(
        [
            "import json, resource, sys, tracemalloc",
            "from pathlib import Path",
            "tracemalloc.start()",
            f"from {MODULE} import verify_population",
            "report = verify_population("
            "Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))",
            "_, peak = tracemalloc.get_traced_memory()",
            "rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024",
            "print(json.dumps({'status': report['status'], "
            "'tracemalloc_peak_bytes': peak, 'rss_peak_bytes': rss}))",
        ]
    )
    root = bundle.root / case
    report_path = tmp_path / f"{case}-memory-report.json"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(root / "inputs"),
            str(root / "artifacts"),
            str(bundle.producer_root),
            str(report_path),
        ],
        capture_output=True,
        check=False,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_source_and_artifact_scaling_keeps_worker_memory_bounded(fixture_bundle, tmp_path) -> None:
    small = fixture_bundle.root / "complete_10hz"
    large = fixture_bundle.root / "resource_scale"

    def size_and_rows(root: Path) -> tuple[int, int, int]:
        source_bytes = source_rows = candidates = artifact_bytes = 0
        for path in (root / "inputs").glob("*/tracking.jsonl"):
            source_bytes += path.stat().st_size
            with path.open("rb") as stream:
                source_rows += sum(1 for _ in stream)
        candidate_path = root / "artifacts/candidates.jsonl"
        with candidate_path.open("rb") as stream:
            candidates = sum(1 for _ in stream)
        artifact_bytes = sum(path.stat().st_size for path in (root / "artifacts").iterdir())
        return source_bytes, source_rows, candidates + artifact_bytes

    small_bytes, small_rows, small_output = size_and_rows(small)
    large_bytes, large_rows, large_output = size_and_rows(large)
    assert large_bytes >= 10 * small_bytes
    assert large_rows >= 10 * small_rows
    assert large_output >= 5 * small_output

    small_memory = _measure_separate_worker(fixture_bundle, "complete_10hz", tmp_path)
    large_memory = _measure_separate_worker(fixture_bundle, "resource_scale", tmp_path)
    assert small_memory["status"] == large_memory["status"] == "RECONCILED_NON_AUTHORITATIVE"
    assert large_memory["tracemalloc_peak_bytes"] < 32 * 1024 * 1024
    assert (
        large_memory["tracemalloc_peak_bytes"]
        <= small_memory["tracemalloc_peak_bytes"] + 16 * 1024 * 1024
    )
    assert large_memory["rss_peak_bytes"] <= small_memory["rss_peak_bytes"] + 64 * 1024 * 1024
