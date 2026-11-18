"""Paper A evidence tables agree with public aggregates and frozen authorities."""

import json
import re
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOC_PATH = ROOT / "docs/paper-a-evidence.md"
DOC = DOC_PATH.read_text(encoding="utf-8")
FINDINGS = json.loads((ROOT / "docs/res440/findings.json").read_text())
TASK = ROOT / "src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction"
PROTOCOL = json.loads((TASK / "prospective_skillcorner_protocol_v2.json").read_text())
PLAN = json.loads((TASK / "empirical_experiment_plan_v2.json").read_text())
CHECKPOINTS = json.loads((TASK / "res593_checkpoint_manifest_v1.json").read_text())["checkpoints"]
REGIME_ORDER = ("history_only", "future_ball", "future_opponent_plus_ball")
TARGETS = {"Absolute XY": "absolute_xy", "Displacement": "origin_relative_displacement"}
MATCHES = [d["match"] for d in FINDINGS["denominators"]]


def rows(prefix: str) -> list[list[str]]:
    found = []
    for line in DOC.splitlines():
        if line.startswith(prefix):
            found.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return found


def four(value: float) -> str:
    return f"{value:.4f}"


def summary(regime: str, representation: str) -> dict:
    return next(
        r
        for r in FINDINGS["summary"]
        if r["regime"] == regime and r["representation"] == representation
    )


def test_six_configuration_table_matches_findings():
    table = [r for r in rows("| `") if len(r) == 5 and r[1] in TARGETS]
    assert len(table) == 6
    for cells in table:
        regime = cells[0].split("`")[1]
        row = summary(regime, TARGETS[cells[1]])
        assert cells[2:] == [four(row["ade_m"]), four(row["fde_m"]), four(row["xy_rmse_m"])]
    for regime in REGIME_ORDER:
        absolute = summary(regime, "absolute_xy")
        displacement = summary(regime, "origin_relative_displacement")
        for metric in ("ade_m", "fde_m", "xy_rmse_m"):
            assert displacement[metric] < absolute[metric]
    gaps = [
        four(
            summary(r, "absolute_xy")["ade_m"] - summary(r, "origin_relative_displacement")["ade_m"]
        )
        for r in REGIME_ORDER
    ]
    assert "ADE gaps were {}, {} and {} m".format(*gaps) in DOC


def test_paired_contrasts_match_findings_and_are_all_positive():
    table = [r for r in rows("| C") if r[0] in {"C1", "C2"}]
    assert len(table) == 4
    for cells in table:
        row = next(
            c
            for c in FINDINGS["contrasts"]
            if c["contrast"] == cells[0] and c["representation"] == TARGETS[cells[1]]
        )
        assert cells[2:] == [four(row[m]) for m in MATCHES] + [four(row["mean_m"])]
        assert all(row[m] > 0 for m in MATCHES)
    assert "All 16 match-level differences are positive." in DOC


def test_baseline_table_and_headline_reductions():
    comparisons = FINDINGS["history_baseline_comparisons"]
    for name, baseline in (
        ("Origin persistence", "origin_persistence_v1"),
        ("Constant velocity, 1 s", "constant_velocity_1s_v1"),
    ):
        (cells,) = rows(f"| {name} |")
        expected = [
            four(
                next(
                    c["baseline_mean_m"]
                    for c in comparisons
                    if c["baseline"] == baseline and c["metric"] == metric
                )
            )
            for metric in ("ade_m", "fde_m", "xy_rmse_m")
        ]
        assert cells[1:4] == expected
    for representation, label in (
        ("absolute_xy", "DeepSets, absolute XY"),
        ("origin_relative_displacement", "DeepSets, displacement"),
    ):
        row = next(
            c
            for c in comparisons
            if c["baseline"] == "constant_velocity_1s_v1"
            and c["representation"] == representation
            and c["metric"] == "ade_m"
        )
        (cells,) = rows(f"| {label} |")
        reduction = f"{four(row['baseline_minus_learned_m'])} m ({row['reduction_percent']:.1f}%)"
        assert cells[4] == reduction
        assert reduction in DOC.split("## 7.")[1]
    assert "1.6680 m ADE against 2.2433 m" in DOC


def test_early_horizon_reversal_and_extrapolation_share():
    def early(regime, representation):
        return next(
            s["ade_m"]
            for s in FINDINGS["strata"]
            if s["stratum"] == "early"
            and s["regime"] == regime
            and s["representation"] == representation
        )

    ball, full = (
        early("future_ball", "absolute_xy"),
        early("future_opponent_plus_ball", "absolute_xy"),
    )
    assert full > ball
    assert f"{four(full)} m against {four(ball)} m" in DOC
    assert f"reversal of {four(full - ball)} m" in DOC
    displacement = [early(r, "origin_relative_displacement") for r in REGIME_ORDER]
    assert displacement == sorted(displacement, reverse=True)
    assert "early-interval ADE was {}, {} and {} m".format(*map(four, displacement)) in DOC

    denominators = FINDINGS["denominators"]
    extrapolated = sum(d["provider_extrapolated"] for d in denominators)
    scored = sum(d["scored_points"] for d in denominators)
    scenes = sum(d["scenes"] for d in denominators)
    detected = sum(d["scene_quality"]["detected_only"] for d in denominators)
    assert f"{extrapolated:,} of the {scored:,}" in DOC
    assert f"({100 * extrapolated / scored:.1f}%" in DOC
    assert f"{detected:,} of {scenes:,} directed scenes" in DOC
    assert f"{FINDINGS['windows']:,} overlapping windows and {scenes:,} directed scenes" in DOC


def test_design_accounting_matches_frozen_authorities():
    roles = PROTOCOL["scientific_state"]["split"]["roles"]
    seeds = PLAN["seeds"]
    assert (len(roles["training"]), len(roles["validation"]), len(roles["evaluation"])) == (
        12,
        4,
        4,
    )
    assert roles["evaluation"] == MATCHES
    assert (seeds["final_fit_count"], seeds["lomo_fit_count"], seeds["total_learned_fits"]) == (
        18,
        216,
        234,
    )
    assert len(CHECKPOINTS) == 18
    assert {tuple(c["train_match_ids"]) for c in CHECKPOINTS} == {tuple(roles["training"])}
    assert {tuple(c["validation_match_ids"]) for c in CHECKPOINTS} == {tuple(roles["validation"])}
    assert FINDINGS["records"] == 72 and FINDINGS["independent_units"] == 4
    assert FINDINGS["classification"] == "research-only NOT_QUALIFIED"
    assert ", ".join(map(str, seeds["stochastic_seed_ids"])) in DOC.replace(" and ", ", ")
    for text in ("| 234 |", "| 216 |", "18 checkpoints, 72 match/seed records", "n = 4"):
        assert text in DOC


@pytest.mark.parametrize("target", re.findall(r"\]\(([^)]+)\)", DOC))
def test_local_links_and_figures_resolve(target):
    if target.startswith(("http://", "https://")):
        return
    path, _, anchor = target.partition("#")
    resolved = (DOC_PATH.parent / unquote(path)).resolve() if path else DOC_PATH
    assert resolved.is_file(), target
    assert resolved.suffix.casefold() != ".csv"
    if anchor and resolved.suffix == ".md":
        headings = {
            re.sub(r"[^\w\- ]", "", h.strip().casefold()).replace(" ", "-")
            for h in re.findall(r"^#+ (.+)$", resolved.read_text(encoding="utf-8"), re.M)
        }
        assert anchor in headings, target
