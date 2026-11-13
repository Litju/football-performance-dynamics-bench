"""Measure signed artificial campaigns, including setup, decoding, audit and final sealing.

Run from the repository with the research/dev environment. The test fixture signer creates
ephemeral SYNTHETIC keys only. No owner key, real source, real checkpoint or production scope
is used. Input fixture generation is outside the campaign; the launcher exits after launch.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "unit"))

from test_res646_campaign import signed_campaign  # noqa: E402

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (  # noqa: E402
    res635_execution as execution,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (  # noqa: E402
    res645_fixtures as fixtures,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (  # noqa: E402
    res645_pipeline as pipeline,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (  # noqa: E402
    res645_workloads as workloads,
)


def measure(samples: int) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="res646-artificial-") as temporary:
        base = Path(temporary)
        bundle = fixtures.build_bundle(base / "bundle", samples=samples)
        config = signed_campaign(base / "campaign", bundle)
        workload = workloads.RealWorkload(config)
        campaign = workload.campaign
        started = subprocess.run(
            [
                sys.executable,
                "-m",
                execution.MODULE,
                "start",
                "--campaign-config",
                str(config),
                "--output",
                str(campaign.output),
                "--ledger-root",
                str(campaign.root),
                "--count",
                str(workload.windows),
                "--predeclare-continuation",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if started.returncode:
            raise RuntimeError(started.stderr)
        deadline = time.monotonic() + execution.REAL_BUDGET["wall_s"] + 60
        while not (campaign.output / "status.json").exists():
            if time.monotonic() >= deadline:
                raise RuntimeError("synthetic supervisor did not finish within frozen wall ceiling")
            time.sleep(0.1)
        status = execution.read(campaign.output / "status.json")
        if status["exit_code"]:
            raise RuntimeError((campaign.output / "supervisor.log").read_text())
        manifest = execution.verify_complete(
            campaign.root,
            campaign.output,
            workload.windows,
            workload=workload,
        )
        ledger = campaign.record()
        assert manifest["aggregate"]["records"] == 72
        return {
            "samples_per_match": samples,
            "windows": workload.windows,
            "records": 72,
            "cpu_s": ledger["cpu_used"],
            "wall_s": ledger["wall_used"],
            "combined_peak_rss_bytes": ledger["peak_rss_bytes"],
            "transient_disk_bytes": ledger["disk_bytes"],
            "read_only_fixture_bytes": sum(
                p.stat().st_size for p in bundle.rglob("*") if p.is_file()
            ),
            "scope_sha256": campaign.scope,
            "charged_phases": [
                "launcher",
                "supervisor setup",
                "model setup",
                "source identity",
                "source decoding",
                "inference",
                "independent feature/truth/metric audit",
                "receipt verification",
                "aggregation",
                "final sealing",
            ],
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", nargs="+", type=int, default=[60, 240, 1040])
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if any(n < 42 for n in args.samples):
        parser.error("at least 42 invented source samples per match required")
    report = {
        "schema": "fpdbench.res646.synthetic-resource-qualification/1",
        "synthetic_only": True,
        "full_scale_real_readiness": False,
        "policy": "measurements only; no extrapolation beyond the tested source populations",
        "code_sha256": pipeline.provenance([], "")["code_sha256"],
        "runtime": pipeline.provenance([], "")["runtime"],
        "limits": execution.REAL_BUDGET,
        "measurements": [],
    }
    for samples in args.samples:
        row = measure(samples)
        report["measurements"].append(row)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
