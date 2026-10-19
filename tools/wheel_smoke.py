"""Smoke-test a built wheel and verify wheel/sdist license metadata."""

from __future__ import annotations

import argparse
import subprocess
import tarfile
import tempfile
import venv
from pathlib import Path

CALIBRATION_SHA256 = "f3b4155899c5d8e9632e9cab7a25e471411c62c4a9a7489c58c1edb16180ce94"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    parser.add_argument("sdist", type=Path)
    args = parser.parse_args()
    wheel = args.wheel.resolve(strict=True)
    sdist = args.sdist.resolve(strict=True)
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
import json
import pathlib
import sys

import fpdbench
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.prospective_protocol import (
    PROTOCOL_SHA256,
    load_prospective_protocol,
    PROTOCOL_V2_SHA256,
    load_prospective_protocol_v2,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    load_empirical_experiment_plan,
    load_empirical_experiment_plan_v2,
    validate_empirical_experiment_plan_document,
    validate_empirical_experiment_plan_v2_document,
)
from fpdbench.evaluation import (
    ABSOLUTE_POSITION_HISTORICAL_SCORER,
    RAW_DISPLACEMENT_EVALUATOR_CONFIGURATION,
)
from fpdbench.evaluation.metrics.trajectory import PHYSICAL_TRAJECTORY_EVALUATOR
from fpdbench.data_states.skillcorner import load_manifest, validate_manifest
from fpdbench.data_states.skillcorner import load_manifest_v2, validate_manifest_v2
from fpdbench.eligibility.skillcorner import (
    load_manifest_v2 as load_eligibility_manifest_v2,
    validate_manifest_v2 as validate_eligibility_manifest_v2,
)

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
measurement_v2 = load_manifest_v2()
assert validate_manifest_v2(measurement_v2) == ()
assert measurement_v2["data_state_hash"] == (
    "1ecf355b3e6e2f04967e8363c1fdecc7f40707a7dda9966ebee1b3d90e97e671"
)
eligibility_v2 = load_eligibility_manifest_v2()
assert validate_eligibility_manifest_v2(eligibility_v2) == ()
assert eligibility_v2["policy_hash"] == (
    "b200e0dffa8a04d465496ee45aae90c25d20c08a9c9a5cb62433441094956581"
)
assert load_prospective_protocol()["protocol_sha256"] == PROTOCOL_SHA256
assert load_prospective_protocol_v2()["protocol_sha256"] == PROTOCOL_V2_SHA256
validate_empirical_experiment_plan_document(load_empirical_experiment_plan())
assert load_empirical_experiment_plan()["plan_version"] == "1.1.0"
plan_v2 = load_empirical_experiment_plan_v2()
validate_empirical_experiment_plan_v2_document(plan_v2)
assert plan_v2["plan_sha256"] == (
    "12db6cf4da3018cd467cf468ebcbe07369208f8a4dc83a063579b7b781453203"
)
versioned_files = (
    "data_states/skillcorner_5hz_v2.json",
    "eligibility/skillcorner_window_v2.json",
    "benchmarks/conditional_multi_agent_motion_prediction/"
    "prospective_skillcorner_protocol_v2.json",
    "benchmarks/conditional_multi_agent_motion_prediction/empirical_experiment_plan_v2.json",
    "benchmarks/conditional_multi_agent_motion_prediction/"
    "evaluation_population_authority_v2.schema.json",
    "benchmarks/conditional_multi_agent_motion_prediction/"
    "prospective_experiment_result_v2.schema.json",
)
packaged_files = {{
    relative: importlib.resources.files("fpdbench").joinpath(relative).read_bytes()
    for relative in versioned_files
}}
assert hashlib.sha256(
    packaged_files["benchmarks/conditional_multi_agent_motion_prediction/"
                   "evaluation_population_authority_v2.schema.json"]
).hexdigest() == plan_v2["population_authority"]["schema_sha256"]
assert hashlib.sha256(
    packaged_files["benchmarks/conditional_multi_agent_motion_prediction/"
                   "prospective_experiment_result_v2.schema.json"]
).hexdigest() == plan_v2["result_manifest_schema"]["schema_sha256"]
croissant = json.loads(
    importlib.resources.files("fpdbench")
    .joinpath("data_sources/skillcorner_croissant_rai_draft.json")
    .read_text()
)
status = json.loads(
    importlib.resources.files("fpdbench")
    .joinpath("data_sources/skillcorner_croissant_rai_status.json")
    .read_text()
)
assert "conformsTo" not in croissant
assert "version" not in croissant
assert croissant["sdVersion"] == "0.1.0-draft"
assert status["achieved_conformance"] is False
assert len(status["target_specifications"]) == 2
assert "distribution" not in croissant
assert not importlib.metadata.distribution("football-performance-dynamics-bench").requires
distribution = importlib.metadata.distribution("football-performance-dynamics-bench")
assert distribution.metadata["License-Expression"] == "Apache-2.0"
assert distribution.metadata.get_all("License-File") == ["LICENSE"]
license_path = next(
    path
    for path in distribution.files or ()
    if path.as_posix().endswith(".dist-info/licenses/LICENSE")
)
license_text = distribution.locate_file(license_path).read_text()
assert "Grant of Patent License" in license_text
assert "limitations under the License." in license_text
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
        subprocess.run(
            [str(cli), "data-states", "verify", "skillcorner_5hz_v2"],
            cwd=empty_working_directory,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            [str(cli), "eligibility", "verify", "skillcorner_window_v2"],
            cwd=empty_working_directory,
            check=True,
            stdout=subprocess.DEVNULL,
        )

        sdist_wheels = root / "sdist-wheels"
        sdist_wheels.mkdir()
        subprocess.run(
            ["uv", "build", "--wheel", "--out-dir", str(sdist_wheels), str(sdist)],
            cwd=empty_working_directory,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        sdist_wheel = next(sdist_wheels.glob("*.whl"))
        sdist_environment = root / "sdist-venv"
        sdist_working_directory = root / "sdist-work"
        sdist_working_directory.mkdir()
        venv.EnvBuilder(with_pip=True).create(sdist_environment)
        sdist_python = sdist_environment / "bin" / "python"
        sdist_cli = sdist_environment / "bin" / "fpdbench"
        subprocess.run(
            [
                str(sdist_python),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                str(sdist_wheel),
            ],
            cwd=sdist_working_directory,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            [str(sdist_python), "-I", "-c", smoke],
            cwd=sdist_working_directory,
            check=True,
        )
        subprocess.run(
            [str(sdist_cli), "data-states", "verify", "skillcorner_5hz_v2"],
            cwd=sdist_working_directory,
            check=True,
            stdout=subprocess.DEVNULL,
        )
    with tarfile.open(sdist, "r:gz") as archive:
        license_member = next(name for name in archive.getnames() if name.endswith("/LICENSE"))
        metadata_member = next(name for name in archive.getnames() if name.endswith("/PKG-INFO"))
        license_file = archive.extractfile(license_member)
        package_metadata = archive.extractfile(metadata_member)
        assert license_file is not None
        assert package_metadata is not None
        assert b"Grant of Patent License" in license_file.read()
        metadata_text = package_metadata.read().decode()
        assert "License-Expression: Apache-2.0" in metadata_text
        assert "License-File: LICENSE" in metadata_text
        versioned_sdist_files = (
            "src/fpdbench/data_states/skillcorner_5hz_v2.json",
            "src/fpdbench/eligibility/skillcorner_window_v2.json",
            "src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/prospective_skillcorner_protocol_v2.json",
            "src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/empirical_experiment_plan_v2.json",
            "src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/evaluation_population_authority_v2.schema.json",
            "src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/prospective_experiment_result_v2.schema.json",
        )
        archive_names = archive.getnames()
        for relative in versioned_sdist_files:
            assert any(name.endswith("/" + relative) for name in archive_names)
    print("isolated wheel smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
