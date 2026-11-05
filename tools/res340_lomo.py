"""Frozen RES340 LOMO identities, scoring boundary, and match-level reporting."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import numpy as np
import torch
import train_res338_final_fits as trainer
from numpy.typing import NDArray

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.learned_deepsets import (
    INFORMATION_REGIMES,
    SEEDS,
    TARGET_REPRESENTATIONS,
    InformationRegime,
    PerTargetContextDeepSetsMLP,
    TargetRepresentation,
    collate_feature_payloads,
    physical_metrics,
)

FIT_COUNT = 216
FOLD_COUNT = 12
FINAL_FIT_COUNT = 18
ALL_LEARNED_FIT_COUNT = 234
LOMO_GPU_CAMPAIGN_BUDGET_SECONDS = 270 * 60 * 60
PROPOSED_COMPUTE_UNIT_SPEND_CAP = 2400.0
RES338_CACHE_CHUNK_INDEX_SHA256 = "5d5a55ede46cac65cacd7d052e657493430d16d9dc927b03728453710ae83f8a"
RES338_CACHE_ARCHIVE_INDEX_SHA256 = (
    "5bdf3a6d46ebd974279796146f8ad8a26bb35b66513a1c8e384449385c0354a7"
)
RES338_CACHE_READBACK_SHA256 = "922156ca828eafe54fd2475c6c7b92080d33f881af97bbccdcbcce24cf56e0ea"
RES338_CACHE_MANIFEST_SHA256 = "9554e03de5ca4ab0ef6143ef8320a266dc71af368a2695030f5264d1c68886c2"
RES338_PROGRESS_INDEX_SHA256 = "073a474769f1d22d3bdadeef2353eed30760ad2e5e792083a8384ea94cc7d721"
RES338_REFERENCE_SHA256 = "836827a9603c6408e35d8127b9a508442b46aab7e4858a97454b3cd78499651a"
SHA256 = re.compile(r"[0-9a-f]{64}")


def canonical_bytes(value: object) -> bytes:
    return trainer._canonical(value)


def fit_run_id(fit: Mapping[str, object]) -> str:
    cell = f"{trainer.MODEL_ID}|{fit['information_regime']}|{fit['target_representation']}"
    return f"{cell}|lomo|{fit['fold_id']}|{fit['seed']}"


def lomo_fit_order(
    training_matches: Sequence[str],
    validation_matches: Sequence[str],
    folds: Sequence[Mapping[str, object]],
    evaluation_matches: Sequence[str] = (),
) -> list[dict[str, object]]:
    """Build the plan-ordered 12 × 2 × 3 × 3 schedule, rejecting role leakage."""
    training = list(training_matches)
    validation = list(validation_matches)
    evaluation = set(evaluation_matches)
    if (
        len(training) != FOLD_COUNT
        or len(set(training)) != FOLD_COUNT
        or len(validation) != 4
        or len(set(validation)) != 4
        or evaluation.intersection(training)
        or evaluation.intersection(validation)
        or set(training).intersection(validation)
    ):
        raise ValueError("LOMO requires disjoint frozen 12/4 roles and no evaluation access")
    expected_folds = [
        {"fold_id": f"fold-{index + 1:02d}", "held_out_match": match_id}
        for index, match_id in enumerate(training)
    ]
    if list(folds) != expected_folds:
        raise ValueError("LOMO fold identities differ from the frozen protocol order")

    fits: list[dict[str, object]] = []
    for fold in folds:
        fold_id = cast(str, fold["fold_id"])
        held_out = cast(str, fold["held_out_match"])
        fit_training = [match_id for match_id in training if match_id != held_out]
        if len(fit_training) != 11 or held_out in fit_training:
            raise ValueError("each LOMO fit must exclude exactly its held-out match")
        for representation in TARGET_REPRESENTATIONS:
            for regime in INFORMATION_REGIMES:
                for seed in SEEDS:
                    fit = {
                        "fold_id": fold_id,
                        "held_out_match_id": held_out,
                        "information_regime": regime,
                        "target_representation": representation,
                        "seed": seed,
                        "train_match_ids": fit_training,
                        "validation_match_ids": validation,
                    }
                    fit["run_id"] = fit_run_id(fit)
                    fits.append(fit)
    validate_lomo_fit_order(fits, training, validation, folds)
    return fits


def validate_lomo_fit_order(
    fits: Sequence[Mapping[str, object]],
    training_matches: Sequence[str],
    validation_matches: Sequence[str],
    folds: Sequence[Mapping[str, object]],
) -> None:
    expected_fits = lomo_fit_order_without_validation(training_matches, validation_matches, folds)
    expected_ids = [fit_run_id(fit) for fit in expected_fits]
    actual_ids = [fit_run_id(fit) for fit in fits]
    if len(fits) != FIT_COUNT or len(set(actual_ids)) != FIT_COUNT:
        raise ValueError("the LOMO fit matrix must contain exactly 216 unique fit identities")
    if actual_ids != expected_ids or any(
        fit.get("run_id") != expected_id
        for fit, expected_id in zip(fits, expected_ids, strict=True)
    ):
        raise ValueError("the LOMO fit matrix is missing or reordering frozen fit identities")
    for fit, expected_fit in zip(fits, expected_fits, strict=True):
        if any(fit.get(key) != value for key, value in expected_fit.items()):
            raise ValueError("a LOMO fit definition differs from its frozen fold or cell")
        held_out = str(fit["held_out_match_id"])
        train = list(cast(Sequence[str], fit["train_match_ids"]))
        if len(train) != 11 or held_out in train:
            raise ValueError("a LOMO fit includes its held-out match in optimization")
        if list(cast(Sequence[str], fit["validation_match_ids"])) != list(validation_matches):
            raise ValueError(
                "checkpoint selection must use the exact four frozen validation matches"
            )


def lomo_fit_order_without_validation(
    training_matches: Sequence[str],
    validation_matches: Sequence[str],
    folds: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Internal expected-ID builder used by validation without recursive checks."""
    training = list(training_matches)
    validation = list(validation_matches)
    fits: list[dict[str, object]] = []
    for fold in folds:
        held_out = str(fold["held_out_match"])
        for representation in TARGET_REPRESENTATIONS:
            for regime in INFORMATION_REGIMES:
                for seed in SEEDS:
                    fit = {
                        "fold_id": fold["fold_id"],
                        "held_out_match_id": held_out,
                        "information_regime": regime,
                        "target_representation": representation,
                        "seed": seed,
                        "train_match_ids": [item for item in training if item != held_out],
                        "validation_match_ids": validation,
                    }
                    fit["run_id"] = fit_run_id(fit)
                    fits.append(fit)
    return fits


