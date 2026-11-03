"""Private, streaming research-only baseline scoring; never a protected admission path."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
import platform
import sys
from pathlib import Path

import research_population_v1 as research

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    streaming_population_producer_v1 as p,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.deterministic_baselines import (
    predict_baseline,
    predict_displacement,
)
from fpdbench.data_sources import protected_skillcorner as source
from fpdbench.data_states.skillcorner import iter_skillcorner_5hz_v2
from fpdbench.eligibility.skillcorner import skillcorner_period_ranges
from fpdbench.evaluation.metrics.trajectory import masked_physical_trajectory_metrics

MANIFEST = "a8c82bfa09ac792d6c4ae779d4b28158c33ed3c2500f8548f3e94d48197f4fd1"
MODELS = ("origin_persistence_v1", "constant_velocity_1s_v1")


def verify(root: Path, source_root: Path) -> dict:
    manifest_path = root / "research-admission.json"
    manifest = json.loads(manifest_path.read_bytes())
    if hashlib.sha256(research.canonical(manifest)).hexdigest() != MANIFEST:
        raise ValueError("research manifest identity mismatch")
    if (
        manifest["status"] != "RESEARCH_RECONCILED"
        or manifest["protected_status"] != "NOT_QUALIFIED"
    ):
        raise ValueError("research admission status mismatch")
    authority = source._authority()
    matches = [str(i) for i in authority["selected_source_matches"]]
    expected = {
        str(m["match_id"]): next(x["lfs_oid_sha256"] for x in m["files"] if "lfs_oid_sha256" in x)
        for m in authority["available_matches"]
    }
    if len(matches) != 20 or set(manifest["per_match"]) != set(matches):
        raise ValueError("research match population mismatch")
    for key, filename in [
        ("source_inventory_sha256", "source-inventory.json"),
        ("independent_source_sha256", "independent-source.json"),
        ("environment_sha256", "environment.json"),
    ]:
        if research.digest(root / filename) != manifest[key]:
            raise ValueError("research identity mismatch: " + filename)
    with source.private_directory(source_root) as fd:
        if source._verify_sources(fd, source._records(authority)) != json.loads(
            (root / "source-inventory.json").read_bytes()
        ):
            raise ValueError("source identity mismatch")
    result = research.reconcile(root / "producer", root / "verifier", matches, expected)
    for key in ("total", "per_match", "roles", "artifacts"):
        if result[key] != manifest[key]:
            raise ValueError("research reconciliation mismatch: " + key)
    return manifest


def mean_metrics(values):
    if not values:
        raise ValueError("no scoreable values")
    return tuple(math.fsum(v[i] for v in values) / len(values) for i in range(3))


def score_scene(support, truth):
    ids = [int(x) for x in truth["player_ids"]]
    histories = []
    for player_id in ids:
        histories.append(
            [p._pair(p._player_map(sample).get(player_id)) for sample in support[20:26]]
        )
    if research.canonical([h[-1] for h in histories]) != research.canonical(truth["origin_xy"]):
        raise ValueError("origin or player order differs")
    scores = {}
    for model in MODELS:
        tracks = [predict_baseline(model, history) for history in histories]
        prediction = [list(x) for x in zip(*tracks, strict=True)]
        metric = masked_physical_trajectory_metrics((prediction,), (truth["absolute_xy"],))
        displacement_tracks = [predict_displacement(model, history) for history in histories]
        displacement = [list(x) for x in zip(*displacement_tracks, strict=True)]
        delta_metric = masked_physical_trajectory_metrics(
            (displacement,), (truth["origin_relative_displacement"],)
        )
        if not all(
            math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)
            for a, b in zip(
                (metric.ade_m, metric.fde_m, metric.xy_rmse_m),
                (delta_metric.ade_m, delta_metric.fde_m, delta_metric.xy_rmse_m),
                strict=True,
            )
        ):
            raise ValueError("representation parity failed")
        scores[model] = (metric.ade_m, metric.fde_m, metric.xy_rmse_m)
    return scores


def score_match(root: Path, match: str, expected_role: str):
    inputs = root / "inputs" / match
    manifest = json.loads((root / "research-admission.json").read_bytes())
    receipt = json.loads((root / "independent-source.json").read_bytes())
    entry = next(x for x in receipt["normalization_receipts"] if x["match_id"] == match)
    if research.digest(inputs / "metadata.json") != entry["metadata_sha256"]:
        raise ValueError("staged metadata identity mismatch")
    expected_tracking = json.loads((root / "producer" / f"{match}.summary.json").read_bytes())[
        "tracking_sha256"
    ]
    if research.digest(inputs / "tracking.jsonl") != expected_tracking:
        raise ValueError("staged tracking identity mismatch")
    metadata = json.loads((inputs / "metadata.json").read_bytes())
    bounds, errors = skillcorner_period_ranges(metadata)
    if errors:
        raise ValueError("invalid metadata")
    counts = {}
    scene_count = window_count = 0
    stream_hash = hashlib.sha256()
    quality = {"detected": 0, "provider_extrapolated": 0}
    strata = {
        key: {model: [] for model in MODELS} for key in ("detected_only", "with_extrapolation")
    }
    totals = {model: [0.0, 0.0, 0.0] for model in MODELS}
    with (
        source.private_directory(inputs) as fd,
        (root / "producer" / f"{match}.jsonl").open("rb") as stream,
    ):
        samples = iter_skillcorner_5hz_v2(
            source._rows(fd, "tracking.jsonl", counts),
            metadata,
            source_release_id=source._authority()["source_release_id"],
        )
        for (period, frame, origin), support in p._population_events(samples, bounds):
            line = stream.readline()
            if not line:
                raise ValueError("missing population record")
            stream_hash.update(line)
            row = json.loads(line)
            if (
                row["match_id"],
                row["role"],
                row["period"],
                row["source_frame"],
                row["origin_sample_id"],
            ) != (match, expected_role, period, frame, origin):
                raise ValueError("origin identity differs")
            if not row["window_id"]:
                continue
            if row["window_id"] != p.prospective_window_id_v2(match, origin):
                raise ValueError("window identity differs")
            scenes = []
            scene_strata = []
            for side, locked in zip(("home", "away"), row["scenes"], strict=True):
                _, actual, scoreable = p._scene(support, side)
                if research.canonical(actual) != research.canonical(locked):
                    raise ValueError("scene, truth or mask mismatch")
                if scoreable:
                    scenes.append(score_scene(support, actual))
                    scene_count += 1
                    extrapolated = False
                    for sample in support[26:]:
                        players = p._player_map(sample)
                        for player_id in actual["player_ids"]:
                            player = players.get(int(player_id))
                            if p._pair(player) is not None:
                                key = (
                                    "detected" if player["is_detected"] else "provider_extrapolated"
                                )
                                quality[key] += 1
                                extrapolated |= not player["is_detected"]
                    scene_strata.append("with_extrapolation" if extrapolated else "detected_only")
            if scenes:
                window_count += 1
                for model in MODELS:
                    value = mean_metrics([s[model] for s in scenes])
                    for i in range(3):
                        totals[model][i] += value[i]
                    for key in strata:
                        subset = [
                            scene[model]
                            for scene, label in zip(scenes, scene_strata, strict=True)
                            if label == key
                        ]
                        if subset:
                            strata[key][model].append(mean_metrics(subset))
        if stream.read(1):
            raise ValueError("extra population records")
    if not window_count:
        raise ValueError("match has no scoreable windows")
    expected = manifest["per_match"][match]["counts"]
    if (
        window_count != expected["scoreable_windows"]
        or scene_count != expected["home_scenes"] + expected["away_scenes"]
    ):
        raise ValueError("scoreable population mismatch")
    if counts["tracking_sha256"] != expected_tracking:
        raise ValueError("staged tracking changed during scoring")
    if stream_hash.hexdigest() != manifest["artifacts"][match]["producer_sha256"]:
        raise ValueError("population stream changed during scoring")
    return {
        "match_id": match,
        "role": expected_role,
        "windows": window_count,
        "scenes": scene_count,
        "future_observation_quality_counts": quality,
        "quality_strata": {
            key: {
                "windows": len(values[MODELS[0]]),
                "metrics": {
                    model: mean_metrics(scores) if scores else None
                    for model, scores in values.items()
                },
            }
            for key, values in strata.items()
        },
        "metrics": {m: [v / window_count for v in totals[m]] for m in MODELS},
        "tracking_sha256": counts["tracking_sha256"],
    }


def runtime_identity():
    repo = Path(__file__).resolve().parents[1]
    files = sorted((repo / "src" / "fpdbench").rglob("*.py"))
    files += [Path(__file__).resolve(), repo / "tools" / "research_population_v1.py"]
    files += sorted((repo / "src" / "fpdbench").rglob("*.json"))
    return {
        "files": {str(path.relative_to(repo)): research.digest(path) for path in files},
        "python": sys.version,
        "executable_sha256": research.digest(Path(sys.executable).resolve()),
        "platform": platform.platform(),
        "dependencies": sorted(
            (d.metadata["Name"], d.version) for d in importlib.metadata.distributions()
        ),
        "research_manifest_sha256": MANIFEST,
    }


def run(root: Path, source_root: Path, output: Path, role: str):
    os.umask(0o077)
    if role not in ("validation", "evaluation", "training"):
        raise ValueError("invalid stage")
    if role == "validation":
        output.mkdir(mode=0o700)
    elif not (
        output
        / ("validation-complete.json" if role == "evaluation" else "evaluation-complete.json")
    ).exists():
        raise ValueError("preceding stage incomplete")
    if (output / f"{role}-started.json").exists():
        raise ValueError("stage already started; preserve partial evidence")
    manifest = verify(root, source_root)
    identity = runtime_identity()
    if role == "validation":
        research.write(output / "execution-identity.json", identity)
    elif json.loads((output / "execution-identity.json").read_bytes()) != json.loads(
        research.canonical(identity)
    ):
        raise ValueError("code or runtime changed after validation")
    if runtime_identity() != identity:
        raise ValueError("code or runtime changed")
    # A marker survives interruptions and prevents an evaluation retry.
    research.write(output / f"{role}-started.json", {"role": role})
    results = []
    for match, data in manifest["per_match"].items():
        if data["role"] != role:
            continue
        result = score_match(root, match, role)
        results.append(result)
        research.write(output / f"{role}-{match}.json", result)
        print(role, "MATCH_COMPLETE", match, flush=True)
    expected = {"validation": 4, "evaluation": 4, "training": 12}[role]
    if len(results) != expected or runtime_identity() != identity:
        raise ValueError("incomplete stage or changed runtime")
    cells = []
    for model in MODELS:
        aggregate = mean_metrics([row["metrics"][model] for row in results])
        for target in ("absolute_xy", "origin_relative_displacement"):
            for regime in ("history_only", "future_ball", "future_opponent_plus_ball"):
                cells.append({"cell_id": f"{model}|{regime}|{target}", "aggregate": aggregate})
    research.write(output / f"{role}-complete.json", {"role": role, "cells": cells})
    if role == "training":
        identity_sha256 = hashlib.sha256(research.canonical(identity)).hexdigest()
        for cell in cells:
            model, regime, target = cell["cell_id"].split("|")
            stages = {}
            for stage in ("validation", "evaluation", "training"):
                rows = [
                    json.loads(path.read_bytes())
                    for path in sorted(output.glob(f"{stage}-*.json"))
                    if path.name not in {f"{stage}-started.json", f"{stage}-complete.json"}
                ]
                stages[stage] = {
                    "matches": rows,
                    "equal_match_metrics": mean_metrics([row["metrics"][model] for row in rows]),
                }
            document = {
                "schema_id": "fpdbench.research-deterministic-result/1.0.0",
                "research_contract": manifest["schema_id"] + "/" + manifest["schema_version"],
                "research_manifest_sha256": MANIFEST,
                "execution_identity_sha256": identity_sha256,
                "population_artifact_identities": manifest["artifacts"],
                "cell_id": cell["cell_id"],
                "model": model,
                "regime": regime,
                "target_representation": target,
                "status": "descriptive_research_only",
                "stages": stages,
            }
            research.write(output / f"cell-{model}-{regime}-{target}.json", document)


if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit("usage: research_baseline_v1.py RESEARCH_ROOT SOURCE_ROOT OUTPUT ROLE")
    run(*(Path(value) for value in sys.argv[1:4]), sys.argv[4])
