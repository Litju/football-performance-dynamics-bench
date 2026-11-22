from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import numpy as np
import pytest
import torch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import res340_lomo as lomo  # noqa: E402
import score_res340_lomo  # noqa: E402
import train_res338_final_fits as trainer  # noqa: E402

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.learned_deepsets import (  # noqa: E402
    PerTargetContextDeepSetsMLP,
    seed_training,
)


def _frozen() -> tuple[dict[str, object], dict[str, object], dict[str, list[str]]]:
    return trainer._frozen_split_and_authorities()


def _fits_and_roles() -> tuple[
    dict[str, object], dict[str, object], dict[str, list[str]], list[dict[str, object]]
]:
    plan, protocol, roles = _frozen()
    matrix = lomo.build_fit_matrix(plan, protocol, roles)
    return plan, protocol, roles, lomo.expand_fit_matrix(matrix)


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def test_frozen_matrix_has_exact_216_fit_keys_and_role_membership() -> None:
    plan, protocol, roles, fits = _fits_and_roles()
    folds = cast(
        list[dict[str, object]],
        cast(dict[str, object], cast(dict[str, object], protocol["scientific_state"])["split"])[
            "lomo"
        ]["folds"],
    )

    assert len(folds) == lomo.FOLD_COUNT == 12
    assert len(fits) == lomo.FIT_COUNT == 216
    assert len({str(fit["run_id"]) for fit in fits}) == 216
    assert {str(fit["fold_id"]) for fit in fits} == {f"fold-{index:02d}" for index in range(1, 13)}
    assert not any(
        set(roles["evaluation"]).intersection(cast(list[str], fit["train_match_ids"]))
        for fit in fits
    )
    for fold in folds:
        held_out = str(fold["held_out_match"])
        fold_fits = [fit for fit in fits if fit["fold_id"] == fold["fold_id"]]
        assert len(fold_fits) == 18
        assert all(len(cast(list[str], fit["train_match_ids"])) == 11 for fit in fold_fits)
        assert all(held_out not in cast(list[str], fit["train_match_ids"]) for fit in fold_fits)
        assert all(
            cast(list[str], fit["validation_match_ids"]) == roles["validation"]
            and held_out not in cast(list[str], fit["validation_match_ids"])
            for fit in fold_fits
        )
        assert {str(fit["seed"]) for fit in fold_fits} == {"1729", "2718", "31415"}
    assert plan["plan_sha256"] == "a59fee6ee8e9fb03f4f0ccdae1933458af2bbf2375db7e6cd2bdf10962e42b62"


def test_committed_matrix_matches_protocol_and_content_hash() -> None:
    plan, protocol, roles = _frozen()
    expected = lomo.build_fit_matrix(plan, protocol, roles)
    path = REPO / "docs/res340-lomo-fit-matrix.json"
    actual = cast(dict[str, object], json.loads(path.read_bytes()))

    assert actual == expected
    assert actual["fit_count"] == 216
    assert lomo.matrix_sha256(actual) == lomo.matrix_sha256(expected)
    assert lomo.matrix_sha256(actual) == (
        "47450802e53dc5ed03b7108fb0a9592165ee3669847f6b061212f1002a67823a"
    )


def test_each_worker_cache_view_excludes_heldout_and_evaluation_roles() -> None:
    _, _, roles, fits = _fits_and_roles()
    fit = fits[0]
    caches = {
        match_id: SimpleNamespace(match_id=match_id, role="training")
        for match_id in roles["training"]
    }
    caches.update(
        {
            match_id: SimpleNamespace(match_id=match_id, role="validation")
            for match_id in roles["validation"]
        }
    )
    view = lomo.cache_view_for_fit(cast(dict[str, trainer.MatchCache], caches), fit)

    assert len(view) == 15
    assert str(fit["held_out_match_id"]) not in view
    assert set(view) == set(cast(list[str], fit["train_match_ids"])) | set(roles["validation"])
    evaluation = roles["evaluation"][0]
    caches[evaluation] = SimpleNamespace(match_id=evaluation, role="evaluation")
    with pytest.raises(ValueError, match="evaluation-role"):
        lomo.cache_view_for_fit(cast(dict[str, trainer.MatchCache], caches), fit)


