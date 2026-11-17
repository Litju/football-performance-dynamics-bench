"""Read sealed RES646 results; publish only non-reconstructive match aggregates.

Run with the existing research environment. No model or source-data loading occurs.
"""

import argparse
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
from statistics import mean, stdev

ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction"
OUT = ROOT / "docs/res440"
REGIMES = ("history_only", "future_ball", "future_opponent_plus_ball")
REPS = ("absolute_xy", "origin_relative_displacement")
METRICS = ("ade_m", "fde_m", "xy_rmse_m")
SEEDS = (1729, 2718, 31415)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def calculate(matches, stratum="all"):
    """Seed means precede equal-match means, including coordinate RMSE."""
    rows = []
    expected = set(itertools.product(REGIMES, REPS, SEEDS))
    for match in matches:
        records = match["records"]
        assert len(records) == 18 and {tuple(r["cell"]) for r in records} == expected
        for regime, rep in itertools.product(REGIMES, REPS):
            selected = [r["strata"][stratum] for r in records if r["cell"][:2] == [regime, rep]]
            assert all(r["windows"] > 0 and r["metrics"] is not None for r in selected)
            if stratum in ("all", "early", "middle", "late"):
                assert all(r["windows"] == match["windows"] for r in selected)
            values = {m: mean(r["metrics"][m] for r in selected) for m in METRICS}
            assert all(math.isfinite(x) and x >= 0 for x in values.values())
            rows.append(
                {"match": match["match_id"], "regime": regime, "representation": rep, **values}
            )
    return rows


