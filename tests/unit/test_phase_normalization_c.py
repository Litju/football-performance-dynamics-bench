import json

import pytest

from fpdbench.data_sources.phase_normalization_c import normalize_phases_c
from fpdbench.data_sources.protected_skillcorner import normalize_phases
from fpdbench.data_sources.skillcorner import canonical_bytes

METADATA = canonical_bytes(
    {
        "match_periods": [
            {"period": 1, "start_frame": 100, "end_frame": 200},
            {"period": 2, "start_frame": 220, "end_frame": 300},
        ]
    }
)


def test_intersection_lineage_and_sensitivity():
    csv = (
        b"period,frame_start,frame_end,duration\n1,190,230,4\n"
        b"1,100,110,1\n1,100,110,1\n1,220,230,1\n2,220,230,1\n"
    )
    phases, lineage, shadow = normalize_phases_c(csv, METADATA)
    assert json.loads(phases) == [
        {"period": 1, "frame_start": 100, "frame_end": 110},
        {"period": 1, "frame_start": 100, "frame_end": 110},
        {"period": 1, "frame_start": 190, "frame_end": 200},
        {"period": 2, "frame_start": 220, "frame_end": 230},
    ]
    assert json.loads(lineage)["rows"][3]["disposition"] == "EMPTY_INTERSECTION"
    assert json.loads(shadow)["status"] == "NON_AUTHORITATIVE_SENSITIVITY"
    assert len(json.loads(shadow)["intervals"]) == 3
    assert normalize_phases_c(csv, METADATA) == (phases, lineage, shadow)
    assert normalize_phases_c(csv.replace(b"190,230", b"189,229"), METADATA)[1] != lineage


def test_legacy_and_ordering():
    first, second = b"100,110\n", b"220,230\n"
    header = b"frame_start,frame_end\n"
    phases, _, _ = normalize_phases_c(header + first + second, METADATA)
    assert phases == normalize_phases(header + second + first, json.loads(METADATA))
    assert phases == normalize_phases_c(header + second + first, METADATA)[0]


@pytest.mark.parametrize(
    "csv",
    [
        b"frame_start,frame_end\n190,230\n",
        b"period,frame_start,frame_end\n,190,230\n",
        b"period,frame_start,frame_end\n3,190,230\n",
        b"period,frame_start,frame_end,duration\n1,190,230,1\n",
        b"period,frame_start,frame_end\n1,200,200\n",
        b"period,frame_start,frame_end\n1,-1,200\n",
        b"period,frame_start,frame_end\n1,100,110,extra\n",
        b'period,frame_start,frame_end\n1,"100,110\n',
    ],
)
def test_invalid_rows_fail(csv):
    with pytest.raises(ValueError):
        normalize_phases_c(csv, METADATA)


def test_lineage_binds_original_bytes_and_overlapping_rows():
    import hashlib

    csv = b"period,frame_start,frame_end,team\n1,100,120,a\n1,110,130,b\n"
    phases, lineage, _ = normalize_phases_c(csv, METADATA)
    record = json.loads(lineage)
    assert record["source_sha256"] == hashlib.sha256(csv).hexdigest()
    assert record["metadata_sha256"] == hashlib.sha256(METADATA).hexdigest()
    assert record["normalized_sha256"] == hashlib.sha256(phases).hexdigest()
    assert [row["source_row"] for row in record["rows"]] == [1, 2]
    assert len(json.loads(phases)) == 2
    assert normalize_phases_c(csv, METADATA + b" ")[1] != lineage


def test_ambiguous_metadata_and_mismatched_match_identity_fail():
    ambiguous = canonical_bytes(
        {
            "match_periods": [
                {"period": 1, "start_frame": 100, "end_frame": 200},
                {"period": 2, "start_frame": 150, "end_frame": 250},
            ]
        }
    )
    with pytest.raises(ValueError):
        normalize_phases_c(b"period,frame_start,frame_end\n1,160,170\n", ambiguous)
    with pytest.raises(ValueError):
        normalize_phases_c(b"match_id,period,frame_start,frame_end\n4,1,100,110\n", METADATA)