def fit_configuration(
    fit: Mapping[str, object],
    *,
    plan_sha256: str,
    protocol_sha256: str,
    device: str,
) -> dict[str, object]:
    config = trainer._per_fit_config(
        cast(InformationRegime, fit["information_regime"]),
        cast(TargetRepresentation, fit["target_representation"]),
        int(fit["seed"]),
        cast(Sequence[str], fit["train_match_ids"]),
        cast(Sequence[str], fit["validation_match_ids"]),
        plan_sha256,
        protocol_sha256,
        device,
    )
    config.update(
        fit_role="lomo",
        lomo_fold_id=fit["fold_id"],
        lomo_held_out_match_id=fit["held_out_match_id"],
    )
    return config


def build_fit_matrix(
    plan: Mapping[str, object],
    protocol: Mapping[str, object],
    roles: Mapping[str, Sequence[str]],
) -> dict[str, object]:
    state = cast(dict[str, object], protocol["scientific_state"])
    split = cast(dict[str, object], state["split"])
    folds = cast(list[dict[str, object]], cast(dict[str, object], split["lomo"])["folds"])
    fits = lomo_fit_order(
        roles["training"],
        roles["validation"],
        folds,
        roles.get("evaluation", ()),
    )
    plan_sha256 = str(plan["plan_sha256"])
    protocol_sha256 = str(protocol["protocol_sha256"])
    records = []
    for fit in fits:
        config = fit_configuration(
            fit,
            plan_sha256=plan_sha256,
            protocol_sha256=protocol_sha256,
            device="cuda",
        )
        records.append(
            {
                key: fit[key]
                for key in (
                    "run_id",
                    "fold_id",
                    "held_out_match_id",
                    "information_regime",
                    "target_representation",
                    "seed",
                )
            }
            | {
                "configuration_sha256": hashlib.sha256(canonical_bytes(config)).hexdigest(),
            }
        )
    return {
        "schema_id": "fpdbench.res340.lomo-fit-matrix",
        "schema_version": "1.0.0",
        "status": "FROZEN_PROSPECTIVE_PENDING_OWNER_APPROVAL",
        "model_id": trainer.MODEL_ID,
        "plan_sha256": plan_sha256,
        "protocol_sha256": protocol_sha256,
        "research_population_sha256": trainer.RESEARCH_MANIFEST_SHA256,
        "factorization": {
            "fold_count": FOLD_COUNT,
            "information_regimes": list(INFORMATION_REGIMES),
            "target_representations": list(TARGET_REPRESENTATIONS),
            "seeds": list(SEEDS),
            "fit_count": FIT_COUNT,
            "order": "protocol fold, target representation, information regime, seed",
        },
        "training_match_ids": list(roles["training"]),
        "validation_match_ids": list(roles["validation"]),
        "folds": [
            {
                "fold_id": fold["fold_id"],
                "held_out_match_id": fold["held_out_match"],
                "train_match_ids": [
                    match_id for match_id in roles["training"] if match_id != fold["held_out_match"]
                ],
            }
            for fold in folds
        ],
        "fit_count": len(records),
        "fits": records,
    }


def expand_fit_matrix(matrix: Mapping[str, object]) -> list[dict[str, object]]:
    """Expand the compact, reviewed matrix into its per-fit role memberships."""
    training = cast(list[str], matrix["training_match_ids"])
    validation = cast(list[str], matrix["validation_match_ids"])
    folds = cast(list[dict[str, object]], matrix["folds"])
    fold_by_id = {str(fold["fold_id"]): fold for fold in folds}
    rows = cast(list[dict[str, object]], matrix["fits"])
    if len(fold_by_id) != FOLD_COUNT or len(rows) != FIT_COUNT:
        raise ValueError("the frozen LOMO matrix has missing folds or fit identities")
    fits = []
    for row in rows:
        fold_id = str(row["fold_id"])
        fold = fold_by_id.get(fold_id)
        if fold is None or row.get("held_out_match_id") != fold.get("held_out_match_id"):
            raise ValueError("a fit identity does not bind its frozen held-out match")
        fit = {
            "run_id": row["run_id"],
            "fold_id": fold_id,
            "held_out_match_id": fold["held_out_match_id"],
            "information_regime": row["information_regime"],
            "target_representation": row["target_representation"],
            "seed": row["seed"],
            "train_match_ids": fold["train_match_ids"],
            "validation_match_ids": validation,
            "configuration_sha256": row["configuration_sha256"],
        }
        if row.get("run_id") != fit_run_id(fit):
            raise ValueError(
                "a frozen fit ID differs from its expanded fold/configuration identity"
            )
        config = fit_configuration(
            fit,
            plan_sha256=str(matrix["plan_sha256"]),
            protocol_sha256=str(matrix["protocol_sha256"]),
            device="cuda",
        )
        if hashlib.sha256(canonical_bytes(config)).hexdigest() != row["configuration_sha256"]:
            raise ValueError("a frozen fit configuration hash differs from its fold membership")
        fits.append(fit)
    protocol_folds = [
        {"fold_id": fold["fold_id"], "held_out_match": fold["held_out_match_id"]} for fold in folds
    ]
    validate_lomo_fit_order(fits, training, validation, protocol_folds)
    for fit in fits:
        fit["plan_sha256"] = matrix["plan_sha256"]
        fit["protocol_sha256"] = matrix["protocol_sha256"]
        fit["population_manifest_sha256"] = matrix["research_population_sha256"]
    return fits


