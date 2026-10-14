"""Original synthetic bytes only; never access restricted storage in tests."""

import hashlib
import json
import runpy
import subprocess
from pathlib import Path

import pytest

from fpdbench.data_sources.skillcorner import git_blob_sha
from fpdbench.data_states.skillcorner import iter_skillcorner_5hz, load_manifest

SCRIPT = Path(__file__).resolve().parents[2] / "tools/qualify_skillcorner_source.py"
preflight = runpy.run_path(str(SCRIPT))


def test_null_ball_flag_independently_detected_and_frozen_transform_rejects():
    metadata = {
        "id": 2017461,
        "home_team": {"id": 101},
        "away_team": {"id": 202},
        "pitch_length": 100,
        "pitch_width": 60,
        "players": [],
    }
    frame = {
        "frame": 100,
        "period": 1,
        "timestamp": "00:00:10.00",
        "player_data": [],
        "ball_data": {"x": None, "y": None, "z": None, "is_detected": None},
        "possession": None,
        "image_corners_projection": None,
    }
    counts, violations = preflight["raw_schema_scan"]([frame])
    assert counts["ball_detection_not_boolean"] == 1
    assert violations == [
        {
            "row_number": 1,
            "source_frame": 100,
            "field": "ball_data.is_detected",
            "value_type": "NoneType",
            "coordinate_pair_missing": True,
        }
    ]
    with pytest.raises(ValueError, match="ball is_detected must be boolean"):
        list(
            iter_skillcorner_5hz(
                [frame], metadata, source_release_id=load_manifest()["source_release_id"]
            )
        )


def test_absent_ball_and_extrapolated_observations_are_not_coerced():
    frames = [
        {
            "frame": index,
            "ball_data": None if index == 0 else {"is_detected": False},
            "player_data": [{"is_detected": False}],
        }
        for index in range(84)
    ]
    counts, violations = preflight["raw_schema_scan"](frames)
    assert violations == []
    assert counts["source_rows"] == 84
    assert counts["even_source_rows"] == 42
    assert counts["retained_row_support_count_upper_bound"] == 2


@pytest.mark.parametrize("frames", [[0, 0], [2, 0], [True]])
def test_independent_scan_rejects_invalid_order(frames):
    with pytest.raises(ValueError, match="frame order or type"):
        preflight["raw_schema_scan"](
            [{"frame": frame, "ball_data": None, "player_data": []} for frame in frames]
        )


@pytest.mark.parametrize(
    "payload", [b"short", b"wrong", b"version https://git-lfs.github.com/spec/v1\n"]
)
def test_payload_gate_rejects_truncation_corruption_and_pointer(payload):
    with pytest.raises(ValueError):
        preflight["verify_payload"](
            payload, {"lfs_payload_size": 5, "lfs_oid_sha256": hashlib.sha256(b"right").hexdigest()}
        )


def test_restricted_output_rejects_repo_permissions_and_overwrite(tmp_path):
    with pytest.raises(ValueError, match="outside the repository"):
        preflight["private_directory"](SCRIPT.parent)
    tmp_path.chmod(0o755)
    with pytest.raises(ValueError, match="0700"):
        preflight["private_directory"](tmp_path)
    tmp_path.chmod(0o700)
    assert preflight["private_directory"](tmp_path) == tmp_path.resolve()
    path = tmp_path / "receipt.json"
    preflight["write_private"](path, {"status": "FAIL"})
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        preflight["write_private"](path, {"status": "PASS"})
    assert json.loads(path.read_text()) == {"status": "FAIL"}


def test_source_preflight_pinned_git_objects_and_actual_lfs_bytes(tmp_path, monkeypatch):
    root = tmp_path / "source"
    directory = root / "data/matches/2017461"
    directory.mkdir(parents=True)
    index = root / "data/matches.json"
    index.write_bytes(b'[{"id":2017461}]')
    payload = b"original synthetic tracking bytes\n"
    oid = hashlib.sha256(payload).hexdigest()
    pointer = (
        f"version https://git-lfs.github.com/spec/v1\noid sha256:{oid}\nsize {len(payload)}\n"
    ).encode()
    tracking = directory / "2017461_tracking_extrapolated.jsonl"
    tracking.write_bytes(pointer)

    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.DEVNULL)

    git("init")
    git("add", ".")
    git(
        "-c",
        "user.name=Synthetic",
        "-c",
        "user.email=synthetic@example.invalid",
        "commit",
        "-m",
        "Synthetic source only",
    )
    revision = git("rev-parse", "HEAD").decode().strip()
    manifest = {
        "upstream": {"pinned_commit": revision},
        "selected_source_matches": [2017461],
        "source_index": {
            "repository_path": "data/matches.json",
            "git_blob_sha": git_blob_sha(index.read_bytes()),
            "raw_sha256": hashlib.sha256(index.read_bytes()).hexdigest(),
        },
        "available_matches": [
            {
                "match_id": 2017461,
                "files": [
                    {
                        "repository_path": (
                            "data/matches/2017461/2017461_tracking_extrapolated.jsonl"
                        ),
                        "identity_type": "git_lfs_pointer",
                        "git_blob_sha": git_blob_sha(pointer),
                        "byte_size": len(pointer),
                        "lfs_oid_sha256": oid,
                        "lfs_payload_size": len(payload),
                    }
                ],
            }
        ],
    }
    namespace = preflight["source_preflight"].__globals__
    monkeypatch.setitem(namespace, "load_manifest", lambda: manifest)
    monkeypatch.setitem(namespace, "validate_manifest", lambda _: ())
    with pytest.raises(ValueError, match="unresolved"):
        preflight["source_preflight"](root)
    tracking.write_bytes(payload)
    receipts = preflight["source_preflight"](root)
    assert receipts[1]["sha256"] == oid
    assert receipts[1]["pointer_sha256"] == hashlib.sha256(pointer).hexdigest()
    manifest["upstream"]["pinned_commit"] = "0" * 40
    with pytest.raises(ValueError, match="revision mismatch"):
        preflight["source_preflight"](root)
    manifest["upstream"]["pinned_commit"] = revision
    tracking.unlink()
    with pytest.raises(ValueError, match="inventory"):
        preflight["source_preflight"](root)
