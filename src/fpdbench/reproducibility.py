"""Deterministic public checks for the executable and hash-verifiable stack."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import replace
from pathlib import Path
from typing import cast

from fpdbench.benchmarks.registry import default_registry
from fpdbench.evaluation import (
    ABSOLUTE_POSITION_CALIBRATION,
    ABSOLUTE_POSITION_CALIBRATION_LOCK_SHA256,
    ABSOLUTE_POSITION_HISTORICAL_SCORER,
    ABSOLUTE_POSITION_PROGRESS_TRANSFORM,
    ABSOLUTE_POSITION_RAW_EVALUATOR,
    ABSOLUTE_POSITION_TARGET_COUNT,
    ABSOLUTE_POSITION_TARGET_IDS,
    DISPLACEMENT_GENERATED_CALIBRATION,
    RAW_DISPLACEMENT_EVALUATOR_CONFIGURATION,
    SENSOR_STATE_EVALUATOR,
    SENSOR_STATE_PUBLIC_NONEXPERT_GATE,
    SIGNED_TANGENTIAL_ACCELERATION_EVALUATOR,
    AbsolutePositionRawEvaluation,
    absolute_position_progress,
    evaluate_absolute_position_population_sre,
    evaluate_sensor_state_channels,
    evaluate_sensor_state_gate,
    evaluate_signed_tangential_acceleration,
    quality_from_sre,
    raw_evaluator_hash,
    score_absolute_position,
)
from fpdbench.evaluation.metrics import PITCH_SCALE_M, physical_trajectory_metrics
from fpdbench.evaluation.metrics.trajectory import PHYSICAL_TRAJECTORY_EVALUATOR
from fpdbench.experiments import ScientificStateBinding, validate_result_scope
from fpdbench.experiments.provenance import evidence_sha256
from fpdbench.provenance.evidence_inventory import validate_evidence_inventory
from fpdbench.provenance.scientific_lock import verify_scientific_lock
from fpdbench.unknown import UNKNOWN
from fpdbench.validation import validate_repository

from .benchmarks.conditional_multi_agent_motion_prediction import (
    absolute_position_prediction as absolute_position,
)
from .benchmarks.conditional_multi_agent_motion_prediction import (
    displacement_reconstruction as displacement,
)
from .benchmarks.conditional_multi_agent_motion_prediction import (
    forecast_origin,
    information,
)
from .benchmarks.conditional_multi_agent_motion_prediction import (
    origin_relative_displacement_prediction as displacement_prediction,
)

SNAPSHOT_SCHEMA_ID = "fpdbench.reproducibility-snapshot"
SNAPSHOT_SCHEMA_VERSION = "1.0.0"
SNAPSHOT_RELATIVE_PATH = Path("benchmarks/reproducibility_snapshot.json")

PUBLIC_EXECUTABLE = "PUBLIC_EXECUTABLE"
PUBLIC_VERIFIABLE = "PUBLIC_VERIFIABLE"
LOCAL_EVIDENCE_VERIFIABLE = "LOCAL_EVIDENCE_VERIFIABLE"
UNAVAILABLE_PUBLIC_ARTIFACT = "UNAVAILABLE_PUBLIC_ARTIFACT"
FORBIDDEN_PRIVATE_TRUTH = "FORBIDDEN_PRIVATE_TRUTH"

CAPABILITY_MATRIX = (
    ("absolute_position.target_transform", PUBLIC_EXECUTABLE),
    ("absolute_position.raw_per_target_sre", PUBLIC_EXECUTABLE),
    ("absolute_position.progress_transform", PUBLIC_EXECUTABLE),
    ("absolute_position.historical_calibrated_score", PUBLIC_EXECUTABLE),
    ("displacement.target_transform", PUBLIC_EXECUTABLE),
    ("displacement.inversion_to_physical_xy", PUBLIC_EXECUTABLE),
    ("displacement.raw_330_target_sre", PUBLIC_EXECUTABLE),
    ("physical_trajectory.ade_fde_xy_rmse", PUBLIC_EXECUTABLE),
    ("information_boundary_validation", PUBLIC_EXECUTABLE),
    ("canonical_protocol_generation_and_hashing", PUBLIC_EXECUTABLE),
    ("scientific_lock_generation_and_verification", PUBLIC_EXECUTABLE),
    ("historical_result_manifest_hashing_and_scope", PUBLIC_EXECUTABLE),
    ("historical_fixture_manifests_and_population_counts", PUBLIC_VERIFIABLE),
    ("historical_result_records_and_output_hashes", PUBLIC_VERIFIABLE),
    ("historical_checkpoint_metadata", PUBLIC_VERIFIABLE),
    ("canonical_registry_evidence_resolution", LOCAL_EVIDENCE_VERIFIABLE),
    ("historical_source_to_full_fixture_regeneration", UNAVAILABLE_PUBLIC_ARTIFACT),
    ("historical_learned_checkpoint_loading", UNAVAILABLE_PUBLIC_ARTIFACT),
    ("historical_learned_model_deterministic_inference", UNAVAILABLE_PUBLIC_ARTIFACT),
    ("j03wmx_private_qualification_truth_evaluation", FORBIDDEN_PRIVATE_TRUTH),
)

ARTIFACT_AVAILABILITY = (
    ("historical_tracking_dataset_bytes", UNAVAILABLE_PUBLIC_ARTIFACT),
    ("historical_learned_checkpoint_bytes", UNAVAILABLE_PUBLIC_ARTIFACT),
    ("absolute_position_calibration_bytes", PUBLIC_EXECUTABLE),
    ("displacement_scientific_lock_files", PUBLIC_VERIFIABLE),
    ("j03wmx_qualification_truth", FORBIDDEN_PRIVATE_TRUTH),
)

_EXPECTED_PROTOCOLS = {
    "conditional_motion.match_role_assignment": (
        "1.0.0",
        "4fe08dd448096f0f54c3c773dcbd672e2f2e47c0b7faca591c72ba9167c0d444",
    ),
    "conditional_motion.public_train_lomo": (
        "1.0.0",
        "17d8e3bbc388971f4b52266c706830f449e5a4fbec77e1be214c52f703d289ee",
    ),
}
_EXPECTED_LOCKS = {
    "public_raw": (
        "d56ef8e1ff37276e258d516fa9ce26231403222e549296777ee27e5f38cfeedc",
        "1f0254c5d687aa6a383d8ce6b53fe825473a6f23cbd7f9bbf7c787a362fa1171",
    ),
    "lomo_raw": (
        "572e28bb5b4675a1fac91eb7c2c2c9cd4f00b28119aa447dd563c080a704cfd0",
        "d3fa4e56b1d4c7c93b424960e0440217f2c45252ceab85f0fc516eb26a3fd621",
    ),
    "public_physical": (
        "2fa5bbb3f5e56f0b2e2256f8b53483480168b098ab569dc6509548a0dba4a3d5",
        None,
    ),
}
_EXPECTED_EVALUATORS = {
    "signed_tangential_acceleration.global_full_row_rmse": (
        "ddaa8c7d78a32fee1bfb3c5fcf1542d0a852cb6bf73dfe7b8321d33cdbcea88f"
    ),
    "multimodal_sensor_state.equal_channel_population_sre": (
        "d07ded665d687efea4e53ea4957c9d7b9bbd7f571647c255541ee9b9d267abe4"
    ),
    "multimodal_sensor_state.public_nonexpert_quality_gate": (
        "4c056bbba1a4b140b507af4b5d37a8562932344445cf1bfcf1867002ab4f6c0a"
    ),
    "absolute_position.population_sre_targets": (
        "2bf4692ba8987caf656ac3243b7c89a0947c3a426f1da8d57475cad811c1fcc0"
    ),
    "absolute_position.per_target_progress": (
        "084e1b87c2139a95dd162d56d7a85e78d572a54538b70f9af5cd140dfb294554"
    ),
    "absolute_position.historical_continuous_pwl_v3": (
        "3e4782253e14e6416753898794ad863ad899a659f7cf24716d6013e7434ca2e8"
    ),
    "origin_relative_displacement_raw_population_sre": (
        "e7ae84ae81bf25cfc121fcb1e00bcb27804adcd4bfa349c1e6117ecf0176275b"
    ),
    "physical_trajectory.ade_fde_xy_rmse": (
        "7ce838398fc0939145362077dea7d62023129cd7936086cf042269a48d918b10"
    ),
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_hash(value: object) -> str:
    return _sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    )


def _trajectory_hex(trajectory: object) -> list[list[list[str]]]:
    return [
        [[float(x).hex(), float(y).hex()] for x, y in step]
        for step in cast(tuple[tuple[tuple[float, float], ...], ...], trajectory)
    ]


def _reference_regeneration() -> dict[str, object]:
    history = tuple(
        tuple(
            (10.0 + player * 3.0 + step * 0.1, 5.0 + player * 1.5 + step * 0.05)
            for player in range(11)
        )
        for step in range(25)
    )
    opponent_history = tuple(
        tuple(
            (30.0 + player * 1.5 - step * 0.04, 5.0 + player * 1.4 + step * 0.03)
            for player in range(11)
        )
        for step in range(25)
    )
    ball_history = tuple((25.0 + step * 0.08, 17.0 - step * 0.02) for step in range(25))
    origin_positions = history[-1]
    future_target = tuple(
        tuple(
            (x + (step + 1) * (0.08 + player * 0.002), y - (step + 1) * 0.035)
            for player, (x, y) in enumerate(origin_positions)
        )
        for step in range(15)
    )
    future_opponent = tuple(
        tuple((x + (step + 1) * 0.04, y) for x, y in frame)
        for step, frame in enumerate(opponent_history[-1:] * 15)
    )
    future_ball = tuple(
        (x + step * 0.05, y - step * 0.03) for step, (x, y) in enumerate(ball_history[-1:] * 15)
    )
    times = tuple(step / 5.0 for step in range(25))
    origin = forecast_origin.ForecastOrigin.from_observations(
        timestamp_s=times[-1],
        available_information_times_s=times,
        feature_names=(
            "history_target_team_xy",
            "history_opponent_team_xy",
            "history_ball_xy",
        ),
        target_origin_positions_m=origin_positions,
    )
    absolute_inputs = absolute_position.AbsolutePositionInputs(
        history,
        opponent_history,
        ball_history,
        future_opponent,
        future_ball,
    )
    displacement_inputs = displacement_prediction.DisplacementInputs(
        history,
        opponent_history,
        ball_history,
        future_opponent,
        future_ball,
        origin,
    )
    absolute_target = absolute_position.make_absolute_position_target(future_target)
    displacement_target = displacement_prediction.make_origin_relative_displacement_target(
        future_target, origin
    )
    absolute_restored = absolute_position.absolute_position_to_physical(absolute_target)
    displacement_restored = displacement_prediction.invert_origin_relative_displacement(
        displacement_target, origin
    )
    absolute_raw = evaluate_absolute_position_population_sre((absolute_target,), (absolute_target,))
    displacement_raw = displacement_prediction.evaluate_raw_displacement_sre(
        (displacement_target,), (displacement_target,)
    )
    physical = physical_trajectory_metrics((absolute_target,), (absolute_target,))
    if len(absolute_raw.per_target_sre) != 330 or absolute_raw.population_rows != 1:
        raise AssertionError("absolute-position raw evaluator did not score 330 targets")
    if len(displacement_raw.per_scalar_sre) != 330 or displacement_raw.population_rows != 1:
        raise AssertionError("displacement raw evaluator did not score 330 targets")
    if absolute_raw.per_target_sre != tuple((name, 0.0) for name in ABSOLUTE_POSITION_TARGET_IDS):
        raise AssertionError("absolute-position raw evaluator output changed")
    if displacement_raw.raw_sre != 0.0:
        raise AssertionError("displacement raw evaluator output changed")
    if (physical.ade_m, physical.fde_m, physical.xy_rmse_m) != (0.0, 0.0, 0.0):
        raise AssertionError("physical trajectory evaluator output changed")
    if any(
        not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-12)
        for restored in (absolute_restored, displacement_restored)
        for actual_step, expected_step in zip(restored, future_target, strict=True)
        for actual_player, expected_player in zip(actual_step, expected_step, strict=True)
        for actual, expected in zip(actual_player, expected_player, strict=True)
    ):
        raise AssertionError("synthetic target transform/inversion exceeded 1e-12 metres")
    if origin.target_origin_positions_m != history[-1]:
        raise AssertionError("forecast origin must equal the final observed target history frame")
    if (len(history), len(history[0]), len(opponent_history[0]), len(ball_history)) != (
        25,
        11,
        11,
        25,
    ):
        raise AssertionError("synthetic history geometry changed")
    if (len(future_target), len(future_target[0]), len(future_target[0][0])) != (15, 11, 2):
        raise AssertionError("synthetic future geometry changed")
    if PITCH_SCALE_M != (52.5, 34.0):
        raise AssertionError("pitch scale changed")
    if (
        "future_target_team_xy" in absolute_inputs.feature_names
        or "future_target_team_xy" in displacement_inputs.feature_names
    ):
        raise AssertionError("future target truth leaked into model inputs")
    if any(
        item not in absolute_inputs.feature_names or item not in displacement_inputs.feature_names
        for item in ("realized_future_opponent_xy", "realized_future_ball_xy")
    ):
        raise AssertionError("realized opponent and ball context must remain conditional inputs")
    if any("future" in name for name in origin.feature_names):
        raise AssertionError("future context or truth crossed the exact forecast-origin boundary")
    forbidden_features = (
        "future_target_team_xy",
        "future_target_s",
        "future_target_a",
        "future_aggregates",
        "event_labels",
        "score",
        "absolute_timestamp",
        "file_identity",
        "row_order",
        "target_encoding",
        "numeric_player_id",
        "numeric_team_id",
        "numeric_match_id",
    )
    for feature in forbidden_features:
        try:
            information.validate_information_boundary((feature,))
        except ValueError:
            continue
        raise AssertionError(f"information-boundary validator accepted forbidden {feature}")

    output = {
        "absolute_target": _trajectory_hex(absolute_target),
        "displacement_target": _trajectory_hex(displacement_target),
        "absolute_restored": _trajectory_hex(absolute_restored),
        "displacement_restored": _trajectory_hex(displacement_restored),
    }
    input_payload = {
        "history_target": _trajectory_hex(history),
        "history_opponent": _trajectory_hex(opponent_history),
        "history_ball": [[x.hex(), y.hex()] for x, y in ball_history],
        "future_target": _trajectory_hex(future_target),
        "future_opponent": _trajectory_hex(future_opponent),
        "future_ball": [[x.hex(), y.hex()] for x, y in future_ball],
        "forecast_origin_s": origin.timestamp_s.hex(),
        "observation_times_s": [value.hex() for value in origin.available_information_times_s],
        "forecast_origin_features": list(origin.feature_names),
    }
    return {
        "history_steps": 25,
        "history_hz": 5,
        "target_steps": 15,
        "target_players": 11,
        "opponent_players": 11,
        "ball_history_steps": 25,
        "future_opponent_steps": 15,
        "future_ball_steps": 15,
        "forecast_origin_is_final_observed_target_frame": True,
        "pitch_scale_m": list(PITCH_SCALE_M),
        "roundtrip_absolute_tolerance_m": 1e-12,
        "future_target_withheld": True,
        "future_opponent_and_ball_are_conditional_context": True,
        "information_boundary_rejects_future_target": True,
        "identity_event_score_timestamp_leakage_rejected": True,
        "input_sha256": _canonical_hash(input_payload),
        "absolute_raw_sre_targets": len(absolute_raw.per_target_sre),
        "displacement_raw_sre_targets": len(displacement_raw.per_scalar_sre),
        "physical_diagnostics_m": {
            "ade": physical.ade_m,
            "fde": physical.fde_m,
            "xy_rmse": physical.xy_rmse_m,
        },
        "output_sha256": _canonical_hash(output),
    }


def _evaluator_regeneration(reference: dict[str, object]) -> dict[str, object]:
    evaluators = (
        SIGNED_TANGENTIAL_ACCELERATION_EVALUATOR,
        SENSOR_STATE_EVALUATOR,
        SENSOR_STATE_PUBLIC_NONEXPERT_GATE,
        ABSOLUTE_POSITION_RAW_EVALUATOR,
        ABSOLUTE_POSITION_PROGRESS_TRANSFORM,
        ABSOLUTE_POSITION_HISTORICAL_SCORER,
        RAW_DISPLACEMENT_EVALUATOR_CONFIGURATION,
        PHYSICAL_TRAJECTORY_EVALUATOR,
    )
    hashes = {item.evaluator_id: item.scientific_config_sha256 for item in evaluators}
    if hashes != _EXPECTED_EVALUATORS:
        raise AssertionError("frozen evaluator/scorer scientific hashes changed")
    if ABSOLUTE_POSITION_CALIBRATION_LOCK_SHA256 != (
        "f3b4155899c5d8e9632e9cab7a25e471411c62c4a9a7489c58c1edb16180ce94"
    ):
        raise AssertionError("absolute-position calibration evidence hash changed")
    if ABSOLUTE_POSITION_CALIBRATION.source_sha256 != ABSOLUTE_POSITION_CALIBRATION_LOCK_SHA256:
        raise AssertionError("absolute-position calibration bytes failed verification")

    calibration = ABSOLUTE_POSITION_CALIBRATION
    reference_raw = AbsolutePositionRawEvaluation(
        tuple((target.target_id, target.reference_sre) for target in calibration.targets), 1
    )
    no_information_raw = AbsolutePositionRawEvaluation(
        tuple((target.target_id, target.no_information_ceiling) for target in calibration.targets),
        1,
    )
    perfect_raw = AbsolutePositionRawEvaluation(
        tuple((target_id, 0.0) for target_id in ABSOLUTE_POSITION_TARGET_IDS), 1
    )
    reference_score = score_absolute_position(absolute_position_progress(reference_raw)).score
    no_information_score = score_absolute_position(
        absolute_position_progress(no_information_raw)
    ).score
    perfect_score = score_absolute_position(absolute_position_progress(perfect_raw)).score
    if (
        not math.isclose(reference_score, 0.5, rel_tol=0.0, abs_tol=1e-14)
        or no_information_score != 0.0
        or perfect_score != 1.0
    ):
        raise AssertionError("absolute-position calibration score anchors changed")
    if ABSOLUTE_POSITION_TARGET_COUNT != 330 or len(calibration.targets) != 330:
        raise AssertionError("absolute-position evaluator target count/order changed")

    # Re-exercise the real raw evaluator against the deterministic public reference target.
    absolute_shape = reference
    if absolute_shape["target_steps"] != 15 or absolute_shape["target_players"] != 11:
        raise AssertionError("synthetic reference is not the canonical target geometry")
    signed = evaluate_signed_tangential_acceleration((0.0, 1.0, 2.0), (0.0, 0.0, 0.0))
    if not math.isclose(signed.rmse_m_s2, math.sqrt(5.0 / 3.0), rel_tol=0.0, abs_tol=1e-15):
        raise AssertionError("signed-acceleration full-row RMSE changed")
    from fpdbench.benchmarks.multimodal_state_estimation import (
        CANDIDATE_TARGET_FAMILIES,
        SELECTED_TARGET_FAMILY,
        SensorCandidateFamily,
    )
    from fpdbench.benchmarks.multimodal_state_estimation import (
        evaluate_sensor_state_channels as evaluate_sensor_pilot,
    )

    signed_acceleration_task = (
        default_registry()
        .lookup_research_object(
            "workload_performance_state/signed_tangential_acceleration_estimation"
        )
        .task
    )
    signed_acceleration_maturity = signed_acceleration_task.scientific_maturity.value
    if signed_acceleration_maturity != "invalidated" or not any(
        "B5" in blocker for blocker in signed_acceleration_task.reconstruction_blockers
    ):
        raise AssertionError("invalidated signed-acceleration and missing B5 state changed")

    sensor_truth = tuple(float(index) for index in range(256))
    sensor = evaluate_sensor_pilot(
        {"x": tuple(value + 1.0 for value in sensor_truth), "y": sensor_truth},
        {"x": sensor_truth, "y": sensor_truth},
        SensorCandidateFamily.CORRUPTION_REGION,
        region_mask=(True,) * 256,
    )
    if (
        len(sensor.per_channel_sre) != 2
        or SELECTED_TARGET_FAMILY is not None
        or sensor.benchmark_reward_emitted
    ):
        raise AssertionError("sensor-state pilot target selection changed")
    per_channel_sre = dict(sensor.per_channel_sre)
    per_channel_quality = dict(sensor.per_channel_quality)
    sensor_mean = sum(sensor_truth) / len(sensor_truth)
    sensor_population_std = math.sqrt(
        sum((value - sensor_mean) ** 2 for value in sensor_truth) / len(sensor_truth)
    )
    expected_sre = 1.0 / sensor_population_std
    if not math.isclose(per_channel_sre["x"], expected_sre, rel_tol=0.0, abs_tol=1e-15):
        raise AssertionError("sensor-state evaluator no longer uses population standard deviation")
    if per_channel_sre["y"] != 0.0 or per_channel_quality["x"] != quality_from_sre(expected_sre):
        raise AssertionError("sensor-state channel q transform changed")
    if sensor.mean_quality != sum(per_channel_quality.values()) / 2:
        raise AssertionError("sensor-state evaluator no longer uses equal-channel aggregation")
    if not evaluate_sensor_state_gate((0.30,)).passes:
        raise AssertionError("public non-expert quality gate must include 0.30")
    if evaluate_sensor_state_gate((0.300001,)).passes or not CANDIDATE_TARGET_FAMILIES:
        raise AssertionError("sensor-state quality gate boundary changed")
    try:
        evaluate_sensor_state_channels(
            {"x": sensor_truth},
            {"x": sensor_truth},
            region_mask=(True,) * 255 + (False,),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("sensor corruption evaluator accepted fewer than 256 rows")

    return {
        "evaluator_scientific_config_sha256": dict(sorted(hashes.items())),
        "absolute_position_target_count": ABSOLUTE_POSITION_TARGET_COUNT,
        "absolute_position_calibration_sha256": ABSOLUTE_POSITION_CALIBRATION_LOCK_SHA256,
        "absolute_position_score_anchors": {
            "reference": 0.5,
            "reference_actual": reference_score,
            "reference_tolerance": 1e-14,
            "no_information": no_information_score,
            "perfect": perfect_score,
        },
        "displacement_calibrated_reward": "UNKNOWN"
        if DISPLACEMENT_GENERATED_CALIBRATION.calibrated_reward is UNKNOWN
        else str(DISPLACEMENT_GENERATED_CALIBRATION.calibrated_reward),
        "signed_acceleration_aggregation": signed.aggregation,
        "sensor_corruption_minimum_rows": 256,
        "sensor_public_nonexpert_gate_maximum": 0.30,
        "sensor_selected_target_family": None,
        "sensor_benchmark_reward_emitted": sensor.benchmark_reward_emitted,
        "signed_acceleration_formulation": signed_acceleration_maturity,
        "signed_acceleration_unrecovered_b5_submetric": "ABSENT",
        "physical_trajectory_evaluator_sha256": (
            PHYSICAL_TRAJECTORY_EVALUATOR.scientific_config_sha256
        ),
        "displacement_raw_evaluator_sha256": raw_evaluator_hash(),
    }


def _protocol_state() -> dict[str, object]:
    from fpdbench.protocols import (
        CANONICAL_LOMO_PROTOCOL,
        CANONICAL_MATCH_ROLE_PROTOCOL,
        HISTORICAL_TRAINING_SEEDS,
        MatchRole,
        lomo_split_sha256,
        match_role_assignment_sha256,
    )

    protocols = {
        CANONICAL_MATCH_ROLE_PROTOCOL.protocol_id: (
            CANONICAL_MATCH_ROLE_PROTOCOL.version,
            CANONICAL_MATCH_ROLE_PROTOCOL.assignment_sha256,
        ),
        CANONICAL_LOMO_PROTOCOL.protocol_id: (
            CANONICAL_LOMO_PROTOCOL.version,
            CANONICAL_LOMO_PROTOCOL.split_sha256,
        ),
    }
    if protocols != _EXPECTED_PROTOCOLS:
        raise AssertionError("canonical protocol identity changed")
    if len(CANONICAL_LOMO_PROTOCOL.folds) != 5:
        raise AssertionError("canonical LOMO must regenerate exactly five folds")
    if "seeds" in CANONICAL_LOMO_PROTOCOL.__dataclass_fields__ or "evaluator_ids" in (
        CANONICAL_LOMO_PROTOCOL.__dataclass_fields__
    ):
        raise AssertionError("LOMO split identity must exclude seeds and evaluators")
    if (
        len(
            {
                lomo_split_sha256(CANONICAL_LOMO_PROTOCOL.folds)
                for _seed in HISTORICAL_TRAINING_SEEDS
            }
        )
        != 1
    ):
        raise AssertionError("LOMO split hash changed across training seeds")
    if lomo_split_sha256(tuple(reversed(CANONICAL_LOMO_PROTOCOL.folds))) != (
        CANONICAL_LOMO_PROTOCOL.split_sha256
    ):
        raise AssertionError("LOMO split hash depends on input fold order")
    reordered = tuple(
        replace(fold, training_matches=tuple(reversed(fold.training_matches)))
        for fold in CANONICAL_LOMO_PROTOCOL.folds
    )
    if lomo_split_sha256(reordered) != CANONICAL_LOMO_PROTOCOL.split_sha256:
        raise AssertionError("LOMO split hash depends on training-match order")
    first, second, *rest = CANONICAL_LOMO_PROTOCOL.folds
    swapped = (
        replace(
            first,
            training_matches=tuple(
                match for match in first.training_matches if match != second.held_out_match
            )
            + (first.held_out_match,),
            held_out_match=second.held_out_match,
        ),
        replace(
            second,
            training_matches=tuple(
                match for match in second.training_matches if match != first.held_out_match
            )
            + (second.held_out_match,),
            held_out_match=first.held_out_match,
        ),
        *rest,
    )
    if lomo_split_sha256(swapped) == CANONICAL_LOMO_PROTOCOL.split_sha256:
        raise AssertionError("LOMO split hash did not respond to held-out membership changes")
    assignments = list(CANONICAL_MATCH_ROLE_PROTOCOL.assignments)
    train_index = next(
        i for i, item in enumerate(assignments) if item.role is MatchRole.PUBLIC_TRAIN
    )
    validation_index = next(
        i for i, item in enumerate(assignments) if item.role is MatchRole.PUBLIC_VALIDATION
    )
    train = assignments[train_index]
    validation = assignments[validation_index]
    moved_match = train.match_ids[-1]
    assignments[train_index] = replace(train, match_ids=train.match_ids[:-1])
    assignments[validation_index] = replace(
        validation, match_ids=(*validation.match_ids, moved_match)
    )
    if match_role_assignment_sha256(assignments) == CANONICAL_MATCH_ROLE_PROTOCOL.assignment_sha256:
        raise AssertionError("role protocol hash did not respond to membership changes")
    if len(HISTORICAL_TRAINING_SEEDS) != 3:
        raise AssertionError("historical seed sensitivity state changed")
    return {
        "protocols": [
            {"id": identifier, "version": version, "sha256": digest}
            for identifier, (version, digest) in sorted(protocols.items())
        ],
        "lomo_folds": [
            {
                "fold_id": fold.fold_id,
                "training_matches": sorted(fold.training_matches),
                "held_out_match": fold.held_out_match,
            }
            for fold in CANONICAL_LOMO_PROTOCOL.folds
        ],
        "lomo_hash_order_invariant": True,
        "lomo_seed_and_evaluator_invariant": True,
        "membership_and_held_out_sensitive": True,
        "seed_count": len(HISTORICAL_TRAINING_SEEDS),
    }


def _lock_state(root: Path) -> tuple[list[dict[str, str]], list[str]]:
    lock_entries = (
        (
            "public_raw",
            displacement.build_public_validation_raw_scientific_lock(),
            displacement.PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK,
            "conditional_multi_agent_motion_prediction/public_validation_raw_displacement_scientific_lock.json",
        ),
        (
            "lomo_raw",
            displacement.build_lomo_raw_scientific_lock(),
            displacement.LOMO_RAW_SCIENTIFIC_LOCK,
            "conditional_multi_agent_motion_prediction/lomo_raw_displacement_scientific_lock.json",
        ),
        (
            "public_physical",
            displacement.build_public_validation_physical_scientific_lock(),
            displacement.PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK,
            "conditional_multi_agent_motion_prediction/public_validation_physical_diagnostic_scientific_lock.json",
        ),
    )
    entries: list[dict[str, str]] = []
    errors: list[str] = []
    for name, generated, canonical, relative in lock_entries:
        lock_path = root / "benchmarks" / relative
        try:
            raw = lock_path.read_bytes()
            checked_in = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{name}: cannot read lock file: {exc}")
            continue
        expected_hash, expected_file_hash = _EXPECTED_LOCKS[name]
        generated_hash = generated.get("scientific_lock_hash")
        if (
            generated != canonical
            or generated != checked_in
            or not verify_scientific_lock(generated)
        ):
            errors.append(f"{name}: regenerated scientific lock differs from checked-in state")
        if generated_hash != expected_hash:
            errors.append(f"{name}: scientific lock hash changed")
        if expected_file_hash is not None and _sha256(raw) != expected_file_hash:
            errors.append(f"{name}: historical raw lock file bytes changed")
        rendered = json.dumps(generated, indent=2, sort_keys=True) + "\n"
        if raw != rendered.encode("utf-8"):
            errors.append(f"{name}: deterministic lock rendering differs from checked-in bytes")
        entries.append(
            {
                "lock_id": name,
                "scientific_lock_sha256": str(generated_hash),
                "lock_file_sha256": _sha256(raw),
            }
        )
    return entries, errors


def _historical_results() -> list[dict[str, object]]:
    lock_by_hash = {
        str(lock["scientific_lock_hash"]): lock
        for lock in (
            displacement.PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK,
            displacement.LOMO_RAW_SCIENTIFIC_LOCK,
            displacement.PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK,
        )
    }
    if len(displacement.HISTORICAL_RESULTS) != 19 or displacement.PRIVATE_RESULT_RECORDS:
        raise AssertionError("historical result count/private-result boundary changed")
    entries: list[dict[str, object]] = []
    for result in displacement.HISTORICAL_RESULTS:
        if result.experiment_manifest is not None:
            raise AssertionError("historical records must not gain modern execution manifests")
        lock = lock_by_hash[result.scientific_lock_hash]
        binding = ScientificStateBinding.from_verified_lock(lock)
        validate_result_scope(binding, result.population, result.evaluator_state)
        if result.provenance_completeness.value != "historical_evidence_bound":
            raise AssertionError("historical evidence-bound result state changed")
        manifest = result.to_manifest(lock)
        entries.append(
            {
                "run_id": result.run_id,
                "metrics": [
                    {
                        "metric_id": metric.metric_id,
                        "value": metric.value,
                        "value_hex": metric.value.hex(),
                        "unit": metric.unit,
                    }
                    for metric in result.metric_records
                ],
                "population": result.population.value,
                "evaluator_state": result.evaluator_state.value,
                "validity": result.validity.value,
                "model_checkpoint_sha256": result.model_checkpoint_sha256,
                "output_sha256s": list(result.output_sha256s),
                "evidence_sha256": sorted(evidence_sha256(item) for item in result.evidence),
                "scientific_lock_sha256": result.scientific_lock_hash,
                "scientific_state_binding": binding.identity_payload(),
                "provenance_completeness": result.provenance_completeness.value,
                "result_sha256": result.result_hash,
                "manifest_sha256": manifest.manifest_hash,
            }
        )
    return entries


def build_reproducibility_snapshot(root: Path | None = None) -> dict[str, object]:
    """Regenerate the public snapshot without timestamps, host paths, or Git state."""
    from fpdbench.protocols import BENCHMARK_IDS

    root = Path.cwd() if root is None else root
    reference = _reference_regeneration()
    evaluator_state = _evaluator_regeneration(reference)
    protocol_state = _protocol_state()
    locks, _ = _lock_state(root)
    evidence = validate_evidence_inventory()
    registry = default_registry()
    return {
        "schema_id": SNAPSHOT_SCHEMA_ID,
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "benchmark_ids": list(BENCHMARK_IDS),
        "registry_counts": {
            "benchmark_count": len(registry.discover()),
            "research_family_count": len(registry.family_ids()),
            "research_object_count": len(registry.research_objects()),
        },
        "protocols": protocol_state["protocols"],
        "lomo_folds": protocol_state["lomo_folds"],
        "evaluator_scientific_config_sha256": evaluator_state["evaluator_scientific_config_sha256"],
        "absolute_position_calibration_sha256": ABSOLUTE_POSITION_CALIBRATION_LOCK_SHA256,
        "scientific_locks": locks,
        "historical_results": _historical_results(),
        "evidence_inventory": {
            "reference_count": evidence.reference_count,
            "unique_digests": evidence.unique_digests,
            "category_counts": dict(evidence.category_counts),
            "legacy_alias_count": evidence.legacy_alias_count,
            "legacy_alias_sha_reference_count": evidence.legacy_alias_sha_reference_count,
        },
        "historical_final_model": {
            "model_id": displacement.FINAL_PUBLIC_MODEL.model_id,
            "checkpoint_sha256": displacement.FINAL_PUBLIC_MODEL.checkpoint_sha256,
            "architecture_family": displacement.FINAL_PUBLIC_MODEL.architecture_family,
            "architecture_config_sha256": (
                displacement.FINAL_PUBLIC_MODEL.architecture_config_sha256
            ),
            "seed": displacement.FINAL_PUBLIC_MODEL.seed,
            "parameter_count": displacement.FINAL_PUBLIC_MODEL.parameter_count,
            "epochs": displacement.FINAL_PUBLIC_MODEL.epochs,
            "optimization_steps": displacement.FINAL_PUBLIC_MODEL.optimization_steps,
            "training_matches": list(displacement.FINAL_PUBLIC_MODEL.training_matches),
            "training_directed_rows": displacement.FINAL_PUBLIC_MODEL.training_directed_rows,
            "public_validation_matches": list(
                displacement.FINAL_PUBLIC_MODEL.public_validation_matches
            ),
            "public_validation_directed_rows": (
                displacement.FINAL_PUBLIC_MODEL.public_validation_directed_rows
            ),
            "model_selection_protocol": str(
                displacement.FINAL_PUBLIC_MODEL.model_selection_protocol
            ),
        },
        "private_result_records_count": len(displacement.PRIVATE_RESULT_RECORDS),
        "public_synthetic_reference": reference,
        "evaluator_regeneration": evaluator_state,
        "capabilities": {name: status for name, status in CAPABILITY_MATRIX},
        "artifact_availability": {name: status for name, status in ARTIFACT_AVAILABILITY},
    }


def render_reproducibility_snapshot(root: Path | None = None) -> bytes:
    return (
        json.dumps(build_reproducibility_snapshot(root), indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def check_reproducibility(root: Path | None = None) -> tuple[str, ...]:
    root = Path.cwd() if root is None else root
    errors = list(validate_repository(root))
    evidence = validate_evidence_inventory()
    errors.extend(evidence.errors)
    if len(CAPABILITY_MATRIX) != len(dict(CAPABILITY_MATRIX)):
        errors.append("reproducibility capability names must be unique")
    required_statuses = {
        UNAVAILABLE_PUBLIC_ARTIFACT,
        FORBIDDEN_PRIVATE_TRUTH,
        LOCAL_EVIDENCE_VERIFIABLE,
        PUBLIC_VERIFIABLE,
        PUBLIC_EXECUTABLE,
    }
    if {status for _, status in CAPABILITY_MATRIX} != required_statuses:
        errors.append("reproducibility capability matrix is incomplete")
    expected_boundary = {
        "historical_source_to_full_fixture_regeneration": UNAVAILABLE_PUBLIC_ARTIFACT,
        "historical_learned_checkpoint_loading": UNAVAILABLE_PUBLIC_ARTIFACT,
        "historical_learned_model_deterministic_inference": UNAVAILABLE_PUBLIC_ARTIFACT,
        "j03wmx_private_qualification_truth_evaluation": FORBIDDEN_PRIVATE_TRUTH,
        "canonical_registry_evidence_resolution": LOCAL_EVIDENCE_VERIFIABLE,
    }
    capabilities = dict(CAPABILITY_MATRIX)
    if any(capabilities.get(name) != status for name, status in expected_boundary.items()):
        errors.append("unavailable/private reproducibility capabilities must fail closed")
    try:
        protocol_state = _protocol_state()
        if protocol_state["protocols"] is None:
            errors.append("protocol regeneration returned no state")
        lock_entries, lock_errors = _lock_state(root)
        errors.extend(lock_errors)
        if len(lock_entries) != 3:
            errors.append("three displacement scientific locks must regenerate")
        reference = _reference_regeneration()
        _evaluator_regeneration(reference)
        _historical_results()
        expected_path = root / SNAPSHOT_RELATIVE_PATH
        expected = expected_path.read_bytes()
        regenerated = render_reproducibility_snapshot(root)
        if expected != regenerated:
            errors.append(
                "checked-in reproducibility snapshot differs from regenerated public state"
            )
    except (AssertionError, KeyError, OSError, TypeError, ValueError) as exc:
        errors.append(f"reproducibility regeneration failed: {exc}")
    return tuple(sorted(set(errors)))


def snapshot_sha256(root: Path | None = None) -> str:
    return _sha256(render_reproducibility_snapshot(root))


__all__ = [
    "ARTIFACT_AVAILABILITY",
    "CAPABILITY_MATRIX",
    "SNAPSHOT_RELATIVE_PATH",
    "SNAPSHOT_SCHEMA_ID",
    "SNAPSHOT_SCHEMA_VERSION",
    "build_reproducibility_snapshot",
    "check_reproducibility",
    "render_reproducibility_snapshot",
    "snapshot_sha256",
]