def matrix_sha256(matrix: Mapping[str, object]) -> str:
    return hashlib.sha256(canonical_bytes(matrix)).hexdigest()


def cache_view_for_fit(
    cache_by_match: Mapping[str, trainer.MatchCache], fit: Mapping[str, object]
) -> dict[str, trainer.MatchCache]:
    held_out = str(fit["held_out_match_id"])
    train = list(cast(Sequence[str], fit["train_match_ids"]))
    validation = list(cast(Sequence[str], fit["validation_match_ids"]))
    if len(train) != 11 or held_out in train or held_out in validation:
        raise ValueError("LOMO cache view must exclude the held-out match")
    required = set(train) | set(validation)
    if not required.issubset(cache_by_match):
        raise ValueError("LOMO fit is missing a training or validation feature cache")
    if any(cache.role not in {"training", "validation"} for cache in cache_by_match.values()):
        raise ValueError("evaluation-role caches are outside the LOMO training runtime")
    view = {match_id: cache_by_match[match_id] for match_id in sorted(required)}
    if held_out in view:
        raise ValueError("held-out features or truth reached the optimization worker")
    return view


def verify_execution_approval(
    approval: Mapping[str, object],
    *,
    amendment_sha256: str,
    private_cloud_amendment_sha256: str,
    fit_matrix_sha256: str,
    cache_manifest_sha256: str,
    cache_ledger_sha256: str,
    code_sha: str,
    compute_unit_spend_cap: float,
) -> None:
    approved_start_balance = approval.get("compute_unit_balance_at_start")
    approved_a100_rate = approval.get("a100_compute_unit_rate_per_hour")
    if (
        approval.get("schema_id") != "fpdbench.res340.lomo-execution-authorization"
        or approval.get("status") != "OWNER_APPROVED"
        or approval.get("scope") != "RES340_RESEARCH_ONLY_216_FIT_LOMO"
        or approval.get("plan_sha256")
        != "a59fee6ee8e9fb03f4f0ccdae1933458af2bbf2375db7e6cd2bdf10962e42b62"
        or approval.get("protocol_sha256")
        != "3d7bdc46300b966a4da274579d21ac4c8219e1ef897719d6b7a308596e9f1d9f"
        or approval.get("research_population_sha256") != trainer.RESEARCH_MANIFEST_SHA256
        or approval.get("gpu_amendment_sha256") != amendment_sha256
        or approval.get("private_cloud_amendment_sha256") != private_cloud_amendment_sha256
        or approval.get("fit_matrix_sha256") != fit_matrix_sha256
        or approval.get("cache_manifest_sha256") != cache_manifest_sha256
        or approval.get("cache_ledger_sha256") != cache_ledger_sha256
        or cache_manifest_sha256 != RES338_CACHE_MANIFEST_SHA256
        or cache_ledger_sha256 != RES338_PROGRESS_INDEX_SHA256
        or approval.get("training_validation_reference_sha256") != RES338_REFERENCE_SHA256
        or approval.get("cache_chunk_index_sha256") != RES338_CACHE_CHUNK_INDEX_SHA256
        or approval.get("cache_archive_index_sha256") != RES338_CACHE_ARCHIVE_INDEX_SHA256
        or approval.get("cache_drive_readback_sha256") != RES338_CACHE_READBACK_SHA256
        or approval.get("code_sha") != code_sha
        or approval.get("compute_unit_spend_cap") != compute_unit_spend_cap
        or isinstance(approved_start_balance, bool)
        or not isinstance(approved_start_balance, int | float)
        or not math.isfinite(float(approved_start_balance))
        or float(approved_start_balance) < compute_unit_spend_cap
        or isinstance(approved_a100_rate, bool)
        or not isinstance(approved_a100_rate, int | float)
        or not math.isfinite(float(approved_a100_rate))
        or float(approved_a100_rate) <= 0
        or approval.get("evaluation_role_access") is not False
        or approval.get("heldout_scoring") is not False
        or approval.get("owner_only_drive_root_shared") is not False
        or not approval.get("owner_only_drive_root_id")
    ):
        raise PermissionError("RES340 fit authorization is missing or differs from this freeze")


def require_compute_unit_budget(
    *,
    current_balance: float,
    current_rate_per_hour: float,
    spend_cap: float,
    starting_balance: float | None = None,
    remaining_work_units: float = 0.0,
) -> float:
    """Fail before the first fit unless the full fixed campaign cap is available."""
    values = (current_balance, current_rate_per_hour, spend_cap, remaining_work_units)
    if (
        any(not math.isfinite(value) for value in values)
        or min(current_balance, current_rate_per_hour, spend_cap) <= 0
        or remaining_work_units < 0
    ):
        raise ValueError("live Colab balance, rate, and approved cap must be finite and positive")
    if spend_cap < PROPOSED_COMPUTE_UNIT_SPEND_CAP:
        raise ValueError("the complete 216-fit design does not fit below the proposed cap")
    start = current_balance if starting_balance is None else starting_balance
    if not math.isfinite(start) or start < spend_cap:
        raise ValueError("available compute units were below the fixed campaign cap at start")
    spent = start - current_balance
    if (
        spent < 0
        or spent > spend_cap
        or current_balance < spend_cap - spent
        or current_balance < remaining_work_units
        or spent + remaining_work_units > spend_cap
    ):
        raise ValueError("live compute units cannot cover the remaining fixed campaign cap")
    return spent


