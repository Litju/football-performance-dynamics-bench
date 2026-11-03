import importlib.util
import json
import os
import sys
import zipfile
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location(
    "research_baseline_v1", TOOLS / "research_baseline_v1.py"
)
assert spec and spec.loader
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_scene_mask_and_physical_representation():
    support = [{"players": [{"player_id": 1, "x_m": float(i), "y_m": 0.0}]} for i in range(26)]
    truth = {
        "player_ids": ["1"],
        "origin_xy": [[25.0, 0.0]],
        "absolute_xy": [[[float(26 + i), 0.0]] for i in range(15)],
        "origin_relative_displacement": [[[float(i + 1), 0.0]] for i in range(15)],
    }
    truth["absolute_xy"][3][0] = None
    truth["origin_relative_displacement"][3][0] = None
    scores = runner.score_scene(support, truth)
    assert scores["constant_velocity_1s_v1"] == pytest.approx((0, 0, 0), abs=1e-12)
    assert scores["origin_persistence_v1"][1] == pytest.approx(15)
    support.extend([{"ball": [999, 999], "players": [{"player_id": 999}]}] * 15)
    assert runner.score_scene(support, truth) == scores
    truth["origin_xy"] = [[0.0, 0.0]]
    with pytest.raises(ValueError, match="origin or player order"):
        runner.score_scene(support, truth)


def test_equal_weight_aggregation():
    assert runner.mean_metrics([(1, 2, 3), (3, 4, 5)]) == (2, 3, 4)
    with pytest.raises(ValueError):
        runner.mean_metrics([])


def test_rejects_unratified_manifest(tmp_path):
    (tmp_path / "research-admission.json").write_text('{"status":"RESEARCH_RECONCILED"}')
    with pytest.raises(ValueError, match="manifest identity"):
        runner.verify(tmp_path, tmp_path)


def test_no_final_truth_is_unscoreable():
    support = [
        {"players": [{"player_id": 1, "group": "home", "x_m": 1.0, "y_m": 2.0}]} for _ in range(41)
    ]
    support[-1] = {"players": []}
    _, truth, scoreable = runner.p._scene(support, "home")
    assert not scoreable
    assert truth["unscoreable_reason"] == "NO_FINAL_TARGET"
    with pytest.raises(ValueError, match="no valid final-horizon"):
        runner.score_scene(support, truth)


def test_stream_scoring_binds_reconstructed_truth(tmp_path, monkeypatch):
    from fpdbench.eligibility import skillcorner

    def protected_gate(*args, **kwargs):
        raise AssertionError("research scoring must not call protected admission")

    monkeypatch.setattr(skillcorner, "evaluate_skillcorner_window_v2", protected_gate)
    research = runner.research
    inputs = tmp_path / "inputs"
    fixture = TOOLS.parent / "tests/fixtures/streaming-verifier-v1/pr25-synthetic-fixtures.zip"
    with zipfile.ZipFile(fixture) as archive:
        for name in archive.namelist():
            prefix = "complete_10hz/inputs/"
            if name.startswith(prefix) and not name.endswith("/"):
                target = inputs / name.removeprefix(prefix)
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                target.write_bytes(archive.read(name))
                target.chmod(0o600)
    match = sorted(p.name for p in inputs.iterdir())[0]
    producer = tmp_path / "producer"
    producer.mkdir(mode=0o700)
    old = os.umask(0o077)
    try:
        summary = research.produce(inputs, match, producer / f"{match}.jsonl")
        research.write(producer / f"{match}.summary.json", summary)
        counts = {}
        for period in summary["periods"].values():
            for key, value in period.items():
                counts[key] = counts.get(key, 0) + value
        research.write(
            tmp_path / "research-admission.json",
            {
                "per_match": {match: {"counts": counts}},
                "artifacts": {match: {"producer_sha256": summary["artifact_sha256"]}},
            },
        )
        research.write(
            tmp_path / "independent-source.json",
            {
                "normalization_receipts": [
                    {
                        "match_id": match,
                        "metadata_sha256": research.digest(inputs / match / "metadata.json"),
                    }
                ]
            },
        )
        result = runner.score_match(tmp_path, match, summary["role"])
        assert result["windows"] == counts["scoreable_windows"]
        artifact = producer / f"{match}.jsonl"
        rows = [json.loads(line) for line in artifact.read_bytes().splitlines()]
        scene = next(row["scenes"][0] for row in rows if row["scenes"])
        scene["truth_mask"][0][0] = not scene["truth_mask"][0][0]
        artifact.write_bytes(b"".join(research.canonical(row) + b"\n" for row in rows))
        with pytest.raises(ValueError, match="scene, truth or mask mismatch"):
            runner.score_match(tmp_path, match, summary["role"])
    finally:
        os.umask(old)