def table(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def markdown_table(headers, rows):
    return "\n".join(
        ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
        + ["| " + " | ".join(map(str, row)) + " |" for row in rows]
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    p = json.loads(args.package.read_bytes())
    assert p["status"] == "COMPLETED_VERIFIED_REAL_RESEARCH_ONLY"
    assert p["research_only"] is True and p["protected_status"] == "NOT_QUALIFIED"
    assert p["attempts"] == 1 and p["continuation_used"] is False
    assert p["record_count"] == 72 and p["window_count"] == 51713

    # Existing completion verification authenticates the ledger and reads receipts only.
    from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
        res635_execution as execution,
    )
    from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
        res635_verification as verification,
    )
    from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
        res645_workloads as workloads,
    )

    config_path = Path(p["campaign_config"])
    assert sha(config_path) == p["campaign_config_sha256"]
    work = workloads.RealWorkload(config_path)
    assert work.campaign.scope == p["scope_sha256"]
    assert work.campaign.identities == p["identities"]
    ledger = work.campaign.record()
    assert ledger["authorization_sha256"] == p["authorization_sha256"]
    assert ledger["attempt"] == 0
    result = execution.verify_complete(
        work.campaign.root, work.campaign.output, 51713, workload=work
    )
    assert sha(work.campaign.output / "result.json") == p["result_file_sha256"]
    verification.assert_equivalent(p["aggregate"], result["aggregate"])
    assert [m["match_id"] for m in p["matches"]] == list(verification.EVALUATION_MATCHES)
    assert sum(m["windows"] for m in p["matches"]) == 51713
    receipts = []
    for match, seal in zip(p["matches"], result["seals"], strict=True):
        path = Path(match["receipt_path"])
        assert sha(path) == match["receipt_file_sha256"] == match["receipt_seal_sha256"] == seal
        receipt = json.loads(path.read_bytes())
        verification.assert_equivalent(match["records"], receipt["records"])
        assert match["record_count"] == 18
        assert receipt["identity"]["windows"] == match["windows"]
        receipts.append(receipt)

    protocol_path = AUTH / "res635_post_failure_descriptive_protocol_v1.json"
    protocol = json.loads(protocol_path.read_bytes())
    baseline_path = AUTH / "res593_baseline_reference_v1.json"
    baseline = json.loads(baseline_path.read_bytes())
    assert sha(baseline_path) == protocol["deterministic_reference"]["baseline_reference_sha256"]
    manifest = json.loads((AUTH / "res593_checkpoint_manifest_v1.json").read_bytes())
    assert all(
        c["population_manifest_sha256"] == baseline["research_admission_sha256"]
        and c["protocol_sha256"] == baseline["original_protocol_sha256"]
        for c in manifest["checkpoints"]
    )
    for receipt in receipts:
        assert receipt["provenance"]["protocol_sha256"] == sha(protocol_path)
        for key, value in baseline["scored_denominators"][receipt["match"]].items():
            identity_key = "scoreable_scenes" if key == "scenes" else key
            assert receipt["identity"][identity_key] == value

    rows = calculate(p["matches"])
    summary = []
    for regime, rep in itertools.product(REGIMES, REPS):
        selected = [r for r in rows if (r["regime"], r["representation"]) == (regime, rep)]
        row = {"regime": regime, "representation": rep}
        for metric in METRICS:
            values = [r[metric] for r in selected]
            row.update(
                {
                    metric: mean(values),
                    metric + "_sd": stdev(values),
                    metric + "_min": min(values),
                    metric + "_max": max(values),
                }
            )
            assert math.isclose(
                row[metric],
                p["aggregate"]["equal_match_means"][f"{regime}/{rep}"][metric],
                abs_tol=1e-12,
                rel_tol=0,
            )
        summary.append(row)
    lookup = {(r["match"], r["regime"], r["representation"]): r for r in rows}
    contrasts = []
    for spec in protocol["contrasts"]:
        name, rep = spec["id"], spec["representation"]
        left, right = REGIMES[:2] if name == "C1" else REGIMES[1:]
        values = [
            lookup[m["match_id"], left, rep]["ade_m"] - lookup[m["match_id"], right, rep]["ade_m"]
            for m in p["matches"]
        ]
        verification.assert_equivalent(
            {"matches": values, "equal_match_mean": mean(values)},
            p["aggregate"]["contrasts"][f"{name}/{rep}"],
        )
        contrasts.append(
            {
                "contrast": name,
                "representation": rep,
                **dict(zip(verification.EVALUATION_MATCHES, values, strict=True)),
                "mean_m": mean(values),
                "sd_m": stdev(values),
                "min_m": min(values),
                "max_m": max(values),
                "delete_one_min_m": min((sum(values) - x) / 3 for x in values),
                "delete_one_max_m": max((sum(values) - x) / 3 for x in values),
            }
        )
    comparisons = []
    for model, scores in baseline["models"].items():
        for rep in REPS:
            for metric in METRICS:
                diffs = [
                    scores[m][metric] - lookup[m, "history_only", rep][metric]
                    for m in verification.EVALUATION_MATCHES
                ]
                base = mean(v[metric] for v in scores.values())
                comparisons.append(
                    {
                        "baseline": model,
                        "representation": rep,
                        "metric": metric,
                        "baseline_mean_m": base,
                        "learned_mean_m": base - mean(diffs),
                        "baseline_minus_learned_m": mean(diffs),
                        "reduction_percent": 100 * mean(diffs) / base,
                        **dict(zip(verification.EVALUATION_MATCHES, diffs, strict=True)),
                    }
                )
    strata = []
    for stratum in ("early", "middle", "late", "detected_only", "with_provider_extrapolation"):
        sub = calculate(p["matches"], stratum)
        for regime, rep in itertools.product(REGIMES, REPS):
            selected = [r for r in sub if (r["regime"], r["representation"]) == (regime, rep)]
            strata.append(
                {
                    "stratum": stratum,
                    "regime": regime,
                    "representation": rep,
                    **{m: mean(r[m] for r in selected) for m in METRICS},
                }
            )

    # Explicit allowlist: never serialize the private package, receipt bodies, or ledger.
    public = {
        "classification": "research-only NOT_QUALIFIED",
        "independent_units": 4,
        "records": 72,
        "windows": 51713,
        "attempts": 1,
        "provenance": {
            "execution_commit": p["commit"],
            "package_sha256": sha(args.package),
            "scope_sha256": p["scope_sha256"],
            "result_file_sha256": p["result_file_sha256"],
            "protocol_sha256": sha(protocol_path),
            "baseline_reference_sha256": sha(baseline_path),
            "verification": "existing authenticated verify_complete; no replay",
        },
        "summary": summary,
        "match_means": rows,
        "contrasts": contrasts,
        "history_baseline_comparisons": comparisons,
        "strata": strata,
        "denominators": [
            {
                "match": r["match"],
                **baseline["scored_denominators"][r["match"]],
                **r["identity"]["future_target_missingness"],
                "scene_quality": r["identity"]["scoreable_scene_quality"],
            }
            for r in receipts
        ],
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "findings.json").write_text(json.dumps(public, indent=2, allow_nan=False) + "\n")
    for name, data in (
        ("summary", summary),
        ("match-means", rows),
        ("contrasts", contrasts),
        ("history-baselines", comparisons),
        ("strata", strata),
    ):
        table(OUT / f"{name}.csv", data)
    labels = {"absolute_xy": "Absolute XY", "origin_relative_displacement": "Displacement"}
    text = "# RES-440 scientific tables\n\n"
    text += (
        "All errors are metres. Four independent matches; three seeds averaged within each "
        "match. SD is descriptive sample SD across four match means, not uncertainty. "
        "Research-only `NOT_QUALIFIED`. Source: [safe findings](findings.json).\n\n"
    )
    text += "## 1. Physical trajectory error\n\n"
    text += markdown_table(
        ["Information regime", "Target", "ADE mean ± SD", "FDE mean ± SD", "XY RMSE mean ± SD"],
        [
            [
                r["regime"],
                labels[r["representation"]],
                *[f"{r[m]:.4f} ± {r[m + '_sd']:.4f}" for m in METRICS],
            ]
            for r in summary
        ],
    )
    text += "\n\n## 2. Prespecified paired ADE contrasts\n\n"
    text += (
        "C1 = history − future ball; C2 = future ball − (future opponents + ball). "
        "Positive values indicate lower ADE with added realized future context.\n\n"
    )
    text += markdown_table(
        ["Contrast", "Target", *verification.EVALUATION_MATCHES, "Mean", "SD", "Delete-one range"],
        [
            [
                r["contrast"],
                labels[r["representation"]],
                *[f"{r[m]:.4f}" for m in verification.EVALUATION_MATCHES],
                f"{r['mean_m']:.4f}",
                f"{r['sd_m']:.4f}",
                f"{r['delete_one_min_m']:.4f}–{r['delete_one_max_m']:.4f}",
            ]
            for r in contrasts
        ],
    )
    text += "\n\nDeletion ranges are descriptive sensitivity, not confidence intervals.\n\n"
    text += "## 3. History-only comparisons with frozen deterministic baselines\n\n"
    text += markdown_table(
        ["Baseline", "Learned target", "Metric", "Baseline", "Learned", "Reduction (m)", "%"],
        [
            [
                r["baseline"],
                labels[r["representation"]],
                r["metric"],
                *[
                    f"{r[k]:.4f}"
                    for k in ("baseline_mean_m", "learned_mean_m", "baseline_minus_learned_m")
                ],
                f"{r['reduction_percent']:.1f}",
            ]
            for r in comparisons
        ],
    )
    text += (
        "\n\nBaselines are means of the published four-decimal match values; each baseline "
        "mean and baseline-minus-learned difference has a rounding bound of 0.00005 m. "
        "Conditional regimes are excluded from this forecasting comparison.\n\n"
    )
    text += "## 4. Predeclared horizon and target-quality ADE\n\n"
    text += markdown_table(
        ["Stratum", "Information regime", "Target", "ADE"],
        [
            [r["stratum"], r["regime"], labels[r["representation"]], f"{r['ade_m']:.4f}"]
            for r in strata
        ],
    )
    text += (
        "\n\nEarly/middle/late = 0.2–1.0/1.2–2.0/2.2–3.0 s. Quality strata "
        "classify scenes; windows can contribute to both quality strata. "
        "They are not additive or causal quality comparisons. "
        "All stratum FDE/RMSE values are in [strata.csv](strata.csv).\n"
    )
    (OUT / "tables.md").write_text(text)
    print("Verified 72 records / four sealed receipts / 51,713 windows; safe aggregates written.")


if __name__ == "__main__":
    main()
