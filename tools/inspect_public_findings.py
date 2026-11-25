"""Read-only public aggregate checks and compact tables; no protected inputs or model inference."""

from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FINDINGS = ROOT / "docs" / "res440" / "findings.json"
REGIMES = ("history_only", "future_ball", "future_opponent_plus_ball")
REPRESENTATIONS = ("absolute_xy", "origin_relative_displacement")
METRICS = ("ade_m", "fde_m", "xy_rmse_m")
MATCH_COUNT = 4
LEARNED_RECORDS = 72
OVERLAPPING_WINDOWS = 51713


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def near(observed: object, expected: float, description: str) -> None:
    require(
        isinstance(observed, (float, int))
        and math.isfinite(observed)
        and math.isclose(float(observed), expected, rel_tol=1e-11, abs_tol=1e-9),
        f"{description}: public aggregate does not reconcile",
    )


def load(path: Path = PUBLIC_FINDINGS) -> dict[str, Any]:
    """Load public, tracked aggregate JSON only; never read a local result/receipt registry."""
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), "findings must be a JSON object")
    return value


def audit(data: dict[str, Any]) -> dict[str, Any]:
    """Independently reconcile match-first summaries and four paired contrasts."""
    require(data.get("classification") == "research-only NOT_QUALIFIED", "scope changed")
    require(data.get("independent_units") == MATCH_COUNT, "wrong independent match count")
    require(data.get("records") == LEARNED_RECORDS, "wrong learned record count")
    require(data.get("windows") == OVERLAPPING_WINDOWS, "wrong window accounting")

    denominators = data["denominators"]
    matches = [row["match"] for row in denominators]
    require(len(matches) == MATCH_COUNT and len(set(matches)) == MATCH_COUNT, "match keys")
    require(sum(row["windows"] for row in denominators) == OVERLAPPING_WINDOWS, "windows")
    require(
        sum(row["scenes"] for row in denominators) == OVERLAPPING_WINDOWS * 2,
        "directed scenes",
    )

    summary_rows = data["summary"]
    match_rows = data["match_means"]
    require(len(summary_rows) == len(REGIMES) * len(REPRESENTATIONS), "summary row count")
    require(len(match_rows) == MATCH_COUNT * len(summary_rows), "match row count")

    summary: dict[tuple[str, str], dict[str, Any]] = {}
    by_match: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in summary_rows:
        key = row["regime"], row["representation"]
        require(key not in summary, "duplicate configuration")
        summary[key] = row
    require(
        set(summary) == {(r, rep) for r in REGIMES for rep in REPRESENTATIONS},
        "configuration coverage",
    )
    for row in match_rows:
        key = row["match"], row["regime"], row["representation"]
        require(key not in by_match, "duplicate match/configuration")
        by_match[key] = row
    require(
        set(by_match) == {(match, reg, rep) for match in matches for reg, rep in summary},
        "match configuration coverage",
    )

    for (regime, representation), aggregate in summary.items():
        for metric in METRICS:
            values = [by_match[match, regime, representation][metric] for match in matches]
            near(aggregate[metric], mean(values), f"{regime}/{representation}/{metric}")

    contrasts = data["contrasts"]
    require(len(contrasts) == 4, "contrast count")
    seen_contrasts: set[tuple[str, str]] = set()
    for row in contrasts:
        contrast, rep = row["contrast"], row["representation"]
        key = contrast, rep
        require(key not in seen_contrasts, "duplicate contrast")
        seen_contrasts.add(key)
        require(contrast in {"C1", "C2"} and rep in REPRESENTATIONS, "unknown contrast")
        left, right = (
            ("history_only", "future_ball")
            if contrast == "C1"
            else ("future_ball", "future_opponent_plus_ball")
        )
        differences = []
        for match in matches:
            difference = (
                by_match[match, left, rep]["ade_m"]
                - by_match[match, right, rep]["ade_m"]
            )
            near(row[match], difference, f"{contrast}/{rep}/{match}")
            differences.append(difference)
        near(row["mean_m"], mean(differences), f"{contrast}/{rep}/equal-match mean")
    require(
        seen_contrasts == {(contrast, rep) for contrast in ("C1", "C2") for rep in REPRESENTATIONS},
        "contrast coverage",
    )

    baselines = data["history_baseline_comparisons"]
    require(len(baselines) == 12, "baseline comparison count")
    baselines_seen: set[tuple[str, str, str]] = set()
    for row in baselines:
        baseline, rep, metric = row["baseline"], row["representation"], row["metric"]
        key = baseline, rep, metric
        require(key not in baselines_seen, "duplicate baseline")
        baselines_seen.add(key)
        require(
            baseline in {"origin_persistence_v1", "constant_velocity_1s_v1"}
            and rep in REPRESENTATIONS
            and metric in METRICS,
            "unexpected baseline comparison",
        )
        learned = summary["history_only", rep][metric]
        near(row["learned_mean_m"], learned, f"{baseline}/{rep}/{metric}/learned")
        difference = row["baseline_mean_m"] - learned
        near(row["baseline_minus_learned_m"], difference, "baseline reduction")
        near(
            row["reduction_percent"],
            100 * difference / row["baseline_mean_m"],
            "baseline reduction percent",
        )
    require(
        len(baselines_seen) == 2 * len(REPRESENTATIONS) * len(METRICS),
        "baseline coverage",
    )

    return {"matches": matches, "summary": summary, "contrasts": contrasts}


def render(data: dict[str, Any]) -> str:
    verified = audit(data)
    rows = [
        "PUBLIC AGGREGATE CHECK: PASS (match-first tables; no private model replay)",
        f"Scope: {data['classification']}; independent matches: {data['independent_units']}",
        f"Overlapping windows: {data['windows']}; learned match/seed records: {data['records']}",
        "",
        "| Regime | Representation | ADE (m) | FDE at 3 s (m) | Scalar XY RMSE (m) |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for regime in REGIMES:
        for representation in REPRESENTATIONS:
            cell = verified["summary"][regime, representation]
            rows.append(
                f"| {regime} | {representation} | {cell['ade_m']:.4f} | "
                f"{cell['fde_m']:.4f} | {cell['xy_rmse_m']:.4f} |"
            )
    rows.extend(
        [
            "",
            "| Contrast | Target | Equal-match paired ADE difference (m) |",
            "| --- | --- | ---: |",
        ]
    )
    for row in verified["contrasts"]:
        rows.append(
            f"| {row['contrast']} | {row['representation']} | {row['mean_m']:.4f} |"
        )
    rows.extend(
        [
            "",
            "C1 = history-only minus realized-future-ball ADE; C2 = future-ball minus "
            "future-opponent-plus-ball ADE. Positive is lower error with added *realized* context.",
            "Only history_only is an ex-ante forecast. Results are descriptive n=4; "
            "no inferential or generalized claim is supported.",
            "The program has no public trained checkpoint bytes or raw SkillCorner data.",
        ]
    )
    return "\n".join(rows)


def main() -> int:
    print(render(load()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
