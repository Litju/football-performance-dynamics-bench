"""Smoke-test a built wheel and verify wheel/sdist license metadata."""

from __future__ import annotations

import argparse
import os
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
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        cli = environment / ("Scripts/fpdbench.exe" if os.name == "nt" else "bin/fpdbench")
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
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.population_producer_v2 import (
    PopulationMatchInputV2,
    PopulationVerificationSubmissionV2,
    produce_population_draft_v2,
)
fixture_input = PopulationMatchInputV2("synthetic", b"{{}}", b"", b"[]")
assert isinstance(fixture_input.metadata_json, bytes)
for kind in ("synthetic", "restricted"):
    try:
        produce_population_draft_v2((), input_kind=kind)
    except ValueError:
        pass
    else:
        raise AssertionError("partial/unauthorized population accepted")
submission = PopulationVerificationSubmissionV2(b"{{}}", b"", b"", b"{{}}")
assert submission.status == "UNQUALIFIED"
try:
    submission.require_empirical_qualification()
except ValueError:
    pass
else:
    raise AssertionError("producer authorized empirical use")
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
    "ed1cdc20ca7a93040fd4aabc91655819c5c4b8c58021c6540c6aaea325dafa11"
)
# Public v2 candidate diagnostics execute installed production code, without qualification.
from fpdbench.eligibility import (
    CandidateWindowDiagnosticV2,
    BallPopulationQualificationStop,
    PhaseInterval,
    diagnose_skillcorner_window_v2,
    evaluate_skillcorner_window_v2,
)
metadata = {{
    "id": 2017461, "home_team": {{"id": 101}}, "away_team": {{"id": 202}},
    "pitch_length": 100.0, "pitch_width": 60.0,
    "match_periods": [{{"period": 1, "start_frame": 100, "end_frame": 200}}],
    "players": [
        {{"id": player, "team_id": 101 if player < 1009 else 202,
         "playing_time": {{"by_period": [
             {{"name": "period_1", "start_frame": 100, "end_frame": 200}}
         ]}}}}
        for player in range(1001, 1017)
    ],
}}
players = [
    {{"player_id": player, "team_id": 101 if player < 1009 else 202,
     "group": "home" if player < 1009 else "away",
     "x_m": float(player % 20), "y_m": 0.0, "is_detected": True}}
    for player in range(1001, 1017)
]
samples = [
    {{"data_state_id": measurement_v2["data_state_id"],
     "data_state_hash": measurement_v2["data_state_hash"],
     "source_release_id": eligibility_v2["source_release_id"],
     "source_release_hash": eligibility_v2["source_release_hash"],
     "match_id": 2017461, "period": 1, "source_frame": 100 + 2 * offset,
     "canonical_sample_index": 50 + offset, "timestamp_deciseconds": 100 + 2 * offset,
     "home_team_id": 101, "away_team_id": 202, "pitch_length_m": 100.0, "pitch_width_m": 60.0,
     "players": players, "ball": {{"x_m": 0.0, "y_m": 0.0, "is_detected": False}},
     "possession": None}}
    for offset in range(41)
]
kwargs = {{
    "history_intervals": 25, "future_intervals": 15, "match_metadata": metadata,
    "phase_intervals": [PhaseInterval(eligibility_v2["source_release_id"], 2017461, 1, 100, 200)],
}}
diagnostic = diagnose_skillcorner_window_v2(samples, **kwargs)
assert isinstance(diagnostic, CandidateWindowDiagnosticV2)
assert diagnostic.status == "UNQUALIFIED" and diagnostic.candidate_rules_pass
assert not hasattr(diagnostic, "eligible")
for history, future in ((24, 16), (26, 14)):
    try:
        diagnose_skillcorner_window_v2(
            samples, **{{**kwargs, "history_intervals": history, "future_intervals": future}}
        )
    except ValueError:
        pass
    else:
        raise AssertionError("installed diagnostic accepted changed horizons")
try:
    evaluate_skillcorner_window_v2(samples, population_qualification=diagnostic, **kwargs)
except ValueError as error:
    assert "population drift gate" in str(error)
else:
    raise AssertionError("installed diagnostic authorized empirical membership")
gapped = [*samples[:3], None, *samples[4:]]
gap_diagnostic = diagnose_skillcorner_window_v2(gapped, **kwargs)
context = gap_diagnostic.quality["play_context"]
assert context["possession_denominator_samples"] == 41
assert context["possession_unknown_samples"] == 40
assert context["possession_missing_samples"] == 1
assert context["possession_invalid_samples"] == 0
assert context["possession_unknown_fraction"] == 40 / 41
assert context["possession_counts_reconcile_to_expected_support"] is True
assert "TEMPORAL_GAP" in {{issue.code for issue in gap_diagnostic.exclusion_reasons}}
samples[25]["ball"] = None
excluded = diagnose_skillcorner_window_v2(samples, **kwargs)
assert excluded.status == "UNQUALIFIED" and not excluded.candidate_rules_pass
assert "BALL_MISSING_AT_ORIGIN" in {{issue.code for issue in excluded.exclusion_reasons}}
samples[25]["ball"] = {{"x_m": 0.0, "y_m": 0.0, "is_detected": None}}
try:
    diagnose_skillcorner_window_v2(samples, **kwargs)
except BallPopulationQualificationStop:
    pass
else:
    raise AssertionError("installed diagnostic suppressed the global drift stop")

assert load_prospective_protocol()["protocol_sha256"] == PROTOCOL_SHA256
assert load_prospective_protocol_v2()["protocol_sha256"] == PROTOCOL_V2_SHA256
validate_empirical_experiment_plan_document(load_empirical_experiment_plan())
assert load_empirical_experiment_plan()["plan_version"] == "1.1.0"
plan_v2 = load_empirical_experiment_plan_v2()
validate_empirical_experiment_plan_v2_document(plan_v2)
assert plan_v2["plan_sha256"] == (
    "a59fee6ee8e9fb03f4f0ccdae1933458af2bbf2375db7e6cd2bdf10962e42b62"
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
        sdist_python = sdist_environment / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )
        sdist_cli = sdist_environment / (
            "Scripts/fpdbench.exe" if os.name == "nt" else "bin/fpdbench"
        )
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
