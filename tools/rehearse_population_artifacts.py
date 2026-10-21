"""Rebuild pinned code artifacts and reconcile synthetic inputs in isolated interpreters."""

from __future__ import annotations

import hashlib
import json
import runpy
import subprocess
import tarfile
import tempfile
from pathlib import Path

PRODUCER = "6644dba8c945ca86be72b54792db30cbe488e5d0"
VERIFIER = "ef1a22583cdd52bb63509a13bfc480a313ea69d4"
PACKAGE_INVENTORIES = {
    "producer": "153bc67c532b8eddba90a98994d60f656526e71961f17c9d1f2454a72dd2e1a4",
    "verifier": "c61851dd0b930694a960d8cf79046258ea92a8c2cc19db60d33fdbb12f4b6b09",
}
REPO = Path(__file__).resolve().parents[1]
WORKER = """
import dataclasses, hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
kind = sys.argv[2]
module = "population_producer_v2" if kind == "producer" else "independent_population_verifier_v2"
import importlib
m = importlib.import_module("fpdbench.benchmarks.conditional_multi_agent_motion_prediction."+module)
package_root = pathlib.Path(m.__file__).resolve().parents[2]
files = [{"path":p.relative_to(package_root).as_posix(),
          "sha256":hashlib.sha256(p.read_bytes()).hexdigest()}
         for p in sorted(package_root.rglob("*"))
         if p.is_file() and p.suffix in (".py", ".json")]
fingerprint = {"schema_id":"fpdbench.production-package-fingerprint",
               "schema_version":"1.0.0", "package":"fpdbench",
               "hash_algorithm":"sha256", "files":files}
fingerprint["sha256"] = hashlib.sha256(json.dumps(
    fingerprint, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
expected_inventory = {
    "producer":"153bc67c532b8eddba90a98994d60f656526e71961f17c9d1f2454a72dd2e1a4",
    "verifier":"c61851dd0b930694a960d8cf79046258ea92a8c2cc19db60d33fdbb12f4b6b09",
}[kind]
assert fingerprint["sha256"] == expected_inventory, "isolated package inventory drift"
fields = ("metadata_json", "tracking_jsonl", "phase_intervals_json")
inputs = [dict(match_id=r["match_id"], **{f:r[f].encode() for f in fields})
          for r in json.loads((root/"inputs.json").read_bytes())]
if kind == "producer":
    output = m.produce_population_draft_v2([m.PopulationMatchInputV2(**r) for r in inputs],
                                         input_kind="synthetic")
    for f in ("manifest_json", "candidates_jsonl", "diagnostic_census_jsonl",
              "truth_jsonl", "receipt_json"):
        (root/f).write_bytes(getattr(output, f))
else:
    inputs = [m.MatchSourceBytesV2(**r) for r in inputs]
    submission = m.PopulationSubmissionV2(**{f.name:(root/f.name).read_bytes()
                  for f in dataclasses.fields(m.PopulationSubmissionV2)})
    report = m.compare_population_v2(inputs, submission, producer_revision=sys.argv[3])
    assert report.status == "RECONCILED", report.status
    assert not report.authoritative and report.qualification_status == "NOT_QUALIFIED"
    rejected = m.compare_population_v2(inputs, submission, producer_revision="0"*40)
    assert rejected.status != "RECONCILED"
    for mutation in ("altered", "mixed"):
        receipt = json.loads(submission.receipt_json)
        fp = receipt["producer_executable_fingerprint"]
        if mutation == "altered": fp["files"][0]["sha256"] = "0"*64
        else: fp["files"].append({"path":"mixed.py", "sha256":"0"*64})
        fp.pop("sha256")
        fp["sha256"] = hashlib.sha256(m.canonical_bytes(fp)).hexdigest()
        receipt.pop("receipt_sha256")
        receipt["receipt_sha256"] = hashlib.sha256(m.canonical_bytes(receipt)).hexdigest()
        forged = dataclasses.replace(submission, receipt_json=m.canonical_bytes(receipt))
        rejected = m.compare_population_v2(inputs, forged, producer_revision=sys.argv[3])
        assert rejected.status != "RECONCILED"
    print(json.dumps({"status":report.status, "candidates":report.candidate_count,
                      "negative_controls":3, "qualification_status":report.qualification_status}))
"""


def main() -> None:
    fixture = runpy.run_path(str(REPO / "tests/unit/test_independent_population_verifier_v2.py"))
    with tempfile.TemporaryDirectory(prefix="res501-synthetic-") as temporary:
        root = Path(temporary)
        inputs = [
            {
                "match_id": row.match_id,
                **{
                    field: getattr(row, field).decode()
                    for field in ("metadata_json", "tracking_jsonl", "phase_intervals_json")
                },
            }
            for row in fixture["_fixture"]()
        ]
        (root / "inputs.json").write_text(json.dumps(inputs))
        for kind, revision in (("producer", PRODUCER), ("verifier", VERIFIER)):
            archive = root / f"{kind}.tar"
            subprocess.run(["git", "archive", revision, "-o", str(archive)], cwd=REPO, check=True)
            checkout = root / kind
            checkout.mkdir()
            with tarfile.open(archive) as source:
                source.extractall(checkout, filter="data")
            paths = sorted(
                (
                    path
                    for path in (checkout / "src/fpdbench").rglob("*")
                    if path.is_file() and path.suffix in {".py", ".json"}
                ),
                key=lambda path: path.relative_to(checkout / "src/fpdbench").as_posix(),
            )
            inventory = [
                {
                    "path": path.relative_to(checkout / "src/fpdbench").as_posix(),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
                for path in paths
            ]
            package = {
                "schema_id": "fpdbench.production-package-fingerprint",
                "schema_version": "1.0.0",
                "package": "fpdbench",
                "hash_algorithm": "sha256",
                "files": inventory,
            }
            inventory_digest = hashlib.sha256(
                json.dumps(
                    package, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ).encode()
            ).hexdigest()
            assert inventory_digest == PACKAGE_INVENTORIES[kind], (
                f"{kind} source package inventory drift"
            )
            subprocess.run(["uv", "build", "--wheel", str(checkout)], check=True)
            wheel = next((checkout / "dist").glob("*.whl"))
            environment = root / f"{kind}-venv"
            subprocess.run(["uv", "venv", str(environment)], check=True)
            python = environment / "bin/python"
            subprocess.run(
                ["uv", "pip", "install", "--python", str(python), "--no-deps", str(wheel)],
                check=True,
            )
            subprocess.run(
                [str(python), "-I", "-c", WORKER, str(root), kind, PRODUCER], cwd=root, check=True
            )
            print(
                f"{kind} revision={revision} "
                f"wheel_sha256={hashlib.sha256(wheel.read_bytes()).hexdigest()}"
            )


if __name__ == "__main__":
    main()
