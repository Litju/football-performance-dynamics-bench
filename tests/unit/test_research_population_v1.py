"""Research science reconciliation tests, including truth tampering; no real data."""

import importlib.util
import json
import os
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_research_reconstructs_and_rejects_changed_truth(tmp_path):
    producer = load("research_population_v1")
    verifier = load("research_population_verifier_v1")
    inputs = tmp_path / "inputs"
    with zipfile.ZipFile(
        ROOT / "tests/fixtures/streaming-verifier-v1/pr25-synthetic-fixtures.zip"
    ) as z:
        for name in z.namelist():
            prefix = "complete_10hz/inputs/"
            if name.startswith(prefix) and not name.endswith("/"):
                target = inputs / name.removeprefix(prefix)
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                target.write_bytes(z.read(name))
                target.chmod(0o600)
    match = sorted(p.name for p in inputs.iterdir())[0]
    outputs = [tmp_path / "producer", tmp_path / "verifier"]
    for path in outputs:
        path.mkdir(mode=0o700)
    old = os.umask(0o077)
    try:
        a = producer.produce(inputs, match, outputs[0] / f"{match}.jsonl")
        b = verifier.derive(inputs, match, outputs[1] / f"{match}.jsonl")
    finally:
        os.umask(old)
    assert a == b
    assert sum(p["rules_pass"] for p in a["periods"].values()) > 0
    for directory, summary in zip(outputs, (a, b), strict=True):
        producer.write(directory / f"{match}.summary.json", summary)
    expected = {match: a["tracking_sha256"]}
    assert producer.reconcile(*outputs, [match], expected)["total"]["rules_pass"] > 0
    artifact = outputs[0] / f"{match}.jsonl"
    rows = [json.loads(line) for line in artifact.read_bytes().splitlines()]
    scene = next(row["scenes"][0] for row in rows if row["scenes"])
    scene["absolute_xy"][0][0][0] += 1
    artifact.write_bytes(b"".join(producer.canonical(row) + b"\n" for row in rows))
    # Even a repaired producer self-hash cannot override the independent reconstruction.
    a["artifact_sha256"] = producer.digest(artifact)
    (outputs[0] / f"{match}.summary.json").write_bytes(producer.canonical(a))
    with pytest.raises(ValueError, match="independent scientific reconciliation"):
        producer.reconcile(*outputs, [match], expected)


def test_resource_shortfall_fails_before_materialization():
    runner = load("research_population_v1")
    census = {"total": {"C": {"theoretical": 10, "scoreable_scenes": 5}}}
    with pytest.raises(ValueError, match="insufficient disk"):
        runner.resource_estimate(census, runner.RESERVE)


def test_verifier_normalizes_labeled_phase_only_within_its_period():
    verifier = load("research_population_verifier_v1")
    from fpdbench.data_sources.phase_normalization_c import normalize_phases_c

    metadata = json.dumps(
        {
            "id": 1,
            "match_periods": [
                {"period": 1, "start_frame": 0, "end_frame": 100},
                {"period": 2, "start_frame": 100, "end_frame": 200},
            ],
        }
    ).encode()
    raw = b"period,frame_start,frame_end,duration\n1,90,110,2\n2,150,210,6\n"
    c, lineage, _ = normalize_phases_c(raw, metadata)
    assert verifier.normalize(raw, metadata) == (c, lineage)
    assert json.loads(c)[0] == {"period": 1, "frame_start": 90, "frame_end": 100}
