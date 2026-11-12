"""Execute RES643 synthetic parity from extracted wheel and sdist outside the checkout.

Uses the already installed pinned research dependencies; installs no packages or credentials.
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
    res635_post_failure_evaluation as s,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import res635_verification as v
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import res635_execution as e
assert pathlib.Path(s.__file__).is_relative_to(pathlib.Path(sys.argv[1]))
assert pathlib.Path(e.__file__).is_relative_to(pathlib.Path(sys.argv[1]))
models = s.models()
result = s.score_match(s.MATCHES[0], 1, models)
v.assert_equivalent(result, v.independent_match(s.MATCHES[0], 1, models))
print(s.digest(result))
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("sdist", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="res643-package-") as temporary:
        root = Path(temporary)
        wheel_root, sdist_root, work = root / "wheel", root / "sdist", root / "work"
        work.mkdir()
        with zipfile.ZipFile(args.wheel) as archive:
            archive.extractall(wheel_root)
            entrypoints = next(n for n in archive.namelist() if n.endswith("entry_points.txt"))
            assert "fpdbench-res635" in archive.read(entrypoints).decode()
        with tarfile.open(args.sdist) as archive:
            archive.extractall(sdist_root, filter="data")
        sources = [wheel_root, next(sdist_root.iterdir()) / "src"]
        identities = [
            subprocess.check_output(
                [sys.executable, "-I", "-c", SMOKE, str(source)], cwd=work, text=True, timeout=60
            ).strip()
            for source in sources
        ]
        assert identities[0] == identities[1], "wheel/sdist scientific identities differ"
        print(f"RES643 isolated wheel/sdist parity passed: {identities[0]}")


if __name__ == "__main__":
    main()