def test_fold_and_configuration_changes_produce_new_fit_identity() -> None:
    plan, protocol, _, fits = _fits_and_roles()
    first = fits[0]
    other_fold = next(fit for fit in fits if fit["fold_id"] != first["fold_id"])
    config = lomo.fit_configuration(
        first,
        plan_sha256=str(plan["plan_sha256"]),
        protocol_sha256=str(protocol["protocol_sha256"]),
        device="cuda",
    )
    other_config = lomo.fit_configuration(
        other_fold,
        plan_sha256=str(plan["plan_sha256"]),
        protocol_sha256=str(protocol["protocol_sha256"]),
        device="cuda",
    )

    assert lomo.fit_run_id(first) != lomo.fit_run_id(other_fold)
    assert (
        hashlib.sha256(lomo.canonical_bytes(config)).hexdigest()
        != hashlib.sha256(lomo.canonical_bytes(other_config)).hexdigest()
    )
    assert "|final_train|" not in lomo.fit_run_id(first)


def test_default_seeded_initialization_is_fresh_and_reproducible() -> None:
    seed_training(1729)
    first = PerTargetContextDeepSetsMLP("history_only").state_dict()
    seed_training(1729)
    replay = PerTargetContextDeepSetsMLP("history_only").state_dict()
    seed_training(2718)
    other = PerTargetContextDeepSetsMLP("history_only").state_dict()

    assert all(torch.equal(first[key], replay[key]) for key in first)
    assert any(not torch.equal(first[key], other[key]) for key in first)


def _synthetic_score_rows(fits: list[dict[str, object]]) -> list[dict[str, object]]:
    base_ade = {
        "history_only": 3.0,
        "future_ball": 2.5,
        "future_opponent_plus_ball": 2.0,
    }
    seed_shift = {1729: 0.0, 2718: 0.03, 31415: -0.03}
    scores = []
    for fit in fits:
        fold_index = int(str(fit["fold_id"])[-2:])
        ade = (
            base_ade[str(fit["information_regime"])]
            + 0.1 * fold_index
            + seed_shift[int(fit["seed"])]
        )
        scores.append(
            {
                "run_id": fit["run_id"],
                "status": "completed",
                "lomo_fold_id": fit["fold_id"],
                "lomo_held_out_match_id": fit["held_out_match_id"],
                "information_regime": fit["information_regime"],
                "target_representation": fit["target_representation"],
                "seed": fit["seed"],
                "configuration_sha256": fit["configuration_sha256"],
                "metrics": {"ade_m": ade, "fde_m": 2.0 * ade, "xy_rmse_m": ade / 2.0},
            }
        )
    return scores


def test_aggregation_averages_seeds_within_match_then_matches_equally() -> None:
    _, _, _, fits = _fits_and_roles()
    scores = _synthetic_score_rows(fits)

    aggregate = lomo.aggregate_lomo_scores(fits, scores)
    contrasts = lomo.prepare_c1_c2_contrasts(aggregate)

    assert aggregate["status"] == "complete"
    assert len(aggregate["individual_fold_seed_scores"]) == 216
    assert len(aggregate["by_held_out_match_and_cell"]) == 72
    history = aggregate["equal_match_aggregates"]["history_only|absolute_xy"]
    assert history["ade_m"] == pytest.approx(3.65)
    assert contrasts["scope"].startswith("descriptive LOMO only")
    assert [row["contrast_id"] for row in contrasts["contrasts"]] == [
        "C1_ABSOLUTE_XY_FUTURE_BALL",
        "C1_DISPLACEMENT_FUTURE_BALL",
        "C2_ABSOLUTE_XY_FUTURE_OPPONENT",
        "C2_DISPLACEMENT_FUTURE_OPPONENT",
    ]
    assert all(
        row["equal_match_mean_control_minus_context_ade_m"] == pytest.approx(0.5)
        for row in contrasts["contrasts"]
    )
    assert "no significance claim" in contrasts["inference"]


def test_aggregation_retains_missing_and_failed_scores() -> None:
    _, _, _, fits = _fits_and_roles()
    scores = _synthetic_score_rows(fits[:-1])
    failed = _synthetic_score_rows([fits[-1]])[0]
    failed.update(status="failed", failure_reason="synthetic infrastructure interruption")
    scores.append(failed)

    aggregate = lomo.aggregate_lomo_scores(fits, scores)

    assert aggregate["status"] == "incomplete"
    assert aggregate["missing_run_ids"] == []
    assert aggregate["failures"] == [
        {
            "run_id": fits[-1]["run_id"],
            "status": "failed",
            "reason": "synthetic infrastructure interruption",
        }
    ]
    assert aggregate["equal_match_aggregates"] is None