def verify_scoring_authorization(
    approval: Mapping[str, object],
    *,
    amendment_sha256: str,
    fit_matrix_sha256: str,
    checkpoint_manifest_sha256: str,
) -> None:
    if (
        approval.get("schema_id") != "fpdbench.res340.lomo-scoring-authorization"
        or approval.get("status") != "OWNER_APPROVED"
        or approval.get("scope") != "RES340_RESEARCH_ONLY_LOMO_HELDOUT_SCORING"
        or approval.get("gpu_amendment_sha256") != amendment_sha256
        or approval.get("fit_matrix_sha256") != fit_matrix_sha256
        or approval.get("checkpoint_manifest_sha256") != checkpoint_manifest_sha256
        or approval.get("plan_sha256")
        != "a59fee6ee8e9fb03f4f0ccdae1933458af2bbf2375db7e6cd2bdf10962e42b62"
        or approval.get("protocol_sha256")
        != "3d7bdc46300b966a4da274579d21ac4c8219e1ef897719d6b7a308596e9f1d9f"
        or approval.get("research_population_sha256") != trainer.RESEARCH_MANIFEST_SHA256
        or approval.get("scoring_roles") != ["lomo_held_out_training_match"]
        or approval.get("evaluation_role_access") is not False
        or approval.get("owner_only_drive_root_shared") is not False
        or not approval.get("owner_only_drive_root_id")
    ):
        raise PermissionError("real LOMO scoring needs its separate owner approval")


def res338_final_checkpoint_hashes(
    progress_index: Mapping[str, object],
    *,
    reference_sha256: str,
) -> list[str]:
    """Require the verified completed 18-fit RES338 progress index as the predecessor."""
    plan, protocol, roles = trainer._frozen_split_and_authorities()
    expected = trainer._fit_order(roles["training"], roles["validation"])
    fits = cast(list[dict[str, object]], progress_index.get("fits", []))
    by_id = {str(fit.get("run_id")): fit for fit in fits}
    expected_ids = [trainer._fit_run_id(fit) for fit in expected]
    status_counts = {
        status: sum(fit.get("status") == status for fit in fits)
        for status in {str(fit.get("status")) for fit in fits}
    }
    if (
        progress_index.get("schema_id") != "fpdbench.res338.colab-progress"
        or progress_index.get("required_fit_count") != FINAL_FIT_COUNT
        or progress_index.get("completed_fit_count") != FINAL_FIT_COUNT
        or progress_index.get("parent_research_manifest_sha256") != trainer.RESEARCH_MANIFEST_SHA256
        or progress_index.get("plan_sha256") != plan["plan_sha256"]
        or progress_index.get("protocol_sha256") != protocol["protocol_sha256"]
        or progress_index.get("research_reference_sha256") != reference_sha256
        or len(fits) != FINAL_FIT_COUNT
        or len(by_id) != FINAL_FIT_COUNT
        or list(by_id) != expected_ids
        or status_counts != {"COMPLETED_AND_VERIFIED": FINAL_FIT_COUNT}
    ):
        raise ValueError("the RES338 predecessor must be the exact verified 18-fit progress index")

    hashes = []
    for fit in fits:
        config = trainer._per_fit_config(
            cast(InformationRegime, fit["information_regime"]),
            cast(TargetRepresentation, fit["target_representation"]),
            int(fit["seed"]),
            roles["training"],
            roles["validation"],
            str(plan["plan_sha256"]),
            str(protocol["protocol_sha256"]),
            "cuda",
        )
        attempts = cast(list[dict[str, object]], fit.get("attempts", []))
        completed = next(
            (
                attempt
                for attempt in reversed(attempts)
                if attempt.get("status") == "COMPLETED_AND_VERIFIED"
            ),
            None,
        )
        if (
            hashlib.sha256(canonical_bytes(config)).hexdigest() != fit.get("configuration_sha256")
            or completed is None
            or completed.get("readback_verified") is not True
            or not completed.get("checkpoint_drive_file_id")
            or not completed.get("receipt_drive_file_id")
            or SHA256.fullmatch(str(completed.get("checkpoint_sha256", ""))) is None
            or SHA256.fullmatch(str(completed.get("receipt_sha256", ""))) is None
        ):
            raise ValueError("a RES338 final checkpoint lacks its verified receipt/readback")
        hashes.append(str(completed["checkpoint_sha256"]))
    if len(set(hashes)) != FINAL_FIT_COUNT:
        raise ValueError("the 18 frozen final checkpoint identities are not unique")
    return hashes


