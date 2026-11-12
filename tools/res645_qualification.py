"""RES645 synthetic qualification measurements (invented fixtures only; no real input exists here).

``measure``  : stream one invented match of N samples through the complete production path
               (source adapter -> features -> artificial checkpoints -> metrics) and print
               traced-allocation, RSS, CPU and wall measurements as JSON.
``report``   : run ``measure`` in separate processes for a small and a large match, run a full
               supervised four-match fixture campaign, compare the independent calculator with the
               scorer, and write a public-safe JSON report.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import platform
import resource
import subprocess
import sys
import tempfile
import time
import tracemalloc
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

PKG = "fpdbench.benchmarks.conditional_multi_agent_motion_prediction"


def measure(samples: int) -> dict[str, Any]:
    from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
        res645_checkpoints as ck,
    )
    from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
        res645_fixtures as fx,
    )
    from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
        res645_pipeline as pipe,
    )
    from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
        res645_source_stream as src,
    )

    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw) / "work"
        root.mkdir(mode=0o700)
        fx.build_match(root / "match-0", 0, samples)
        manifest = fx.build_checkpoints(root / "checkpoints", root / "receipts")
        spec = src.SourceMatchSpec("synthetic-match-0", fx.FIXTURE_MATCH_IDS[0], root / "match-0")
        frozen = ck.load_models(manifest, root / "checkpoints", "synthetic", root / "receipts")
        tracemalloc.start()
        cpu0, wall0 = time.process_time(), time.monotonic()
        match = src.SourceMatch(spec, "synthetic")
        match.prepare()
        count = sum(1 for _ in match.windows())
        match = src.SourceMatch(spec, "synthetic")
        match.prepare()
        body = pipe.score_stream(
            spec.label, spec.match_id, match.windows(), frozen, count, lambda: None
        )
        _, traced_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return {
            "samples": samples,
            "eligible_windows": count,
            "scoreable_windows": body["identity"]["scoreable_windows"],
            "tracking_bytes": (root / "match-0" / "tracking.jsonl").stat().st_size,
            "fixture_disk_bytes": sum(p.stat().st_size for p in root.rglob("*") if p.is_file()),
            "traced_peak_bytes": traced_peak,
            "ru_maxrss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            "cpu_s": round(time.process_time() - cpu0, 3),
            "wall_s": round(time.monotonic() - wall0, 3),
            "forward_calls": count * 18,  # one batched forward (both scenes) per cell per window
        }


def run(arguments: list[str]) -> str:
    done = subprocess.run(arguments, capture_output=True, text=True, check=False)
    if done.returncode:
        raise SystemExit(done.stderr)
    return done.stdout


def campaign() -> dict[str, Any]:
    import torch

    from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
        learned_deepsets as lds,
    )
    from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
        res635_execution as e,
    )
    from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
        res635_post_failure_evaluation as s,
    )
    from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
        res645_fixtures as fx,
    )
    from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
        res645_independent as ind,
    )
    from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
        res645_source_stream as src,
    )
    from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
        res645_workloads as wl,
    )

    with tempfile.TemporaryDirectory() as raw:
        base = Path(raw)
        bundle = fx.build_bundle(base / "bundle")
        workload = wl.FixtureWorkload(bundle)
        root, output = base / "ledger", base / "output"
        e.launch(root, output, workload.windows, workload=workload)
        end = time.monotonic() + 600
        while not (output / "status.json").exists():
            if time.monotonic() > end:
                raise SystemExit("campaign timeout")
            time.sleep(0.2)
        status = e.read(output / "status.json")
        if status["exit_code"] != 0:
            raise SystemExit((output / "supervisor.log").read_text())
        record = e.bound_record(root, output, workload.windows, workload=workload)
        manifest = e.verify_complete(root, output, workload.windows, workload=workload)
        attestation = e.authenticated(output / "postmortem.json", record["key"])
        # Independent calculator vs scorer: largest absolute metric difference over all 72 records.
        worst = 0.0
        independent_records, identities = [], []
        feature_tensors = 0
        for i in range(4):
            receipt = e.read(output / f"match-{i}.json")
            spec = workload.specs[i]
            other = ind.match_body(
                bundle / spec.directory.name,
                spec.label,
                workload.manifest,
                workload.checkpoints,
                workload.receipts,
            )
            independent_records.append(other["records"])
            identities.append(other["identity"])
            source = src.SourceMatch(spec, "synthetic")
            source.prepare()
            for adapted, raw_window in zip(
                source.windows(), ind.raw_windows(spec.directory, spec.label), strict=True
            ):
                assert adapted["window_id"] == raw_window["window_id"]
                for regime in lds.INFORMATION_REGIMES:
                    production = lds.collate_feature_payloads(
                        [
                            lds.build_scene_feature_payload(
                                adapted["support"],
                                target_side=sc["scene_id"],
                                target_player_ids=sc["player_ids"],
                                home_player_ids=adapted["home_player_ids"],
                                away_player_ids=adapted["away_player_ids"],
                                regime=regime,
                            )
                            for sc in adapted["scenes"]
                        ],
                        regime,
                    )
                    separate = ind.model_inputs(raw_window, regime)
                    for field in dataclasses.fields(production):
                        a, b = getattr(production, field.name), getattr(separate, field.name)
                        assert (a is None and b is None) or torch.equal(a, b), field.name
                        feature_tensors += a is not None
            for a, b in zip(receipt["records"], other["records"], strict=True):
                for name in s.STRATA:
                    ma, mb = a["strata"][name]["metrics"], b["strata"][name]["metrics"]
                    if ma is not None:
                        worst = max(worst, *(abs(ma[k] - mb[k]) for k in ma))
        # Separate array calculation: mean over seeds, then equal weighting of four matches.
        import numpy as np

        cube = np.array(
            [
                [[r["strata"]["all"]["metrics"][m] for m in s.METRICS] for r in rows]
                for rows in independent_records
            ]
        ).reshape(4, 3, 2, 3, 3)
        seed_means = cube.mean(axis=3)
        contrasts = {}
        for rep, name in enumerate(lds.TARGET_REPRESENTATIONS):
            for label, left, right in (("C1", 0, 1), ("C2", 1, 2)):
                values = seed_means[:, left, rep, 0] - seed_means[:, right, rep, 0]
                contrasts[f"{label}/{name}"] = {
                    "matches": values.tolist(),
                    "equal_match_mean": float(values.mean()),
                }
        for key, value in contrasts.items():
            actual = manifest["aggregate"]["contrasts"][key]
            assert np.allclose(value["matches"], actual["matches"], rtol=0, atol=1e-12)
            assert abs(value["equal_match_mean"] - actual["equal_match_mean"]) < 1e-12
        assert worst < 1e-12
        return {
            "records": manifest["aggregate"]["records"],
            "source_identities": identities,
            "feature_tensors_compared_exactly": feature_tensors,
            "independent_72_cell_records": independent_records,
            "independent_equal_match_means": seed_means.mean(axis=0).tolist(),
            "independent_contrasts": contrasts,
            "code_runtime_provenance": e.read(output / "match-0.json")["provenance"],
            "scope_sha256": record["scope_sha256"],
            "receipt_sha256": record["seals"],
            "aggregate_sha256": s.digest(manifest["aggregate"]),
            "declared_windows": workload.declared,
            "cumulative_cpu_s": round(record["cpu_used"], 3),
            "cumulative_wall_s": round(record["wall_used"], 3),
            "peak_monitored_rss_bytes": attestation["peak_rss_bytes"],
            "output_bytes": sum(p.stat().st_size for p in output.iterdir() if p.is_file()),
            "budget": record["budget"],
            "independent_vs_scorer_max_abs_diff_m": worst,
            "bundle_tree_sha256": wl._tree_identity(bundle),
        }


def report(out: Path, junit: Path) -> None:
    small = json.loads(run([sys.executable, __file__, "measure", "--samples", "46"]))
    large = json.loads(run([sys.executable, __file__, "measure", "--samples", "146"]))
    head = run(["git", "rev-parse", "HEAD"]).strip()
    test_xml = ET.fromstring(junit.read_bytes())
    suites = list(test_xml.iter("testsuite"))
    assert suites and all(
        int(s.get("failures", "0")) == 0 and int(s.get("errors", "0")) == 0 for s in suites
    )
    cases = [
        {
            "name": c.get("classname", "") + "." + c.get("name", ""),
            "seconds": float(c.get("time", "0")),
            "status": "skipped" if c.find("skipped") is not None else "passed",
        }
        for c in test_xml.iter("testcase")
    ]
    document = {
        "schema": "fpdbench.res645.synthetic-qualification-report/1",
        "synthetic_only": True,
        "test_evidence": {
            "junit_sha256": hashlib.sha256(junit.read_bytes()).hexdigest(),
            "cases": cases,
        },
        "real_data_readiness_claimed": False,
        "git_head_at_measurement": head,
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "python_executable_sha256": hashlib.sha256(
                Path(sys.executable).read_bytes()
            ).hexdigest(),
        },
        "qualification_tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "protocol_sha256": "ac931391ecb0afcb68974e1765f65fbff17071ade2bcaab93bdadd22f84a0305",
        "bounded_memory": {
            "small": small,
            "large": large,
            "window_growth": round(large["eligible_windows"] / small["eligible_windows"], 2),
            "traced_peak_growth": round(large["traced_peak_bytes"] / small["traced_peak_bytes"], 3),
            "rss_growth": round(large["ru_maxrss_bytes"] / small["ru_maxrss_bytes"], 3),
        },
        "supervised_campaign": campaign(),
    }
    assert document["bounded_memory"]["window_growth"] > 10
    assert document["bounded_memory"]["traced_peak_growth"] < 1.6
    document["limitations"] = [
        "Invented frames/artificial CPU weights only; no private preflight or held-out inference",
        "No host OOM/reboot qualification or victim evidence; every SIGKILL is permanent",
        "Memory results bound the measured synthetic sizes, not private source scale",
    ]
    out.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    print(hashlib.sha256(out.read_bytes()).hexdigest())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("measure", "report"))
    parser.add_argument("--samples", type=int, default=46)
    parser.add_argument(
        "--out", type=Path, default=Path("docs/res645-synthetic-qualification-report.json")
    )
    parser.add_argument("--pytest-junit", type=Path)
    args = parser.parse_args()
    if args.action == "measure":
        print(json.dumps(measure(args.samples)))
    else:
        if args.pytest_junit is None:
            parser.error("report requires --pytest-junit from a passing final-code test run")
        report(args.out, args.pytest_junit)


if __name__ == "__main__":
    main()