def test_recovered_score_failure_remains_in_complete_report() -> None:
    _, _, _, fits = _fits_and_roles()
    scores = _synthetic_score_rows(fits)
    failure = {
        "run_id": fits[0]["run_id"],
        "status": "failed",
        "failure_reason": "synthetic transient scorer interruption",
    }

    aggregate = lomo.aggregate_lomo_scores(fits, [failure, *scores])

    assert aggregate["status"] == "complete_with_scoring_failures"
    assert aggregate["complete"] is True
    assert aggregate["completed_score_count"] == 216
    assert aggregate["failures"] == [
        {
            "run_id": fits[0]["run_id"],
            "status": "failed",
            "reason": "synthetic transient scorer interruption",
        }
    ]
    assert lomo.prepare_c1_c2_contrasts(aggregate)["status"] == "complete"


def test_compute_budget_requires_capacity_for_the_complete_design() -> None:
    rate = 6.73
    full_fit_ceiling = 216 * 1.25 * rate

    assert (
        lomo.require_compute_unit_budget(
            current_balance=2400,
            current_rate_per_hour=rate,
            spend_cap=2400,
            remaining_work_units=full_fit_ceiling,
        )
        == 0
    )
    with pytest.raises(ValueError, match="fixed campaign cap"):
        lomo.require_compute_unit_budget(
            current_balance=94.31,
            current_rate_per_hour=rate,
            spend_cap=2400,
        )
    with pytest.raises(ValueError, match="remaining fixed campaign cap"):
        lomo.require_compute_unit_budget(
            current_balance=2200,
            current_rate_per_hour=10,
            spend_cap=2400,
            starting_balance=2400,
            remaining_work_units=216 * 1.25 * 10,
        )


def test_checkpoint_freeze_requires_all_234_unique_and_disjoint_identities() -> None:
    _, _, roles, lomo_fits = _fits_and_roles()
    final_fits = trainer._fit_order(roles["training"], roles["validation"])
    final_receipts = []
    for index, fit in enumerate(final_fits):
        config = trainer._per_fit_config(
            cast(trainer.InformationRegime, fit["information_regime"]),
            cast(trainer.TargetRepresentation, fit["target_representation"]),
            int(fit["seed"]),
            roles["training"],
            roles["validation"],
            str(_frozen()[0]["plan_sha256"]),
            str(_frozen()[1]["protocol_sha256"]),
            "cuda",
        )
        final_receipts.append(
            {
                **fit,
                "run_id": trainer._fit_run_id(fit),
                "fit_role": "final_train",
                "status": "completed",
                "checkpoint_sha256": f"{index + 1:064x}",
                "receipt_sha256": f"{index + 100:064x}",
                "plan_sha256": config["plan_sha256"],
                "protocol_sha256": config["protocol_sha256"],
                "population_manifest_sha256": trainer.RESEARCH_MANIFEST_SHA256,
                "configuration_sha256": hashlib.sha256(lomo.canonical_bytes(config)).hexdigest(),
            }
        )
    lomo_receipts = [
        {
            "run_id": fit["run_id"],
            "fit_role": "lomo",
            "status": "completed",
            "checkpoint_sha256": f"{index + 1000:064x}",
            "receipt_sha256": f"{index + 2000:064x}",
            "lomo_fold_id": fit["fold_id"],
            "lomo_held_out_match_id": fit["held_out_match_id"],
            "information_regime": fit["information_regime"],
            "target_representation": fit["target_representation"],
            "seed": fit["seed"],
            "configuration_sha256": fit["configuration_sha256"],
            "train_match_ids": fit["train_match_ids"],
            "validation_match_ids": fit["validation_match_ids"],
            "plan_sha256": fit["plan_sha256"],
            "protocol_sha256": fit["protocol_sha256"],
            "population_manifest_sha256": trainer.RESEARCH_MANIFEST_SHA256,
        }
        for index, fit in enumerate(lomo_fits)
    ]
    matrix = lomo.build_fit_matrix(*_frozen()[:2], roles)

    frozen = lomo.freeze_all_checkpoint_manifests(
        final_receipts,
        lomo_receipts,
        matrix,
        final_run_ids=[trainer._fit_run_id(fit) for fit in final_fits],
    )
    assert frozen["required_fit_count"] == 234
    assert len(frozen["fits"]) == 234

    lomo_receipts[0]["checkpoint_sha256"] = final_receipts[0]["checkpoint_sha256"]
    with pytest.raises(ValueError, match="reuses"):
        lomo.freeze_all_checkpoint_manifests(
            final_receipts,
            lomo_receipts,
            matrix,
            final_run_ids=[trainer._fit_run_id(fit) for fit in final_fits],
        )