def freeze_all_checkpoint_manifests(
    final_receipts: Sequence[Mapping[str, object]],
    lomo_receipts: Sequence[Mapping[str, object]],
    fit_matrix: Mapping[str, object],
    *,
    final_run_ids: Sequence[str],
) -> dict[str, object]:
    expected_lomo = {
        str(fit["run_id"]) for fit in cast(list[dict[str, object]], fit_matrix["fits"])
    }
    expected_lomo_fits = {str(fit["run_id"]): fit for fit in expand_fit_matrix(fit_matrix)}
    final_by_id = {str(item.get("run_id")): item for item in final_receipts}
    lomo_by_id = {str(item.get("run_id")): item for item in lomo_receipts}
    if (
        len(final_by_id) != FINAL_FIT_COUNT
        or set(final_by_id) != set(final_run_ids)
        or set(lomo_by_id) != expected_lomo
        or len(lomo_by_id) != FIT_COUNT
    ):
        raise ValueError("all 18 final and 216 LOMO fit receipts are required before scoring")
    for receipt in (*final_by_id.values(), *lomo_by_id.values()):
        if (
            receipt.get("status") != "completed"
            or SHA256.fullmatch(str(receipt.get("checkpoint_sha256", ""))) is None
            or SHA256.fullmatch(str(receipt.get("receipt_sha256", ""))) is None
        ):
            raise ValueError("checkpoint freeze requires completed receipts with valid hashes")
    if any(item.get("fit_role") != "final_train" for item in final_by_id.values()) or any(
        item.get("fit_role") != "lomo" for item in lomo_by_id.values()
    ):
        raise ValueError("checkpoint manifest fit roles differ from the 18/216 plan")
    plan, protocol, roles = trainer._frozen_split_and_authorities()
    expected_final_fits = {
        trainer._fit_run_id(fit): fit
        for fit in trainer._fit_order(roles["training"], roles["validation"])
    }
    for run_id, receipt in final_by_id.items():
        fit = expected_final_fits[run_id]
        config = trainer._per_fit_config(
            cast(InformationRegime, fit["information_regime"]),
            cast(TargetRepresentation, fit["target_representation"]),
            int(fit["seed"]),
            roles["training"],
            roles["validation"],
            str(plan["plan_sha256"]),
            str(protocol["protocol_sha256"]),
            "cuda",
        )
        if (
            receipt.get("information_regime") != fit["information_regime"]
            or receipt.get("target_representation") != fit["target_representation"]
            or receipt.get("seed") != fit["seed"]
            or receipt.get("train_match_ids") != roles["training"]
            or receipt.get("validation_match_ids") != roles["validation"]
            or receipt.get("plan_sha256") != plan["plan_sha256"]
            or receipt.get("protocol_sha256") != protocol["protocol_sha256"]
            or receipt.get("population_manifest_sha256") != trainer.RESEARCH_MANIFEST_SHA256
            or receipt.get("configuration_sha256")
            != hashlib.sha256(canonical_bytes(config)).hexdigest()
        ):
            raise ValueError("final checkpoint receipt differs from the frozen 18-fit contract")
    for run_id, receipt in lomo_by_id.items():
        fit = expected_lomo_fits[run_id]
        if any(
            receipt.get(receipt_key) != fit.get(fit_key)
            for receipt_key, fit_key in (
                ("lomo_fold_id", "fold_id"),
                ("lomo_held_out_match_id", "held_out_match_id"),
                ("information_regime", "information_regime"),
                ("target_representation", "target_representation"),
                ("seed", "seed"),
                ("configuration_sha256", "configuration_sha256"),
                ("train_match_ids", "train_match_ids"),
                ("validation_match_ids", "validation_match_ids"),
                ("plan_sha256", "plan_sha256"),
                ("protocol_sha256", "protocol_sha256"),
            )
        ):
            raise ValueError("LOMO receipt differs from its frozen fit matrix identity")
    final_hashes = {str(item["checkpoint_sha256"]) for item in final_by_id.values()}
    lomo_hashes = {str(item["checkpoint_sha256"]) for item in lomo_by_id.values()}
    if len(final_hashes) != FINAL_FIT_COUNT or len(lomo_hashes) != FIT_COUNT:
        raise ValueError("each frozen learned fit needs a distinct checkpoint identity")
    if final_hashes.intersection(lomo_hashes):
        raise ValueError("a LOMO checkpoint reuses a frozen final-fit checkpoint identity")
    ordered = [final_by_id[run_id] for run_id in final_run_ids] + [
        lomo_by_id[str(fit["run_id"])] for fit in cast(list[dict[str, object]], fit_matrix["fits"])
    ]
    return {
        "schema_id": "fpdbench.res340.learned-checkpoint-manifest",
        "schema_version": "1.0.0",
        "status": "FROZEN_PENDING_SEPARATE_SCORING_AUTHORIZATION",
        "required_fit_count": ALL_LEARNED_FIT_COUNT,
        "final_fit_count": FINAL_FIT_COUNT,
        "lomo_fit_count": FIT_COUNT,
        "plan_sha256": fit_matrix["plan_sha256"],
        "protocol_sha256": fit_matrix["protocol_sha256"],
        "fit_matrix_sha256": matrix_sha256(fit_matrix),
        "fits": [
            {
                "run_id": item["run_id"],
                "fit_role": item["fit_role"],
                "checkpoint_sha256": item["checkpoint_sha256"],
                "receipt_sha256": item.get("receipt_sha256"),
            }
            for item in ordered
        ],
    }


