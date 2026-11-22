"""Score one RES340 held-out training match after its separate owner scoring GO."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import cast

import res340_lomo as lomo
import train_res338_final_fits as trainer

SHA256 = re.compile(r"[0-9a-f]{64}")


def _load_private_json(path: Path, expected_sha256: str | None = None) -> dict[str, object]:
    if expected_sha256 is not None and trainer._sha256_file(path) != expected_sha256:
        raise ValueError("private scoring evidence SHA-256 differs")
    return trainer._read_private_json(path)


def _validate_checkpoint_manifest(
    manifest: dict[str, object],
    fit_matrix: dict[str, object],
    expected_sha256: str,
) -> set[str]:
    if (
        manifest.get("schema_id") != "fpdbench.res340.learned-checkpoint-manifest"
        or manifest.get("status") != "FROZEN_PENDING_SEPARATE_SCORING_AUTHORIZATION"
        or manifest.get("required_fit_count") != lomo.ALL_LEARNED_FIT_COUNT
        or manifest.get("final_fit_count") != lomo.FINAL_FIT_COUNT
        or manifest.get("lomo_fit_count") != lomo.FIT_COUNT
        or manifest.get("fit_matrix_sha256") != expected_sha256
        or manifest.get("plan_sha256")
        != "a59fee6ee8e9fb03f4f0ccdae1933458af2bbf2375db7e6cd2bdf10962e42b62"
        or manifest.get("protocol_sha256")
        != "3d7bdc46300b966a4da274579d21ac4c8219e1ef897719d6b7a308596e9f1d9f"
    ):
        raise ValueError("the exact 234-checkpoint freeze is required before LOMO scoring")
    plan, protocol, roles = trainer._frozen_split_and_authorities()
    final_ids = {
        trainer._fit_run_id(fit)
        for fit in trainer._fit_order(roles["training"], roles["validation"])
    }
    lomo_ids = {str(fit["run_id"]) for fit in cast(list[dict[str, object]], fit_matrix["fits"])}
    rows = cast(list[dict[str, object]], manifest.get("fits", []))
    actual_ids = {str(row.get("run_id")) for row in rows}
    roles_match = all(
        row.get("fit_role") == ("lomo" if str(row.get("run_id")) in lomo_ids else "final_train")
        for row in rows
    )
    if (
        len(rows) != lomo.ALL_LEARNED_FIT_COUNT
        or actual_ids != final_ids | lomo_ids
        or len(actual_ids) != lomo.ALL_LEARNED_FIT_COUNT
        or not roles_match
        or any(SHA256.fullmatch(str(row.get("checkpoint_sha256", ""))) is None for row in rows)
        or any(SHA256.fullmatch(str(row.get("receipt_sha256", ""))) is None for row in rows)
    ):
        raise ValueError("checkpoint freeze has a missing, duplicate, or invalid fit identity")
    final_hashes = {
        str(row["checkpoint_sha256"]) for row in rows if row.get("fit_role") == "final_train"
    }
    lomo_hashes = {str(row["checkpoint_sha256"]) for row in rows if row.get("fit_role") == "lomo"}
    if len(final_hashes) != lomo.FINAL_FIT_COUNT or final_hashes.intersection(lomo_hashes):
        raise ValueError("LOMO checkpoint identities overlap final-fit checkpoints")
    return lomo_ids


def score_one(
    *,
    campaign_root: Path,
    fit_matrix_path: Path,
    fit_matrix_sha256: str,
    fit_run_id: str,
    checkpoint_manifest_path: Path,
    checkpoint_manifest_sha256: str,
    scoring_authorization_path: Path,
    amendment_sha256: str,
    output_root: Path,
) -> dict[str, object]:
    fit_matrix = cast(
        dict[str, object],
        json.loads(fit_matrix_path.read_bytes(), object_pairs_hook=trainer._unique_json_object),
    )
    if lomo.matrix_sha256(fit_matrix) != fit_matrix_sha256:
        raise ValueError("LOMO fit matrix differs from its frozen SHA-256")
    fit = next(
        (
            candidate
            for candidate in lomo.expand_fit_matrix(fit_matrix)
            if candidate["run_id"] == fit_run_id
        ),
        None,
    )
    if fit is None:
        raise ValueError("requested score is outside the frozen 216-fit LOMO matrix")

    ledger = _load_private_json(campaign_root / "campaign.json")
    freeze = _load_private_json(campaign_root / "reproducibility-manifest.json")
    freeze_sha256 = trainer._sha256_file(campaign_root / "reproducibility-manifest.json")
    if (
        ledger.get("status") != "RES340_RESEARCH_LOMO_FITS_COMPLETE"
        or ledger.get("required_fit_count") != lomo.FIT_COUNT
        or ledger.get("completed_fit_count") != lomo.FIT_COUNT
        or ledger.get("failed_fit_count") != 0
        or ledger.get("frozen_manifest_sha256") != freeze_sha256
        or freeze.get("fit_role") != "lomo"
        or freeze.get("lomo_fit_matrix_sha256") != fit_matrix_sha256
    ):
        raise ValueError("incomplete LOMO campaigns cannot enter held-out scoring")

    checkpoint_manifest = _load_private_json(checkpoint_manifest_path, checkpoint_manifest_sha256)
    expected_lomo_ids = _validate_checkpoint_manifest(
        checkpoint_manifest, fit_matrix, fit_matrix_sha256
    )
    if fit_run_id not in expected_lomo_ids:
        raise ValueError("requested fold checkpoint is outside the 234-checkpoint freeze")
    manifest_fit = next(
        row
        for row in cast(list[dict[str, object]], checkpoint_manifest["fits"])
        if row.get("run_id") == fit_run_id
    )
    scoring_approval = _load_private_json(scoring_authorization_path)
    lomo.verify_scoring_authorization(
        scoring_approval,
        amendment_sha256=amendment_sha256,
        fit_matrix_sha256=fit_matrix_sha256,
        checkpoint_manifest_sha256=checkpoint_manifest_sha256,
    )

    ledger_runs = cast(list[dict[str, object]], ledger["runs"])
    run = next((row for row in ledger_runs if row.get("run_id") == fit_run_id), None)
    if run is None or run.get("status") != "completed":
        raise ValueError("selected LOMO receipt is not a completed campaign record")
    run_dir = campaign_root / "runs" / fit_run_id.replace("|", "--")
    receipt_path = run_dir / "receipt.json"
    receipt = _load_private_json(receipt_path, str(run["receipt_sha256"]))
    if manifest_fit.get("checkpoint_sha256") != receipt.get("checkpoint_sha256"):
        raise ValueError("LOMO checkpoint differs from the frozen 234-checkpoint manifest")
    feature_cache = cast(dict[str, dict[str, object]], freeze["feature_cache"])
    cache_receipt = feature_cache[str(fit["held_out_match_id"])]
    target_mask_set_sha256 = hashlib.sha256(
        trainer._canonical(
            {
                match_id: item["target_mask_identity_sha256"]
                for match_id, item in sorted(feature_cache.items())
            }
        )
    ).hexdigest()
    if target_mask_set_sha256 != freeze.get("target_mask_identity_sha256"):
        raise ValueError("LOMO campaign freeze has a changed source truth/mask set")
    cache = trainer._open_match_cache(
        campaign_root
        / "feature-cache"
        / str(cache_receipt["role"])
        / str(fit["held_out_match_id"]),
        str(fit["held_out_match_id"]),
        str(cache_receipt["role"]),
    )
    try:
        try:
            scored = lomo.score_heldout_fold(
                fit,
                receipt,
                run_dir / "checkpoint.pt",
                cache,
                cache_receipt=cache_receipt,
                target_mask_set_sha256=target_mask_set_sha256,
                final_checkpoint_sha256s=[
                    str(row["checkpoint_sha256"])
                    for row in cast(list[dict[str, object]], checkpoint_manifest["fits"])
                    if row.get("fit_role") == "final_train"
                ],
            )
        except Exception as exc:
            output_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            output_root.chmod(0o700)
            with trainer.source.private_directory(output_root):
                pass
            failure = {
                "schema_id": "fpdbench.res340.lomo-heldout-score",
                "schema_version": "1.0.0",
                "status": "failed",
                "run_id": fit_run_id,
                "fit_role": "lomo",
                "lomo_fold_id": fit["fold_id"],
                "lomo_held_out_match_id": fit["held_out_match_id"],
                "failure_type": type(exc).__name__,
                "failure_reason": str(exc)[:1000],
            }
            failure_bytes = trainer._canonical(failure)
            failure_sha256 = hashlib.sha256(failure_bytes).hexdigest()
            failure_path = output_root / (f"{fit_run_id.replace('|', '--')}--{failure_sha256}.json")
            if not failure_path.exists():
                trainer._atomic_write(failure_path, failure_bytes)
            raise
    finally:
        for array in cache.arrays.values():
            mmap = getattr(array, "_mmap", None)
            if mmap is not None:
                mmap.close()

    output_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    output_root.chmod(0o700)
    with trainer.source.private_directory(output_root):
        pass
    payload = trainer._canonical(scored)
    output_sha256 = hashlib.sha256(payload).hexdigest()
    target = output_root / f"{fit_run_id.replace('|', '--')}--{output_sha256}.json"
    if target.exists():
        if trainer._sha256_file(target) != output_sha256:
            raise FileExistsError("content-addressed LOMO score path contains different bytes")
    else:
        trainer._atomic_write(target, payload)
    return {"status": "SCORED", "run_id": fit_run_id, "output_sha256": output_sha256}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign_root", type=Path)
    parser.add_argument("fit_matrix", type=Path)
    parser.add_argument("fit_run_id")
    parser.add_argument("checkpoint_manifest", type=Path)
    parser.add_argument("checkpoint_manifest_sha256")
    parser.add_argument("scoring_authorization", type=Path)
    parser.add_argument("amendment_sha256")
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--fit-matrix-sha256", required=True)
    args = parser.parse_args()
    if args.fit_matrix_sha256 and SHA256.fullmatch(args.fit_matrix_sha256) is None:
        parser.error("--fit-matrix-sha256 must be a lowercase SHA-256")
    result = score_one(
        campaign_root=args.campaign_root,
        fit_matrix_path=args.fit_matrix,
        fit_matrix_sha256=args.fit_matrix_sha256,
        fit_run_id=args.fit_run_id,
        checkpoint_manifest_path=args.checkpoint_manifest,
        checkpoint_manifest_sha256=args.checkpoint_manifest_sha256,
        scoring_authorization_path=args.scoring_authorization,
        amendment_sha256=args.amendment_sha256,
        output_root=args.output_root,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    os.umask(0o077)
    main()
