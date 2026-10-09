"""Install and smoke-test one built wheel outside the source tree."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
import venv
from pathlib import Path

CALIBRATION_SHA256 = "f3b4155899c5d8e9632e9cab7a25e471411c62c4a9a7489c58c1edb16180ce94"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    wheel = parser.parse_args().wheel.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="fpdbench-wheel-") as temporary:
        root = Path(temporary)
        environment = root / "venv"
        empty_working_directory = root / "work"
        empty_working_directory.mkdir()
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / "bin" / "python"
        cli = environment / "bin" / "fpdbench"
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                str(wheel),
            ],
            cwd=empty_working_directory,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        smoke = f"""
import hashlib
import importlib.metadata
import importlib.resources
import pathlib
import sys

import fpdbench
from fpdbench.evaluation import (
    ABSOLUTE_POSITION_HISTORICAL_SCORER,
    RAW_DISPLACEMENT_EVALUATOR_CONFIGURATION,
)
from fpdbench.evaluation.metrics.trajectory import PHYSICAL_TRAJECTORY_EVALUATOR
from fpdbench.data_states.skillcorner import load_manifest, validate_manifest

assert pathlib.Path(fpdbench.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix))
calibration = importlib.resources.files("fpdbench").joinpath(
    "evaluation/absolute_xy_calibration_lock.json"
).read_bytes()
assert hashlib.sha256(calibration).hexdigest() == "{CALIBRATION_SHA256}"
assert (
    ABSOLUTE_POSITION_HISTORICAL_SCORER.evaluator_id
    == "absolute_position.historical_continuous_pwl_v3"
)
assert (
    RAW_DISPLACEMENT_EVALUATOR_CONFIGURATION.evaluator_id
    == "origin_relative_displacement_raw_population_sre"
)
assert PHYSICAL_TRAJECTORY_EVALUATOR.evaluator_id == "physical_trajectory.ade_fde_xy_rmse"
assert load_manifest()["data_state_id"] == "skillcorner_5hz_v1"
assert validate_manifest(load_manifest()) == ()
assert not importlib.metadata.distribution("football-performance-dynamics-bench").requires
"""
        subprocess.run([str(python), "-I", "-c", smoke], cwd=empty_working_directory, check=True)
        subprocess.run(
            [str(cli), "--help"],
            cwd=empty_working_directory,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        discovered = subprocess.run(
            [str(cli), "benchmarks", "list"],
            cwd=empty_working_directory,
            check=True,
            capture_output=True,
            text=True,
        )
        if len(discovered.stdout.splitlines()) != 2:
            raise RuntimeError("installed CLI did not discover both public benchmarks")
        subprocess.run(
            [str(cli), "data-states", "verify"],
            cwd=empty_working_directory,
            check=True,
            stdout=subprocess.DEVNULL,
        )
    print("isolated wheel smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