def test_independent_rederivation_rejects_tampering():
    import hashlib

    from fpdbench.data_sources.phase_normalization_c import verify_phases_c

    source = b"period,frame_start,frame_end\n1,190,230\n1,220,230\n2,220,230\n"
    phases, lineage, shadow = normalize_phases_c(source, METADATA)
    verify_phases_c(source, METADATA, phases, lineage)
    original = json.loads(lineage)
    altered = []
    for mutation in (
        "bounds",
        "label",
        "missing",
        "duplicate",
        "reorder",
        "normalized",
        "period",
        "empty_missing",
        "empty_wrong",
        "source_hash",
        "metadata_hash",
        "output_hash",
    ):
        packet = json.loads(lineage)
        rows = packet["rows"]
        if mutation == "bounds":
            rows[0]["raw_start"] -= 1
        elif mutation == "label":
            rows[0]["source_period"] = "2"
        elif mutation == "missing":
            rows.pop(0)
        elif mutation == "duplicate":
            rows.append(rows[0])
        elif mutation == "reorder":
            rows.reverse()
        elif mutation == "normalized":
            rows[0]["normalized"]["frame_end"] -= 1
        elif mutation == "period":
            rows[0]["normalized"]["period"] = 2
        elif mutation == "empty_missing":
            del rows[1]["disposition"]
        elif mutation == "empty_wrong":
            rows[1]["disposition"] = "COVERED"
        else:
            packet[
                {
                    "source_hash": "source_sha256",
                    "metadata_hash": "metadata_sha256",
                    "output_hash": "normalized_sha256",
                }[mutation]
            ] = "0" * 64
        altered.append(canonical_bytes(packet))
    for packet in altered:
        with pytest.raises(ValueError):
            verify_phases_c(source, METADATA, phases, packet)
    for modified in (source.replace(b"190,230", b"189,230"), source.replace(b"1,190", b"2,190")):
        with pytest.raises(ValueError):
            verify_phases_c(modified, METADATA, phases, lineage)
    with pytest.raises(ValueError):
        verify_phases_c(source, METADATA + b" ", phases, lineage)
    for field, value in (("frame_end", 199), ("period", 2)):
        changed_output = json.loads(phases)
        changed_output[0][field] = value
        packet = json.loads(lineage)
        modified_bytes = canonical_bytes(changed_output)
        packet["normalized_sha256"] = hashlib.sha256(modified_bytes).hexdigest()
        with pytest.raises(ValueError):
            verify_phases_c(source, METADATA, modified_bytes, canonical_bytes(packet))
    forged_phases = canonical_bytes(json.loads(shadow)["intervals"])
    original["normalized_sha256"] = hashlib.sha256(forged_phases).hexdigest()
    original["rows"][0]["normalized"] = None
    original["rows"][0]["disposition"] = "EMPTY_INTERSECTION"
    with pytest.raises(ValueError):
        verify_phases_c(source, METADATA, forged_phases, canonical_bytes(original))
    with pytest.raises(ValueError):
        verify_phases_c(source, METADATA, shadow, lineage)


def test_synthetic_census_arithmetic():
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "census", Path(__file__).parents[2] / "tools/replay_phase_c_census.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    coverage = module.coverage

    source = b"period,frame_start,frame_end\n1,100,180\n1,170,210\n1,100,180\n2,220,300\n"
    phases, _, shadow = normalize_phases_c(source, METADATA)
    assert coverage(json.loads(phases)) == (180, 10)
    assert coverage(json.loads(shadow)["intervals"]) == (160, 0)


def test_local_census_replay_checks_blob_identity(tmp_path, monkeypatch):
    import hashlib
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "census", Path(__file__).parents[2] / "tools/replay_phase_c_census.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "source"
    source.mkdir()
    records = []
    for name, payload in (
        ("1_match.json", METADATA),
        ("1_phases_of_play.csv", b"period,frame_start,frame_end\n1,100,110\n"),
    ):
        (source / name).write_bytes(payload)
        records.append(
            {
                "repository_path": name,
                "byte_size": len(payload),
                "git_blob_sha": hashlib.sha1(
                    b"blob " + str(len(payload)).encode() + b"\0" + payload
                ).hexdigest(),
                "pinned_source_url": f"https://raw.githubusercontent.com/SkillCorner/opendata/{module.REVISION}/{name}",
            }
        )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"available_matches": [{"match_id": 1, "files": records}]}))
    monkeypatch.setattr(module, "MANIFEST_PATH", manifest)
    monkeypatch.setattr(
        module.empirical_experiment_plan,
        "protocol_split_v2",
        lambda: {"roles": {"training": ["1"]}},
    )
    expected = {
        "matches": 1,
        "conflicting_matches": 0,
        "clean_matches": 1,
        "covered_frames_gain": 0,
        "theoretical_origins_gain": {"training": 0, "validation": 0, "evaluation": 0},
    }
    monkeypatch.setattr(module, "EXPECTED", expected)
    assert module.replay(source) == expected
    (source / "1_phases_of_play.csv").write_bytes(b"altered")
    with pytest.raises(ValueError, match="identity"):
        module.replay(source)
