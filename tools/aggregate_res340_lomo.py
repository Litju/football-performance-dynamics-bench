"""Aggregate authorized RES340 scores by held-out match and prepare matched descriptives."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import cast

import res340_lomo as lomo
import train_res338_final_fits as trainer


def aggregate_directory(
    score_directory: Path,
    fit_matrix_path: Path,
    *,
    fit_matrix_sha256: str,
    checkpoint_manifest: dict[str, object],
    checkpoint_manifest_sha256: str,
) -> dict[str, object]:
    matrix = cast(
        dict[str, object],
        json.loads(fit_matrix_path.read_bytes(), object_pairs_hook=trainer._unique_json_object),
    )
    if lomo.matrix_sha256(matrix) != fit_matrix_sha256:
        raise ValueError("fit matrix SHA-256 differs from the frozen 216-fit set")
    checkpoint_rows = cast(list[dict[str, object]], checkpoint_manifest["fits"])
    expected_checkpoints = {
        str(row["run_id"]): str(row["checkpoint_sha256"])
        for row in checkpoint_rows
        if row.get("fit_role") == "lomo"
    }
    scores = []
    for path in sorted(score_directory.glob("*.json")):
        if path.is_symlink() or not path.is_file():
            raise ValueError("score directory contains a nonregular result")
        value = trainer._read_private_json(path)
        expected_name = (
            f"{str(value.get('run_id', '')).replace('|', '--')}--"
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}.json"
        )
        if path.name != expected_name:
            raise ValueError("score filename is not content-addressed to its exact bytes")
        if value.get("status") == "completed" and (
            value.get("checkpoint_sha256") != expected_checkpoints.get(str(value.get("run_id")))
            or value.get("plan_sha256") != matrix.get("plan_sha256")
            or value.get("protocol_sha256") != matrix.get("protocol_sha256")
            or value.get("research_population_sha256") != matrix.get("research_population_sha256")
        ):
            value = {
                "run_id": value.get("run_id"),
                "status": "invalid",
                "failure_reason": "score does not bind the authorized checkpoint/source manifest",
            }
        scores.append(value)
    aggregate = lomo.aggregate_lomo_scores(lomo.expand_fit_matrix(matrix), scores)
    contrasts = lomo.prepare_c1_c2_contrasts(aggregate)
    return {
        "schema_id": "fpdbench.res340.lomo-private-report",
        "schema_version": "1.0.0",
        "fit_matrix_sha256": fit_matrix_sha256,
        "checkpoint_manifest_sha256": checkpoint_manifest_sha256,
        "aggregate": aggregate,
        "matched_c1_c2_descriptives": contrasts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("score_directory", type=Path)
    parser.add_argument("fit_matrix", type=Path)
    parser.add_argument("checkpoint_manifest", type=Path)
    parser.add_argument("checkpoint_manifest_sha256")
    parser.add_argument("scoring_authorization", type=Path)
    parser.add_argument("amendment_sha256")
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--fit-matrix-sha256", required=True)
    args = parser.parse_args()
    checkpoint_manifest = trainer._read_private_json(args.checkpoint_manifest)
    if trainer._sha256_file(args.checkpoint_manifest) != args.checkpoint_manifest_sha256:
        parser.error("checkpoint manifest SHA-256 differs")
    lomo.verify_scoring_authorization(
        trainer._read_private_json(args.scoring_authorization),
        amendment_sha256=args.amendment_sha256,
        fit_matrix_sha256=args.fit_matrix_sha256,
        checkpoint_manifest_sha256=args.checkpoint_manifest_sha256,
    )
    if (
        checkpoint_manifest.get("schema_id") != "fpdbench.res340.learned-checkpoint-manifest"
        or checkpoint_manifest.get("status") != "FROZEN_PENDING_SEPARATE_SCORING_AUTHORIZATION"
        or checkpoint_manifest.get("required_fit_count") != lomo.ALL_LEARNED_FIT_COUNT
    ):
        parser.error("all 234 learned checkpoint manifests must be frozen before aggregation")
    report = aggregate_directory(
        args.score_directory,
        args.fit_matrix,
        fit_matrix_sha256=args.fit_matrix_sha256,
        checkpoint_manifest=checkpoint_manifest,
        checkpoint_manifest_sha256=args.checkpoint_manifest_sha256,
    )
    args.output_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.output_directory.chmod(0o700)
    with trainer.source.private_directory(args.output_directory):
        pass
    payload = trainer._canonical(report)
    digest = hashlib.sha256(payload).hexdigest()
    output = args.output_directory / f"res340-lomo-report-{digest}.json"
    if output.exists():
        if trainer._sha256_file(output) != digest:
            raise FileExistsError("content-addressed report path contains different bytes")
    else:
        trainer._atomic_write(output, payload)
    print(json.dumps({"status": report["aggregate"]["status"], "sha256": digest}, sort_keys=True))
    if report["aggregate"]["complete"] is not True:
        raise SystemExit(2)


if __name__ == "__main__":
    os.umask(0o077)
    main()
