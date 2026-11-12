"""Execute the RES645 source/checkpoint synthetic pipeline from extracted wheel and sdist.

Builds an invented fixture bundle outside the checkout, scores one match through the complete
production path, verifies it with the independent raw-file calculator, and requires the wheel and
sdist to yield the same scientific identity. Installs nothing and reads no real input.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

SMOKE = """
import pathlib, sys
sys.path.insert(0, sys.argv[1])
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    res635_post_failure_evaluation as s, res645_fixtures as fx, res645_workloads as wl,
    res645_pipeline as p)
assert pathlib.Path(wl.__file__).is_relative_to(pathlib.Path(sys.argv[1]))
bundle = fx.build_bundle(pathlib.Path(sys.argv[2]) / "bundle")
workload = wl.FixtureWorkload(bundle)
frozen = workload.prepare()
receipt = workload.score(1, workload.windows, frozen, lambda: None)
workload.check_receipt(1, workload.windows, receipt)
print(s.digest({"identity": receipt["identity"], "records": receipt["records"]}))
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("sdist", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="res645-package-") as temporary:
        root = Path(temporary)
        wheel_root, sdist_root = root / "wheel", root / "sdist"
        with zipfile.ZipFile(args.wheel) as archive:
            archive.extractall(wheel_root)
        with tarfile.open(args.sdist) as archive:
            archive.extractall(sdist_root, filter="data")
        sources = [wheel_root, next(sdist_root.iterdir()) / "src"]
        identities = []
        for number, source in enumerate(sources):
            work = root / f"work-{number}"
            work.mkdir()
            identities.append(
                subprocess.check_output(
                    [sys.executable, "-I", "-c", SMOKE, str(source), str(work)],
                    cwd=work,
                    text=True,
                    timeout=180,
                ).strip()
            )
        assert identities[0] == identities[1], "wheel/sdist scientific identities differ"
        print(f"RES645 isolated wheel/sdist parity passed: {identities[0]}")


if __name__ == "__main__":
    main()