def test_real_scoring_authorization_is_a_separate_hard_gate() -> None:
    with pytest.raises(PermissionError, match="separate owner approval"):
        lomo.verify_scoring_authorization(
            {},
            amendment_sha256="a" * 64,
            fit_matrix_sha256="b" * 64,
            checkpoint_manifest_sha256="c" * 64,
        )


def test_real_lomo_campaign_requires_owner_approval_before_writing(tmp_path: Path) -> None:
    output_root = tmp_path / "res340" / "campaign"
    with pytest.raises(PermissionError, match="owner execution approval"):
        trainer.run_campaign(
            tmp_path / "private-research",
            tmp_path / "private-source",
            output_root,
            device="cuda",
            research_scope="training-validation",
            reference_manifest_path=tmp_path / "reference.json",
            fit_role="lomo",
            max_new_fits=1,
            compute_unit_balance=2400.0,
            compute_unit_rate_per_hour=6.73,
        )
    assert not output_root.exists()


def test_incomplete_campaign_is_rejected_before_checkpoint_scoring(tmp_path: Path) -> None:
    plan, protocol, roles = _frozen()
    matrix = lomo.build_fit_matrix(plan, protocol, roles)
    fit_matrix_path = tmp_path / "fit-matrix.json"
    fit_matrix_path.write_bytes(trainer._canonical(matrix))
    campaign = tmp_path / "campaign"
    campaign.mkdir(mode=0o700)
    freeze = {
        "fit_role": "lomo",
        "lomo_fit_matrix_sha256": lomo.matrix_sha256(matrix),
    }
    trainer._atomic_json(campaign / "reproducibility-manifest.json", freeze)
    trainer._atomic_json(
        campaign / "campaign.json",
        {
            "status": "INCOMPLETE",
            "required_fit_count": 216,
            "completed_fit_count": 215,
            "failed_fit_count": 0,
            "frozen_manifest_sha256": trainer._sha256_file(
                campaign / "reproducibility-manifest.json"
            ),
        },
    )

    with pytest.raises(ValueError, match="incomplete LOMO campaigns"):
        score_res340_lomo.score_one(
            campaign_root=campaign,
            fit_matrix_path=fit_matrix_path,
            fit_matrix_sha256=lomo.matrix_sha256(matrix),
            fit_run_id=str(matrix["fits"][0]["run_id"]),
            checkpoint_manifest_path=tmp_path / "checkpoint-manifest.json",
            checkpoint_manifest_sha256="a" * 64,
            scoring_authorization_path=tmp_path / "scoring-authorization.json",
            amendment_sha256="b" * 64,
            output_root=tmp_path / "scores",
        )