def score_heldout_fold(
    fit: Mapping[str, object],
    receipt: Mapping[str, object],
    checkpoint_path: Path,
    cache: trainer.MatchCache,
    *,
    cache_receipt: Mapping[str, object],
    target_mask_set_sha256: str,
    final_checkpoint_sha256s: Sequence[str] = (),
) -> dict[str, object]:
    """Score one held-out training match after a separate scoring gate is checked."""
    run_id = fit_run_id(fit)
    held_out = str(fit["held_out_match_id"])
    plan, protocol, roles = trainer._frozen_split_and_authorities()
    scientific_state = cast(dict[str, object], protocol["scientific_state"])
    split = cast(dict[str, object], scientific_state["split"])
    lomo = cast(dict[str, object], split["lomo"])
    fold_assignments = cast(list[dict[str, object]], lomo["folds"])
    fold = next((item for item in fold_assignments if item["fold_id"] == fit["fold_id"]), None)
    if (
        fold is None
        or fold.get("held_out_match") != held_out
        or held_out not in roles["training"]
        or receipt.get("status") != "completed"
        or receipt.get("fit_role") != "lomo"
        or receipt.get("run_id") != run_id
        or receipt.get("lomo_fold_id") != fit["fold_id"]
        or receipt.get("lomo_held_out_match_id") != held_out
        or receipt.get("target_representation") != fit["target_representation"]
        or receipt.get("information_regime") != fit["information_regime"]
        or receipt.get("seed") != fit["seed"]
        or receipt.get("configuration_sha256") != fit.get("configuration_sha256")
        or receipt.get("plan_sha256") != plan["plan_sha256"]
        or receipt.get("protocol_sha256") != protocol["protocol_sha256"]
        or receipt.get("population_manifest_sha256") != trainer.RESEARCH_MANIFEST_SHA256
        or receipt.get("train_match_ids") != fit["train_match_ids"]
        or receipt.get("validation_match_ids") != fit["validation_match_ids"]
    ):
        raise ValueError("fit receipt does not bind the requested LOMO held-out match")
    if (
        cache.match_id != held_out
        or cache.role != "training"
        or held_out in cast(Sequence[str], fit["train_match_ids"])
        or held_out in cast(Sequence[str], fit["validation_match_ids"])
    ):
        raise ValueError("LOMO scoring cache must be exactly the training-role held-out match")
    if str(receipt["checkpoint_sha256"]) in set(final_checkpoint_sha256s):
        raise ValueError("LOMO scoring cannot use a final-role checkpoint")
    if cache_receipt.get("match_id") != held_out or cache_receipt.get("role") != "training":
        raise ValueError("held-out cache identity differs from the fold-scoped training source")
    if receipt.get("target_mask_identity_sha256") != target_mask_set_sha256:
        raise ValueError("fit receipt differs from the frozen 16-cache target/mask set")
    cache_metadata_sha256 = str(cache_receipt.get("cache_metadata_sha256", ""))
    if SHA256.fullmatch(cache_metadata_sha256) is None:
        raise ValueError("held-out cache metadata needs its frozen SHA-256")
    metadata = trainer._read_private_json(cache.directory / "cache.json")
    if trainer._sha256_file(
        cache.directory / "cache.json"
    ) != cache_metadata_sha256 or metadata != {
        key: value for key, value in cache_receipt.items() if key != "cache_metadata_sha256"
    }:
        raise ValueError("held-out cache differs from its frozen source identity")

    checkpoint_sha256 = str(receipt["checkpoint_sha256"])
    loaded = trainer.load_checkpoint_verified(checkpoint_path, checkpoint_sha256)
    expected_config = str(receipt["configuration_sha256"])
    checkpoint_metadata = cast(dict[str, object], loaded["metadata"])
    if (
        checkpoint_metadata.get("run_id") != run_id
        or checkpoint_metadata.get("configuration_sha256") != expected_config
        or checkpoint_metadata.get("attempt_number") != receipt.get("attempt_number")
    ):
        raise ValueError("LOMO checkpoint identity differs from its selected fit receipt")
    regime = cast(InformationRegime, fit["information_regime"])
    representation = cast(TargetRepresentation, fit["target_representation"])
    model = PerTargetContextDeepSetsMLP(regime)
    model.load_state_dict(cast(dict[str, torch.Tensor], loaded["state_dict"]), strict=True)
    model.eval()
    selected = np.argwhere(cast(NDArray[np.bool_], cache.arrays["scoreable"]))
    if not len(selected):
        raise ValueError("held-out match has no scoreable scenes")
    prediction = np.empty((len(selected), 11, 15, 2), dtype=np.float32)
    for start in range(0, len(selected), trainer.BATCH_SIZE):
        batch_ids = selected[start : start + trainer.BATCH_SIZE]
        payloads = [
            trainer._scene_payload(cache, int(window), int(lane), regime)
            for window, lane in batch_ids
        ]
        inputs = trainer._model_inputs_to_device(
            collate_feature_payloads(payloads, regime), torch.device("cpu")
        )
        with torch.inference_mode():
            batch_prediction = model(inputs).cpu().numpy()
        if not np.isfinite(batch_prediction).all():
            raise FloatingPointError("held-out scoring produced a non-finite prediction")
        prediction[start : start + len(batch_ids)] = batch_prediction
    panel = "target_absolute_xy" if representation == "absolute_xy" else "target_displacement"
    truth = np.stack([cache.arrays[panel][int(window), int(lane)] for window, lane in selected])
    mask = np.stack(
        [cache.arrays["target_mask"][int(window), int(lane)] for window, lane in selected]
    )
    scoreable = cast(NDArray[np.bool_], cache.arrays["scoreable"])
    if np.any(~scoreable.any(axis=1)):
        raise ValueError("cache retained a window with no scoreable directed scene")
    per_window: list[dict[str, float]] = []
    scene_position = 0
    scored_points = final_targets = 0
    for window_index in range(scoreable.shape[0]):
        scene_metrics: list[dict[str, float]] = []
        for lane in range(2):
            if not scoreable[window_index, lane]:
                continue
            scene = physical_metrics(
                prediction[scene_position : scene_position + 1],
                truth[scene_position : scene_position + 1],
                mask[scene_position : scene_position + 1],
            )
            scene_position += 1
            scored_points += int(scene["scored_points"])
            final_targets += int(scene["final_targets"])
            scene_metrics.append(scene)
        if scene_metrics:
            per_window.append(
                {
                    metric: math.fsum(value[metric] for value in scene_metrics) / len(scene_metrics)
                    for metric in ("ade_m", "fde_m", "xy_rmse_m")
                }
            )
    if (
        scene_position != len(selected)
        or len(per_window) != int(metadata["window_count"])
        or len(selected) != int(metadata["scoreable_scene_count"])
    ):
        raise ValueError("held-out scoreable scene/window counts differ from the frozen cache")
    metrics = {
        metric: math.fsum(value[metric] for value in per_window) / len(per_window)
        for metric in ("ade_m", "fde_m", "xy_rmse_m")
    }
    population_authority = cast(dict[str, object], plan["population_authority"])
    return {
        "schema_id": "fpdbench.res340.lomo-heldout-score",
        "schema_version": "1.0.0",
        "status": "completed",
        "run_id": run_id,
        "fit_role": "lomo",
        "lomo_fold_id": fit["fold_id"],
        "lomo_held_out_match_id": held_out,
        "model_id": trainer.MODEL_ID,
        "information_regime": regime,
        "target_representation": representation,
        "seed": fit["seed"],
        "plan_sha256": receipt["plan_sha256"],
        "protocol_sha256": receipt["protocol_sha256"],
        "research_population_sha256": receipt["population_manifest_sha256"],
        "source_release_hash": population_authority["source_release_hash"],
        "source_population_hash": population_authority["source_population_hash"],
        "source_cache_metadata_sha256": cache_metadata_sha256,
        "training_validation_target_mask_set_sha256": target_mask_set_sha256,
        "origin_window_identity_sha256": metadata["window_identity_sha256"],
        "ordered_player_panel_truth_and_mask_sha256": metadata["target_mask_identity_sha256"],
        "scoreable_window_count": len(per_window),
        "scoreable_scene_count": len(selected),
        "metric_aggregation": (
            "physical metrics within directed scene; equal scoreable scenes within window; "
            "equal scoreable windows within held-out match"
        ),
        "checkpoint_sha256": checkpoint_sha256,
        "configuration_sha256": expected_config,
        "metrics": metrics,
        "scored_points": scored_points,
        "final_targets": final_targets,
    }


