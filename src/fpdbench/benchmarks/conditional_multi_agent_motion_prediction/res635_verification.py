"""Independent receipt readback, metric calculation and 72-record aggregation.

Shares only synthetic input/model prediction and public frozen measurement contracts with
 the scorer. Never accepts the scorer's campaign aggregate as authority.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, cast

from fpdbench.evaluation.metrics.trajectory import masked_physical_trajectory_metrics

from . import learned_deepsets as lds
from . import res635_post_failure_evaluation as scorer


def independent_match(match: str, count: int, models: scorer.Models) -> scorer.Document:
    """Separate scalar public-metric path and explicit scene/window arithmetic."""
    sums = [[[0.0] * 3 for _ in scorer.STRATA] for _ in scorer.CELLS]
    counts = [[0] * len(scorer.STRATA) for _ in scorer.CELLS]
    identity = scorer.StreamIdentity(match)
    for row in scorer.windows(match, count):
        identity.observe(row)
        values: dict[tuple[int, int], list[list[float]]] = {}
        for cell, scene, prediction in scorer.predictions(row, models):
            if not scene["scoreable"]:
                continue
            lds.validate_truth_scene(scene)
            for j, stratum in enumerate(scorer.STRATA):
                if j >= 4 and scene["quality"] != stratum:
                    continue
                start, end = {"early": (0, 5), "middle": (5, 10), "late": (10, 15)}.get(
                    stratum, (0, 15)
                )
                actual = scene["absolute_xy"][start:end]
                if not any(p is not None for p in actual[-1]):
                    continue
                predicted = prediction[:, start:end].transpose(1, 0, 2).tolist()
                metric = masked_physical_trajectory_metrics([predicted], [actual])
                values.setdefault((cell, j), []).append(
                    [metric.ade_m, metric.fde_m, metric.xy_rmse_m]
                )
        for (cell, j), scenes in values.items():
            for k in range(3):
                sums[cell][j][k] += sum(s[k] for s in scenes) / len(scenes)
            counts[cell][j] += 1
    records: list[scorer.Document] = []
    for i, cell in enumerate(scorer.CELLS):
        strata = {
            s: {
                "windows": counts[i][j],
                "metrics": {m: sums[i][j][k] / counts[i][j] for k, m in enumerate(scorer.METRICS)}
                if counts[i][j]
                else None,
            }
            for j, s in enumerate(scorer.STRATA)
        }
        records.append({"cell": list(cell), "strata": strata})
    return {
        "match": match,
        "identity": identity.result(),
        "records": records,
        "provenance": scorer.provenance(),
    }


def assert_equivalent(actual: Any, expected: Any) -> None:
    """Only numerical metric roundoff is tolerated; structure and counts are exact."""
    if isinstance(expected, float):
        if type(actual) is not float or not math.isclose(
            actual, expected, rel_tol=0, abs_tol=1e-12
        ):
            raise ValueError("independent metric parity failed")
    elif isinstance(expected, dict):
        if not isinstance(actual, dict) or actual.keys() != expected.keys():
            raise ValueError("independent record shape differs")
        for key, value in cast(dict[str, Any], expected).items():
            assert_equivalent(actual[key], value)
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(cast(list[Any], actual)) != len(
            cast(list[Any], expected)
        ):
            raise ValueError("incomplete cell matrix")
        for a, e in zip(cast(list[Any], actual), cast(list[Any], expected), strict=True):
            assert_equivalent(a, e)
    elif type(actual) is not type(expected) or actual != expected:
        raise ValueError("identity, denominator, or provenance differs")


EVALUATION_MATCHES = ("1874553", "1925299", "2006229", "2010085")


def _valid_metrics(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    metrics = cast(dict[str, object], value)
    for name in scorer.METRICS:
        number = metrics.get(name)
        if type(number) not in (int, float) or not math.isfinite(cast(float, number)):
            return False
        if cast(float, number) < 0:
            return False
    return True


def aggregate(
    receipts: list[scorer.Document], *, matches: tuple[str, ...] = scorer.MATCHES
) -> scorer.Document:
    if matches not in (scorer.MATCHES, EVALUATION_MATCHES):
        raise ValueError("unrecognized match inventory")
    if [r["match"] for r in receipts] != list(matches):
        raise ValueError("exactly four ordered matches required")
    seed_means: dict[str, list[dict[str, float]]] = {}
    for regime in lds.INFORMATION_REGIMES:
        for representation in lds.TARGET_REPRESENTATIONS:
            key = f"{regime}/{representation}"
            seed_means[key] = []
            for receipt in receipts:
                records = receipt["records"]
                if [r["cell"] for r in records] != [list(c) for c in scorer.CELLS]:
                    raise ValueError("expected 18 unique ordered cells")
                selected = [
                    r["strata"]["all"]["metrics"]
                    for r in records
                    if r["cell"][:2] == [regime, representation]
                ]
                if any(not _valid_metrics(row) for row in selected):
                    raise ValueError("invalid aggregate metric")
                seed_means[key].append({m: sum(r[m] for r in selected) / 3 for m in scorer.METRICS})
    means = {
        key: {m: sum(v[m] for v in matches) / 4 for m in scorer.METRICS}
        for key, matches in seed_means.items()
    }
    contrasts: dict[str, scorer.Document] = {}
    for representation in lds.TARGET_REPRESENTATIONS:
        for name, left, right in (
            ("C1", "history_only", "future_ball"),
            ("C2", "future_ball", "future_opponent_plus_ball"),
        ):
            values = [
                seed_means[f"{left}/{representation}"][i]["ade_m"]
                - seed_means[f"{right}/{representation}"][i]["ade_m"]
                for i in range(4)
            ]
            contrasts[f"{name}/{representation}"] = {
                "matches": values,
                "equal_match_mean": sum(values) / 4,
            }
    return {
        "records": 72,
        "seed_means_within_match": seed_means,
        "equal_match_means": means,
        "contrasts": contrasts,
    }


def verify_prefix(
    directory: Path, count: int, seals: list[str], *, replay: bool = True
) -> list[scorer.Document]:
    """External ledger seals are authoritative, never receipt self hashes alone."""
    import json

    if not 0 <= len(seals) <= 4:
        raise ValueError("invalid receipt prefix")
    if any(directory.glob("*.tmp")) or any(directory.glob(".*.tmp")):
        raise ValueError("partial receipt write present")
    names = sorted(p.name for p in directory.glob("match-*.json"))
    if names != [f"match-{i}.json" for i in range(len(seals))]:
        raise ValueError("partial, extra, duplicated or missing receipt")
    models = scorer.models() if replay and seals else None
    previous = "0" * 64
    receipts: list[scorer.Document] = []
    for i, seal in enumerate(seals):
        path = directory / f"match-{i}.json"
        if path.is_symlink() or path.stat().st_size > 1_000_000:
            raise ValueError("invalid receipt file")
        receipt = json.loads(path.read_bytes())
        if scorer.digest(receipt) != seal or receipt["previous_sha256"] != previous:
            raise ValueError("altered or forged receipt chain")
        if receipt["match"] != scorer.MATCHES[i] or receipt["scope_sha256"] != receipts_scope(
            count
        ):
            raise ValueError("wrong match or synthetic scope")
        body = {k: v for k, v in receipt.items() if k not in ("scope_sha256", "previous_sha256")}
        if models is not None:
            assert_equivalent(body, independent_match(scorer.MATCHES[i], count, models))
        previous = seal
        receipts.append(receipt)
    return receipts


def receipts_scope(count: int) -> str:
    return scorer.digest(
        {
            "namespace": "RES643-SYNTHETIC-ONLY-v1",
            "windows_per_match": count,
            "provenance": scorer.provenance(),
        }
    )
