from __future__ import annotations

import hashlib
import json
import math
import shutil
import sys
from pathlib import Path
from typing import cast

import numpy as np
import pytest
import torch

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    amended_heldout_evaluation as amended,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    population_producer_v2,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.evaluation_population import (
    prospective_window_id_v2,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.learned_deepsets import (
    INFORMATION_REGIMES,
    PerTargetContextDeepSetsMLP,
    build_scene_feature_payload,
    configure_deterministic_cpu,
    physical_metrics,
    validate_feature_payload,
)
from fpdbench.data_sources.skillcorner import canonical_bytes

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
import res338_cuda_qualification as cuda_fixture  # noqa: E402

RESEARCH_SHA256 = "a8c82bfa09ac792d6c4ae779d4b28158c33ed3c2500f8548f3e94d48197f4fd1"
SOURCE_RELEASE_SHA256 = "e92c417b7640b27399451134ee3fce4b1961b0c0dfc2e01175a8f3c906a9ae07"
SOURCE_POPULATION_SHA256 = "e9054b7ddc2dfeff4dd8425ea61a23ed0b326076a08899e47502484228fdbdf4"
PROTOCOL_SHA256 = "3d7bdc46300b966a4da274579d21ac4c8219e1ef897719d6b7a308596e9f1d9f"

configure_deterministic_cpu()


def _sha(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _support(
    *,
    future_home_shift: float = 0.0,
    future_away_shift: float = 0.0,
    missing_final: bool = False,
) -> list[dict[str, object]]:
    support: list[dict[str, object]] = []
    for sample_index in range(41):
        players: list[dict[str, object]] = []
        for side, ids in (("home", range(1, 12)), ("away", range(21, 32))):
            extra_ids = (32,) if side == "away" and sample_index >= 30 else ()
            for player_id in (*ids, *extra_ids):
                shift = (
                    future_home_shift
                    if side == "home" and sample_index >= 26
                    else future_away_shift
                    if side == "away" and sample_index >= 26
                    else 0.0
                )
                missing = missing_final and sample_index == 40
                players.append(
                    {
                        "player_id": player_id,
                        "group": side,
                        "x_m": None if missing else float(player_id + sample_index + shift),
                        "y_m": None if missing else float(player_id - sample_index + shift),
                        "is_detected": not (player_id == 1 and sample_index >= 26),
                    }
                )
        ball = {
            "x_m": float(sample_index + 0.5),
            "y_m": float(-sample_index + 0.25),
            "is_detected": True,
        }
        support.append(
            {
                "match_id": 1874553,
                "period": 1,
                "source_frame": 2 * sample_index,
                "timestamp_deciseconds": 2 * sample_index,
                "players": players,
                "ball": ball,
                "possession": None,
            }
        )
    return support


def _row(
    *,
    support: list[dict[str, object]] | None = None,
    match_id: str = "1874553",
) -> dict[str, object]:
    support_values = support or _support()
    scenes = [population_producer_v2._scene(support_values, side)[1] for side in ("home", "away")]
    origin_id = "period_1/sample_25"
    return {
        "kind": "window",
        "match_id": match_id,
        "role": "evaluation",
        "origin_sample_id": origin_id,
        "window_id": prospective_window_id_v2(match_id, origin_id),
        "source_match_sha256": "a" * 64,
        "time_offsets_s": [round(-5.0 + index * 0.2, 10) for index in range(41)],
        "support_sample_ids": [f"period_1/sample_{index}" for index in range(41)],
        "support": support_values,
        "home_player_ids": list(range(1, 12)),
        "away_player_ids": list(range(21, 33)),
        "scenes": scenes,
    }


def _history_manifest() -> dict[str, object]:
    _, _, manifest, _ = amended.load_frozen_artifacts()
    records = cast(list[dict[str, object]], manifest["checkpoints"])
    return {
        **manifest,
        "checkpoints": [row for row in records if row["information_regime"] == "history_only"],
    }


def _result_matrix() -> tuple[list[dict[str, object]], dict[str, object], dict[str, object]]:
    _, _, manifest, baseline = amended.load_frozen_artifacts()
    denominators = cast(dict[str, dict[str, int]], baseline["scored_denominators"])
    records: list[dict[str, object]] = []
    match_index = {match: index for index, match in enumerate(amended._MATCHES)}
    seed_shift = {1729: 0.0, 2718: 1.0, 31415: 2.0}
    for fit in cast(list[dict[str, object]], manifest["checkpoints"]):
        regime = str(fit["information_regime"])
        representation = str(fit["target_representation"])
        seed = int(fit["seed"])
        context_offset = {
            "history_only": 4.0,
            "future_ball": 2.0,
            "future_opponent_plus_ball": 1.0,
        }[regime]
        for match in amended._MATCHES:
            ade = match_index[match] + context_offset + seed_shift[seed]
            record: dict[str, object] = {
                "schema_id": "fpdbench.res594.match-result",
                "schema_version": "1.0.0",
                "study_id": amended._STUDY_ID,
                "authority_scope": "research-only-amended-heldout",
                "role": "evaluation",
                "model_id": fit["model_id"],
                "information_regime": regime,
                "target_representation": representation,
                "seed": seed,
                "evaluation_match_id": match,
                "checkpoint_sha256": fit["checkpoint_sha256"],
                "completed_fit_receipt_sha256": fit["receipt_sha256"],
                "configuration_sha256": fit["configuration_sha256"],
                "selected_step": fit["selected_step"],
                "metrics": {"ade_m": ade, "fde_m": ade + 10.0, "xy_rmse_m": ade + 1.0},
                "unit": "metres",
                "denominators": {
                    "windows": denominators[match]["windows"],
                    "scoreable_scenes": denominators[match]["scenes"],
                    "scored_points": denominators[match]["scored_points"],
                    "final_targets": denominators[match]["final_targets"],
                },
                "target_mask_identity_sha256": fit["target_mask_identity_sha256"],
                "evaluated_mask_sha256": hashlib.sha256(f"mask-{match}".encode()).hexdigest(),
                "window_identity_sha256": hashlib.sha256(f"window-{match}".encode()).hexdigest(),
                "source_match_sha256": hashlib.sha256(f"source-{match}".encode()).hexdigest(),
                "population_stream_sha256": hashlib.sha256(f"stream-{match}".encode()).hexdigest(),
                "evaluation_input_sha256": hashlib.sha256(b"synthetic fixture").hexdigest(),
                "quality_strata": {
                    stratum: {
                        "status": "scoreable",
                        "windows": 1,
                        "scoreable_scenes": 1,
                        "scored_points": 100,
                        "final_targets": 10,
                        "metrics": {
                            "ade_m": ade,
                            "fde_m": ade + 10.0,
                            "xy_rmse_m": ade + 1.0,
                        },
                    }
                    for stratum in (
                        "detected_only",
                        "with_provider_extrapolation",
                        "unclassified",
                    )
                },
                "horizon_strata": {
                    stratum: {
                        "status": "scoreable",
                        "windows": 1,
                        "scoreable_scenes": 2,
                        "scored_points": 100,
                        "final_targets": 10,
                        "metrics": {
                            "ade_m": ade,
                            "fde_m": ade + 10.0,
                            "xy_rmse_m": ade + 1.0,
                        },
                    }
                    for stratum in (
                        "early_0.2_1.0s",
                        "middle_1.2_2.0s",
                        "late_2.2_3.0s",
                    )
                },
            }
            record["result_receipt_sha256"] = hashlib.sha256(canonical_bytes(record)).hexdigest()
            records.append(record)
    return records, manifest, baseline


def _auth_document() -> dict[str, object]:
    _amendment, amendment_sha, _manifest, _baseline = amended.load_frozen_artifacts()
    manifest_sha = hashlib.sha256(amended._read_resource(amended._MANIFEST_FILE)).hexdigest()
    scorer_sha = amended._scorer_code_identity_sha256()
    return {
        "schema_id": "fpdbench.res594.owner-execution-authorization",
        "schema_version": "1.0.0",
        "study_id": amended._STUDY_ID,
        "owner_approved": True,
        "owner_name": "Synthetic Test Owner",
        "authorized_at_utc": "2026-11-06T00:00:00Z",
        "authorized_by_owner": True,
        "research_only": True,
        "protected_status": "NOT_QUALIFIED",
        "one_campaign_only": True,
        "retry_after_failure": False,
        "amendment_sha256": amendment_sha,
        "checkpoint_manifest_sha256": manifest_sha,
        "scorer_code_sha256": scorer_sha,
        "research_admission_sha256": RESEARCH_SHA256,
        "evaluation_match_ids": list(amended._MATCHES),
        "resource_limits": amended._RESOURCE_LIMITS,
        "runtime": {
            "python": "3.12.8",
            "numpy": "2.2.4",
            "pytorch": "2.6.0+cpu",
            "device": "cpu",
            "precision": "float32",
            "threads": 1,
        },
        "evaluation_input_identity": {
            "research_admission_sha256": RESEARCH_SHA256,
            "source_release_hash": SOURCE_RELEASE_SHA256,
            "source_population_hash": SOURCE_POPULATION_SHA256,
            "protocol_sha256": PROTOCOL_SHA256,
        },
    }


def _write_auth(path: Path, document: dict[str, object]) -> str:
    path.write_bytes(json.dumps(document, sort_keys=True).encode())
    path.chmod(0o600)
    return (
        f"RES594-OWNER-GO:{document['amendment_sha256']}:"
        f"{document['checkpoint_manifest_sha256']}:"
        f"{document['research_admission_sha256']}:{document['scorer_code_sha256']}"
    )


def test_checkpoint_manifest_is_the_exact_verified_18_cell_matrix() -> None:
    amendment, amendment_sha, manifest, _ = amended.load_frozen_artifacts()
    assert len(manifest["checkpoints"]) == 18
    assert set(amendment["population"]["match_ids"]) == set(amended._MATCHES)
    assert amendment["status"] == "PROPOSED_UNRATIFIED"
    assert amendment["timing"]["original_preregistration"] is False
    assert amendment["deviation"]["original_required_training_lomo_fits"] == 216
    assert amendment["deviation"]["original_checkpoint_manifests_required_before_scoring"] == 234
    assert amendment["deviation"]["original_234_checkpoint_prerequisite_fulfilled"] is False
    assert len(amendment_sha) == 64


def test_manifest_rejects_missing_duplicate_or_unexpected_cells() -> None:
    _, _, manifest, _ = amended.load_frozen_artifacts()
    broken = dict(manifest)
    broken["checkpoints"] = manifest["checkpoints"][:-1]
    with pytest.raises(ValueError, match="exact 18"):
        amended._validate_checkpoint_manifest(broken)
    broken = dict(manifest)
    broken["checkpoints"] = [*manifest["checkpoints"], manifest["checkpoints"][0]]
    with pytest.raises(ValueError, match="duplicates"):
        amended._validate_checkpoint_manifest(broken)
    broken = dict(manifest)
    broken["checkpoints"] = [dict(row) for row in manifest["checkpoints"]]
    cast(dict[str, object], broken["checkpoints"][0])["model_id"] = "unexpected_model"
    with pytest.raises(ValueError, match="unexpected model"):
        amended._validate_checkpoint_manifest(broken)


def _write_synthetic_frozen_evidence(
    root: Path,
    *,
    bad_checkpoint_config: bool = False,
    missing_receipt: bool = False,
    bad_receipt_step: bool = False,
) -> tuple[Path, Path, dict[str, object]]:
    _, _, manifest, _ = amended.load_frozen_artifacts()
    checkpoint_directory = root / "checkpoints"
    receipt_directory = root / "receipts"
    checkpoint_directory.mkdir(mode=0o700)
    receipt_directory.mkdir(mode=0o700)
    rows: list[dict[str, object]] = []
    for index, source_row in enumerate(manifest["checkpoints"]):
        row = dict(cast(dict[str, object], source_row))
        regime = cast(str, row["information_regime"])
        model = PerTargetContextDeepSetsMLP(regime).cpu()
        payload = {
            "metadata": {
                "run_id": amended._run_id(row),
                "configuration_sha256": (
                    "f" * 64
                    if bad_checkpoint_config and index == 0
                    else row["configuration_sha256"]
                ),
                "selected_step": row["selected_step"],
                "attempt_number": 1,
            },
            "state_dict": model.state_dict(),
        }
        torch.save(payload, root / "checkpoint.tmp")
        (root / "checkpoint.tmp").chmod(0o600)
        checkpoint_sha = amended._secure_sha256(root / "checkpoint.tmp")
        checkpoint_path = checkpoint_directory / f"{checkpoint_sha}.pt"
        shutil.move(root / "checkpoint.tmp", checkpoint_path)
        checkpoint_path.chmod(0o600)
        row["checkpoint_sha256"] = checkpoint_sha
        receipt = {
            "status": "completed",
            "fit_role": "final_train",
            "run_id": amended._run_id(row),
            "model_id": row["model_id"],
            "information_regime": row["information_regime"],
            "target_representation": row["target_representation"],
            "seed": row["seed"],
            "attempt_number": 1,
            "selected_step": row["selected_step"],
            "optimizer_steps": row["optimizer_steps"],
            "checkpoint_sha256": checkpoint_sha,
            "configuration_sha256": row["configuration_sha256"],
            "environment_sha256": row["environment_sha256"],
            "population_manifest_sha256": row["population_manifest_sha256"],
            "target_mask_identity_sha256": row["target_mask_identity_sha256"],
            "plan_sha256": row["plan_sha256"],
            "protocol_sha256": row["protocol_sha256"],
            "train_match_ids": row["train_match_ids"],
            "validation_match_ids": row["validation_match_ids"],
        }
        if bad_receipt_step and index == 0:
            receipt["selected_step"] = cast(int, receipt["selected_step"]) + 100
        receipt_bytes = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
        receipt_sha = hashlib.sha256(receipt_bytes).hexdigest()
        row["receipt_sha256"] = receipt_sha
        if not (missing_receipt and index == 0):
            receipt_path = receipt_directory / f"{receipt_sha}.json"
            receipt_path.write_bytes(receipt_bytes)
            receipt_path.chmod(0o600)
        rows.append(row)
    return checkpoint_directory, receipt_directory, {**manifest, "checkpoints": rows}


def test_all_checkpoints_and_receipts_are_hash_checked_against_fit_identities(
    tmp_path: Path,
) -> None:
    checkpoints, receipts, manifest = _write_synthetic_frozen_evidence(tmp_path)
    models = amended.load_frozen_models(checkpoints, receipts, manifest)
    assert len(models) == 18
    first_record = manifest["checkpoints"][0]
    tampered = checkpoints / f"{first_record['checkpoint_sha256']}.pt"
    with tampered.open("ab") as stream:
        stream.write(b"changed checkpoint bytes")
    with pytest.raises(ValueError, match="checkpoint SHA-256 mismatch"):
        amended.load_frozen_models(checkpoints, receipts, manifest)

    missing_root = tmp_path / "missing"
    missing_root.mkdir()
    missing_checkpoints, missing_receipts, missing_manifest = _write_synthetic_frozen_evidence(
        missing_root, missing_receipt=True
    )
    with pytest.raises(FileNotFoundError):
        amended.load_frozen_models(missing_checkpoints, missing_receipts, missing_manifest)

    config_root = tmp_path / "config-mismatch"
    config_root.mkdir()
    config_checkpoints, config_receipts, config_manifest = _write_synthetic_frozen_evidence(
        config_root, bad_checkpoint_config=True
    )
    with pytest.raises(ValueError, match="metadata differs"):
        amended.load_frozen_models(config_checkpoints, config_receipts, config_manifest)

    step_root = tmp_path / "receipt-step-mismatch"
    step_root.mkdir()
    step_checkpoints, step_receipts, step_manifest = _write_synthetic_frozen_evidence(
        step_root, bad_receipt_step=True
    )
    with pytest.raises(ValueError, match="receipt differs"):
        amended.load_frozen_models(step_checkpoints, step_receipts, step_manifest)


def test_owner_gate_binds_exact_scope_and_cpu_limits(tmp_path: Path) -> None:
    document = _auth_document()
    auth_path = tmp_path / "owner.json"
    owner_go = _write_auth(auth_path, document)
    auth = amended.authorize_owner_execution(
        auth_path,
        owner_go,
        amendment_sha256=str(document["amendment_sha256"]),
        checkpoint_manifest_sha256=str(document["checkpoint_manifest_sha256"]),
        scorer_code_sha256=str(document["scorer_code_sha256"]),
    )
    assert auth.document["research_only"] is True
    with pytest.raises(PermissionError, match="typed owner GO"):
        amended.authorize_owner_execution(
            auth_path,
            owner_go + "x",
            amendment_sha256=str(document["amendment_sha256"]),
            checkpoint_manifest_sha256=str(document["checkpoint_manifest_sha256"]),
            scorer_code_sha256=str(document["scorer_code_sha256"]),
        )


def test_execution_without_owner_authorization_fails_before_source_or_eval_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def opened_source(*_args: object, **_kwargs: object) -> None:
        pytest.fail("evaluation or source files were opened before owner authorization")

    monkeypatch.setattr(amended, "_prepare_verified_research_input", opened_source)
    with pytest.raises(FileNotFoundError):
        amended.run_authorized_campaign(
            owner_authorization_path=tmp_path / "missing-owner.json",
            owner_go="",
            checkpoint_directory=tmp_path / "never-opened-checkpoints",
            receipt_directory=tmp_path / "never-opened-receipts",
            research_root=tmp_path / "evaluation-labels-never-opened",
            source_root=tmp_path / "source-never-opened",
            output_directory=tmp_path / "never-created-output",
        )
    assert not (tmp_path / "never-created-output").exists()


def test_four_evaluation_roles_and_window_identity_are_fail_closed() -> None:
    row = _row()
    assert row["window_id"] == prospective_window_id_v2("1874553", "period_1/sample_25")
    broken = dict(row)
    broken["role"] = "training"
    with pytest.raises(ValueError, match="role"):
        amended._validate_window_record(broken, expected_source_sha256="a" * 64)
    broken = dict(row)
    broken["window_id"] = "0" * 64
    with pytest.raises(ValueError, match="window identity"):
        amended._validate_window_record(broken, expected_source_sha256="a" * 64)
    broken = dict(row)
    broken["source_match_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="source identity"):
        amended._validate_window_record(broken, expected_source_sha256="a" * 64)


def test_input_header_freezes_role_orientation_horizon_and_mask_provenance() -> None:
    _amendment, amendment_sha, manifest, baseline = amended.load_frozen_artifacts()
    manifest_sha = hashlib.sha256(amended._read_resource(amended._MANIFEST_FILE)).hexdigest()
    source_authority = {
        "window_identity_sha256_by_match": {match: "a" * 64 for match in amended._MATCHES},
        "mask_identity_sha256_by_match": {match: "b" * 64 for match in amended._MATCHES},
        "source_match_sha256_by_match": {match: "c" * 64 for match in amended._MATCHES},
        "producer_stream_sha256_by_match": {match: "d" * 64 for match in amended._MATCHES},
        "expected_scoreable_window_counts": {
            match: baseline["scored_denominators"][match]["windows"] for match in amended._MATCHES
        },
        "source_verification_sha256": "e" * 64,
    }
    header = {
        "kind": "header",
        "schema_id": amended._INPUT_SCHEMA,
        "schema_version": "1.0.0",
        "study_id": amended._STUDY_ID,
        "amendment_sha256": amendment_sha,
        "checkpoint_manifest_sha256": manifest_sha,
        "role": "evaluation",
        "research_admission_sha256": RESEARCH_SHA256,
        "source_release_hash": SOURCE_RELEASE_SHA256,
        "source_population_hash": SOURCE_POPULATION_SHA256,
        "measurement_state_hash": amended.EXPECTED_MEASUREMENT_STATE_V2_HASH,
        "eligibility_policy_hash": amended.EXPECTED_ELIGIBILITY_POLICY_V2_HASH,
        "protocol_sha256": amended.PROTOCOL_V2_SHA256,
        "coordinate_frame": "source_pitch_xy_m",
        "scene_orientation": "source_xy_no_reflection",
        "history_intervals": 25,
        "origin_included": True,
        "future_steps": 15,
        "step_seconds": 0.2,
        "window_identity_version": "2.0.0",
        "verification_status": "RESEARCH_RECONCILED",
        "protected_status": "NOT_QUALIFIED",
        "evaluation_match_ids": list(amended._MATCHES),
        "window_identity_sha256_by_match": source_authority["window_identity_sha256_by_match"],
        "mask_identity_sha256_by_match": source_authority["mask_identity_sha256_by_match"],
        "source_match_sha256_by_match": source_authority["source_match_sha256_by_match"],
        "population_stream_sha256_by_match": source_authority["producer_stream_sha256_by_match"],
        "expected_scoreable_window_counts": source_authority["expected_scoreable_window_counts"],
        "source_verification_sha256": source_authority["source_verification_sha256"],
    }
    amended._validate_input_header(
        header,
        amendment_sha256=amendment_sha,
        checkpoint_manifest_sha256=manifest_sha,
        source_authority=source_authority,
    )
    wrong = dict(header, scene_orientation="mirrored")
    with pytest.raises(ValueError, match="protocol"):
        amended._validate_input_header(
            wrong,
            amendment_sha256=amendment_sha,
            checkpoint_manifest_sha256=manifest_sha,
            source_authority=source_authority,
        )


def test_missing_context_channel_and_future_target_leak_are_rejected() -> None:
    row = _row()
    cast(list[dict[str, object]], row["support"])[26].pop("ball")
    with pytest.raises(ValueError, match="player and ball channels"):
        amended._validate_window_record(row, expected_source_sha256="a" * 64)
    row = _row()
    cast(list[dict[str, object]], row["support"])[30]["future_target_xy"] = [[0.0, 0.0]]
    with pytest.raises(ValueError, match="information-boundary"):
        amended._validate_window_record(row, expected_source_sha256="a" * 64)
    payload = build_scene_feature_payload(
        _support(),
        target_side="home",
        target_player_ids=list(range(1, 12)),
        home_player_ids=list(range(1, 12)),
        away_player_ids=list(range(21, 33)),
        regime="future_ball",
    )
    del payload["future_ball"]
    with pytest.raises(ValueError, match="fields"):
        validate_feature_payload(payload, "future_ball")


def test_history_only_payload_does_not_change_with_future_target_positions() -> None:
    first = _support()
    second = _support(future_home_shift=500.0)
    arguments = {
        "target_side": "home",
        "target_player_ids": list(range(1, 12)),
        "home_player_ids": list(range(1, 12)),
        "away_player_ids": list(range(21, 33)),
    }
    first_payload = build_scene_feature_payload(first, regime="history_only", **arguments)
    second_payload = build_scene_feature_payload(second, regime="history_only", **arguments)
    assert first_payload.keys() == second_payload.keys()
    for key in first_payload:
        assert np.array_equal(first_payload[key], second_payload[key])


def test_truth_masks_and_origin_relative_reconstruction_share_physical_truth() -> None:
    row = _row()
    truth = cast(dict[str, object], cast(list[dict[str, object]], row["scenes"])[0])
    absolute, displacement, mask = amended.validate_truth_scene(truth)
    origin = np.asarray(cast(list[list[float]], truth["origin_xy"]), dtype=np.float64)
    absolute_prediction = absolute.copy()
    displacement_prediction = amended.reconstruct_physical_prediction(
        displacement.copy(), "origin_relative_displacement", origin
    )
    assert amended._metric(absolute_prediction, absolute, mask).ade_m == pytest.approx(0.0)
    assert amended._metric(displacement_prediction, absolute, mask).ade_m == pytest.approx(0.0)
    wrong_origin = origin + 1.0
    wrong_prediction = amended.reconstruct_physical_prediction(
        displacement.copy(), "origin_relative_displacement", wrong_origin
    )
    assert amended._metric(wrong_prediction, absolute, mask).ade_m == pytest.approx(2**0.5)
    wrong_mask = dict(truth)
    wrong_mask["truth_mask"] = [
        [False, *cast(list[bool], line)[1:]] for line in cast(list[list[bool]], truth["truth_mask"])
    ]
    with pytest.raises(ValueError, match="share the locked truth mask"):
        amended.validate_truth_scene(wrong_mask)
    wrong_origin_truth = dict(truth)
    wrong_origin_truth["origin_xy"] = [
        list(pair) for pair in cast(list[list[float]], truth["origin_xy"])
    ]
    cast(list[list[float]], wrong_origin_truth["origin_xy"])[0][0] += 1.0
    with pytest.raises(ValueError, match="target representations"):
        amended.validate_truth_scene(wrong_origin_truth)


def test_zero_eligible_targets_fail_closed_before_model_scoring() -> None:
    row = _row(support=_support(missing_final=True))
    manifest = _history_manifest()
    accumulators = {}
    for fit in manifest["checkpoints"]:
        key = amended._checkpoint_key(fit)
        accumulators[(*key, "1874553")] = amended.WindowMetricAccumulator()
    with pytest.raises(ValueError, match="zero final targets"):
        amended._score_window(
            row,
            {},
            manifest,
            "a" * 64,
            accumulators,
            {"1874553": set()},
            {"1874553": hashlib.sha256()},
            {"1874553": hashlib.sha256()},
            {},
            {},
        )


class _NonFiniteModel(PerTargetContextDeepSetsMLP):
    def forward(self, inputs):
        return torch.full(
            (inputs.target_history.shape[0], 11, 15, 2),
            float("nan"),
            dtype=torch.float32,
        )


def test_actual_streaming_scorer_uses_production_model_and_rejects_nonfinite() -> None:
    row = _row()
    manifest = _history_manifest()
    models = {
        amended._checkpoint_key(fit): PerTargetContextDeepSetsMLP("history_only").eval()
        for fit in manifest["checkpoints"]
    }
    accumulators = {
        (*amended._checkpoint_key(fit), "1874553"): amended.WindowMetricAccumulator()
        for fit in manifest["checkpoints"]
    }
    quality = {
        (*amended._checkpoint_key(fit), "1874553", stratum): amended.WindowMetricAccumulator()
        for fit in manifest["checkpoints"]
        for stratum in ("detected_only", "with_provider_extrapolation", "unclassified")
    }
    horizon = {
        (*amended._checkpoint_key(fit), "1874553", stratum): amended.WindowMetricAccumulator()
        for fit in manifest["checkpoints"]
        for stratum in ("early_0.2_1.0s", "middle_1.2_2.0s", "late_2.2_3.0s")
    }
    amended._score_window(
        row,
        models,
        manifest,
        "a" * 64,
        accumulators,
        {"1874553": set()},
        {"1874553": hashlib.sha256()},
        {"1874553": hashlib.sha256()},
        quality,
        horizon,
    )
    first = next(iter(accumulators.values()))
    assert first.windows == 1
    assert first.scenes == 2
    assert first.points == 330
    assert first.final_targets == 22
    assert math.isfinite(first.mean()["ade_m"])

    nonfinite = dict(models)
    first_key = next(iter(nonfinite))
    nonfinite[first_key] = _NonFiniteModel("history_only").eval()
    with pytest.raises(FloatingPointError, match="non-finite"):
        amended._score_window(
            row,
            nonfinite,
            manifest,
            "a" * 64,
            accumulators,
            {"1874553": set()},
            {"1874553": hashlib.sha256()},
            {"1874553": hashlib.sha256()},
            quality,
            horizon,
        )


def test_existing_gpu_qualification_fixture_runs_through_cpu_scoring_semantics() -> None:
    seed = 1729
    for regime in INFORMATION_REGIMES:
        rng = np.random.default_rng(seed)
        inputs = cuda_fixture._inputs(rng, 4, regime)
        torch.manual_seed(seed)
        model = PerTargetContextDeepSetsMLP(regime).cpu().eval()
        with torch.inference_mode():
            first = model(inputs)
            replay = model(inputs)
        assert torch.equal(first, replay)
        truth, mask = cuda_fixture._truth_and_mask(np.random.default_rng(2718), 4)
        for scene_index in range(4):
            prediction = first[scene_index].cpu().numpy().astype(np.float64)
            actual_truth = truth[scene_index].cpu().numpy().astype(np.float64)
            actual_mask = mask[scene_index].cpu().numpy()
            expected = physical_metrics(
                prediction[None].astype(np.float32),
                actual_truth[None],
                actual_mask[None],
            )
            observed = amended._metric(prediction, actual_truth, actual_mask)
            assert observed.ade_m == pytest.approx(expected["ade_m"])
            assert observed.fde_m == pytest.approx(expected["fde_m"])
            assert observed.xy_rmse_m == pytest.approx(expected["xy_rmse_m"])


def test_result_matrix_requires_all_cells_matches_hashes_and_common_denominators() -> None:
    records, manifest, baseline = _result_matrix()
    amended.validate_result_matrix(records, manifest)
    with pytest.raises(ValueError, match="72"):
        amended.validate_result_matrix(records[:-1], manifest)
    with pytest.raises(ValueError, match="duplicate"):
        amended.validate_result_matrix([*records, records[0]], manifest)
    broken = [dict(record) for record in records]
    broken[0]["checkpoint_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="checkpoint, receipt, or configuration"):
        amended.validate_result_matrix(broken, manifest)
    broken = [dict(record) for record in records]
    broken[0]["target_representation"] = "future"
    with pytest.raises(ValueError, match="unexpected model"):
        amended.validate_result_matrix(broken, manifest)
    broken = [dict(record) for record in records]
    broken[0]["denominators"] = dict(broken[0]["denominators"], windows=1)
    with pytest.raises(ValueError, match="denominators differ"):
        amended.validate_result_matrix(broken, manifest)
    broken = [dict(record) for record in records]
    broken[0]["authority_scope"] = "protected"
    with pytest.raises(ValueError, match="authority"):
        amended.validate_result_matrix(broken, manifest)
    assert (
        baseline["status"] == "PUBLISHED_AGGREGATE_REFERENCE_PRIVATE_CELL_MANIFESTS_NOT_RECOVERED"
    )


def test_aggregates_match_seed_then_equal_matches_and_frozen_contrast_sign() -> None:
    records, manifest, baseline = _result_matrix()
    analysis = amended.aggregate_results(records, manifest, baseline)
    summary = next(
        item
        for item in analysis["configuration_summaries"]
        if item["information_regime"] == "history_only"
        and item["target_representation"] == "absolute_xy"
    )
    assert summary["aggregation"]["ade_m"] == pytest.approx(6.5)
    assert summary["match_seed_means"]["1874553"]["ade_m"] == pytest.approx(5.0)
    assert summary["seed_variation"]["ade_m"]["sample_sd_across_three_seed_means"] == pytest.approx(
        1.0
    )
    contrast_c1 = next(
        item
        for item in analysis["frozen_contrasts"]
        if item["contrast"] == "C1" and item["target_representation"] == "absolute_xy"
    )
    contrast_c2 = next(
        item
        for item in analysis["frozen_contrasts"]
        if item["contrast"] == "C2" and item["target_representation"] == "absolute_xy"
    )
    assert contrast_c1["equal_match_mean_m"] == pytest.approx(2.0)
    assert contrast_c2["equal_match_mean_m"] == pytest.approx(1.0)
    assert set(contrast_c1["match_values_m"]) == set(amended._MATCHES)
    assert analysis["deletion_diagnostic_label"] == "evaluation-match deletion sensitivity"
    campaign = {
        "analysis": analysis,
        "manifest_sha256": "a" * 64,
        "checkpoint_manifest_sha256": "b" * 64,
        "evaluation_input_sha256": "c" * 64,
        "research_admission_sha256": RESEARCH_SHA256,
        "runtime": {"pytorch": "2.6.0+cpu"},
        "baseline_comparability": amended._BASELINE_COMPARABILITY,
    }
    report = amended.render_scientific_report(campaign, records)
    assert "Six-cell comparison" in report
    assert "Four-match result summary" in report
    assert "Evaluation-match deletion sensitivity" in report
    assert "cell manifests not recovered" in report
    assert "significance tests or confidence intervals" in report
    assert "future target positions" not in report
    assert "held-out ade by regime" in amended._svg_ade(campaign).lower()
    assert "frozen context contrasts" in amended._svg_contrasts(campaign).lower()


def test_repeated_or_partial_campaigns_fail_closed(tmp_path: Path) -> None:
    owner = amended.OwnerAuthorization(
        {"research_admission_sha256": RESEARCH_SHA256}, "a" * 64, "b" * 64, None, "c" * 64
    )
    output = tmp_path / "campaign"
    amended._reserve_campaign(output, owner)
    with pytest.raises(FileExistsError, match="repeated execution"):
        amended._reserve_campaign(output, owner)
    partial = tmp_path / "partial"
    partial.mkdir(mode=0o700)
    (partial / ".started.json").write_text('{"started": true}', encoding="utf-8")
    (partial / ".started.json").chmod(0o600)
    with pytest.raises(FileNotFoundError):
        amended.verify_committed_campaign(partial)