def aggregate_lomo_scores(
    fits: Sequence[Mapping[str, object]], scores: Sequence[Mapping[str, object]]
) -> dict[str, object]:
    """Average seeds within each match, then average the 12 matches equally."""
    expected = {str(fit.get("run_id", fit_run_id(fit))): fit for fit in fits}
    by_id: dict[str, list[Mapping[str, object]]] = {}
    for score in scores:
        by_id.setdefault(str(score.get("run_id", "")), []).append(score)
    if len(expected) != FIT_COUNT:
        raise ValueError("scientific aggregation requires the exact frozen 216-fit matrix")
    missing = sorted(set(expected).difference(by_id))
    unexpected = sorted(set(by_id).difference(expected))
    failures: list[dict[str, object]] = []
    successful: list[dict[str, object]] = []
    unscored: list[str] = []
    for run_id, attempts in by_id.items():
        if run_id not in expected:
            continue
        fit = expected[run_id]
        valid_attempts: list[Mapping[str, object]] = []
        for score in attempts:
            if score.get("status") != "completed":
                failures.append(
                    {
                        "run_id": run_id,
                        "status": score.get("status"),
                        "reason": score.get("failure_reason"),
                    }
                )
                continue
            if (
                score.get("lomo_fold_id") != fit.get("fold_id")
                or score.get("lomo_held_out_match_id") != fit.get("held_out_match_id")
                or score.get("information_regime") != fit.get("information_regime")
                or score.get("target_representation") != fit.get("target_representation")
                or score.get("seed") != fit.get("seed")
                or score.get("configuration_sha256") != fit.get("configuration_sha256")
            ):
                failures.append(
                    {"run_id": run_id, "status": "invalid", "reason": "score identity mismatch"}
                )
                continue
            metrics = cast(dict[str, object], score.get("metrics", {}))
            values = [metrics.get(name) for name in ("ade_m", "fde_m", "xy_rmse_m")]
            if any(
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not math.isfinite(float(value))
                for value in values
            ):
                failures.append(
                    {"run_id": run_id, "status": "invalid", "reason": "invalid metrics"}
                )
                continue
            valid_attempts.append(score)
        if not valid_attempts:
            unscored.append(run_id)
            continue
        fingerprints = {
            canonical_bytes(
                {
                    key: score.get(key)
                    for key in (
                        "lomo_fold_id",
                        "lomo_held_out_match_id",
                        "information_regime",
                        "target_representation",
                        "seed",
                        "configuration_sha256",
                        "checkpoint_sha256",
                        "metrics",
                    )
                }
            )
            for score in valid_attempts
        }
        if len(fingerprints) != 1:
            failures.append(
                {
                    "run_id": run_id,
                    "status": "conflicting",
                    "reason": "repeated completed scores differ",
                }
            )
            unscored.append(run_id)
            continue
        successful.append({**valid_attempts[0], "run_id": run_id})
    complete = not missing and not unexpected and not unscored and len(successful) == FIT_COUNT
    result: dict[str, object] = {
        "schema_id": "fpdbench.res340.lomo-match-aggregate",
        "schema_version": "1.0.0",
        "status": (
            "complete_with_scoring_failures"
            if complete and failures
            else "complete"
            if complete
            else "incomplete"
        ),
        "complete": complete,
        "primary_experimental_unit": "held_out_match",
        "required_fit_count": FIT_COUNT,
        "completed_score_count": len(successful),
        "missing_run_ids": missing,
        "unexpected_run_ids": unexpected,
        "unscored_run_ids": sorted(set(unscored)),
        "scoring_attempt_count": len(scores),
        "failures": failures,
        "individual_fold_seed_scores": [
            {
                "run_id": row["run_id"],
                "fold_id": row.get("fold_id", row.get("lomo_fold_id")),
                "held_out_match_id": row.get(
                    "held_out_match_id", row.get("lomo_held_out_match_id")
                ),
                "information_regime": row["information_regime"],
                "target_representation": row["target_representation"],
                "seed": row["seed"],
                "metrics": row["metrics"],
            }
            for row in successful
        ],
        "by_held_out_match_and_cell": [],
        "equal_match_aggregates": None,
    }
    if not complete:
        return result

    grouped: dict[tuple[str, str, str, str], list[dict[str, object]]] = {}
    for row in successful:
        key = (
            str(row.get("fold_id", row.get("lomo_fold_id"))),
            str(row.get("held_out_match_id", row.get("lomo_held_out_match_id"))),
            str(row["information_regime"]),
            str(row["target_representation"]),
        )
        grouped.setdefault(key, []).append(row)
    expected_cells = FOLD_COUNT * len(INFORMATION_REGIMES) * len(TARGET_REPRESENTATIONS)
    if len(grouped) != expected_cells or any(len(rows) != len(SEEDS) for rows in grouped.values()):
        result["status"] = "incomplete"
        result["failures"] = failures + [
            {"status": "invalid", "reason": "every held-out match and cell needs three seeds"}
        ]
        return result

    fold_cells = []
    by_cell: dict[tuple[str, str], list[dict[str, float]]] = {}
    for (fold_id, match_id, regime, representation), rows in sorted(grouped.items()):
        row_scores = [cast(dict[str, object], row["metrics"]) for row in rows]
        mean_metrics = {
            metric: math.fsum(float(value[metric]) for value in row_scores) / len(row_scores)
            for metric in ("ade_m", "fde_m", "xy_rmse_m")
        }
        cell = {
            "fold_id": fold_id,
            "held_out_match_id": match_id,
            "information_regime": regime,
            "target_representation": representation,
            "seed_run_ids": [
                str(row["run_id"]) for row in sorted(rows, key=lambda r: int(r["seed"]))
            ],
            "seed_metrics": [row["metrics"] for row in sorted(rows, key=lambda r: int(r["seed"]))],
            "mean_of_three_seed_metrics": mean_metrics,
        }
        fold_cells.append(cell)
        by_cell.setdefault((regime, representation), []).append(mean_metrics)
    equal_match = {
        f"{regime}|{representation}": {
            metric: math.fsum(value[metric] for value in values) / FOLD_COUNT
            for metric in ("ade_m", "fde_m", "xy_rmse_m")
        }
        for (regime, representation), values in sorted(by_cell.items())
    }
    result["by_held_out_match_and_cell"] = fold_cells
    result["equal_match_aggregates"] = equal_match
    result["inference"] = "descriptive only; overlapping windows and folds are not iid"
    return result


