"""RES645 synthetic qualification: invented sources, artificial checkpoints, no real inputs."""

from __future__ import annotations

import copy
import functools
import hashlib
import io
import json
import os
import shutil
import stat
import sys
import tracemalloc
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).parent))
from test_population_producer_v2 import synthetic_sources  # noqa: E402
from test_streaming_population_producer_v1 import _persist  # noqa: E402

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (  # noqa: E402
    learned_deepsets as lds,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (  # noqa: E402
    res635_post_failure_evaluation as s,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (  # noqa: E402
    res635_verification as v,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (  # noqa: E402
    res645_checkpoints as ck,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (  # noqa: E402
    res645_fixtures as fx,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (  # noqa: E402
    res645_independent as ind,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (  # noqa: E402
    res645_paths as paths,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (  # noqa: E402
    res645_pipeline as pipe,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (  # noqa: E402
    res645_source_stream as src,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (  # noqa: E402
    res645_workloads as wl,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (  # noqa: E402
    streaming_population_producer_v1 as producer,
)
from fpdbench.data_sources.skillcorner import canonical_bytes  # noqa: E402


@pytest.fixture(scope="module")
def bundle(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return fx.build_bundle(tmp_path_factory.mktemp("res645") / "bundle")


@pytest.fixture(scope="module")
def workload(bundle: Path) -> wl.FixtureWorkload:
    return wl.FixtureWorkload(bundle)


@pytest.fixture(scope="module")
def frozen(workload: wl.FixtureWorkload) -> ck.FrozenModelSet:
    return workload.prepare()


@pytest.fixture(scope="module")
def receipts(workload: wl.FixtureWorkload, frozen: ck.FrozenModelSet) -> list[dict[str, Any]]:
    return [workload.score(i, workload.windows, frozen, lambda: None) for i in range(4)]


def clone(bundle: Path, tmp_path: Path) -> Path:
    target = tmp_path / "copy"
    shutil.copytree(bundle, target)
    return target


def test_metadata_inventory_never_loads_models_and_rejects_changed_checkpoint(
    bundle: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = clone(bundle, tmp_path)
    _, manifest, checkpoints = fx.read_bundle(target)
    monkeypatch.setattr(torch, "load", lambda *args, **kwargs: pytest.fail("deserialized"))
    assert ck.verify_inventory(manifest, checkpoints, target / "receipts", "synthetic") == (
        ck.validate_manifest(manifest, "synthetic")
    )
    path = next(checkpoints.glob("*.pt"))
    with path.open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ck.CheckpointContractError, match="SHA-256 mismatch"):
        ck.verify_inventory(manifest, checkpoints, target / "receipts", "synthetic")


def test_source_stream_accepts_separate_synthetic_population_lock(tmp_path: Path) -> None:
    directory = tmp_path / "match"
    fx.build_match(directory, 0, 46)
    spec = src.SourceMatchSpec("synthetic-match-0", fx.FIXTURE_MATCH_IDS[0], directory)
    original = src.SourceMatch(spec, "synthetic")
    original.prepare()
    expected = list(original.windows())
    lock = tmp_path / "population.jsonl"
    (directory / "locked.jsonl").rename(lock)
    shutil.copyfile(directory / "fixture.json", tmp_path / "fixture.json")
    separate = src.SourceMatch(
        src.SourceMatchSpec(spec.label, spec.match_id, directory, locked_path=lock), "synthetic"
    )
    separate.prepare()
    assert list(separate.windows()) == expected
    assert (
        separate.source_document()["locked_sha256"] == original.source_document()["locked_sha256"]
    )
    (tmp_path / "fixture.json").unlink()
    with pytest.raises(PermissionError):
        src.SourceMatch(
            src.SourceMatchSpec(spec.label, spec.match_id, directory, locked_path=lock), "synthetic"
        )


@functools.cache
def windows_of(bundle: Path, index: int = 0) -> list[dict[str, Any]]:
    spec = fx.read_bundle(bundle)[0][index]
    match = src.SourceMatch(spec, "synthetic")
    match.prepare()
    return list(match.windows())


# ---------------------------------------------------------------- source contract and parity
def test_adapter_matches_production_producer_truth_exactly(tmp_path: Path) -> None:
    """Invented raw frames -> production streaming producer vs adapter, byte-level truth parity."""
    inputs = _persist(tmp_path / "population", synthetic_sources())
    result = producer.produce_streaming_population_draft_v1(inputs, tmp_path / "out")
    truth_rows = [
        json.loads(line)
        for line in (result.output_directory / "truth.jsonl").read_bytes().splitlines()
    ]
    chosen = "1886347"  # pinned training-role identity, never an evaluation match
    item = next(i for i in inputs if i.match_id == chosen)
    metadata = json.loads(item.metadata_path.read_bytes())
    frames = [json.loads(line) for line in item.tracking_jsonl_path.read_bytes().splitlines()]
    phases = json.loads(item.phase_intervals_path.read_bytes())[0]
    directory = tmp_path / "adapter"
    directory.mkdir(mode=0o700)
    locked, eligible = fx.lock_pass(
        metadata, frames, chosen, phases["frame_start"], phases["frame_end"]
    )
    for name, data in (
        (
            "fixture.json",
            canonical_bytes({"synthetic_source_fixture": src.SOURCE_MARKER, "match_id": chosen}),
        ),
        ("metadata.json", item.metadata_path.read_bytes()),
        ("tracking.jsonl", item.tracking_jsonl_path.read_bytes()),
        ("phases.json", item.phase_intervals_path.read_bytes()),
        ("locked.jsonl", locked),
    ):
        fx._write(directory / name, data)
    match = src.SourceMatch(
        src.SourceMatchSpec("synthetic-match-0", chosen, directory), "synthetic"
    )
    match.prepare()
    adapted = list(match.windows())
    expected = [r for r in truth_rows if r["match_id"] == chosen]
    assert eligible == len(adapted) and len(expected) == 2 * len(adapted) > 0
    for index, window in enumerate(adapted):
        for scene, row in zip(window["scenes"], expected[2 * index : 2 * index + 2], strict=True):
            assert row["window_id"] == window["window_id"]
            assert scene["scene_id"] == row["scene_id"]
            assert scene["player_ids"] == [int(p) for p in row["player_ids"]]
            for key in ("origin_xy", "absolute_xy", "origin_relative_displacement", "truth_mask"):
                assert canonical_bytes(scene[key]) == canonical_bytes(row[key])
            assert scene["scoreable"] is row["scoreable"]
            assert scene["truth_mask_sha256"] == row["truth_mask_sha256"]


@pytest.mark.parametrize(
    "mutation",
    [
        "none",
        "ball_origin",
        "ball_coverage",
        "partial_ball",
        "false_flag",
        "team_count",
        "gross_player",
        "gross_ball",
        "phase_gap",
        "timestamp",
        "period",
        "missing_sample",
        "appearance",
    ],
)
def test_independent_raw_eligibility_matches_adapter(tmp_path: Path, mutation: str) -> None:
    directory = tmp_path / "match"
    fx.build_match(directory, 0, 46)
    metadata = json.loads((directory / "metadata.json").read_bytes())
    frames = [json.loads(line) for line in (directory / "tracking.jsonl").read_bytes().splitlines()]
    if mutation == "ball_origin":
        frames[50]["ball_data"]["x"] = None
    elif mutation == "ball_coverage":
        for frame in frames[0:10:2]:
            frame["ball_data"] = None
    elif mutation == "partial_ball":
        frames[0]["ball_data"]["x"] = None
    elif mutation == "false_flag":
        for frame in frames:
            frame["ball_data"]["is_detected"] = False
    elif mutation == "team_count":
        frames[50]["player_data"] = frames[50]["player_data"][:6]
    elif mutation == "gross_player":
        frames[50]["player_data"][0]["x"] = 106.0
    elif mutation == "gross_ball":
        frames[50]["ball_data"]["x"] = 211.0
    elif mutation == "timestamp":
        for frame in frames:
            frame["timestamp"] = None
    elif mutation == "period":
        frames[50]["period"] = 2
    elif mutation == "missing_sample":
        frames = [f for f in frames if f["frame"] != 150]
    elif mutation == "appearance":
        for person in metadata["players"][:6]:
            person["playing_time"]["by_period"][0]["end_frame"] = 110
    first = 151 if mutation == "phase_gap" else 100
    locked, _ = fx.lock_pass(metadata, frames, fx.FIXTURE_MATCH_IDS[0], first, 192)
    (directory / "metadata.json").write_bytes(canonical_bytes(metadata))
    (directory / "tracking.jsonl").write_bytes(b"".join(canonical_bytes(f) + b"\n" for f in frames))
    (directory / "locked.jsonl").write_bytes(locked)
    (directory / "phases.json").write_bytes(
        canonical_bytes([{"period": 1, "frame_start": first, "frame_end": 192}])
    )
    match = src.SourceMatch(
        src.SourceMatchSpec("synthetic-match-0", fx.FIXTURE_MATCH_IDS[0], directory), "synthetic"
    )
    match.prepare()
    assert [w["window_id"] for w in match.windows()] == [
        w["window_id"] for w in ind.raw_windows(directory, "synthetic-match-0")
    ]


def test_independent_verifier_refuses_forged_lock_membership(bundle: Path, tmp_path: Path) -> None:
    directory = clone(bundle, tmp_path) / "match-0"
    rows = [json.loads(line) for line in (directory / "locked.jsonl").read_bytes().splitlines()]
    next(r for r in rows if r["window_id"] is not None)["window_id"] = None
    (directory / "locked.jsonl").write_bytes(b"".join(canonical_bytes(r) + b"\n" for r in rows))
    with pytest.raises(ValueError, match="independent raw eligibility"):
        list(ind.raw_windows(directory, "synthetic-match-0"))


def test_window_contract(bundle: Path) -> None:
    for index in range(4):
        windows = windows_of(bundle, index)
        assert [w["index"] for w in windows] == list(range(len(windows)))
        for w in windows:
            assert len(w["support"]) == 41
            assert w["support"][25]["source_frame"] == w["source_frame"]
            assert [x["source_frame"] for x in w["support"]] == [
                w["source_frame"] + 2 * (k - 25) for k in range(41)
            ]  # 25 history + origin + 15 future at 0.2 s
            assert [c["scene_id"] for c in w["scenes"]] == ["home", "away"]
            assert set(w["home_player_ids"]).isdisjoint(w["away_player_ids"])
            for scene in w["scenes"]:
                assert len(scene["player_ids"]) == 11 and len(scene["origin_xy"]) == 11
                assert set(scene["player_ids"]) <= set(
                    w["home_player_ids"] if scene["scene_id"] == "home" else w["away_player_ids"]
                )
                assert scene["quality"] in {
                    "detected_only",
                    "with_provider_extrapolation",
                    "unclassified",
                }
                counts = scene["missingness"]
                assert sum(counts.values()) == 11 * 15  # every target step has one category
                observed = sum(
                    counts[k]
                    for k in ("observed_detected", "provider_extrapolated", "flag_missing")
                )
                assert observed == sum(sum(row) for row in scene["truth_mask"])


def test_missingness_scoreability_and_quality_are_exercised(bundle: Path) -> None:
    match1, match3 = windows_of(bundle, 1), windows_of(bundle, 3)
    assert [sc["scoreable"] for sc in match1[0]["scenes"]] == [True, False]  # away XI swapped out
    assert not any(sc["scoreable"] for sc in match3[0]["scenes"])  # whole window unscoreable
    qualities = {
        sc["quality"] for i in range(4) for w in windows_of(bundle, i) for sc in w["scenes"]
    }
    assert {"detected_only", "with_provider_extrapolation"} <= qualities


def test_scene_truth_reproduces_source_xy_in_metres(bundle: Path) -> None:
    for w in windows_of(bundle, 0):
        by_step = [{p["player_id"]: p for p in sample["players"]} for sample in w["support"]]
        for scene in w["scenes"]:
            for p, pid in enumerate(scene["player_ids"]):
                origin = by_step[25][pid]
                assert scene["origin_xy"][p] == [origin["x_m"], origin["y_m"]]
                for t in range(15):
                    got = by_step[26 + t].get(pid)
                    cell = scene["absolute_xy"][t][p]
                    if got is None or got["x_m"] is None:
                        assert cell is None and scene["truth_mask"][t][p] is False
                    else:
                        assert cell == [got["x_m"], got["y_m"]]
                        assert scene["origin_relative_displacement"][t][p] == pytest.approx(
                            [got["x_m"] - origin["x_m"], got["y_m"] - origin["y_m"]], abs=1e-12
                        )


# --------------------------------------------------------------------- source gate refusals
def test_real_source_mode_and_heldout_identities_are_refused(bundle: Path, tmp_path: Path) -> None:
    spec = fx.read_bundle(bundle)[0][0]
    with pytest.raises(PermissionError, match="RES646"):
        src.SourceMatch(spec, "frozen")
    for held_out in sorted(src.evaluation_match_ids()):
        forged = src.SourceMatchSpec("synthetic-match-0", held_out, spec.directory)
        with pytest.raises(PermissionError, match="held-out evaluation identity"):
            src.SourceMatch(forged, "synthetic")
    with pytest.raises(PermissionError, match="synthetic fixtures"):
        src.SourceMatch(
            src.SourceMatchSpec("real-match", spec.match_id, spec.directory), "synthetic"
        )


def test_unmarked_or_historical_source_directories_are_refused(
    bundle: Path, tmp_path: Path
) -> None:
    spec = fx.read_bundle(bundle)[0][0]
    target = clone(bundle, tmp_path) / "match-0"
    (target / "fixture.json").unlink()
    with pytest.raises(PermissionError):
        src.SourceMatch(src.SourceMatchSpec(spec.label, spec.match_id, target), "synthetic")
    historical = tmp_path / "res594-private" / "match-0"
    shutil.copytree(bundle / "match-0", historical)
    with pytest.raises(PermissionError, match="historical"):
        src.SourceMatch(src.SourceMatchSpec(spec.label, spec.match_id, historical), "synthetic")


def test_path_aliases_are_refused(bundle: Path, tmp_path: Path) -> None:
    target = clone(bundle, tmp_path)
    original = target / "match-0" / "tracking.jsonl"
    spec = src.SourceMatchSpec("synthetic-match-0", "1886347", target / "match-0")
    os.rename(original, target / "real.jsonl")
    os.symlink(target / "real.jsonl", original)
    match = src.SourceMatch(spec, "synthetic")
    with pytest.raises(PermissionError, match="aliased"):
        match.prepare()
    os.unlink(original)
    os.link(target / "real.jsonl", original)  # hard-link alias
    with pytest.raises(PermissionError):
        src.SourceMatch(spec, "synthetic").prepare()
    os.unlink(original)
    shutil.copy(target / "real.jsonl", original)
    alias = tmp_path / "linked"
    os.symlink(target, alias)  # symlinked parent directory
    with pytest.raises(PermissionError):
        src.SourceMatch(
            src.SourceMatchSpec("synthetic-match-0", "1886347", alias / "match-0"), "synthetic"
        )
    with pytest.raises(PermissionError):
        paths.reject_unsafe_path(target / "match-0" / ".." / "match-0")
    with pytest.raises(PermissionError):
        paths.reject_unsafe_path(Path("relative/path"))


def _locked_lines(directory: Path) -> list[bytes]:
    return (directory / "locked.jsonl").read_bytes().splitlines(keepends=True)


def _run(directory: Path) -> list[dict[str, Any]]:
    match = src.SourceMatch(
        src.SourceMatchSpec("synthetic-match-0", "1886347", directory), "synthetic"
    )
    match.prepare()
    return list(match.windows())


@pytest.mark.parametrize(
    "mutation, message",
    [
        ("drop_row", "ended before its source"),
        ("extra_row", "beyond the source"),
        ("wrong_origin", "frozen population stream"),
        ("flip_eligibility", "eligibility differs"),
        ("wrong_window_id", "window identity"),
        ("forged_truth", "truth or mask"),
    ],
)
def test_locked_population_stream_forgeries_fail_closed(
    bundle: Path, tmp_path: Path, mutation: str, message: str
) -> None:
    directory = clone(bundle, tmp_path) / "match-0"
    lines = _locked_lines(directory)
    rows = [json.loads(line) for line in lines]
    index = next(i for i, r in enumerate(rows) if r["window_id"])
    if mutation == "drop_row":
        del lines[-1]
    elif mutation == "extra_row":
        lines.append(lines[-1])
    elif mutation == "wrong_origin":
        rows[index]["source_frame"] += 2
        lines[index] = canonical_bytes(rows[index]) + b"\n"
    elif mutation == "flip_eligibility":
        rows[index]["window_id"] = None
        lines[index] = canonical_bytes(rows[index]) + b"\n"
    elif mutation == "wrong_window_id":
        rows[index]["window_id"] = "0" * 64
        lines[index] = canonical_bytes(rows[index]) + b"\n"
    else:
        rows[index]["scenes"][0]["absolute_xy"][-1][0] = [1.0, 2.0]
        lines[index] = canonical_bytes(rows[index]) + b"\n"
    (directory / "locked.jsonl").write_bytes(b"".join(lines))
    with pytest.raises(ValueError, match=message):
        _run(directory)


def test_source_drift_and_mutation_between_passes(bundle: Path, tmp_path: Path) -> None:
    directory = clone(bundle, tmp_path) / "match-0"
    spec = src.SourceMatchSpec("synthetic-match-0", "1886347", directory)
    match = src.SourceMatch(spec, "synthetic")
    match.prepare()
    lines = (directory / "tracking.jsonl").read_bytes().splitlines(keepends=True)
    row = json.loads(lines[10])
    row["player_data"][0]["x"] += 0.5
    lines[10] = canonical_bytes(row) + b"\n"
    (directory / "tracking.jsonl").write_bytes(b"".join(lines))
    with pytest.raises(ValueError):  # changed content or inode metadata between pass 1 and 2
        list(match.windows())
    # ball null-flag / finite-XY sentinel
    frames = [json.loads(x) for x in lines]
    frames[10]["ball_data"] = {"x": 1.0, "y": 2.0, "z": None, "is_detected": None}
    (directory / "tracking.jsonl").write_bytes(b"".join(canonical_bytes(f) + b"\n" for f in frames))
    with pytest.raises(ValueError):
        src.SourceMatch(spec, "synthetic").prepare()


def test_source_identity_must_match_metadata(bundle: Path, tmp_path: Path) -> None:
    directory = clone(bundle, tmp_path) / "match-0"
    wrong = src.SourceMatchSpec("synthetic-match-0", "1899585", directory)
    (directory / "fixture.json").write_bytes(
        canonical_bytes({"synthetic_source_fixture": src.SOURCE_MARKER, "match_id": "1899585"})
    )
    with pytest.raises(ValueError, match="identity differs"):
        src.SourceMatch(wrong, "synthetic")


# ------------------------------------------------------------- information boundary / leakage
def _poison(
    window: dict[str, Any], *, ball: bool = False, opponents: bool = False, own: bool = False
) -> dict[str, Any]:
    clone_ = copy.deepcopy(window)
    target_side = "home"
    own_ids, opponent_ids = set(window["home_player_ids"]), set(window["away_player_ids"])
    for sample in clone_["support"][26:]:
        if ball and sample["ball"] is not None:
            sample["ball"]["x_m"], sample["ball"]["y_m"] = 91.0, -73.0
        for player in sample["players"]:
            if player["x_m"] is None:
                continue
            if (opponents and player["player_id"] in opponent_ids) or (
                own and player["player_id"] in own_ids
            ):
                player["x_m"], player["y_m"] = -88.0, 77.0
    assert target_side == "home"
    return clone_


def _outputs(
    window: dict[str, Any], frozen: ck.FrozenModelSet
) -> dict[tuple[int, str], np.ndarray[Any, Any]]:
    return {
        (cell, scene["scene_id"]): prediction
        for cell, scene, prediction in pipe.predictions(window, frozen)
    }


def test_information_regimes_enforce_future_boundaries(
    bundle: Path, frozen: ck.FrozenModelSet
) -> None:
    window = windows_of(bundle, 0)[1]
    base = _outputs(window, frozen)
    regime_of = {i: c[0] for i, c in enumerate(s.CELLS)}

    def changed(poisoned: dict[str, Any]) -> set[str]:
        other = _outputs(poisoned, frozen)
        return {regime_of[k[0]] for k in base if not np.array_equal(base[k], other[k])}

    assert changed(_poison(window, ball=True)) == {"future_ball", "future_opponent_plus_ball"}
    # Away future tracks reach only the future-opponent regime (as the home scene's opponents).
    assert changed(_poison(window, opponents=True)) == {"future_opponent_plus_ball"}
    assert changed(_poison(window, ball=True, opponents=True, own=True)) == {
        "future_ball",
        "future_opponent_plus_ball",
    }  # history_only is blind to every realized future channel


def test_target_team_future_never_reaches_the_model(
    bundle: Path, frozen: ck.FrozenModelSet
) -> None:
    window = windows_of(bundle, 0)[1]
    base = _outputs(window, frozen)
    poisoned = copy.deepcopy(window)
    home = set(window["home_player_ids"])
    for sample in poisoned["support"][26:]:
        for player in sample["players"]:
            if player["player_id"] in home and player["x_m"] is not None:
                player["x_m"] = 5000.0
    other = _outputs(poisoned, frozen)
    for (cell, side), prediction in base.items():
        if side == "home":  # target team's own future: the truth, forbidden in every regime
            assert np.array_equal(prediction, other[cell, side])
        elif cell // 6 == 2:  # away scene, future_opponent regime legitimately sees home tracks
            assert not np.array_equal(prediction, other[cell, side])
        else:
            assert np.array_equal(prediction, other[cell, side])


def test_feature_payload_keys_and_forbidden_names(bundle: Path) -> None:
    window = windows_of(bundle, 0)[0]
    scene = window["scenes"][0]
    for regime in lds.INFORMATION_REGIMES:
        payload = lds.build_scene_feature_payload(
            window["support"],
            target_side="home",
            target_player_ids=scene["player_ids"],
            home_player_ids=window["home_player_ids"],
            away_player_ids=window["away_player_ids"],
            regime=regime,
        )
        lds.validate_feature_payload(payload, regime)
        assert ("future_ball" in payload) == (regime != "history_only")
        assert ("future_opponent_tracks" in payload) == (regime == "future_opponent_plus_ball")
    leaky = copy.deepcopy(window)
    leaky["support"][3]["future_target_s"] = [1.0]
    with pytest.raises(ValueError, match="forbidden"):
        pipe.SourceIdentity("synthetic-match-0", "1886347").observe(leaky)


# ---------------------------------------------------------------- adversarial window streams
def _identity_run(
    windows: list[dict[str, Any]], match: str = "synthetic-match-0", expected: int | None = None
) -> None:
    identity = pipe.SourceIdentity(match, windows[0]["match_id"])
    for w in windows:
        identity.observe(w)
    if expected is not None and identity.count != expected:
        raise ValueError("incomplete")


def test_duplicate_missing_and_reordered_windows_fail(bundle: Path) -> None:
    ws = windows_of(bundle, 0)
    _identity_run(ws)
    with pytest.raises(ValueError, match="duplicate window|wrong match"):
        _identity_run([ws[0], ws[0], *ws[1:]])
    with pytest.raises(ValueError, match="wrong match|missing window"):
        _identity_run([ws[0], ws[2]])
    with pytest.raises(ValueError):
        _identity_run([ws[1], ws[0]])
    swapped = [ws[0], {**ws[2], "index": 1}, {**ws[1], "index": 2}]
    with pytest.raises(ValueError, match="out-of-order"):
        _identity_run(swapped)
    with pytest.raises(ValueError, match="wrong match"):
        _identity_run(ws, match="synthetic-match-1")


@pytest.mark.parametrize(
    "mutate, message",
    [
        (
            lambda w: w["scenes"][0]["truth_mask"][4].__setitem__(
                0, not w["scenes"][0]["truth_mask"][4][0]
            ),
            "mask",
        ),
        (
            lambda w: w["scenes"][0].__setitem__("scoreable", not w["scenes"][0]["scoreable"]),
            "scoreab",
        ),
        (lambda w: w["scenes"][0]["origin_xy"][0].__setitem__(0, 1.5), "same trajectory|origin"),
        (lambda w: w["scenes"][1].__setitem__("scene_id", "home"), "directed scene"),
        (
            lambda w: w["scenes"][0]["player_ids"].__setitem__(0, w["away_player_ids"][0]),
            "outside their directed team",
        ),
        (lambda w: w["support"].pop(), "support or directed"),
        (lambda w: w["support"][30].__setitem__("source_frame", 1), "source frame order"),
        (
            lambda w: w["scenes"][0]["origin_relative_displacement"][3][0].__setitem__(0, 9.0),
            "same trajectory",
        ),
        (lambda w: w["scenes"][0].__setitem__("truth_mask_sha256", "0" * 64), "mask identity"),
        (lambda w: w["home_player_ids"].append(w["away_player_ids"][0]), "disjoint"),
    ],
)
def test_incorrect_masks_origins_identities_and_representations_fail(
    bundle: Path, mutate: Any, message: str
) -> None:
    window = copy.deepcopy(windows_of(bundle, 0)[0])
    mutate(window)
    with pytest.raises(ValueError, match=message):
        pipe.SourceIdentity("synthetic-match-0", "1886347").observe(window)


def test_forged_truth_that_still_matches_its_own_mask_is_caught_by_the_support(
    bundle: Path,
) -> None:
    window = copy.deepcopy(windows_of(bundle, 0)[0])
    scene = window["scenes"][0]
    t, p = next((t, p) for t in range(15) for p in range(11) if scene["truth_mask"][t][p])
    scene["absolute_xy"][t][p][0] += 0.25
    scene["origin_relative_displacement"][t][p][0] += 0.25
    scene["truth_mask_sha256"] = scene["truth_mask_sha256"]  # mask unchanged; truth values forged
    with pytest.raises(ValueError, match="differs from the source support"):
        pipe.SourceIdentity("synthetic-match-0", "1886347").observe(window)


def test_incomplete_results_fail(bundle: Path, frozen: ck.FrozenModelSet) -> None:
    ws = windows_of(bundle, 0)
    with pytest.raises(ValueError, match="incomplete"):
        pipe.score_stream("synthetic-match-0", "1886347", iter(ws[:3]), frozen, len(ws))
    unscoreable = windows_of(bundle, 3)[:1]
    assert not any(c["scoreable"] for c in unscoreable[0]["scenes"])
    with pytest.raises(ValueError, match="incomplete or unscoreable"):
        pipe.score_stream("synthetic-match-3", "1959846", iter(unscoreable), frozen, 1)


# --------------------------------------------------------------------- checkpoint contract
def manifest_records(manifest: dict[str, Any]) -> dict[tuple[str, str, int], dict[str, Any]]:
    return {
        (r["information_regime"], r["target_representation"], r["seed"]): r
        for r in manifest["checkpoints"]
    }


def test_valid_set_binds_every_cell(
    workload: wl.FixtureWorkload, frozen: ck.FrozenModelSet
) -> None:
    assert len(frozen.models) == 18 and len(frozen.bindings) == 18
    records = manifest_records(workload.manifest)
    assert [b.cell for b in frozen.bindings] == list(ck.EXPECTED_CELLS)
    for binding in frozen.bindings:
        record = records[binding.cell]
        assert (binding.checkpoint_sha256, binding.configuration_sha256, binding.selected_step) == (
            record["checkpoint_sha256"],
            record["configuration_sha256"],
            record["selected_step"],
        )
        model = frozen.models[binding.cell]
        assert model.regime == binding.cell[0] and not model.training
        assert all(not p.requires_grad and p.dtype == torch.float32 for p in model.parameters())
    frozen.assert_unchanged()


def test_loading_is_read_only(bundle: Path, tmp_path: Path) -> None:
    target = clone(bundle, tmp_path)
    directory = target / "checkpoints"

    def snapshot() -> dict[str, tuple[int, int, str]]:
        return {
            p.name: (
                p.stat().st_mtime_ns,
                p.stat().st_mode,
                hashlib.sha256(p.read_bytes()).hexdigest(),
            )
            for p in sorted(directory.iterdir())
        } | {"dir": (directory.stat().st_mtime_ns, directory.stat().st_mode, "")}

    before = snapshot()
    manifest = json.loads((target / "manifest.json").read_bytes())
    ck.load_models(manifest, directory, "synthetic", target / "receipts")
    assert snapshot() == before
    os.chmod(directory, 0o500)  # a genuinely read-only tree still loads
    try:
        ck.load_models(manifest, directory, "synthetic", target / "receipts")
    finally:
        os.chmod(directory, 0o700)


def resign(
    target: Path,
    manifest: dict[str, Any],
    key: tuple[str, str, int],
    payload: dict[str, Any],
    *,
    receipt: bool = True,
) -> dict[str, Any]:
    """Replace one cell's file with ``payload`` and make the manifest self-consistent.

    With ``receipt=True`` the completed-fit receipt is re-issued for the new checkpoint hash, so a
    failure can only come from the shape/metadata layers. ``receipt=False`` leaves the original
    receipt, modelling a substitution by someone who cannot forge the owner-private fit receipt.
    """
    directory = target / "checkpoints"
    record = manifest_records(manifest)[key]
    (directory / f"{record['checkpoint_sha256']}.pt").unlink()
    buffer = io.BytesIO()
    torch.save(payload, buffer)
    digest = hashlib.sha256(buffer.getvalue()).hexdigest()
    fx._write(directory / f"{digest}.pt", buffer.getvalue())
    if receipt:
        old = target / "receipts" / f"{record['receipt_sha256']}.json"
        body = json.loads(old.read_bytes())
        body["checkpoint_sha256"] = digest
        data = canonical_bytes(body)
        old.unlink()
        record["receipt_sha256"] = hashlib.sha256(data).hexdigest()
        fx._write(target / "receipts" / f"{record['receipt_sha256']}.json", data)
    record["checkpoint_sha256"] = digest
    return manifest


def valid_payload(manifest: dict[str, Any], key: tuple[str, str, int]) -> dict[str, Any]:
    record = manifest_records(manifest)[key]
    model = lds.PerTargetContextDeepSetsMLP(key[0])
    return {
        "metadata": {
            "run_id": ck.run_id(key),
            "configuration_sha256": record["configuration_sha256"],
            "selected_step": record["selected_step"],
            "attempt_number": 1,
        },
        "state_dict": model.state_dict(),
    }


CELL: tuple[str, str, int] = ("future_ball", "absolute_xy", 2718)


def load(
    target: Path, manifest: dict[str, Any] | None = None, mode: str = "synthetic"
) -> ck.FrozenModelSet:
    manifest = manifest or json.loads((target / "manifest.json").read_bytes())
    return ck.load_models(manifest, target / "checkpoints", mode, target / "receipts")  # type: ignore[arg-type]


def test_hash_mismatch_missing_and_extra_files(bundle: Path, tmp_path: Path) -> None:
    target = clone(bundle, tmp_path)
    record = manifest_records(json.loads((target / "manifest.json").read_bytes()))[CELL]
    path = target / "checkpoints" / f"{record['checkpoint_sha256']}.pt"
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 1
    path.write_bytes(bytes(data))
    with pytest.raises(ck.CheckpointContractError, match="SHA-256 mismatch"):
        load(target)
    path.unlink()
    with pytest.raises(ck.CheckpointContractError, match="differs from the manifest files"):
        load(target)
    shutil.rmtree(target)
    target = clone(bundle, tmp_path)
    fx._write(target / "checkpoints" / ("f" * 64 + ".pt"), b"stray")
    with pytest.raises(ck.CheckpointContractError, match="differs from the manifest files"):
        load(target)


def test_substitution_between_cells_is_rejected(bundle: Path, tmp_path: Path) -> None:
    target = clone(bundle, tmp_path)
    manifest = json.loads((target / "manifest.json").read_bytes())
    records = manifest_records(manifest)
    a, b = (
        records[("history_only", "absolute_xy", 1729)],
        records[("history_only", "absolute_xy", 2718)],
    )
    directory = target / "checkpoints"
    first, second = (
        directory / f"{a['checkpoint_sha256']}.pt",
        directory / f"{b['checkpoint_sha256']}.pt",
    )
    one, two = first.read_bytes(), second.read_bytes()
    first.write_bytes(two)
    second.write_bytes(one)  # swapped contents under the original names
    with pytest.raises(ck.CheckpointContractError, match="SHA-256 mismatch"):
        load(target, manifest)
    # Cell B's manifest entry now names cell A's valid file: a duplicated digest.
    first.write_bytes(one)
    second.write_bytes(two)
    b["checkpoint_sha256"] = a["checkpoint_sha256"]
    with pytest.raises(ck.CheckpointContractError, match="duplicates a checkpoint digest"):
        load(target, manifest)


def test_cross_cell_substitution_with_consistent_hash_fails_metadata_binding(
    bundle: Path, tmp_path: Path
) -> None:
    target = clone(bundle, tmp_path)
    manifest = json.loads((target / "manifest.json").read_bytes())
    donor = valid_payload(manifest, ("future_ball", "absolute_xy", 1729))  # another cell's identity
    resign(target, manifest, CELL, donor)
    with pytest.raises(ck.CheckpointContractError, match="metadata differs"):
        load(target, manifest)
    # Without a re-issued owner-private fit receipt the substitution fails earlier still.
    other = clone(bundle, tmp_path / "stale")
    manifest2 = json.loads((other / "manifest.json").read_bytes())
    resign(other, manifest2, CELL, valid_payload(manifest2, CELL), receipt=False)
    with pytest.raises(ck.CheckpointContractError, match="fit receipt differs"):
        load(other, manifest2)


@pytest.mark.parametrize(
    "mutate, message",
    [
        (
            lambda p: p["state_dict"].__setitem__("prediction_head.0.weight", torch.zeros(3, 3)),
            "tensor shape",
        ),
        (lambda p: p["state_dict"].__setitem__("surprise", torch.zeros(1)), "frozen structure"),
        (lambda p: p["state_dict"].pop("prediction_head.0.bias"), "frozen structure"),
        (
            lambda p: p["state_dict"].__setitem__(
                "prediction_head.0.bias", torch.zeros(128, dtype=torch.float64)
            ),
            "dtype",
        ),
        (
            lambda p: p["state_dict"]["prediction_head.0.bias"].__setitem__(0, float("nan")),
            "non-finite",
        ),
        (lambda p: p.__setitem__("optimizer", {"step": 1}), "optimizer or extra state"),
        (lambda p: p["metadata"].__setitem__("configuration_sha256", "1" * 64), "metadata differs"),
        (lambda p: p["metadata"].__setitem__("selected_step", 100), "metadata differs"),
        (lambda p: p["metadata"].__setitem__("attempt_number", 2), "metadata differs"),
        (
            lambda p: p["metadata"].__setitem__(
                "run_id", ck.run_id(("history_only", "absolute_xy", 1729))
            ),
            "metadata differs",
        ),
    ],
)
def test_unexpected_shapes_and_incorrect_configurations_fail(
    bundle: Path, tmp_path: Path, mutate: Any, message: str
) -> None:
    target = clone(bundle, tmp_path)
    manifest = json.loads((target / "manifest.json").read_bytes())
    payload = valid_payload(manifest, CELL)
    payload["state_dict"] = {k: v_.clone() for k, v_ in payload["state_dict"].items()}
    mutate(payload)
    resign(target, manifest, CELL, payload)
    with pytest.raises(ck.CheckpointContractError, match=message):
        load(target, manifest)


def test_representation_and_regime_mismatches_fail(bundle: Path, tmp_path: Path) -> None:
    target = clone(bundle, tmp_path)
    manifest = json.loads((target / "manifest.json").read_bytes())
    payload = valid_payload(manifest, CELL)
    payload["metadata"]["run_id"] = ck.run_id(("future_ball", "origin_relative_displacement", 2718))
    resign(target, manifest, CELL, payload)
    with pytest.raises(ck.CheckpointContractError, match="metadata differs"):
        load(target, manifest)
    # A history_only network cannot stand in for a future_ball cell (input width / tensors differ).
    target2 = clone(bundle, tmp_path / "second")
    manifest2 = json.loads((target2 / "manifest.json").read_bytes())
    payload2 = valid_payload(manifest2, CELL)
    payload2["state_dict"] = lds.PerTargetContextDeepSetsMLP("history_only").state_dict()
    resign(target2, manifest2, CELL, payload2)
    with pytest.raises(ck.CheckpointContractError, match="tensor shape"):
        load(target2, manifest2)


def test_pickle_payloads_are_never_executed(bundle: Path, tmp_path: Path) -> None:
    target = clone(bundle, tmp_path)
    manifest = json.loads((target / "manifest.json").read_bytes())
    marker = tmp_path / "executed"

    class Evil:
        def __reduce__(self) -> tuple[Any, ...]:
            return (os.system, (f"touch {marker}",))

    resign(target, manifest, CELL, {"metadata": Evil(), "state_dict": {}})
    with pytest.raises(ck.CheckpointContractError, match="tensors-only"):
        load(target, manifest)
    assert not marker.exists()


@pytest.mark.parametrize(
    "mutate, message",
    [
        (
            lambda m: m["checkpoints"].append(copy.deepcopy(m["checkpoints"][0])),
            "exact 18|duplicates",
        ),
        (lambda m: m["checkpoints"].pop(), "exact 18"),
        (lambda m: m["checkpoints"][1].update(seed=1729), "duplicates a model cell"),
        (lambda m: m["checkpoints"][0].update(seed=7), "unexpected model cell"),
        (lambda m: m["checkpoints"][0].update(attempt_number=2), "nonfinal or retried"),
        (lambda m: m["checkpoints"][0].update(selected_step=150), "cadence"),
        (lambda m: m["checkpoints"][0].update(checkpoint_sha256="XYZ"), "SHA-256"),
        (
            lambda m: m["checkpoints"][1].update(
                configuration_sha256=m["checkpoints"][0]["configuration_sha256"]
            ),
            "configuration digest",
        ),
        (lambda m: m.pop("synthetic_fixture"), "masquerade"),
        (
            lambda m: m.update(
                study_id="fpdbench.public-skillcorner-post-failure-descriptive-heldout/1.0.0"
            ),
            "masquerade",
        ),
    ],
)
def test_manifest_violations(bundle: Path, mutate: Any, message: str) -> None:
    manifest = json.loads((bundle / "manifest.json").read_bytes())
    mutate(manifest)
    with pytest.raises(ck.CheckpointContractError, match=message):
        ck.validate_manifest(manifest, "synthetic")


def test_unsafe_checkpoint_paths(bundle: Path, tmp_path: Path) -> None:
    target = clone(bundle, tmp_path)
    manifest = json.loads((target / "manifest.json").read_bytes())
    directory = target / "checkpoints"
    record = manifest_records(manifest)[CELL]
    path = directory / f"{record['checkpoint_sha256']}.pt"
    # symlinked file
    real = tmp_path / "elsewhere.pt"
    shutil.move(path, real)
    os.symlink(real, path)
    with pytest.raises(ck.CheckpointContractError, match="aliased"):
        load(target, manifest)
    os.unlink(path)
    shutil.move(real, path)
    # hard-linked file
    os.link(path, tmp_path / "hardlink.pt")
    with pytest.raises(ck.CheckpointContractError, match="unreadable or aliased"):
        load(target, manifest)
    os.unlink(tmp_path / "hardlink.pt")
    # group/other readable file and directory
    os.chmod(path, 0o644)
    with pytest.raises(ck.CheckpointContractError):
        load(target, manifest)
    os.chmod(path, 0o600)
    os.chmod(directory, 0o755)
    with pytest.raises(ck.CheckpointContractError, match="owner-private"):
        load(target, manifest)
    os.chmod(directory, 0o700)
    # symlinked directory, traversal and historical aliases
    alias = tmp_path / "dir-alias"
    os.symlink(directory, alias)
    with pytest.raises(ck.CheckpointContractError):
        ck.load_models(manifest, alias, "synthetic", target / "receipts")
    with pytest.raises(ck.CheckpointContractError):
        ck.load_models(manifest, directory / ".." / "checkpoints", "synthetic", target / "receipts")
    historical = tmp_path / "res594-snapshot"
    shutil.copytree(directory, historical)
    with pytest.raises(ck.CheckpointContractError, match="historical"):
        ck.load_models(manifest, historical, "synthetic", target / "receipts")
    # missing directory
    with pytest.raises(ck.CheckpointContractError):
        ck.load_models(manifest, tmp_path / "does-not-exist", "synthetic", target / "receipts")


def test_frozen_contract_never_opens_private_checkpoints(tmp_path: Path, bundle: Path) -> None:
    frozen_manifest = ck.frozen_manifest()
    assert (
        hashlib.sha256(
            Path(ck.__file__).with_name("res593_checkpoint_manifest_v1.json").read_bytes()
        ).hexdigest()
        == ck.FROZEN_MANIFEST_SHA256
    )
    assert ck.validate_manifest(frozen_manifest, "frozen") == ck.FROZEN_MANIFEST_SHA256
    assert len(ck.validate_records(frozen_manifest)) == 18
    # The frozen manifest cannot validate as a synthetic fixture, nor the reverse.
    with pytest.raises(ck.CheckpointContractError, match="masquerade"):
        ck.validate_manifest(frozen_manifest, "synthetic")
    synthetic = json.loads((bundle / "manifest.json").read_bytes())
    with pytest.raises(ck.CheckpointContractError, match="not the pinned frozen"):
        ck.validate_manifest(synthetic, "frozen")
    # Pointing the frozen mode at an empty (or synthetic) directory fails before any file read.
    empty = tmp_path / "empty"
    empty.mkdir(mode=0o700)
    with pytest.raises(ck.CheckpointContractError, match="differs from the manifest files"):
        ck.load_models(frozen_manifest, empty, "frozen", empty)
    with pytest.raises(ck.CheckpointContractError, match="not the pinned frozen"):
        ck.load_models(synthetic, bundle / "checkpoints", "frozen", bundle / "receipts")


def test_mutated_model_is_detected(frozen: ck.FrozenModelSet) -> None:
    model = frozen.models[ck.EXPECTED_CELLS[0]]
    with torch.no_grad():
        first = next(model.parameters())
        original = first.clone()
        first += 1e-3
    try:
        with pytest.raises(ck.CheckpointContractError):
            frozen.assert_unchanged()
    finally:
        with torch.no_grad():
            first.copy_(original)
    model.train()
    try:
        with pytest.raises(ck.CheckpointContractError):
            frozen.assert_unchanged()
    finally:
        model.eval()
    frozen.assert_unchanged()


def test_fit_receipt_binding(bundle: Path, tmp_path: Path) -> None:
    target = clone(bundle, tmp_path)
    manifest = json.loads((target / "manifest.json").read_bytes())
    receipts = target / "receipts"
    record = manifest_records(manifest)[CELL]
    path = receipts / f"{record['receipt_sha256']}.json"
    original = path.read_bytes()
    # A receipt that hashes correctly but names another configuration is not this fit.
    forged = json.loads(original)
    forged["configuration_sha256"] = "2" * 64
    body = canonical_bytes(forged)
    path.unlink()
    digest = hashlib.sha256(body).hexdigest()
    fx._write(receipts / f"{digest}.json", body)
    record["receipt_sha256"] = digest
    with pytest.raises(ck.CheckpointContractError, match="fit receipt differs"):
        load(target, manifest)
    # Same bytes under a stale hash name.
    (receipts / f"{digest}.json").write_bytes(original)
    with pytest.raises(ck.CheckpointContractError, match="receipt SHA-256 mismatch"):
        load(target, manifest)
    (receipts / f"{digest}.json").unlink()
    with pytest.raises(ck.CheckpointContractError, match="receipt directory differs"):
        load(target, manifest)
    fresh = clone(bundle, tmp_path / "fresh")
    fx._write(fresh / "receipts" / ("e" * 64 + ".json"), b"{}")
    with pytest.raises(ck.CheckpointContractError, match="receipt directory differs"):
        load(fresh)
    os.chmod(fresh / "receipts", 0o755)
    (fresh / "receipts" / ("e" * 64 + ".json")).unlink()
    with pytest.raises(ck.CheckpointContractError, match="owner-private"):
        load(fresh)


# ----------------------------------------------------------------------- end-to-end parity
def test_complete_72_record_pipeline_and_independent_verification(
    workload: wl.FixtureWorkload, receipts: list[dict[str, Any]]
) -> None:
    assert (
        [r["match"] for r in receipts]
        == list(s.MATCHES)
        == [f"synthetic-match-{i}" for i in range(4)]
    )
    assert sum(len(r["records"]) for r in receipts) == 72
    for i, receipt in enumerate(receipts):
        assert [r["cell"] for r in receipt["records"]] == [
            list(c) for c in s.CELLS
        ]  # 3x2x3, ordered
        workload.check_receipt(i, workload.windows, receipt)  # independent raw-file recalculation
        identity = receipt["identity"]
        assert identity["scalar_coordinates"] == 2 * identity["scored_points"]
        assert (
            receipt["provenance"]["checkpoint_bindings"] and receipt["provenance"]["synthetic_only"]
        )


def test_independent_calculation_is_not_the_scorers_code(receipts: list[dict[str, Any]]) -> None:
    imported = Path(ind.__file__).read_text()
    for forbidden in (
        "build_scene_feature_payload",
        "collate_feature_payloads",
        "res645_pipeline",
        "res645_source_stream",
        "res645_checkpoints",
        "streaming_population_producer",
        "iter_skillcorner_5hz_v2",
        "scene_metrics",
    ):
        assert forbidden not in imported


def test_hand_calculated_metrics_match_for_one_cell(
    bundle: Path, frozen: ck.FrozenModelSet, receipts: list[dict[str, Any]]
) -> None:
    """ADE, FDE and 2N-denominator RMSE with equal-scene then equal-window means, from scratch."""
    cell = ("future_opponent_plus_ball", "origin_relative_displacement", 31415)
    index = s.CELLS.index(cell)
    spec = fx.read_bundle(bundle)[0][1]
    window_scores = []
    for w in windows_of(bundle, 1):
        scene_scores = []
        for c, scene, prediction in pipe.predictions(w, frozen):
            if c != index or not scene["scoreable"]:
                continue
            truth = np.array(
                [
                    [x if x is not None else [np.nan, np.nan] for x in row]
                    for row in scene["absolute_xy"]
                ]
            )
            truth = truth.transpose(1, 0, 2)  # player-major
            mask = ~np.isnan(truth[..., 0])
            delta = (prediction - truth)[mask]
            dist = np.sqrt((delta**2).sum(axis=1))
            fde = np.sqrt(((prediction - truth)[..., -1, :][mask[:, -1]] ** 2).sum(axis=1)).mean()
            rmse = np.sqrt((delta**2).sum() / (2 * mask.sum()))
            scene_scores.append((dist.mean(), fde, rmse))
        if scene_scores:
            window_scores.append(np.mean(scene_scores, axis=0))
    expected = np.mean(window_scores, axis=0)
    actual = receipts[1]["records"][index]["strata"]["all"]["metrics"]
    assert [actual[m] for m in ("ade_m", "fde_m", "xy_rmse_m")] == pytest.approx(
        expected, abs=1e-12
    )
    assert spec.label == receipts[1]["match"]


def test_aggregation_and_all_four_contrasts_from_72_records(receipts: list[dict[str, Any]]) -> None:
    aggregate = v.aggregate(receipts)
    assert aggregate["records"] == 72 and set(aggregate["contrasts"]) == {
        "C1/absolute_xy",
        "C1/origin_relative_displacement",
        "C2/absolute_xy",
        "C2/origin_relative_displacement",
    }

    # Third, plain-Python recomputation: seeds inside match, then equal match mean, then contrast.
    def ade(regime: str, rep: str, match: int) -> float:
        rows = [r for r in receipts[match]["records"] if r["cell"][:2] == [regime, rep]]
        assert len(rows) == 3
        return sum(r["strata"]["all"]["metrics"]["ade_m"] for r in rows) / 3

    for rep in lds.TARGET_REPRESENTATIONS:
        for name, left, right in (
            ("C1", "history_only", "future_ball"),
            ("C2", "future_ball", "future_opponent_plus_ball"),
        ):
            values = [ade(left, rep, m) - ade(right, rep, m) for m in range(4)]
            got = aggregate["contrasts"][f"{name}/{rep}"]
            assert got["matches"] == pytest.approx(values, abs=1e-12)
            assert got["equal_match_mean"] == pytest.approx(sum(values) / 4, abs=1e-12)


def test_receipt_tampering_is_caught_by_independent_verification(
    workload: wl.FixtureWorkload, receipts: list[dict[str, Any]]
) -> None:
    tampered = copy.deepcopy(receipts[0])
    tampered["records"][3]["strata"]["all"]["metrics"]["ade_m"] += 1e-6
    with pytest.raises(ValueError, match="independent metric parity"):
        workload.check_receipt(0, workload.windows, tampered)
    for path, message in (
        (("identity", "scored_points"), "identity differs"),
        (("identity", "mask_sha256"), "identity differs"),
        (("identity", "truth_sha256"), "identity differs"),
        (("identity", "window_ids_sha256"), "identity differs"),
    ):
        forged = copy.deepcopy(receipts[0])
        value = forged[path[0]][path[1]]
        forged[path[0]][path[1]] = value + 1 if isinstance(value, int) else "0" * 64
        with pytest.raises(ValueError, match=message):
            workload.check_receipt(0, workload.windows, forged)
    forged = copy.deepcopy(receipts[0])
    forged["provenance"]["checkpoint_bindings"][0]["selected_step"] += 100
    with pytest.raises(ValueError, match="checkpoint binding"):
        workload.check_receipt(0, workload.windows, forged)
    forged = copy.deepcopy(receipts[0])
    forged["source"]["tracking_raw_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="source identity"):
        workload.check_receipt(0, workload.windows, forged)


def test_receipt_chain_tamper_and_removal(
    workload: wl.FixtureWorkload, receipts: list[dict[str, Any]], tmp_path: Path
) -> None:
    scope, previous, seals = workload.scope_sha256(workload.windows), "0" * 64, []
    directory = tmp_path / "chain"
    directory.mkdir(mode=0o700)
    for i, body in enumerate(receipts):
        receipt = {**body, "scope_sha256": scope, "previous_sha256": previous}
        fx._write(directory / f"match-{i}.json", s.canonical(receipt))
        previous = s.digest(receipt)
        seals.append(previous)
    assert len(workload.verify_prefix(directory, workload.windows, seals)) == 4
    assert len(workload.verify_prefix(directory, workload.windows, seals[:4])) == 4
    forged = list(seals)
    forged[1] = "0" * 64
    with pytest.raises(ValueError, match="forged receipt chain"):
        workload.verify_prefix(directory, workload.windows, forged)
    (directory / "match-3.json").rename(tmp_path / "removed.json")
    with pytest.raises(ValueError, match="partial, extra, duplicated or missing"):
        workload.verify_prefix(directory, workload.windows, seals)
    assert len(workload.verify_prefix(directory, workload.windows, seals[:3])) == 3
    edited = json.loads((directory / "match-1.json").read_bytes())
    edited["records"][0]["strata"]["all"]["metrics"]["fde_m"] += 0.5
    (directory / "match-1.json").write_bytes(s.canonical(edited))
    with pytest.raises(ValueError, match="forged receipt chain"):
        workload.verify_prefix(directory, workload.windows, seals[:3])


def test_scope_is_bound_to_inputs_and_code(
    bundle: Path, tmp_path: Path, workload: wl.FixtureWorkload
) -> None:
    target = clone(bundle, tmp_path)
    changed = wl.FixtureWorkload(target)
    # Same bytes at another location give one scope; one flipped input byte gives another.
    assert changed.scope_sha256(changed.windows) == workload.scope_sha256(workload.windows)
    data = bytearray((target / "match-2" / "tracking.jsonl").read_bytes())
    data[100] = ord(" ") if data[100] != ord(" ") else ord("\t")
    (target / "match-2" / "tracking.jsonl").write_bytes(bytes(data))
    assert wl.FixtureWorkload(target).scope_sha256(workload.windows) != workload.scope_sha256(
        workload.windows
    )
    with pytest.raises(ValueError, match="declared eligible window total"):
        workload.scope_sha256(workload.windows + 1)


def test_streaming_state_is_bounded(bundle: Path, tmp_path: Path) -> None:
    """Allocation peak must not scale with the number of windows streamed."""
    small = windows_of(bundle, 0)
    assert len(small) == 6
    (tmp_path / "large").mkdir(mode=0o700)
    fx.build_match(tmp_path / "large" / "match-0", 0, 106)
    large_spec = src.SourceMatchSpec(
        "synthetic-match-0", fx.FIXTURE_MATCH_IDS[0], tmp_path / "large" / "match-0"
    )

    def peak(spec: src.SourceMatchSpec) -> tuple[int, int]:
        tracemalloc.start()
        match = src.SourceMatch(spec, "synthetic")
        match.prepare()
        count = 0
        identity = pipe.SourceIdentity(spec.label, spec.match_id)
        for w in match.windows():
            identity.observe(w)
            count += 1
        _, top = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return count, top

    n_small, peak_small = peak(fx.read_bundle(bundle)[0][0])
    n_large, peak_large = peak(large_spec)
    assert n_large >= 6 * n_small
    assert peak_large < 1.6 * peak_small  # >10x more windows, same bounded working set
    assert not hasattr(src.SourceMatch, "all_windows")


def test_package_files_are_read_only_inputs(bundle: Path) -> None:
    mode = stat.S_IMODE((bundle / "match-0" / "tracking.jsonl").stat().st_mode)
    assert mode & 0o077 == 0  # fixtures are generated owner-private


def test_fixture_tree_hash_refuses_file_alias(bundle: Path, tmp_path: Path) -> None:
    target = clone(bundle, tmp_path)
    (target / "alias.json").symlink_to(target / "manifest.json")
    with pytest.raises(PermissionError, match="symlink"):
        wl._tree_identity(target)


def test_source_role_is_fixed(bundle: Path) -> None:
    spec = fx.read_bundle(bundle)[0][0]
    with pytest.raises(ValueError, match="source role"):
        src.SourceMatch(
            src.SourceMatchSpec(spec.label, spec.match_id, spec.directory, "train"), "synthetic"
        )