def test_synthetic_heldout_score_binds_checkpoint_source_panels_and_masks(
    tmp_path: Path,
) -> None:
    plan, protocol, roles, fits = _fits_and_roles()
    fit = next(
        row
        for row in fits
        if row["information_regime"] == "history_only"
        and row["target_representation"] == "absolute_xy"
    )
    held_out = str(fit["held_out_match_id"])
    cache_root = tmp_path / "private"
    cache_root.mkdir(mode=0o700)
    cache_directory = cache_root / "cache"
    cache_directory.mkdir(mode=0o700)
    sha_window = _hash(b"synthetic ordered origins and windows")
    sha_target = _hash(b"synthetic ordered players, truth, and masks")
    cache_metadata = {
        "schema_id": "fpdbench.res338-feature-cache",
        "schema_version": "1.0.0",
        "match_id": held_out,
        "role": "training",
        "window_count": 1,
        "scoreable_scene_count": 2,
        "pool_size": 2,
        "population_stream_sha256": _hash(b"population"),
        "tracking_sha256": _hash(b"tracking"),
        "window_identity_sha256": sha_window,
        "target_mask_identity_sha256": sha_target,
        "arrays": {},
    }
    cache_bytes = trainer._canonical(cache_metadata)
    (cache_directory / "cache.json").write_bytes(cache_bytes)
    (cache_directory / "cache.json").chmod(0o600)
    cache_receipt = {
        **cache_metadata,
        "cache_metadata_sha256": hashlib.sha256(cache_bytes).hexdigest(),
    }
    target_mask_set_sha256 = _hash(trainer._canonical({held_out: sha_target}))
    arrays: dict[str, np.ndarray] = {
        "target_history": np.zeros((1, 2, 11, 78), dtype=np.float32),
        "history_team_tracks": np.zeros((1, 2, 2, 78), dtype=np.float32),
        "history_team_mask": np.ones((1, 2, 2), dtype=np.bool_),
        "history_ball": np.zeros((1, 78), dtype=np.float32),
        "target_side": np.array([[1.0, -1.0]], dtype=np.float32),
        "target_absolute_xy": np.zeros((1, 2, 11, 15, 2), dtype=np.float64),
        "target_displacement": np.zeros((1, 2, 11, 15, 2), dtype=np.float64),
        "target_mask": np.ones((1, 2, 11, 15), dtype=np.bool_),
        "scoreable": np.ones((1, 2), dtype=np.bool_),
    }
    arrays["target_mask"][0, 1, 1:, :] = False
    cache = trainer.MatchCache(held_out, "training", cache_directory, arrays)
    seed_training(int(fit["seed"]))
    model = PerTargetContextDeepSetsMLP("history_only")
    config = lomo.fit_configuration(
        fit,
        plan_sha256=str(plan["plan_sha256"]),
        protocol_sha256=str(protocol["protocol_sha256"]),
        device="cuda",
    )
    config_sha = hashlib.sha256(lomo.canonical_bytes(config)).hexdigest()
    run_id = lomo.fit_run_id(fit)
    checkpoint_path = cache_root / "checkpoint.pt"
    checkpoint_path.chmod(0o600) if checkpoint_path.exists() else None
    checkpoint_sha = trainer.save_checkpoint_atomically(
        checkpoint_path,
        {
            "metadata": {
                "run_id": run_id,
                "configuration_sha256": config_sha,
                "selected_step": 100,
                "attempt_number": 1,
            },
            "state_dict": model.state_dict(),
        },
    )
    receipt = {
        "status": "completed",
        "fit_role": "lomo",
        "run_id": run_id,
        "lomo_fold_id": fit["fold_id"],
        "lomo_held_out_match_id": held_out,
        "information_regime": fit["information_regime"],
        "target_representation": fit["target_representation"],
        "seed": fit["seed"],
        "train_match_ids": fit["train_match_ids"],
        "validation_match_ids": fit["validation_match_ids"],
        "plan_sha256": plan["plan_sha256"],
        "protocol_sha256": protocol["protocol_sha256"],
        "population_manifest_sha256": trainer.RESEARCH_MANIFEST_SHA256,
        "target_mask_identity_sha256": target_mask_set_sha256,
        "configuration_sha256": config_sha,
        "checkpoint_sha256": checkpoint_sha,
        "attempt_number": 1,
    }

    result = lomo.score_heldout_fold(
        fit,
        receipt,
        checkpoint_path,
        cache,
        cache_receipt=cache_receipt,
        target_mask_set_sha256=target_mask_set_sha256,
    )

    assert result["lomo_held_out_match_id"] == held_out
    assert result["research_population_sha256"] == trainer.RESEARCH_MANIFEST_SHA256
    assert result["origin_window_identity_sha256"] == sha_window
    assert result["ordered_player_panel_truth_and_mask_sha256"] == sha_target
    assert set(result["metrics"]) == {"ade_m", "fde_m", "xy_rmse_m"}
    scored_model = PerTargetContextDeepSetsMLP("history_only")
    scored_model.load_state_dict(
        cast(
            dict[str, torch.Tensor],
            trainer.load_checkpoint_verified(checkpoint_path, checkpoint_sha)["state_dict"],
        )
    )
    scored_model.eval()
    scene_metrics = []
    for lane in range(2):
        payload = trainer._scene_payload(cache, 0, lane, "history_only")
        inputs = trainer._model_inputs_to_device(
            trainer.collate_feature_payloads([payload], "history_only"), torch.device("cpu")
        )
        with torch.inference_mode():
            prediction = scored_model(inputs).cpu().numpy()
        scene_metrics.append(
            trainer.physical_metrics(
                prediction,
                arrays["target_absolute_xy"][0, lane][None, ...],
                arrays["target_mask"][0, lane][None, ...],
            )
        )
    assert result["metrics"]["ade_m"] == pytest.approx(
        math.fsum(value["ade_m"] for value in scene_metrics) / 2
    )
    assert result["metrics"]["fde_m"] == pytest.approx(
        math.fsum(value["fde_m"] for value in scene_metrics) / 2
    )
    assert result["metrics"]["xy_rmse_m"] == pytest.approx(
        math.fsum(value["xy_rmse_m"] for value in scene_metrics) / 2
    )
    evaluation_match = roles["evaluation"][0]
    cache.match_id = evaluation_match
    with pytest.raises(ValueError, match="training-role held-out"):
        lomo.score_heldout_fold(
            fit,
            receipt,
            checkpoint_path,
            cache,
            cache_receipt=cache_receipt,
            target_mask_set_sha256=target_mask_set_sha256,
        )