def prepare_c1_c2_contrasts(aggregate: Mapping[str, object]) -> dict[str, object]:
    """Prepare the four preregistered matched ADE contrasts as LOMO descriptives."""
    if aggregate.get("complete") is not True:
        return {
            "status": "incomplete",
            "scope": (
                "descriptive LOMO only; primary C1/C2 evaluation remains four evaluation matches"
            ),
            "contrasts": [],
        }
    cells = cast(list[dict[str, object]], aggregate["by_held_out_match_and_cell"])
    lookup = {
        (
            str(row["held_out_match_id"]),
            str(row["information_regime"]),
            str(row["target_representation"]),
        ): cast(dict[str, float], row["mean_of_three_seed_metrics"])
        for row in cells
    }
    definitions = (
        ("C1_ABSOLUTE_XY_FUTURE_BALL", "absolute_xy", "history_only", "future_ball"),
        (
            "C1_DISPLACEMENT_FUTURE_BALL",
            "origin_relative_displacement",
            "history_only",
            "future_ball",
        ),
        (
            "C2_ABSOLUTE_XY_FUTURE_OPPONENT",
            "absolute_xy",
            "future_ball",
            "future_opponent_plus_ball",
        ),
        (
            "C2_DISPLACEMENT_FUTURE_OPPONENT",
            "origin_relative_displacement",
            "future_ball",
            "future_opponent_plus_ball",
        ),
    )
    output = []
    match_ids = sorted({match for match, _, _ in lookup})
    for contrast_id, representation, control, context in definitions:
        matches = []
        for match_id in match_ids:
            left = lookup[(match_id, control, representation)]["ade_m"]
            right = lookup[(match_id, context, representation)]["ade_m"]
            matches.append(
                {
                    "held_out_match_id": match_id,
                    "control_ade_m": left,
                    "context_ade_m": right,
                    "control_minus_context_ade_m": left - right,
                }
            )
        output.append(
            {
                "contrast_id": contrast_id,
                "target_representation": representation,
                "control_regime": control,
                "context_regime": context,
                "direction": "control ADE minus context ADE",
                "match_count": len(matches),
                "equal_match_mean_control_minus_context_ade_m": math.fsum(
                    float(row["control_minus_context_ade_m"]) for row in matches
                )
                / len(matches),
                "match_values": matches,
            }
        )
    return {
        "status": "complete",
        "scope": "descriptive LOMO only; primary C1/C2 evaluation remains four evaluation matches",
        "inference": "no significance claim; held-out matches, not windows or seeds, are units",
        "contrasts": output,
    }


__all__ = [
    "ALL_LEARNED_FIT_COUNT",
    "FIT_COUNT",
    "FINAL_FIT_COUNT",
    "FOLD_COUNT",
    "LOMO_GPU_CAMPAIGN_BUDGET_SECONDS",
    "PROPOSED_COMPUTE_UNIT_SPEND_CAP",
    "aggregate_lomo_scores",
    "build_fit_matrix",
    "cache_view_for_fit",
    "fit_configuration",
    "fit_run_id",
    "lomo_fit_order",
    "freeze_all_checkpoint_manifests",
    "matrix_sha256",
    "prepare_c1_c2_contrasts",
    "require_compute_unit_budget",
    "score_heldout_fold",
    "validate_lomo_fit_order",
    "verify_execution_approval",
    "verify_scoring_authorization",
]
