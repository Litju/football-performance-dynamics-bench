# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportMissingImports=false, reportPrivateUsage=false
# ruff: noqa: E501
# Long scientific-report prose and SVG literals are kept beside their template output.
"""Owner-gated research-only scoring for the proposed one-pass study."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import html
import json
import math
import os
import platform
import resource
import stat
import sys
import time
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Literal, Protocol, cast

import numpy as np
import torch
from numpy.typing import NDArray
from torch import Tensor

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.evaluation_population import (
    prospective_window_id_v2,
    truth_mask_sha256,
    truth_sha256,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.information import (
    validate_information_boundary,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.learned_deepsets import (
    FUTURE_SAMPLES,
    INFORMATION_REGIMES,
    SEEDS,
    TARGET_PLAYERS,
    TARGET_REPRESENTATIONS,
    InformationRegime,
    PerTargetContextDeepSetsMLP,
    TargetRepresentation,
    build_scene_feature_payload,
    collate_feature_payloads,
    load_checkpoint_verified,
    validate_feature_payload,
    validate_truth_scene,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.prospective_protocol import (
    EXPECTED_ELIGIBILITY_POLICY_V2_HASH,
    EXPECTED_MEASUREMENT_STATE_V2_HASH,
    EXPECTED_SOURCE_POPULATION_HASH,
    EXPECTED_SOURCE_RELEASE_HASH,
    PROTOCOL_V2_SHA256,
    load_prospective_protocol_v2,
)
from fpdbench.evaluation.metrics.trajectory import (
    ADE_METRIC_ID,
    FDE_METRIC_ID,
    XY_RMSE_METRIC_ID,
    MaskedTrajectoryMetrics,
    masked_physical_trajectory_metrics,
)

_MANIFEST_FILE = "res593_checkpoint_manifest_v1.json"
_AMENDMENT_FILE = "res593_amendment_v1.json"
_BASELINE_FILE = "res593_baseline_reference_v1.json"
_STUDY_ID = "fpdbench.public-skillcorner-amended-heldout-evaluation/1.0.0"
_INPUT_SCHEMA = "fpdbench.res594.private-evaluation-input"
_AUTH_SCHEMA = "fpdbench.res594.owner-execution-authorization"
_MATCHES = ("1874553", "1925299", "2006229", "2010085")
_MATCH_INDEX = {value: index for index, value in enumerate(_MATCHES)}
_RESOURCE_LIMITS = {
    "cpu_seconds": 14_400,
    "wall_seconds": 21_600,
    "rss_bytes": 8 * 1024**3,
    "input_bytes": 8 * 1024**3,
    "paid_compute_units": 0,
    "paid_cost_usd": 0,
}
_HEX64 = frozenset("0123456789abcdef")
_BASELINE_COMPARABILITY = "published aggregate reference; exact immutable private deterministic-baseline cell manifests not recovered"


class DigestWriter(Protocol):
    """The small hashlib interface used for streamed window and mask identities."""

    def update(self, data: bytes, /) -> None: ...

    def hexdigest(self) -> str: ...


def canonical_bytes(value: object) -> bytes:
    """Encode the small identity records with the repository's canonical JSON rules."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be a JSON object with string keys")
    return cast(dict[str, object], value)


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a JSON array")
    return cast(list[object], value)


def _sha(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _HEX64 for character in value)
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _strict_int(value: object, label: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{label} must be an integer")
    return value


def _strict_float(value: object, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(cast(int | float, value)):
        raise ValueError(f"{label} must be a finite number")
    return float(cast(int | float, value))


def _read_resource(name: str) -> bytes:
    return files(__package__).joinpath(name).read_bytes()


def _read_baseline_report() -> bytes:
    packaged = files(__package__).joinpath("res337_deterministic_results_v1.md")
    if packaged.is_file():
        return packaged.read_bytes()
    repository_root = Path(__file__).resolve().parents[4]
    return (repository_root / "docs" / "res337-deterministic-research-results.md").read_bytes()


def _load_resource_json(name: str) -> tuple[dict[str, object], bytes]:
    raw = _read_resource(name)
    return _mapping(json.loads(raw, object_pairs_hook=_unique_object), name), raw


def load_frozen_artifacts() -> tuple[dict[str, object], str, dict[str, object], dict[str, object]]:
    """Load proposed identities and verify the safe checkpoint/baseline references."""
    amendment, amendment_bytes = _load_resource_json(_AMENDMENT_FILE)
    manifest, manifest_bytes = _load_resource_json(_MANIFEST_FILE)
    baseline, baseline_bytes = _load_resource_json(_BASELINE_FILE)
    authorization_schema_bytes = _read_resource("res594_owner_authorization_v1.schema.json")
    amendment_sha256 = hashlib.sha256(amendment_bytes).hexdigest()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    baseline_report_sha256 = hashlib.sha256(_read_baseline_report()).hexdigest()
    if amendment.get("study_id") != _STUDY_ID or amendment.get("status") != "PROPOSED_UNRATIFIED":
        raise ValueError("amended-study identity or ratification state differs")
    authorities = _mapping(amendment.get("authorities"), "amendment authorities")
    if authorities.get("checkpoint_manifest_sha256") != manifest_sha256:
        raise ValueError("amendment is not bound to the exact 18-checkpoint manifest")
    if (
        authorities.get("baseline_reference_sha256") != hashlib.sha256(baseline_bytes).hexdigest()
        or authorities.get("owner_authorization_schema_sha256")
        != hashlib.sha256(authorization_schema_bytes).hexdigest()
    ):
        raise ValueError("amendment baseline or authorization-schema identity differs")
    if manifest.get("study_id") != _STUDY_ID or manifest.get("status") != "PROPOSED_UNRATIFIED":
        raise ValueError("checkpoint manifest identity or ratification state differs")
    baseline_sha = _sha(baseline.get("results_document_sha256"), "baseline report identity")
    if (
        baseline_sha != authorities.get("deterministic_results_document_sha256")
        or baseline_sha != baseline_report_sha256
    ):
        raise ValueError(
            "baseline reference differs from the disclosed deterministic-baseline report"
        )
    _validate_checkpoint_manifest(manifest)
    _validate_baseline_reference(baseline)
    return amendment, amendment_sha256, manifest, baseline


def _protocol_roles() -> dict[str, tuple[str, ...]]:
    protocol = load_prospective_protocol_v2()
    state = _mapping(protocol.get("scientific_state"), "v2 scientific state")
    split = _mapping(state.get("split"), "v2 protocol split")
    raw_roles = _mapping(split.get("roles"), "v2 protocol roles")
    roles = {
        role: tuple(cast(str, value) for value in _list(raw_roles.get(role), f"{role} roles"))
        for role in ("training", "validation", "evaluation")
    }
    if roles["evaluation"] != _MATCHES:
        raise ValueError("amended evaluator match roles differ from frozen v2")
    return roles


def _validate_checkpoint_manifest(manifest: Mapping[str, object]) -> None:
    identity = _mapping(manifest.get("identity"), "checkpoint manifest identity")
    if identity != {
        "original_plan_sha256": "a59fee6ee8e9fb03f4f0ccdae1933458af2bbf2375db7e6cd2bdf10962e42b62",
        "original_protocol_sha256": PROTOCOL_V2_SHA256,
        "research_admission_sha256": "a8c82bfa09ac792d6c4ae779d4b28158c33ed3c2500f8548f3e94d48197f4fd1",
        "training_implementation_commit": "fd06e1b15eaf8982a1bef8708f3063c965ed801d",
    }:
        raise ValueError("checkpoint manifest original fit identities differ")
    model = _mapping(manifest.get("model"), "checkpoint manifest model")
    records = _list(manifest.get("checkpoints"), "checkpoint records")
    roles = _protocol_roles()
    expected = {
        (regime, representation, seed)
        for regime in INFORMATION_REGIMES
        for representation in TARGET_REPRESENTATIONS
        for seed in SEEDS
    }
    actual: set[tuple[str, str, int]] = set()
    checkpoints: set[str] = set()
    receipts: set[str] = set()
    configurations: set[str] = set()
    for raw_record in records:
        record = _mapping(raw_record, "checkpoint record")
        model_id = record.get("model_id")
        regime = record.get("information_regime")
        representation = record.get("target_representation")
        seed = record.get("seed")
        if (
            model_id != "per_target_context_deepsets_mlp_v1"
            or not isinstance(regime, str)
            or regime not in INFORMATION_REGIMES
            or not isinstance(representation, str)
            or representation not in TARGET_REPRESENTATIONS
            or type(seed) is not int
            or seed not in SEEDS
        ):
            raise ValueError("checkpoint manifest contains an unexpected model cell")
        if record.get("fit_role") != "final_train" or record.get("attempt_number") != 1:
            raise ValueError("checkpoint manifest includes a nonfinal or retried fit")
        cell = (regime, representation, seed)
        if cell in actual:
            raise ValueError("checkpoint manifest duplicates a model/seed cell")
        actual.add(cell)
        if record.get("train_match_ids") != list(roles["training"]) or record.get(
            "validation_match_ids"
        ) != list(roles["validation"]):
            raise ValueError("checkpoint fit role matches differ from original v2")
        if (
            type(record.get("selected_step")) is not int
            or type(record.get("optimizer_steps")) is not int
            or not 100 <= cast(int, record["selected_step"]) <= cast(int, record["optimizer_steps"])
            or cast(int, record["selected_step"]) > 5000
            or cast(int, record["selected_step"]) % 100
        ):
            raise ValueError("checkpoint selected optimizer step differs from frozen cadence")
        for name in (
            "checkpoint_sha256",
            "receipt_sha256",
            "configuration_sha256",
            "environment_sha256",
            "population_manifest_sha256",
            "plan_sha256",
            "protocol_sha256",
            "target_mask_identity_sha256",
        ):
            _sha(record.get(name), name)
        if (
            record["population_manifest_sha256"]
            != "a8c82bfa09ac792d6c4ae779d4b28158c33ed3c2500f8548f3e94d48197f4fd1"
        ):
            raise ValueError(
                "checkpoint fit population differs from the ratified research admission"
            )
        if (
            record["plan_sha256"]
            != "a59fee6ee8e9fb03f4f0ccdae1933458af2bbf2375db7e6cd2bdf10962e42b62"
        ):
            raise ValueError("checkpoint fit plan differs from original v2")
        if record["protocol_sha256"] != PROTOCOL_V2_SHA256:
            raise ValueError("checkpoint fit protocol differs from original v2")
        if record["checkpoint_sha256"] in checkpoints or record["receipt_sha256"] in receipts:
            raise ValueError("checkpoint or fit receipt digest is duplicated")
        if record["configuration_sha256"] in configurations:
            raise ValueError("fit configuration digest is duplicated")
        checkpoints.add(cast(str, record["checkpoint_sha256"]))
        receipts.add(cast(str, record["receipt_sha256"]))
        configurations.add(cast(str, record["configuration_sha256"]))
    if actual != expected or len(records) != 18:
        raise ValueError("checkpoint manifest must contain the exact 18 frozen cells once")
    manifest_roles = _mapping(manifest.get("roles"), "checkpoint manifest roles")
    if any(manifest_roles.get(role) != list(match_ids) for role, match_ids in roles.items()):
        raise ValueError("checkpoint manifest training, validation, or evaluation roles differ")
    if (
        model.get("model_id") != "per_target_context_deepsets_mlp_v1"
        or model.get("fit_role") != "final_train"
        or model.get("attempts_per_fit") != 1
        or model.get("warm_start_allowed") is not False
        or model.get("checkpoint_substitution_allowed") is not False
        or model.get("seeds") != list(SEEDS)
        or model.get("information_regimes") != list(INFORMATION_REGIMES)
        or model.get("target_representations") != list(TARGET_REPRESENTATIONS)
        or model.get("checkpoint_weights_in_repository") is not False
    ):
        raise ValueError("checkpoint manifest factor declaration differs")
    evidence = _mapping(manifest.get("source_evidence"), "checkpoint source evidence")
    claims = _mapping(evidence.get("evidence_claims"), "checkpoint evidence claims")
    if (
        claims.get("completed_and_verified_fits") != 18
        or claims.get("checkpoint_readbacks_verified") != 18
        or claims.get("receipt_readbacks_verified") != 18
        or claims.get("evaluation_or_lomo_run") is not False
        or claims.get("single_attempt_per_fit") is not True
        or claims.get("warm_start_or_retraining") is not False
        or claims.get("evaluation_informed_model_selection") is not False
        or claims.get("protected_status") != "NOT_QUALIFIED"
    ):
        raise ValueError("private final-fit evidence claims differ")
    for key in (
        "final_evidence_index_sha256",
        "final_progress_index_sha256",
        "campaign_manifest_sha256",
        "private_final_report_sha256",
    ):
        _sha(evidence.get(key), f"source evidence {key}")


def _validate_baseline_reference(baseline: Mapping[str, object]) -> None:
    if baseline.get("schema_id") != "fpdbench.res593.deterministic-baseline-reference":
        raise ValueError("unexpected deterministic baseline reference")
    if (
        baseline.get("research_admission_sha256")
        != "a8c82bfa09ac792d6c4ae779d4b28158c33ed3c2500f8548f3e94d48197f4fd1"
        or baseline.get("original_protocol_sha256") != PROTOCOL_V2_SHA256
        or baseline.get("source_release_hash") != EXPECTED_SOURCE_RELEASE_HASH
        or baseline.get("source_population_hash") != EXPECTED_SOURCE_POPULATION_HASH
        or baseline.get("measurement_state_hash") != EXPECTED_MEASUREMENT_STATE_V2_HASH
        or baseline.get("eligibility_policy_hash") != EXPECTED_ELIGIBILITY_POLICY_V2_HASH
        or baseline.get("total_evaluation_windows") != 51713
        or baseline.get("total_evaluation_scenes") != 103426
    ):
        raise ValueError("deterministic baseline source, mask, or population identity differs")
    if (
        tuple(
            cast(str, value)
            for value in _list(baseline.get("evaluation_match_ids"), "baseline matches")
        )
        != _MATCHES
    ):
        raise ValueError("baseline match coverage differs from the frozen evaluation role")
    denominators = _mapping(baseline.get("scored_denominators"), "baseline denominators")
    models = _mapping(baseline.get("models"), "baseline models")
    if set(models) != {"origin_persistence_v1", "constant_velocity_1s_v1"}:
        raise ValueError("deterministic baseline model identities differ")
    expected_counts = {
        "1874553": (12363, 24726, 4079790, 271986),
        "1925299": (14018, 28036, 4625940, 308396),
        "2006229": (12501, 25002, 4125330, 275022),
        "2010085": (12831, 25662, 4234230, 282282),
    }
    for match in _MATCHES:
        values = _mapping(denominators.get(match), "baseline denominator")
        if (
            tuple(
                values.get(key) for key in ("windows", "scenes", "scored_points", "final_targets")
            )
            != expected_counts[match]
        ):
            raise ValueError(f"published persistence/velocity denominators differ for {match}")
        for model in models.values():
            metrics = _mapping(_mapping(model, "baseline model").get(match), "baseline match")
            if any(
                type(metrics.get(name)) not in (float, int)
                or not math.isfinite(cast(float, metrics[name]))
                for name in ("ade_m", "fde_m", "xy_rmse_m")
            ):
                raise ValueError("baseline aggregate contains invalid metrics")


@dataclass(frozen=True, slots=True)
class OwnerAuthorization:
    document: dict[str, object]
    amendment_sha256: str
    checkpoint_manifest_sha256: str
    evaluation_input_sha256: str | None
    scorer_code_sha256: str


def _scorer_code_identity_sha256() -> str:
    module_path = Path(__file__).resolve()
    repository_root = module_path.parents[4]
    entrypoint_path = repository_root / "tools" / "score_res594_heldout.py"
    identity = {
        module_path.name: hashlib.sha256(module_path.read_bytes()).hexdigest(),
        entrypoint_path.name: hashlib.sha256(entrypoint_path.read_bytes()).hexdigest(),
    }
    return hashlib.sha256(canonical_bytes(identity)).hexdigest()


def authorize_owner_execution(
    authorization_path: Path,
    owner_go: str,
    *,
    amendment_sha256: str,
    checkpoint_manifest_sha256: str,
    scorer_code_sha256: str,
) -> OwnerAuthorization:
    """Read the explicit owner GO before any evaluation input or checkpoint is opened."""
    fd = os.open(authorization_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o077:
            raise ValueError("owner authorization must be a private, exclusive regular file")
        document = _mapping(
            json.loads(stream.read(), object_pairs_hook=_unique_object), "owner authorization"
        )
    required_fields = {
        "schema_id",
        "schema_version",
        "study_id",
        "owner_approved",
        "owner_name",
        "authorized_at_utc",
        "authorized_by_owner",
        "research_only",
        "protected_status",
        "one_campaign_only",
        "retry_after_failure",
        "amendment_sha256",
        "checkpoint_manifest_sha256",
        "scorer_code_sha256",
        "research_admission_sha256",
        "evaluation_match_ids",
        "resource_limits",
        "runtime",
        "evaluation_input_identity",
    }
    if not required_fields.issubset(document) or set(document) - (
        required_fields | {"evaluation_input_sha256"}
    ):
        raise ValueError("owner authorization fields differ from the frozen schema")
    if (
        document.get("schema_id") != _AUTH_SCHEMA
        or document.get("schema_version") != "1.0.0"
        or document.get("study_id") != _STUDY_ID
        or document.get("owner_approved") is not True
        or document.get("research_only") is not True
        or document.get("protected_status") != "NOT_QUALIFIED"
        or document.get("authorized_by_owner") is not True
        or document.get("one_campaign_only") is not True
        or document.get("retry_after_failure") is not False
        or not isinstance(document.get("owner_name"), str)
        or not cast(str, document["owner_name"]).strip()
        or not isinstance(document.get("authorized_at_utc"), str)
        or not cast(str, document["authorized_at_utc"]).strip()
    ):
        raise PermissionError("explicit separate owner authorization is required")
    if (
        document.get("amendment_sha256") != amendment_sha256
        or document.get("checkpoint_manifest_sha256") != checkpoint_manifest_sha256
    ):
        raise PermissionError("owner authorization does not bind this amendment and manifest")
    research_admission_sha256 = _sha(
        document.get("research_admission_sha256"), "authorized research admission identity"
    )
    if (
        research_admission_sha256
        != "a8c82bfa09ac792d6c4ae779d4b28158c33ed3c2500f8548f3e94d48197f4fd1"
    ):
        raise PermissionError(
            "owner authorization differs from the frozen research-only population"
        )
    if document.get("scorer_code_sha256") != scorer_code_sha256:
        raise PermissionError("owner authorization does not bind this scorer source")
    if document.get("evaluation_match_ids") != list(_MATCHES):
        raise PermissionError(
            "owner authorization does not bind exactly the four evaluation matches"
        )
    runtime = _mapping(document.get("runtime"), "authorized runtime")
    if runtime != {
        "python": "3.12.8",
        "numpy": "2.2.4",
        "pytorch": "2.6.0+cpu",
        "device": "cpu",
        "precision": "float32",
        "threads": 1,
    }:
        raise PermissionError("owner authorization runtime differs from the frozen CPU plan")
    expected_go = (
        f"RES594-OWNER-GO:{amendment_sha256}:"
        f"{checkpoint_manifest_sha256}:{research_admission_sha256}:{scorer_code_sha256}"
    )
    if owner_go != expected_go:
        raise PermissionError("typed owner GO phrase does not match the exact frozen inputs")
    limits = _mapping(document.get("resource_limits"), "owner resource limits")
    if limits != _RESOURCE_LIMITS:
        raise PermissionError("owner authorization resource limits differ from the amendment")
    input_identity = _mapping(document.get("evaluation_input_identity"), "input identity")
    if set(input_identity) != {
        "research_admission_sha256",
        "source_release_hash",
        "source_population_hash",
        "protocol_sha256",
    }:
        raise PermissionError("owner input identity fields differ from the frozen source contract")
    for key, expected in {
        "research_admission_sha256": "a8c82bfa09ac792d6c4ae779d4b28158c33ed3c2500f8548f3e94d48197f4fd1",
        "source_release_hash": EXPECTED_SOURCE_RELEASE_HASH,
        "source_population_hash": EXPECTED_SOURCE_POPULATION_HASH,
        "protocol_sha256": PROTOCOL_V2_SHA256,
    }.items():
        if input_identity.get(key) != expected:
            raise PermissionError(f"owner input authority differs: {key}")
    return OwnerAuthorization(
        document,
        amendment_sha256,
        checkpoint_manifest_sha256,
        (
            _sha(document["evaluation_input_sha256"], "optional preapproved input identity")
            if document.get("evaluation_input_sha256") is not None
            else None
        ),
        scorer_code_sha256,
    )


def _read_json_lines(path: Path) -> Iterator[dict[str, object]]:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_mode & 0o077:
            raise ValueError("private evaluation snapshot must be an exclusive regular file")
        for line_number, line in enumerate(stream, start=1):
            if not line.endswith(b"\n"):
                raise ValueError(f"evaluation JSONL line {line_number} is not newline-terminated")
            yield _mapping(
                json.loads(line, object_pairs_hook=_unique_object),
                f"evaluation JSONL line {line_number}",
            )
        after = os.fstat(stream.fileno())
        if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ValueError("private evaluation snapshot changed during scoring")


def _validate_input_header(
    header: Mapping[str, object],
    *,
    amendment_sha256: str,
    checkpoint_manifest_sha256: str,
    source_authority: Mapping[str, object],
) -> dict[str, object]:
    if (
        header.get("kind") != "header"
        or header.get("schema_id") != _INPUT_SCHEMA
        or header.get("schema_version") != "1.0.0"
        or header.get("study_id") != _STUDY_ID
        or header.get("amendment_sha256") != amendment_sha256
        or header.get("checkpoint_manifest_sha256") != checkpoint_manifest_sha256
        or header.get("role") != "evaluation"
        or header.get("research_admission_sha256")
        != "a8c82bfa09ac792d6c4ae779d4b28158c33ed3c2500f8548f3e94d48197f4fd1"
        or header.get("source_release_hash") != EXPECTED_SOURCE_RELEASE_HASH
        or header.get("source_population_hash") != EXPECTED_SOURCE_POPULATION_HASH
        or header.get("measurement_state_hash") != EXPECTED_MEASUREMENT_STATE_V2_HASH
        or header.get("eligibility_policy_hash") != EXPECTED_ELIGIBILITY_POLICY_V2_HASH
        or header.get("protocol_sha256") != PROTOCOL_V2_SHA256
        or header.get("coordinate_frame") != "source_pitch_xy_m"
        or header.get("scene_orientation") != "source_xy_no_reflection"
        or header.get("history_intervals") != 25
        or header.get("origin_included") is not True
        or header.get("future_steps") != FUTURE_SAMPLES
        or header.get("step_seconds") != 0.2
        or header.get("window_identity_version") != "2.0.0"
        or header.get("verification_status") != "RESEARCH_RECONCILED"
        or header.get("protected_status") != "NOT_QUALIFIED"
    ):
        raise ValueError("evaluation input header differs from the frozen research-only protocol")
    if header.get("evaluation_match_ids") != list(_MATCHES):
        raise ValueError(
            "evaluation input does not contain exactly the four frozen evaluation roles"
        )
    for header_key, auth_key in (
        ("window_identity_sha256_by_match", "window_identity_sha256_by_match"),
        ("mask_identity_sha256_by_match", "mask_identity_sha256_by_match"),
        ("source_match_sha256_by_match", "source_match_sha256_by_match"),
        ("population_stream_sha256_by_match", "producer_stream_sha256_by_match"),
    ):
        header_map = _mapping(header.get(header_key), header_key)
        auth_map = _mapping(source_authority.get(auth_key), auth_key)
        if set(header_map) != set(_MATCHES) or header_map != auth_map:
            raise ValueError(f"evaluation input {header_key} differs from verified population")
        for match_id, identity in header_map.items():
            _sha(identity, f"{header_key}[{match_id}]")
    expected_counts = _mapping(header.get("expected_scoreable_window_counts"), "window counts")
    if expected_counts != _mapping(
        source_authority.get("expected_scoreable_window_counts"), "verified window counts"
    ):
        raise ValueError(
            "evaluation eligible-window counts differ from verified research admission"
        )
    baseline, _ = _load_resource_json(_BASELINE_FILE)
    denominators = _mapping(baseline.get("scored_denominators"), "baseline denominators")
    for match_id in _MATCHES:
        count = _mapping(denominators.get(match_id), "baseline denominator").get("windows")
        if expected_counts.get(match_id) != count:
            raise ValueError(
                f"frozen eligible-window count differs for evaluation match {match_id}"
            )
    verifier_sha = _sha(header.get("source_verification_sha256"), "source verification report")
    if source_authority.get("source_verification_sha256") != verifier_sha:
        raise ValueError("source verification report identity differs from verified population")
    return {
        "window_identity_sha256_by_match": cast(
            dict[str, object], header["window_identity_sha256_by_match"]
        ),
        "mask_identity_sha256_by_match": cast(
            dict[str, object], header["mask_identity_sha256_by_match"]
        ),
        "source_match_sha256_by_match": cast(
            dict[str, object], header["source_match_sha256_by_match"]
        ),
        "producer_stream_sha256_by_match": cast(
            dict[str, object], header["population_stream_sha256_by_match"]
        ),
        "expected_scoreable_window_counts": expected_counts,
        "source_verification_sha256": verifier_sha,
    }


def _metadata_rosters(metadata: Mapping[str, object]) -> tuple[list[int], list[int]]:
    home_id = _strict_int(_mapping(metadata["home_team"], "home team")["id"], "home team ID")
    away_id = _strict_int(_mapping(metadata["away_team"], "away team")["id"], "away team ID")
    home_players: list[int] = []
    away_players: list[int] = []
    for raw in _list(metadata.get("players"), "match roster"):
        player = _mapping(raw, "roster player")
        player_id = _strict_int(player.get("id"), "roster player ID")
        team_id = _strict_int(player.get("team_id"), "roster team ID")
        if team_id == home_id:
            home_players.append(player_id)
        elif team_id == away_id:
            away_players.append(player_id)
        else:
            raise ValueError("match roster contains a player outside the frozen teams")
    if not home_players or not away_players or set(home_players) & set(away_players):
        raise ValueError("match metadata must contain two disjoint nonempty team rosters")
    return sorted(home_players), sorted(away_players)


def _prepare_verified_research_input(
    research_root: Path,
    source_root: Path,
    output_directory: Path,
    *,
    amendment_sha256: str,
    checkpoint_manifest_sha256: str,
    campaign_start_cpu: float,
    campaign_start_wall: float,
) -> tuple[Path, dict[str, object], str]:
    """Reconcile the already-admitted private population, then stream four windows into a private file."""
    repository_root = Path(__file__).resolve().parents[4]
    tools_path = repository_root / "tools"
    if not tools_path.is_dir():
        raise RuntimeError("held-out source preparation requires the canonical repository tools")
    if str(tools_path) not in sys.path:
        sys.path.insert(0, str(tools_path))
    import research_baseline_v1 as baseline_runner
    import research_population_v1 as research

    from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
        streaming_population_producer_v1 as producer,
    )
    from fpdbench.data_sources import protected_skillcorner as source
    from fpdbench.data_states.skillcorner import iter_skillcorner_5hz_v2
    from fpdbench.eligibility.skillcorner import skillcorner_period_ranges

    manifest = baseline_runner.verify(research_root, source_root)
    admission_sha256 = hashlib.sha256(research.canonical(manifest)).hexdigest()
    if (
        admission_sha256 != "a8c82bfa09ac792d6c4ae779d4b28158c33ed3c2500f8548f3e94d48197f4fd1"
        or manifest.get("status") != "RESEARCH_RECONCILED"
        or manifest.get("protected_status") != "NOT_QUALIFIED"
    ):
        raise ValueError("private source does not match the owner-ratified research admission")
    roles = _protocol_roles()
    per_match = _mapping(manifest.get("per_match"), "research match roles")
    if set(per_match) != set(roles["training"] + roles["validation"] + roles["evaluation"]):
        raise ValueError("research admission role membership differs from original v2")
    if any(
        _mapping(per_match[match_id], "research match").get("role") != role
        for role, match_ids in roles.items()
        for match_id in match_ids
    ):
        raise ValueError("research admission match role differs from original v2")

    source_by_match: dict[str, str] = {}
    producer_by_match: dict[str, str] = {}
    window_identity: dict[str, str] = {}
    mask_identity: dict[str, str] = {}
    expected_counts: dict[str, int] = {}
    artifacts = _mapping(manifest.get("artifacts"), "research artifacts")
    for match_id in _MATCHES:
        artifact = _mapping(artifacts[match_id], "research match artifacts")
        producer_sha = _sha(artifact.get("producer_sha256"), "research producer stream")
        producer_path = research_root / "producer" / f"{match_id}.jsonl"
        if research.digest(producer_path) != producer_sha:
            raise ValueError("evaluation producer stream differs from admitted research identity")
        summary = _mapping(
            json.loads(
                (research_root / "producer" / f"{match_id}.summary.json").read_bytes(),
                object_pairs_hook=_unique_object,
            ),
            "evaluation producer summary",
        )
        if summary.get("role") != "evaluation":
            raise ValueError("producer summary does not bind the evaluation role")
        tracking_sha = _sha(summary.get("tracking_sha256"), "evaluation tracking source")
        source_by_match[match_id] = tracking_sha
        producer_by_match[match_id] = producer_sha
        counts = _mapping(_mapping(per_match[match_id], "research match")["counts"], "match counts")
        window_count = counts.get("scoreable_windows")
        if type(window_count) is not int:
            raise ValueError("research population has no exact scoreable-window count")
        expected_counts[match_id] = window_count

        window_digest = hashlib.sha256()
        mask_digest = hashlib.sha256()
        observed_windows = 0
        with producer_path.open("rb") as stream:
            for line in stream:
                row = _mapping(json.loads(line, object_pairs_hook=_unique_object), "producer row")
                if not row.get("window_id"):
                    continue
                window_id = row.get("window_id")
                origin_id = row.get("origin_sample_id")
                if (
                    not isinstance(window_id, str)
                    or not isinstance(origin_id, str)
                    or window_id != prospective_window_id_v2(match_id, origin_id)
                ):
                    raise ValueError("research producer has a mismatched v2 window identity")
                window_digest.update(
                    canonical_bytes({"origin_sample_id": origin_id, "window_id": window_id}) + b"\n"
                )
                producer_scenes = _list(row.get("scenes"), "producer scenes")
                if len(producer_scenes) != 2:
                    raise ValueError("research producer window lacks both directed scenes")
                for side, raw_scene in zip(("home", "away"), producer_scenes, strict=True):
                    scene = _mapping(raw_scene, "producer scene")
                    if scene.get("scene_id") != side:
                        raise ValueError("research producer target-panel order differs")
                    mask_digest.update(
                        canonical_bytes(
                            {
                                "scene_id": side,
                                "truth_mask_sha256": _sha(
                                    scene.get("truth_mask_sha256"), "producer target mask"
                                ),
                                "window_id": window_id,
                            }
                        )
                        + b"\n"
                    )
                observed_windows += 1
        if observed_windows != window_count:
            raise ValueError("research producer window count differs from admission")
        window_identity[match_id] = window_digest.hexdigest()
        mask_identity[match_id] = mask_digest.hexdigest()

    source_authority: dict[str, object] = {
        "source_verification_sha256": admission_sha256,
        "source_match_sha256_by_match": source_by_match,
        "producer_stream_sha256_by_match": producer_by_match,
        "window_identity_sha256_by_match": window_identity,
        "mask_identity_sha256_by_match": mask_identity,
        "expected_scoreable_window_counts": expected_counts,
    }
    header: dict[str, object] = {
        "kind": "header",
        "schema_id": _INPUT_SCHEMA,
        "schema_version": "1.0.0",
        "study_id": _STUDY_ID,
        "amendment_sha256": amendment_sha256,
        "checkpoint_manifest_sha256": checkpoint_manifest_sha256,
        "research_admission_sha256": admission_sha256,
        "source_release_hash": EXPECTED_SOURCE_RELEASE_HASH,
        "source_population_hash": EXPECTED_SOURCE_POPULATION_HASH,
        "measurement_state_hash": EXPECTED_MEASUREMENT_STATE_V2_HASH,
        "eligibility_policy_hash": EXPECTED_ELIGIBILITY_POLICY_V2_HASH,
        "protocol_sha256": PROTOCOL_V2_SHA256,
        "role": "evaluation",
        "evaluation_match_ids": list(_MATCHES),
        "coordinate_frame": "source_pitch_xy_m",
        "scene_orientation": "source_xy_no_reflection",
        "history_intervals": 25,
        "origin_included": True,
        "future_steps": 15,
        "step_seconds": 0.2,
        "window_identity_version": "2.0.0",
        "verification_status": "RESEARCH_RECONCILED",
        "protected_status": "NOT_QUALIFIED",
        "source_verification_sha256": admission_sha256,
        "source_match_sha256_by_match": source_by_match,
        "population_stream_sha256_by_match": producer_by_match,
        "window_identity_sha256_by_match": window_identity,
        "mask_identity_sha256_by_match": mask_identity,
        "expected_scoreable_window_counts": expected_counts,
    }
    output_path = output_directory / "evaluation-input.private.jsonl"
    fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    output_bytes = 0
    try:
        with os.fdopen(fd, "wb") as writer:
            payload = canonical_bytes(header) + b"\n"
            writer.write(payload)
            output_bytes += len(payload)
            for match_id in _MATCHES:
                match_dir = research_root / "inputs" / match_id
                metadata = _mapping(
                    json.loads(
                        (match_dir / "metadata.json").read_bytes(), object_pairs_hook=_unique_object
                    ),
                    "evaluation match metadata",
                )
                bounds, errors = skillcorner_period_ranges(metadata)
                if errors:
                    raise ValueError("evaluation match metadata has invalid period ranges")
                home_ids, away_ids = _metadata_rosters(metadata)
                expected_role = next(
                    role for role, match_ids in roles.items() if match_id in match_ids
                )
                if expected_role != "evaluation":
                    raise ValueError("only evaluation-role matches can enter the held-out study")
                producer_path = research_root / "producer" / f"{match_id}.jsonl"
                producer_fd = os.open(producer_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with (
                    source.private_directory(match_dir) as source_fd,
                    os.fdopen(producer_fd, "rb") as producer_stream,
                ):
                    stats: dict[str, object] = {}
                    samples = iter_skillcorner_5hz_v2(
                        source._rows(source_fd, "tracking.jsonl", stats),
                        metadata,
                        source_release_id=cast(
                            str,
                            _mapping(source._authority(), "source authority")["source_release_id"],
                        ),
                    )
                    for (period, frame, origin_id), support in producer._population_events(
                        samples, bounds
                    ):
                        _check_resource_limits(campaign_start_cpu, campaign_start_wall)
                        line = producer_stream.readline()
                        if not line:
                            raise ValueError("research producer stream ended before its source")
                        locked_row = _mapping(
                            json.loads(line, object_pairs_hook=_unique_object),
                            "locked evaluation population row",
                        )
                        if (
                            locked_row.get("match_id"),
                            locked_row.get("role"),
                            locked_row.get("period"),
                            locked_row.get("source_frame"),
                            locked_row.get("origin_sample_id"),
                        ) != (match_id, expected_role, period, frame, origin_id):
                            raise ValueError(
                                "evaluation origin differs from the frozen producer stream"
                            )
                        window_id = locked_row.get("window_id")
                        if not window_id:
                            continue
                        if window_id != prospective_window_id_v2(match_id, origin_id):
                            raise ValueError("evaluation source window ID differs from original v2")
                        if len(support) != 41 or any(sample is None for sample in support):
                            raise ValueError(
                                "eligible evaluation window has incomplete 41-sample support"
                            )
                        scenes: list[dict[str, object]] = []
                        for side, locked_scene in zip(
                            ("home", "away"),
                            _list(locked_row.get("scenes"), "locked scene panels"),
                            strict=True,
                        ):
                            _, truth, scoreable = producer._scene(support, side)
                            if research.canonical(truth) != research.canonical(locked_scene):
                                raise ValueError(
                                    "evaluation source truth or mask differs from admitted population"
                                )
                            if scoreable != truth["scoreable"]:
                                raise ValueError(
                                    "evaluation scene scoreability differs from frozen mask"
                                )
                            scenes.append(truth)
                        if not any(cast(bool, scene["scoreable"]) for scene in scenes):
                            raise ValueError(
                                "eligible evaluation window has zero scoreable target scenes"
                            )
                        complete_support = cast(Sequence[Mapping[str, object]], support)
                        support_ids = [
                            f"period_{_strict_int(sample['period'], 'support period')}/sample_"
                            f"{_strict_int(sample['source_frame'], 'support frame') // 2}"
                            for sample in complete_support
                        ]
                        row = {
                            "kind": "window",
                            "match_id": match_id,
                            "role": "evaluation",
                            "origin_sample_id": origin_id,
                            "window_id": window_id,
                            "source_match_sha256": source_by_match[match_id],
                            "time_offsets_s": [
                                round(-5.0 + 0.2 * index, 10) for index in range(41)
                            ],
                            "support_sample_ids": support_ids,
                            "support": complete_support,
                            "home_player_ids": home_ids,
                            "away_player_ids": away_ids,
                            "scenes": scenes,
                        }
                        payload = canonical_bytes(row) + b"\n"
                        output_bytes += len(payload)
                        if output_bytes > _RESOURCE_LIMITS["input_bytes"]:
                            raise ValueError(
                                "prepared private evaluation input exceeds its byte ceiling"
                            )
                        writer.write(payload)
                    if producer_stream.read(1):
                        raise ValueError("evaluation source ended before its population stream")
                if stats.get("tracking_sha256") != source_by_match[match_id]:
                    raise ValueError("evaluation source tracking hash differs from admission")
                if research.digest(producer_path) != producer_by_match[match_id]:
                    raise ValueError(
                        "evaluation producer stream changed during source reconciliation"
                    )
            writer.flush()
            os.fsync(writer.fileno())
    except BaseException:
        try:
            output_path.unlink()
        except FileNotFoundError:
            pass
        raise
    return output_path, source_authority, admission_sha256


CheckpointKey = tuple[str, str, int]


def _checkpoint_key(record: Mapping[str, object]) -> CheckpointKey:
    return (
        cast(str, record["information_regime"]),
        cast(str, record["target_representation"]),
        cast(int, record["seed"]),
    )


def _run_id(record: Mapping[str, object]) -> str:
    regime, representation, seed = _checkpoint_key(record)
    return f"per_target_context_deepsets_mlp_v1|{regime}|{representation}|final_train|final|{seed}"


def _secure_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_mode & 0o077:
            raise ValueError("private fit evidence must be an exclusive owner-only regular file")
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
        after = os.fstat(stream.fileno())
        if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ValueError("private fit evidence changed while its identity was read")
    return digest.hexdigest()


def _verify_fit_receipt(
    receipt_directory: Path,
    record: Mapping[str, object],
) -> None:
    receipt_sha = cast(str, record["receipt_sha256"])
    path = receipt_directory / f"{receipt_sha}.json"
    if _secure_sha256(path) != receipt_sha:
        raise ValueError("completed-fit receipt SHA-256 mismatch")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        receipt = _mapping(
            json.loads(stream.read(), object_pairs_hook=_unique_object), "fit receipt"
        )
    expected = {
        "status": "completed",
        "fit_role": "final_train",
        "run_id": _run_id(record),
        "model_id": "per_target_context_deepsets_mlp_v1",
        "information_regime": record["information_regime"],
        "target_representation": record["target_representation"],
        "seed": record["seed"],
        "attempt_number": 1,
        "selected_step": record["selected_step"],
        "optimizer_steps": record["optimizer_steps"],
        "checkpoint_sha256": record["checkpoint_sha256"],
        "configuration_sha256": record["configuration_sha256"],
        "environment_sha256": record["environment_sha256"],
        "population_manifest_sha256": record["population_manifest_sha256"],
        "target_mask_identity_sha256": record["target_mask_identity_sha256"],
        "plan_sha256": record["plan_sha256"],
        "protocol_sha256": record["protocol_sha256"],
        "train_match_ids": record["train_match_ids"],
        "validation_match_ids": record["validation_match_ids"],
    }
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise ValueError("fit receipt differs from the frozen checkpoint manifest")


def load_frozen_models(
    checkpoint_directory: Path,
    receipt_directory: Path,
    manifest: Mapping[str, object],
) -> dict[CheckpointKey, PerTargetContextDeepSetsMLP]:
    """Load exactly the listed final checkpoints as frozen FP32 CPU models."""
    for directory in (checkpoint_directory, receipt_directory):
        info = directory.stat(follow_symlinks=False)
        if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
            raise ValueError("checkpoint and receipt directories must be owner-private")
    records = cast(list[dict[str, object]], _list(manifest["checkpoints"], "checkpoints"))
    models: dict[CheckpointKey, PerTargetContextDeepSetsMLP] = {}
    for record in records:
        _verify_fit_receipt(receipt_directory, record)
        digest = cast(str, record["checkpoint_sha256"])
        path = checkpoint_directory / f"{digest}.pt"
        if _secure_sha256(path) != digest:
            raise ValueError("checkpoint SHA-256 mismatch")
        payload = load_checkpoint_verified(path, digest)
        if set(payload) != {"metadata", "state_dict"}:
            raise ValueError("checkpoint cannot contain optimizer, warm-start, or extra state")
        metadata = _mapping(payload["metadata"], "checkpoint metadata")
        if (
            metadata.get("run_id") != _run_id(record)
            or metadata.get("configuration_sha256") != record["configuration_sha256"]
            or metadata.get("selected_step") != record["selected_step"]
            or metadata.get("attempt_number") != 1
        ):
            raise ValueError("checkpoint metadata differs from the frozen fit receipt")
        regime = cast(InformationRegime, record["information_regime"])
        model = PerTargetContextDeepSetsMLP(regime).cpu()
        state = _mapping(payload["state_dict"], "checkpoint state_dict")
        if not all(isinstance(value, Tensor) for value in state.values()):
            raise ValueError("checkpoint tensors differ from the frozen model structure")
        model.load_state_dict(cast(dict[str, Tensor], state), strict=True)
        if any(
            parameter.dtype != torch.float32 or not torch.isfinite(parameter).all()
            for parameter in model.parameters()
        ):
            raise ValueError("checkpoint must contain finite FP32 model parameters")
        model.eval()
        key = _checkpoint_key(record)
        if key in models:
            raise ValueError("checkpoint directory resolves duplicate frozen model cells")
        models[key] = model
    if len(models) != 18:
        raise ValueError("all 18 frozen models must load exactly once")
    return models


def _player_index(sample: Mapping[str, object]) -> dict[int, Mapping[str, object]]:
    validate_information_boundary(sample.keys())
    players = _list(sample.get("players"), "support players")
    result: dict[int, Mapping[str, object]] = {}
    for raw_player in players:
        player = _mapping(raw_player, "support player")
        validate_information_boundary(player.keys())
        player_id = player.get("player_id")
        if type(player_id) is not int or player_id in result:
            raise ValueError("support player IDs must be unique integers")
        if player.get("group") not in {"home", "away"}:
            raise ValueError("support player team membership differs")
        result[player_id] = player
    return result


def _xy(player: Mapping[str, object] | None) -> tuple[float, float] | None:
    if player is None:
        return None
    x, y = player.get("x_m"), player.get("y_m")
    if x is None and y is None:
        return None
    if x is None or y is None:
        raise ValueError("source coordinates must be finite metre-valued XY pairs or null")
    return _strict_float(x, "source x_m"), _strict_float(y, "source y_m")


def _integer_ids(value: object, label: str) -> tuple[int, ...]:
    values = _list(value, label)
    if any(type(item) is not int for item in values):
        raise ValueError(f"{label} must contain integer provider IDs")
    result = tuple(cast(int, item) for item in values)
    if not result or len(result) != len(set(result)):
        raise ValueError(f"{label} must contain unique IDs")
    return result


def _validate_truth_and_panel(
    scene: Mapping[str, object],
    *,
    side: str,
    support: Sequence[Mapping[str, object]],
    home_ids: Sequence[int],
    away_ids: Sequence[int],
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.bool_], str]:
    if scene.get("scene_id") != side:
        raise ValueError("directed scene order must remain home then away")
    player_ids_raw = _list(scene.get("player_ids"), "scene player panel")
    if any(not isinstance(value, str) or not value.isdecimal() for value in player_ids_raw):
        raise ValueError("frozen target player panel must use ordered provider IDs")
    target_ids = tuple(int(cast(str, value)) for value in player_ids_raw)
    origin_players = _player_index(support[25])
    expected_ids = tuple(
        player_id
        for player_id in sorted(origin_players)
        if origin_players[player_id].get("group") == side
        and _xy(origin_players[player_id]) is not None
    )
    if target_ids != expected_ids or len(target_ids) != TARGET_PLAYERS:
        raise ValueError("origin target-player panel or order differs from original v2")
    team_ids = set(home_ids if side == "home" else away_ids)
    if not set(target_ids).issubset(team_ids) or set(home_ids) & set(away_ids):
        raise ValueError("target panel differs from frozen match roster")
    absolute, displacement, mask = validate_truth_scene(scene)
    origins = cast(list[list[float]], scene["origin_xy"])
    if len(origins) != TARGET_PLAYERS:
        raise ValueError("origin panel differs from the frozen eleven-player target panel")
    for player_index, player_id in enumerate(target_ids):
        observed = _xy(origin_players[player_id])
        if any(
            isinstance(value, bool) or type(value) not in (int, float)
            for value in cast(list[object], origins[player_index])
        ):
            raise ValueError("target origins must be finite numeric XY pairs")
        if observed is None or any(
            not math.isclose(
                _strict_float(origins[player_index][axis], "target origin"),
                observed[axis],
                rel_tol=0,
                abs_tol=1e-12,
            )
            for axis in (0, 1)
        ):
            raise ValueError("target origin or target-player order differs from source")
    if tuple(absolute.shape) != (TARGET_PLAYERS, FUTURE_SAMPLES, 2):
        raise ValueError("absolute physical truth panel shape differs")
    if tuple(displacement.shape) != tuple(absolute.shape) or tuple(mask.shape) != (
        TARGET_PLAYERS,
        FUTURE_SAMPLES,
    ):
        raise ValueError("truth representation or mask shape differs")
    absolute_rows = cast(Sequence[Sequence[Sequence[float] | None]], scene["absolute_xy"])
    displacement_rows = cast(
        Sequence[Sequence[Sequence[float] | None]], scene["origin_relative_displacement"]
    )
    for representation, panel in (
        ("absolute_xy", absolute_rows),
        ("origin_relative_displacement", displacement_rows),
    ):
        expected_hash = truth_sha256(panel, target_representation=representation)
        key = (
            "absolute_xy_truth_sha256"
            if representation == "absolute_xy"
            else "displacement_truth_sha256"
        )
        if scene.get(key) != expected_hash:
            raise ValueError("truth panel identity differs from the source research manifest")
    mask_sha = truth_mask_sha256(absolute_rows)
    if scene.get("truth_mask_sha256") != mask_sha:
        raise ValueError("physical target mask identity differs from the frozen population")
    if type(scene.get("scoreable")) is not bool or scene["scoreable"] != bool(mask[:, -1].any()):
        raise ValueError("scene scoreability differs from the frozen final-target rule")
    return absolute, displacement, mask, mask_sha


def _quality_stratum(
    support: Sequence[Mapping[str, object]],
    player_ids: Sequence[int],
) -> str:
    detected: list[bool] = []
    missing_flag = False
    for sample in support[26:]:
        players = _player_index(sample)
        for player_id in player_ids:
            player = players.get(player_id)
            if player is None or _xy(player) is None:
                continue
            flag = player.get("is_detected")
            if type(flag) is bool:
                detected.append(flag)
            elif flag is None:
                missing_flag = True
            else:
                raise ValueError("source quality flags must be Boolean or null")
    if any(not value for value in detected):
        return "with_provider_extrapolation"
    if not detected or missing_flag:
        return "unclassified"
    return "detected_only"


def _metric(
    prediction: NDArray[np.float64],
    truth: NDArray[np.float64],
    mask: NDArray[np.bool_],
    *,
    start: int = 0,
    stop: int = FUTURE_SAMPLES,
) -> MaskedTrajectoryMetrics:
    prediction_time_major = np.transpose(prediction[:, start:stop, :], (1, 0, 2))
    predicted_time_major: list[list[list[float]]] = [
        [
            [float(prediction_time_major[time_index, player_index, axis]) for axis in (0, 1)]
            for player_index in range(TARGET_PLAYERS)
        ]
        for time_index in range(stop - start)
    ]
    truth_time_major: list[list[list[float] | None]] = []
    for time_index in range(start, stop):
        truth_time_major.append(
            [
                [float(truth[player, time_index, axis]) for axis in (0, 1)]
                if mask[player, time_index]
                else None
                for player in range(TARGET_PLAYERS)
            ]
        )
    return masked_physical_trajectory_metrics(
        (predicted_time_major,), (truth_time_major,), scale_xy_m=(1.0, 1.0)
    )


def reconstruct_physical_prediction(
    prediction: NDArray[np.float64],
    representation: TargetRepresentation,
    origin_xy: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Convert the frozen target frame to absolute source XY metres for scoring."""
    if (
        prediction.shape != (TARGET_PLAYERS, FUTURE_SAMPLES, 2)
        or origin_xy.shape != (TARGET_PLAYERS, 2)
        or not np.isfinite(prediction).all()
        or not np.isfinite(origin_xy).all()
    ):
        raise ValueError("prediction and origin must be finite frozen eleven-player XY panels")
    if representation == "absolute_xy":
        return prediction
    if representation == "origin_relative_displacement":
        return prediction + origin_xy[:, None, :]
    raise ValueError("unknown frozen target representation")


@dataclass(slots=True)
class WindowMetricAccumulator:
    """Equal-window aggregation with separately retained scoreable denominators."""

    ade_sum: float = 0.0
    fde_sum: float = 0.0
    rmse_sum: float = 0.0
    windows: int = 0
    scenes: int = 0
    points: int = 0
    final_targets: int = 0

    def add_window(self, metrics: Sequence[MaskedTrajectoryMetrics]) -> None:
        if not metrics:
            raise ValueError("a scoreable evaluation window must contain a target scene")
        self.ade_sum += math.fsum(item.ade_m for item in metrics) / len(metrics)
        self.fde_sum += math.fsum(item.fde_m for item in metrics) / len(metrics)
        self.rmse_sum += math.fsum(item.xy_rmse_m for item in metrics) / len(metrics)
        self.windows += 1
        self.scenes += len(metrics)
        self.points += sum(item.scored_points for item in metrics)
        self.final_targets += sum(item.final_targets for item in metrics)

    def mean(self) -> dict[str, float]:
        if not self.windows:
            raise ValueError("match contains zero scoreable windows")
        return {
            "ade_m": self.ade_sum / self.windows,
            "fde_m": self.fde_sum / self.windows,
            "xy_rmse_m": self.rmse_sum / self.windows,
        }


def _validate_window_record(
    row: Mapping[str, object],
    *,
    expected_source_sha256: str,
) -> tuple[
    str,
    str,
    Sequence[Mapping[str, object]],
    tuple[int, ...],
    tuple[int, ...],
    list[dict[str, object]],
]:
    match_id = row.get("match_id")
    origin_id = row.get("origin_sample_id")
    if (
        not isinstance(match_id, str)
        or match_id not in _MATCH_INDEX
        or row.get("role") != "evaluation"
        or not isinstance(origin_id, str)
        or row.get("window_id") != prospective_window_id_v2(match_id, origin_id)
        or row.get("source_match_sha256") != expected_source_sha256
    ):
        raise ValueError("evaluation role, source identity, or v2 window identity differs")
    times = _list(row.get("time_offsets_s"), "window time offsets")
    expected_times = [round(-5.0 + 0.2 * index, 10) for index in range(41)]
    if len(times) != 41 or any(
        type(value) not in (int, float)
        or not math.isclose(_strict_float(value, "window time offset"), expected, abs_tol=1e-9)
        for value, expected in zip(times, expected_times, strict=True)
    ):
        raise ValueError("window must preserve the 26 history/origin and 15 future intervals")
    support_raw = _list(row.get("support"), "window support")
    if len(support_raw) != 41:
        raise ValueError("window support must contain exactly 41 samples")
    support = tuple(_mapping(sample, "support sample") for sample in support_raw)
    if any("players" not in sample or "ball" not in sample for sample in support):
        raise ValueError("every source sample must preserve the frozen player and ball channels")
    for sample in support:
        validate_information_boundary(sample.keys())
        for raw_player in _list(sample["players"], "support players"):
            validate_information_boundary(_mapping(raw_player, "support player").keys())
    sample_ids = _list(row.get("support_sample_ids"), "support sample identities")
    if (
        len(sample_ids) != 41
        or any(not isinstance(value, str) for value in sample_ids)
        or sample_ids[25] != origin_id
    ):
        raise ValueError("support sample identities do not bind the forecast origin")
    home_ids = _integer_ids(row.get("home_player_ids"), "home player IDs")
    away_ids = _integer_ids(row.get("away_player_ids"), "away player IDs")
    if set(home_ids) & set(away_ids):
        raise ValueError("home and away rosters overlap")
    scenes_raw = _list(row.get("scenes"), "window scenes")
    if len(scenes_raw) != 2:
        raise ValueError("each evaluation window must contain its home and away panels")
    scenes = [_mapping(scene, "directed scene") for scene in scenes_raw]
    if [scene.get("scene_id") for scene in scenes] != ["home", "away"]:
        raise ValueError("directed scene order differs from original v2")
    return (
        match_id,
        cast(str, row["window_id"]),
        support,
        home_ids,
        away_ids,
        scenes,
    )


def _score_window(
    row: Mapping[str, object],
    models: Mapping[CheckpointKey, PerTargetContextDeepSetsMLP],
    manifest: Mapping[str, object],
    source_sha256: str,
    accumulators: Mapping[tuple[str, str, int, str], WindowMetricAccumulator],
    window_seen: dict[str, set[str]],
    mask_digest: dict[str, DigestWriter],
    window_digest: dict[str, DigestWriter],
    quality_accumulators: Mapping[tuple[str, str, int, str, str], WindowMetricAccumulator],
    horizon_accumulators: Mapping[tuple[str, str, int, str, str], WindowMetricAccumulator],
) -> None:
    match_id, window_id, support, home_ids, away_ids, scenes = _validate_window_record(
        row, expected_source_sha256=source_sha256
    )
    if window_id in window_seen[match_id]:
        raise ValueError("duplicate evaluation window identity")
    window_seen[match_id].add(window_id)
    window_digest[match_id].update(
        canonical_bytes({"origin_sample_id": row["origin_sample_id"], "window_id": window_id})
        + b"\n"
    )
    validated_scenes: list[dict[str, object]] = []
    for scene, side in zip(scenes, ("home", "away"), strict=True):
        absolute, _displacement, truth_mask, mask_sha = _validate_truth_and_panel(
            scene, side=side, support=support, home_ids=home_ids, away_ids=away_ids
        )
        mask_digest[match_id].update(
            canonical_bytes(
                {"scene_id": side, "truth_mask_sha256": mask_sha, "window_id": window_id}
            )
            + b"\n"
        )
        validated_scenes.append(
            {
                "scene": scene,
                "side": side,
                "player_ids": tuple(int(value) for value in cast(list[str], scene["player_ids"])),
                "absolute": absolute,
                "mask": truth_mask,
                "mask_sha": mask_sha,
                "origin": np.asarray(cast(list[list[float]], scene["origin_xy"]), dtype=np.float64),
                "scoreable": bool(truth_mask[:, -1].any()),
                "quality": _quality_stratum(
                    support,
                    tuple(int(value) for value in cast(list[str], scene["player_ids"])),
                ),
            }
        )
    scoreable = [scene for scene in validated_scenes if scene["scoreable"]]
    if not scoreable:
        raise ValueError("evaluation input contains an eligible window with zero final targets")

    checkpoint_records = cast(
        list[dict[str, object]], _list(manifest["checkpoints"], "checkpoints")
    )
    for regime in INFORMATION_REGIMES:
        payloads = [
            build_scene_feature_payload(
                support,
                target_side=cast("Literal['home', 'away']", cast(str, scene["side"])),
                target_player_ids=cast(tuple[int, ...], scene["player_ids"]),
                home_player_ids=home_ids,
                away_player_ids=away_ids,
                regime=regime,
            )
            for scene in scoreable
        ]
        for payload in payloads:
            validate_feature_payload(payload, regime)
        inputs = collate_feature_payloads(payloads, regime)
        float_tensors = (
            inputs.target_history,
            inputs.history_team_tracks,
            inputs.history_ball,
            inputs.target_side,
            inputs.future_ball,
            inputs.future_opponent_tracks,
        )
        if any(
            tensor.dtype != torch.float32 for tensor in float_tensors if isinstance(tensor, Tensor)
        ):
            raise ValueError("held-out inference inputs must be FP32")
        boolean_tensors = (inputs.history_team_mask, inputs.future_opponent_mask)
        if any(
            tensor.dtype != torch.bool for tensor in boolean_tensors if isinstance(tensor, Tensor)
        ):
            raise ValueError("held-out source observation masks must remain Boolean")
        matching_records = [
            record for record in checkpoint_records if record["information_regime"] == regime
        ]
        for record in matching_records:
            key = _checkpoint_key(record)
            model = models[key]
            with torch.inference_mode():
                outputs = model(inputs).cpu().numpy().astype(np.float64)
            if outputs.shape != (len(scoreable), TARGET_PLAYERS, FUTURE_SAMPLES, 2):
                raise ValueError("model output differs from the frozen scene/panel shape")
            if not np.isfinite(outputs).all():
                raise FloatingPointError("model emitted a non-finite prediction")
            representation = cast(TargetRepresentation, record["target_representation"])
            scene_metrics: list[MaskedTrajectoryMetrics] = []
            seed_quality_metrics: dict[str, list[MaskedTrajectoryMetrics]] = defaultdict(list)
            seed_horizon_metrics: dict[str, list[MaskedTrajectoryMetrics]] = defaultdict(list)
            for scene_index, scene in enumerate(scoreable):
                origin = cast(NDArray[np.float64], scene["origin"])
                physical = reconstruct_physical_prediction(
                    outputs[scene_index], representation, origin
                )
                metric = _metric(
                    physical,
                    cast(NDArray[np.float64], scene["absolute"]),
                    cast(NDArray[np.bool_], scene["mask"]),
                )
                scene_metrics.append(metric)
                quality = cast(str, scene["quality"])
                if quality in {"detected_only", "with_provider_extrapolation", "unclassified"}:
                    seed_quality_metrics[quality].append(metric)
                for stratum, start, stop in (
                    ("early_0.2_1.0s", 0, 5),
                    ("middle_1.2_2.0s", 5, 10),
                    ("late_2.2_3.0s", 10, 15),
                ):
                    try:
                        seed_horizon_metrics[stratum].append(
                            _metric(
                                physical,
                                cast(NDArray[np.float64], scene["absolute"]),
                                cast(NDArray[np.bool_], scene["mask"]),
                                start=start,
                                stop=stop,
                            )
                        )
                    except ValueError as exc:
                        if str(exc) not in {
                            "trajectories contain no valid truth targets",
                            "trajectories contain no valid final-horizon targets",
                        }:
                            raise
            accumulator = accumulators[(*key, match_id)]
            accumulator.add_window(scene_metrics)
            for stratum, values in seed_quality_metrics.items():
                quality_accumulators[(*key, match_id, stratum)].add_window(values)
            for stratum, values in seed_horizon_metrics.items():
                if values:
                    horizon_accumulators[(*key, match_id, stratum)].add_window(values)


def _expected_result_keys(
    manifest: Mapping[str, object],
) -> set[tuple[str, str, int, str]]:
    records = cast(list[dict[str, object]], _list(manifest["checkpoints"], "checkpoints"))
    return {(*_checkpoint_key(record), match_id) for record in records for match_id in _MATCHES}


def validate_result_matrix(
    records: Sequence[Mapping[str, object]], manifest: Mapping[str, object]
) -> None:
    """Require the complete, nonduplicated 18-cell by four-match matrix."""
    expected = _expected_result_keys(manifest)
    by_identity: dict[tuple[str, str, int, str], Mapping[str, object]] = {}
    fit_records = cast(list[dict[str, object]], _list(manifest["checkpoints"], "checkpoints"))
    checkpoint_by_key = {_checkpoint_key(row): row for row in fit_records}
    denominators_by_match: dict[str, dict[str, int]] = {}
    mask_by_match: dict[str, str] = {}
    windows_by_match: dict[str, str] = {}
    for record in records:
        if record.get("model_id") != "per_target_context_deepsets_mlp_v1":
            raise ValueError("result contains an unexpected model")
        regime, representation, seed, match_id = (
            record.get("information_regime"),
            record.get("target_representation"),
            record.get("seed"),
            record.get("evaluation_match_id"),
        )
        if (
            not isinstance(regime, str)
            or regime not in INFORMATION_REGIMES
            or not isinstance(representation, str)
            or representation not in TARGET_REPRESENTATIONS
            or type(seed) is not int
            or seed not in SEEDS
            or not isinstance(match_id, str)
            or match_id not in _MATCH_INDEX
        ):
            raise ValueError("result matrix contains an unexpected model, seed, or match")
        key = (regime, representation, seed, match_id)
        if key in by_identity:
            raise ValueError("result matrix contains a duplicate model/seed/match record")
        frozen_fit = checkpoint_by_key[(regime, representation, seed)]
        if (
            record.get("checkpoint_sha256") != frozen_fit["checkpoint_sha256"]
            or record.get("completed_fit_receipt_sha256") != frozen_fit["receipt_sha256"]
            or record.get("configuration_sha256") != frozen_fit["configuration_sha256"]
            or record.get("selected_step") != frozen_fit["selected_step"]
        ):
            raise ValueError("result checkpoint, receipt, or configuration differs from frozen fit")
        if record.get("target_representation") != representation:
            raise ValueError("result target representation differs from the frozen cell")
        metrics = _mapping(record.get("metrics"), "result metrics")
        if any(
            type(metrics.get(name)) not in (int, float) or _strict_float(metrics[name], name) < 0
            for name in ("ade_m", "fde_m", "xy_rmse_m")
        ):
            raise ValueError("result metrics must be finite and nonnegative")
        denominators = _mapping(record.get("denominators"), "result denominators")
        if any(
            type(denominators.get(name)) is not int or cast(int, denominators[name]) <= 0
            for name in ("windows", "scoreable_scenes", "scored_points", "final_targets")
        ):
            raise ValueError("result scoreability denominators must be positive integers")
        normalized_denominators = {
            name: cast(int, denominators[name])
            for name in ("windows", "scoreable_scenes", "scored_points", "final_targets")
        }
        previous_denominators = denominators_by_match.setdefault(match_id, normalized_denominators)
        if previous_denominators != normalized_denominators:
            raise ValueError("scoreability denominators differ across matched model cells")
        if record.get("role") != "evaluation" or record.get("unit") != "metres":
            raise ValueError("result role or physical metric unit differs")
        if record.get("authority_scope") != "research-only-amended-heldout":
            raise ValueError("result entered through an unexpected or protected scoring authority")
        mask_sha = _sha(record.get("evaluated_mask_sha256"), "evaluated mask identity")
        window_sha = _sha(record.get("window_identity_sha256"), "window identity")
        if mask_by_match.setdefault(match_id, mask_sha) != mask_sha:
            raise ValueError("physical target mask identity differs across matched cells")
        if windows_by_match.setdefault(match_id, window_sha) != window_sha:
            raise ValueError("evaluation window identity differs across matched cells")
        _sha(record.get("source_match_sha256"), "source match identity")
        _sha(record.get("population_stream_sha256"), "population producer identity")
        _sha(record.get("evaluation_input_sha256"), "evaluation input identity")
        _sha(record.get("result_receipt_sha256"), "result receipt identity")
        by_identity[key] = record
    if set(by_identity) != expected or len(records) != 72:
        raise ValueError(
            "result matrix is incomplete; exactly 72 match-scoped records are required"
        )


def aggregate_results(
    records: Sequence[Mapping[str, object]],
    manifest: Mapping[str, object],
    baseline: Mapping[str, object],
) -> dict[str, object]:
    """Return the frozen equal-seed-within-match, equal-match analysis."""
    validate_result_matrix(records, manifest)
    index = {
        (
            cast(str, record["information_regime"]),
            cast(str, record["target_representation"]),
            cast(int, record["seed"]),
            cast(str, record["evaluation_match_id"]),
        ): record
        for record in records
    }
    summaries: list[dict[str, object]] = []
    for regime in INFORMATION_REGIMES:
        for representation in TARGET_REPRESENTATIONS:
            seed_match_means: dict[int, dict[str, dict[str, float]]] = {}
            match_means: dict[str, dict[str, float]] = {}
            seed_overall: dict[str, list[float]] = {
                metric: [] for metric in ("ade_m", "fde_m", "xy_rmse_m")
            }
            for seed in SEEDS:
                per_match: dict[str, dict[str, float]] = {}
                for match_id in _MATCHES:
                    record = index[(regime, representation, seed, match_id)]
                    values = _mapping(record["metrics"], "record metrics")
                    per_match[match_id] = {
                        metric: _strict_float(values[metric], f"result {metric}")
                        for metric in ("ade_m", "fde_m", "xy_rmse_m")
                    }
                seed_match_means[seed] = per_match
                for metric in seed_overall:
                    seed_overall[metric].append(
                        math.fsum(per_match[match][metric] for match in _MATCHES) / len(_MATCHES)
                    )
            for match_id in _MATCHES:
                match_means[match_id] = {
                    metric: math.fsum(seed_match_means[seed][match_id][metric] for seed in SEEDS)
                    / len(SEEDS)
                    for metric in ("ade_m", "fde_m", "xy_rmse_m")
                }
            aggregate = {
                metric: math.fsum(match_means[match][metric] for match in _MATCHES) / len(_MATCHES)
                for metric in ("ade_m", "fde_m", "xy_rmse_m")
            }
            seed_variation = {
                metric: {
                    "seed_values": {
                        str(seed): seed_overall[metric][index_seed]
                        for index_seed, seed in enumerate(SEEDS)
                    },
                    "sample_sd_across_three_seed_means": _sample_sd(seed_overall[metric]),
                }
                for metric in ("ade_m", "fde_m", "xy_rmse_m")
            }
            deletion = {
                metric: {
                    match_id: math.fsum(
                        match_means[other][metric] for other in _MATCHES if other != match_id
                    )
                    / (len(_MATCHES) - 1)
                    for match_id in _MATCHES
                }
                for metric in ("ade_m", "fde_m", "xy_rmse_m")
            }
            summaries.append(
                {
                    "model_id": "per_target_context_deepsets_mlp_v1",
                    "information_regime": regime,
                    "target_representation": representation,
                    "aggregation": aggregate,
                    "match_seed_means": match_means,
                    "individual_seed_match_values": {
                        str(seed): seed_match_means[seed] for seed in SEEDS
                    },
                    "seed_variation": seed_variation,
                    "evaluation_match_deletion_sensitivity": deletion,
                }
            )

    by_cell: dict[tuple[str, str], dict[str, object]] = {
        (str(row["information_regime"]), str(row["target_representation"])): row
        for row in summaries
    }
    contrasts: list[dict[str, object]] = []
    for contrast_id, left_regime, right_regime in (
        ("C1", "history_only", "future_ball"),
        ("C2", "future_ball", "future_opponent_plus_ball"),
    ):
        for representation in TARGET_REPRESENTATIONS:
            left = by_cell[(left_regime, representation)]
            right = by_cell[(right_regime, representation)]
            left_matches = cast(dict[str, dict[str, float]], left["match_seed_means"])
            right_matches = cast(dict[str, dict[str, float]], right["match_seed_means"])
            values = {
                match_id: left_matches[match_id]["ade_m"] - right_matches[match_id]["ade_m"]
                for match_id in _MATCHES
            }
            contrasts.append(
                {
                    "contrast": contrast_id,
                    "target_representation": representation,
                    "formula": (
                        "history_only ADE - future_ball ADE"
                        if contrast_id == "C1"
                        else "future_ball ADE - future_opponent_plus_ball ADE"
                    ),
                    "match_values_m": values,
                    "equal_match_mean_m": math.fsum(values.values()) / len(_MATCHES),
                    "positive_means_lower_error_with_added_realized_context": True,
                }
            )

    baseline_models = _mapping(baseline.get("models"), "baseline models")
    paired_baselines: list[dict[str, object]] = []
    for summary in summaries:
        match_means = cast(dict[str, dict[str, float]], summary["match_seed_means"])
        for baseline_model, raw_values in baseline_models.items():
            baseline_values = _mapping(raw_values, "baseline match metrics")
            differences: dict[str, dict[str, float]] = {
                metric: {} for metric in ("ade_m", "fde_m", "xy_rmse_m")
            }
            for match_id in _MATCHES:
                baseline_match = _mapping(baseline_values[match_id], "baseline metric record")
                for metric in differences:
                    differences[metric][match_id] = match_means[match_id][metric] - _strict_float(
                        baseline_match[metric], f"baseline {metric}"
                    )
            paired_baselines.append(
                {
                    "information_regime": summary["information_regime"],
                    "target_representation": summary["target_representation"],
                    "baseline_model": baseline_model,
                    "learned_minus_baseline": differences,
                    "equal_match_means_m": {
                        metric: math.fsum(values.values()) / len(_MATCHES)
                        for metric, values in differences.items()
                    },
                    "baseline_manifest_status": baseline.get("status"),
                    "comparability": _BASELINE_COMPARABILITY,
                }
            )
    return {
        "configuration_summaries": summaries,
        "frozen_contrasts": contrasts,
        "paired_deterministic_baseline_comparisons": paired_baselines,
        "independent_match_count": 4,
        "inferential_tests_performed": False,
        "overlapping_windows_treated_as_independent": False,
        "deletion_diagnostic_label": "evaluation-match deletion sensitivity",
    }


def _sample_sd(values: Sequence[float]) -> float:
    if len(values) < 2:
        raise ValueError("sample standard deviation requires at least two seed values")
    mean = math.fsum(values) / len(values)
    return math.sqrt(math.fsum((value - mean) ** 2 for value in values) / (len(values) - 1))


def _runtime_manifest(module_path: Path) -> dict[str, object]:
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pytorch": torch.__version__,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "logical_cpu_count": os.cpu_count(),
        "device": "cpu",
        "precision": "float32",
        "torch_threads": torch.get_num_threads(),
        "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
        "scorer_source_sha256": hashlib.sha256(module_path.read_bytes()).hexdigest(),
        "scorer_code_identity_sha256": _scorer_code_identity_sha256(),
        "cuda_used": False,
        "optimizer_steps": 0,
    }


def _set_cpu_inference_runtime() -> None:
    if (
        platform.python_version() != "3.12.8"
        or np.__version__ != "2.2.4"
        or torch.__version__ != "2.6.0+cpu"
    ):
        raise RuntimeError(
            "held-out inference requires Python 3.12.8, NumPy 2.2.4, and PyTorch 2.6.0+cpu"
        )
    torch.set_num_threads(1)
    if torch.get_num_interop_threads() != 1:
        torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision("highest")
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False


def _new_accumulators(
    manifest: Mapping[str, object],
) -> tuple[
    dict[tuple[str, str, int, str], WindowMetricAccumulator],
    dict[tuple[str, str, int, str, str], WindowMetricAccumulator],
    dict[tuple[str, str, int, str, str], WindowMetricAccumulator],
]:
    base: dict[tuple[str, str, int, str], WindowMetricAccumulator] = {}
    quality: dict[tuple[str, str, int, str, str], WindowMetricAccumulator] = {}
    horizon: dict[tuple[str, str, int, str, str], WindowMetricAccumulator] = {}
    for record in cast(list[dict[str, object]], _list(manifest["checkpoints"], "checkpoints")):
        key = _checkpoint_key(record)
        for match_id in _MATCHES:
            base[(*key, match_id)] = WindowMetricAccumulator()
            for stratum in ("detected_only", "with_provider_extrapolation", "unclassified"):
                quality[(*key, match_id, stratum)] = WindowMetricAccumulator()
            for stratum in ("early_0.2_1.0s", "middle_1.2_2.0s", "late_2.2_3.0s"):
                horizon[(*key, match_id, stratum)] = WindowMetricAccumulator()
    return base, quality, horizon


def _write_private_json(path: Path, document: Mapping[str, object]) -> str:
    raw = (
        json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode(
            "utf-8"
        )
        + b"\n"
    )
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(raw).hexdigest()


def _receipt_body(record: Mapping[str, object]) -> dict[str, object]:
    body = dict(record)
    body.pop("result_receipt_sha256", None)
    return body


def _build_result_records(
    manifest: Mapping[str, object],
    baseline: Mapping[str, object],
    accumulators: Mapping[tuple[str, str, int, str], WindowMetricAccumulator],
    quality_accumulators: Mapping[tuple[str, str, int, str, str], WindowMetricAccumulator],
    horizon_accumulators: Mapping[tuple[str, str, int, str, str], WindowMetricAccumulator],
    window_identities: Mapping[str, str],
    mask_identities: Mapping[str, str],
    source_identities: Mapping[str, str],
    population_stream_identities: Mapping[str, str],
    input_sha256: str,
    source_verification_sha256: str,
    runtime: Mapping[str, object],
    amendment_sha256: str,
    manifest_sha256: str,
) -> list[dict[str, object]]:
    baseline_counts = _mapping(baseline["scored_denominators"], "baseline denominators")
    records: list[dict[str, object]] = []
    for fit in cast(list[dict[str, object]], _list(manifest["checkpoints"], "checkpoints")):
        regime, representation, seed = _checkpoint_key(fit)
        for match_id in _MATCHES:
            key = (regime, representation, seed, match_id)
            accumulator = accumulators[key]
            expected_counts = _mapping(baseline_counts[match_id], "baseline match denominators")
            actual_counts = {
                "windows": accumulator.windows,
                "scenes": accumulator.scenes,
                "scored_points": accumulator.points,
                "final_targets": accumulator.final_targets,
            }
            if actual_counts != {
                "windows": expected_counts["windows"],
                "scenes": expected_counts["scenes"],
                "scored_points": expected_counts["scored_points"],
                "final_targets": expected_counts["final_targets"],
            }:
                raise ValueError(
                    f"scoreable denominators differ from frozen population for {match_id}"
                )
            metrics = accumulator.mean()
            record: dict[str, object] = {
                "schema_id": "fpdbench.res594.match-result",
                "schema_version": "1.0.0",
                "study_id": _STUDY_ID,
                "authority_scope": "research-only-amended-heldout",
                "role": "evaluation",
                "model_id": cast(str, fit["model_id"]),
                "information_regime": regime,
                "target_representation": representation,
                "seed": seed,
                "evaluation_match_id": match_id,
                "checkpoint_sha256": fit["checkpoint_sha256"],
                "completed_fit_receipt_sha256": fit["receipt_sha256"],
                "configuration_sha256": fit["configuration_sha256"],
                "selected_step": fit["selected_step"],
                "metrics": metrics,
                "unit": "metres",
                "denominators": {
                    "windows": accumulator.windows,
                    "scoreable_scenes": accumulator.scenes,
                    "scored_points": accumulator.points,
                    "final_targets": accumulator.final_targets,
                },
                "target_mask_identity_sha256": fit["target_mask_identity_sha256"],
                "evaluated_mask_sha256": mask_identities[match_id],
                "window_identity_sha256": window_identities[match_id],
                "population_identity_sha256": "a8c82bfa09ac792d6c4ae779d4b28158c33ed3c2500f8548f3e94d48197f4fd1",
                "source_match_sha256": source_identities[match_id],
                "population_stream_sha256": population_stream_identities[match_id],
                "source_verification_sha256": source_verification_sha256,
                "evaluation_input_sha256": input_sha256,
                "amendment_sha256": amendment_sha256,
                "checkpoint_manifest_sha256": manifest_sha256,
                "scorer_code_sha256": runtime["scorer_code_identity_sha256"],
                "runtime": dict(runtime),
                "scorer_provenance": {
                    "module_sha256": runtime["scorer_source_sha256"],
                    "metric_ids": {
                        "ade": ADE_METRIC_ID,
                        "fde": FDE_METRIC_ID,
                        "xy_rmse": XY_RMSE_METRIC_ID,
                    },
                    "metric_function": "masked_physical_trajectory_metrics",
                    "aggregation": "equal scene within window, equal windows within match",
                },
                "quality_strata": {
                    stratum: _optional_window_metrics(quality_accumulators[(*key, stratum)])
                    for stratum in ("detected_only", "with_provider_extrapolation", "unclassified")
                },
                "horizon_strata": {
                    stratum: _optional_window_metrics(horizon_accumulators[(*key, stratum)])
                    for stratum in ("early_0.2_1.0s", "middle_1.2_2.0s", "late_2.2_3.0s")
                },
            }
            record["result_receipt_sha256"] = hashlib.sha256(canonical_bytes(record)).hexdigest()
            records.append(record)
    validate_result_matrix(records, manifest)
    return records


def _optional_window_metrics(accumulator: WindowMetricAccumulator) -> dict[str, object]:
    if not accumulator.windows:
        return {
            "status": "not_scoreable",
            "windows": 0,
            "scoreable_scenes": 0,
            "scored_points": 0,
            "final_targets": 0,
            "metrics": None,
        }
    return {
        "status": "scoreable",
        "windows": accumulator.windows,
        "scoreable_scenes": accumulator.scenes,
        "scored_points": accumulator.points,
        "final_targets": accumulator.final_targets,
        "metrics": accumulator.mean(),
    }


def _reserve_campaign(output_directory: Path, owner: OwnerAuthorization) -> Path:
    if output_directory.exists() or output_directory.is_symlink():
        raise FileExistsError(
            "held-out campaign output already exists; repeated execution is locked"
        )
    output_directory.mkdir(mode=0o700, parents=True)
    marker = {
        "schema_id": "fpdbench.res594.campaign-started",
        "amendment_sha256": owner.amendment_sha256,
        "checkpoint_manifest_sha256": owner.checkpoint_manifest_sha256,
        "scorer_code_sha256": owner.scorer_code_sha256,
        "research_admission_sha256": owner.document["research_admission_sha256"],
        "evaluation_input_sha256": owner.evaluation_input_sha256,
        "started": True,
    }
    _write_private_json(output_directory / ".started.json", marker)
    return output_directory


def _write_failure_marker(output_directory: Path, exc: BaseException) -> None:
    failure = {
        "schema_id": "fpdbench.res594.campaign-failed",
        "status": "FAILED_OR_PARTIAL",
        "error_type": type(exc).__name__,
        "error": str(exc)[:400],
        "retry_allowed": False,
    }
    path = output_directory / ".failed.json"
    if not path.exists():
        try:
            _write_private_json(path, failure)
        except OSError:
            pass


def _check_resource_limits(start_cpu: float, start_wall: float) -> None:
    cpu = time.process_time() - start_cpu
    wall = time.monotonic() - start_wall
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_bytes = rss if sys.platform == "darwin" else rss * 1024
    if cpu > _RESOURCE_LIMITS["cpu_seconds"]:
        raise TimeoutError("held-out CPU-time ceiling exceeded")
    if wall > _RESOURCE_LIMITS["wall_seconds"]:
        raise TimeoutError("held-out wall-time ceiling exceeded")
    if rss_bytes > _RESOURCE_LIMITS["rss_bytes"]:
        raise MemoryError("held-out RSS ceiling exceeded")


def _score_authorized_snapshot(
    snapshot: Path,
    output_directory: Path,
    *,
    owner: OwnerAuthorization,
    manifest: Mapping[str, object],
    manifest_sha256: str,
    baseline: Mapping[str, object],
    models: Mapping[CheckpointKey, PerTargetContextDeepSetsMLP],
    module_path: Path,
    source_authority: Mapping[str, object],
    campaign_start_cpu: float,
    campaign_start_wall: float,
) -> dict[str, object]:
    records_iter = _read_json_lines(snapshot)
    try:
        header = next(records_iter)
    except StopIteration as exc:
        raise ValueError("evaluation input is empty") from exc
    identities = _validate_input_header(
        header,
        amendment_sha256=owner.amendment_sha256,
        checkpoint_manifest_sha256=manifest_sha256,
        source_authority=source_authority,
    )
    if owner.evaluation_input_sha256 is None:
        raise PermissionError("held-out evaluation input was not bound after source verification")
    evaluation_input_sha256 = owner.evaluation_input_sha256
    accumulators, quality_accumulators, horizon_accumulators = _new_accumulators(manifest)
    window_seen: dict[str, set[str]] = {match_id: set() for match_id in _MATCHES}
    mask_digest: dict[str, DigestWriter] = {match_id: hashlib.sha256() for match_id in _MATCHES}
    window_digest: dict[str, DigestWriter] = {match_id: hashlib.sha256() for match_id in _MATCHES}
    for row in records_iter:
        if row.get("kind") != "window":
            raise ValueError("evaluation input contains an unexpected record kind")
        match_id = row.get("match_id")
        if not isinstance(match_id, str) or match_id not in _MATCH_INDEX:
            raise ValueError("evaluation input contains a non-evaluation match")
        _score_window(
            row,
            models,
            manifest,
            cast(
                str,
                cast(dict[str, object], identities["source_match_sha256_by_match"])[match_id],
            ),
            accumulators,
            window_seen,
            mask_digest,
            window_digest,
            quality_accumulators,
            horizon_accumulators,
        )
        _check_resource_limits(campaign_start_cpu, campaign_start_wall)
    expected_counts = cast(dict[str, object], identities["expected_scoreable_window_counts"])
    mask_identities: dict[str, str] = {}
    window_identities: dict[str, str] = {}
    source_identities = cast(dict[str, str], identities["source_match_sha256_by_match"])
    population_stream_identities = cast(
        dict[str, str], identities["producer_stream_sha256_by_match"]
    )
    for match_id in _MATCHES:
        expected_count = _strict_int(expected_counts[match_id], "evaluation window count")
        if len(window_seen[match_id]) != expected_count:
            raise ValueError(f"evaluation window count differs for match {match_id}")
        mask_identities[match_id] = mask_digest[match_id].hexdigest()
        window_identities[match_id] = window_digest[match_id].hexdigest()
        expected_mask_sha = cast(dict[str, object], identities["mask_identity_sha256_by_match"])[
            match_id
        ]
        expected_window_sha = cast(
            dict[str, object], identities["window_identity_sha256_by_match"]
        )[match_id]
        if mask_identities[match_id] != expected_mask_sha:
            raise ValueError(f"evaluation physical-mask digest differs for match {match_id}")
        if window_identities[match_id] != expected_window_sha:
            raise ValueError(f"evaluation window-identity digest differs for match {match_id}")

    runtime = _runtime_manifest(module_path)
    if runtime.get("scorer_code_identity_sha256") != owner.scorer_code_sha256:
        raise ValueError("held-out scorer code changed after explicit owner authorization")
    records = _build_result_records(
        manifest,
        baseline,
        accumulators,
        quality_accumulators,
        horizon_accumulators,
        window_identities,
        mask_identities,
        source_identities,
        population_stream_identities,
        evaluation_input_sha256,
        cast(str, identities["source_verification_sha256"]),
        runtime,
        owner.amendment_sha256,
        manifest_sha256,
    )
    analysis = aggregate_results(records, manifest, baseline)
    campaign: dict[str, object] = {
        "schema_id": "fpdbench.res594.heldout-campaign-result",
        "schema_version": "1.0.0",
        "study_id": _STUDY_ID,
        "status": "COMPLETED",
        "authority_scope": "research-only-amended-heldout",
        "amendment_sha256": owner.amendment_sha256,
        "checkpoint_manifest_sha256": manifest_sha256,
        "scorer_code_sha256": owner.scorer_code_sha256,
        "evaluation_input_sha256": owner.evaluation_input_sha256,
        "research_admission_sha256": "a8c82bfa09ac792d6c4ae779d4b28158c33ed3c2500f8548f3e94d48197f4fd1",
        "role": "evaluation",
        "evaluation_match_ids": list(_MATCHES),
        "expected_record_count": 72,
        "optimizer_steps": 0,
        "protected_status": "NOT_QUALIFIED",
        "result_receipts": [],
        "analysis": analysis,
        "runtime": runtime,
        "baseline_reference_status": baseline.get("status"),
        "baseline_comparability": _BASELINE_COMPARABILITY,
    }
    receipts_directory = output_directory / "records"
    receipts_directory.mkdir(mode=0o700)
    for record in records:
        name = (
            f"{record['information_regime']}--{record['target_representation']}"
            f"--seed{record['seed']}--match{record['evaluation_match_id']}.json"
        )
        path = receipts_directory / name
        receipt_sha = _write_private_json(path, record)
        receipt_index = cast(list[object], campaign["result_receipts"])
        receipt_index.append(
            {
                "path": f"records/{name}",
                "file_sha256": receipt_sha,
                "result_record_sha256": record["result_receipt_sha256"],
                "model_identity": [
                    record["information_regime"],
                    record["target_representation"],
                    record["seed"],
                ],
                "match_id": record["evaluation_match_id"],
            }
        )
    campaign["manifest_sha256"] = hashlib.sha256(canonical_bytes(campaign)).hexdigest()
    _write_private_json(output_directory / "campaign-result.json", campaign)
    _check_resource_limits(campaign_start_cpu, campaign_start_wall)
    return campaign


def run_authorized_campaign(
    *,
    owner_authorization_path: Path,
    owner_go: str,
    checkpoint_directory: Path,
    receipt_directory: Path,
    research_root: Path,
    source_root: Path,
    output_directory: Path,
) -> dict[str, object]:
    """Run one owner-authorized CPU campaign; all failures permanently consume the output path."""
    _amendment, amendment_sha, manifest, baseline = load_frozen_artifacts()
    manifest_sha = hashlib.sha256(_read_resource(_MANIFEST_FILE)).hexdigest()
    scorer_sha = _scorer_code_identity_sha256()
    owner = authorize_owner_execution(
        owner_authorization_path,
        owner_go,
        amendment_sha256=amendment_sha,
        checkpoint_manifest_sha256=manifest_sha,
        scorer_code_sha256=scorer_sha,
    )
    output = _reserve_campaign(output_directory, owner)
    snapshot: Path | None = None
    campaign_start_cpu, campaign_start_wall = time.process_time(), time.monotonic()
    try:
        _set_cpu_inference_runtime()
        models = load_frozen_models(checkpoint_directory, receipt_directory, manifest)
        snapshot, source_authority, _source_verification_sha = _prepare_verified_research_input(
            research_root,
            source_root,
            output,
            amendment_sha256=amendment_sha,
            checkpoint_manifest_sha256=manifest_sha,
            campaign_start_cpu=campaign_start_cpu,
            campaign_start_wall=campaign_start_wall,
        )
        evaluation_input_sha256 = _secure_sha256(snapshot)
        if (
            owner.evaluation_input_sha256 is not None
            and owner.evaluation_input_sha256 != evaluation_input_sha256
        ):
            raise PermissionError("prepared evaluation input differs from optional owner input pin")
        owner = dataclasses.replace(owner, evaluation_input_sha256=evaluation_input_sha256)
        campaign = _score_authorized_snapshot(
            snapshot,
            output,
            owner=owner,
            manifest=manifest,
            manifest_sha256=manifest_sha,
            baseline=baseline,
            models=models,
            module_path=Path(__file__),
            source_authority=source_authority,
            campaign_start_cpu=campaign_start_cpu,
            campaign_start_wall=campaign_start_wall,
        )
        snapshot.unlink()
        return campaign
    except BaseException as exc:
        if snapshot is not None:
            try:
                snapshot.unlink()
            except FileNotFoundError:
                pass
        _write_failure_marker(output, exc)
        raise


def verify_committed_campaign(
    campaign_directory: Path,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Independently read back and validate a complete private 72-receipt campaign."""
    _amendment, amendment_sha, manifest, baseline = load_frozen_artifacts()
    campaign_path = campaign_directory / "campaign-result.json"
    campaign = _mapping(
        json.loads(campaign_path.read_bytes(), object_pairs_hook=_unique_object),
        "campaign result",
    )
    manifest_sha = hashlib.sha256(_read_resource(_MANIFEST_FILE)).hexdigest()
    if (
        campaign.get("status") != "COMPLETED"
        or campaign.get("study_id") != _STUDY_ID
        or campaign.get("authority_scope") != "research-only-amended-heldout"
        or campaign.get("amendment_sha256") != amendment_sha
        or campaign.get("checkpoint_manifest_sha256") != manifest_sha
        or campaign.get("scorer_code_sha256") != _scorer_code_identity_sha256()
        or campaign.get("role") != "evaluation"
        or campaign.get("protected_status") != "NOT_QUALIFIED"
        or campaign.get("expected_record_count") != 72
        or campaign.get("optimizer_steps") != 0
    ):
        raise ValueError("campaign result authority or completion state differs")
    entries = _list(campaign.get("result_receipts"), "campaign result receipts")
    if len(entries) != 72:
        raise ValueError("campaign result commit is incomplete")
    records: list[dict[str, object]] = []
    seen_paths: set[str] = set()
    for raw_entry in entries:
        entry = _mapping(raw_entry, "campaign receipt index")
        relative = entry.get("path")
        if (
            not isinstance(relative, str)
            or relative.startswith("/")
            or ".." in Path(relative).parts
        ):
            raise ValueError("result receipt path escapes the campaign directory")
        if relative in seen_paths:
            raise ValueError("campaign result receipt path is duplicated")
        seen_paths.add(relative)
        path = campaign_directory / relative
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o077:
                raise ValueError("result receipt must remain owner-private")
            raw = stream.read()
        if hashlib.sha256(raw).hexdigest() != entry.get("file_sha256"):
            raise ValueError("result receipt file SHA-256 mismatch")
        record = _mapping(json.loads(raw, object_pairs_hook=_unique_object), "match result")
        if record.get("scorer_code_sha256") != campaign.get("scorer_code_sha256"):
            raise ValueError("result receipt scorer code identity differs from the campaign")
        if hashlib.sha256(canonical_bytes(_receipt_body(record))).hexdigest() != record.get(
            "result_receipt_sha256"
        ):
            raise ValueError("match result canonical receipt identity mismatch")
        if record.get("result_receipt_sha256") != entry.get("result_record_sha256"):
            raise ValueError("campaign result index differs from receipt identity")
        records.append(record)
    validate_result_matrix(records, manifest)
    if campaign.get("analysis") != aggregate_results(records, manifest, baseline):
        raise ValueError("campaign analysis does not reproduce from the 72 match receipts")
    expected_hash = campaign.get("manifest_sha256")
    body = dict(campaign)
    body.pop("manifest_sha256", None)
    if hashlib.sha256(canonical_bytes(body)).hexdigest() != expected_hash:
        raise ValueError("campaign manifest SHA-256 mismatch")
    return campaign, records


def _format_table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    bar = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(str(value) for value in row) + " |" for row in rows]
    return "\n".join((head, bar, *body))


def _svg_ade(campaign: Mapping[str, object]) -> str:
    analysis = _mapping(campaign["analysis"], "campaign analysis")
    summaries = cast(
        list[dict[str, object]], _list(analysis["configuration_summaries"], "summaries")
    )
    max_ade = max(
        _strict_float(
            _mapping(item["aggregation"], "aggregate metrics")["ade_m"],
            "aggregate ADE",
        )
        for item in summaries
    )
    width, height = 960, 420
    left, right, top, row_height = 320, 28, 45, 56
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="Six-cell ADE with individual match values">',
        "<style>text{font:14px sans-serif;fill:#1f2937}.label{font-weight:600}.bar{fill:#2563eb}.match{fill:#f97316;stroke:white;stroke-width:1}</style>",
        '<text x="20" y="24" class="label">Held-out ADE by regime and representation (metres)</text>',
    ]
    match_values: list[float] = []
    for item in summaries:
        match_means = _mapping(item["match_seed_means"], "match means")
        match_values.extend(
            _strict_float(_mapping(match_means[match], "match metric")["ade_m"], "match ADE")
            for match in _MATCHES
        )
    axis_max = max(max_ade, max(match_values)) * 1.08
    chart_width = width - left - right
    for index, item in enumerate(summaries):
        y = top + index * row_height
        label = f"{item['information_regime']} / {item['target_representation']}"
        parts.append(f'<text x="20" y="{y + 20}" class="label">{html.escape(label)}</text>')
        value = _strict_float(
            _mapping(item["aggregation"], "aggregate metrics")["ade_m"], "aggregate ADE"
        )
        bar_width = chart_width * value / axis_max
        parts.append(
            f'<rect class="bar" x="{left}" y="{y + 4}" width="{bar_width:.2f}" height="24" rx="3"/>'
        )
        parts.append(f'<text x="{left + bar_width + 8:.2f}" y="{y + 21}">{value:.3f}</text>')
        match_means = _mapping(item["match_seed_means"], "match means")
        for dot_index, match in enumerate(_MATCHES):
            match_value = _strict_float(
                _mapping(match_means[match], "match metric")["ade_m"], "match ADE"
            )
            dot_x = left + chart_width * match_value / axis_max
            dot_y = y + 36 + dot_index * 3
            parts.append(
                f'<circle class="match" cx="{dot_x:.2f}" cy="{dot_y}" r="4"><title>{match}: {match_value:.3f} m</title></circle>'
            )
    parts.append(
        f'<line x1="{left}" y1="{top - 8}" x2="{left}" y2="{height - 20}" stroke="#6b7280"/>'
    )
    parts.append(f'<text x="{left}" y="{height - 4}">0</text>')
    parts.append(f'<text x="{left + chart_width - 28}" y="{height - 4}">{axis_max:.2f} m</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def _svg_contrasts(campaign: Mapping[str, object]) -> str:
    analysis = _mapping(campaign["analysis"], "campaign analysis")
    contrasts = cast(list[dict[str, object]], _list(analysis["frozen_contrasts"], "contrasts"))
    values = [
        cast(dict[str, float], item["match_values_m"])[match]
        for item in contrasts
        for match in _MATCHES
    ]
    bound = max((abs(value) for value in values), default=1.0) * 1.15
    width, height = 940, 360
    left, center, row_height = 340, 550, 34
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="Four frozen context contrasts by evaluation match">',
        "<style>text{font:13px sans-serif;fill:#1f2937}.label{font-weight:600}.dot{fill:#0f766e}.mean{stroke:#dc2626;stroke-width:2}</style>",
        '<text x="20" y="24" class="label">Frozen context contrasts by evaluation match (ADE metres)</text>',
        f'<line x1="{center}" y1="38" x2="{center}" y2="{height - 20}" stroke="#6b7280"/>',
    ]
    for index, item in enumerate(contrasts):
        y = 52 + index * row_height * 4
        label = f"{item['contrast']} / {item['target_representation']}"
        parts.append(f'<text x="20" y="{y + 8}" class="label">{html.escape(label)}</text>')
        match_values = cast(dict[str, float], item["match_values_m"])
        mean = _strict_float(item["equal_match_mean_m"], "contrast mean")
        mean_x = center + (left - 20) * mean / bound
        # The visual axis is centered on zero; bars preserve each match's sign.
        for match_index, match in enumerate(_MATCHES):
            value = _strict_float(match_values[match], "match contrast")
            x = center + (value / bound) * (left - 20)
            yy = y + 20 + match_index * 7
            parts.append(
                f'<circle class="dot" cx="{x:.2f}" cy="{yy}" r="4"><title>{match}: {value:.3f} m</title></circle>'
            )
        parts.append(
            f'<line class="mean" x1="{center}" y1="{y + 18}" x2="{mean_x:.2f}" y2="{y + 18}"><title>equal-match mean {mean:.3f} m</title></line>'
        )
        parts.append(
            f'<text x="20" y="{y + row_height * 4 - 6}">mean {mean:.3f} m; positive means lower error with added realized context</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def render_scientific_report(
    campaign: Mapping[str, object], records: Sequence[Mapping[str, object]]
) -> str:
    """Create a publication-ready aggregate report without source rows or trajectories."""
    analysis = _mapping(campaign["analysis"], "campaign analysis")
    runtime = _mapping(campaign.get("runtime"), "campaign runtime")
    summaries = cast(
        list[dict[str, object]], _list(analysis["configuration_summaries"], "summaries")
    )
    six_cells = []
    for item in summaries:
        metrics = _mapping(item["aggregation"], "configuration metrics")
        six_cells.append(
            [
                item["information_regime"],
                item["target_representation"],
                *(
                    f"{_strict_float(metrics[name], name):.3f}"
                    for name in ("ade_m", "fde_m", "xy_rmse_m")
                ),
            ]
        )
    match_rows = []
    record_index = {
        (
            str(record["information_regime"]),
            str(record["target_representation"]),
            cast(int, record["seed"]),
            str(record["evaluation_match_id"]),
        ): record
        for record in records
    }
    for item in summaries:
        matches = cast(dict[str, dict[str, float]], item["match_seed_means"])
        for match_id in _MATCHES:
            metric = matches[match_id]
            denominators = _mapping(
                record_index[
                    (
                        str(item["information_regime"]),
                        str(item["target_representation"]),
                        SEEDS[0],
                        match_id,
                    )
                ]["denominators"],
                "match denominators",
            )
            match_rows.append(
                [
                    item["information_regime"],
                    item["target_representation"],
                    match_id,
                    *(f"{metric[name]:.3f}" for name in ("ade_m", "fde_m", "xy_rmse_m")),
                    *(
                        denominators[name]
                        for name in (
                            "windows",
                            "scoreable_scenes",
                            "scored_points",
                            "final_targets",
                        )
                    ),
                ]
            )
    seed_rows = []
    deletion_rows = []
    quality_rows = []
    horizon_rows = []
    for item in summaries:
        for metric_name in ("ade_m", "fde_m", "xy_rmse_m"):
            variation = _mapping(item["seed_variation"], "seed variation")
            metric_values = _mapping(variation[metric_name], "seed variation metric")
            seed_rows.append(
                [
                    item["information_regime"],
                    item["target_representation"],
                    metric_name,
                    ", ".join(
                        f"{seed}: {_strict_float(cast(dict[str, object], metric_values['seed_values'])[str(seed)], 'seed value'):.3f}"
                        for seed in SEEDS
                    ),
                    f"{_strict_float(metric_values['sample_sd_across_three_seed_means'], 'seed SD'):.3f}",
                ]
            )
        deletion = cast(dict[str, dict[str, float]], item["evaluation_match_deletion_sensitivity"])
        for omitted_match in _MATCHES:
            deletion_rows.append(
                [
                    item["information_regime"],
                    item["target_representation"],
                    omitted_match,
                    f"{deletion['ade_m'][omitted_match]:.3f}",
                ]
            )
        for match_id in _MATCHES:
            for stratum in ("detected_only", "with_provider_extrapolation", "unclassified"):
                values = []
                for seed in SEEDS:
                    raw = _mapping(
                        _mapping(
                            record_index[
                                (
                                    str(item["information_regime"]),
                                    str(item["target_representation"]),
                                    seed,
                                    match_id,
                                )
                            ]["quality_strata"],
                            "quality strata",
                        )[stratum],
                        "quality stratum result",
                    )
                    if raw.get("status") == "scoreable":
                        values.append(_mapping(raw["metrics"], "quality stratum metrics"))
                if values:
                    quality_rows.append(
                        [
                            item["information_regime"],
                            item["target_representation"],
                            match_id,
                            stratum,
                            *(
                                f"{math.fsum(_strict_float(row[name], name) for row in values) / len(values):.3f}"
                                for name in ("ade_m", "fde_m", "xy_rmse_m")
                            ),
                        ]
                    )
                else:
                    quality_rows.append(
                        [
                            item["information_regime"],
                            item["target_representation"],
                            match_id,
                            stratum,
                            "not scoreable",
                            "not scoreable",
                            "not scoreable",
                        ]
                    )
            for stratum in ("early_0.2_1.0s", "middle_1.2_2.0s", "late_2.2_3.0s"):
                values = []
                for seed in SEEDS:
                    raw = _mapping(
                        _mapping(
                            record_index[
                                (
                                    str(item["information_regime"]),
                                    str(item["target_representation"]),
                                    seed,
                                    match_id,
                                )
                            ]["horizon_strata"],
                            "horizon strata",
                        )[stratum],
                        "horizon stratum result",
                    )
                    if raw.get("status") == "scoreable":
                        values.append(_mapping(raw["metrics"], "horizon stratum metrics"))
                if values:
                    horizon_rows.append(
                        [
                            item["information_regime"],
                            item["target_representation"],
                            match_id,
                            stratum,
                            *(
                                f"{math.fsum(_strict_float(row[name], name) for row in values) / len(values):.3f}"
                                for name in ("ade_m", "fde_m", "xy_rmse_m")
                            ),
                        ]
                    )
                else:
                    horizon_rows.append(
                        [
                            item["information_regime"],
                            item["target_representation"],
                            match_id,
                            stratum,
                            "not scoreable",
                            "not scoreable",
                            "not scoreable",
                        ]
                    )
    contrast_rows = []
    for item in cast(list[dict[str, object]], _list(analysis["frozen_contrasts"], "contrasts")):
        values = cast(dict[str, float], item["match_values_m"])
        contrast_rows.append(
            [
                item["contrast"],
                item["target_representation"],
                *(f"{values[match]:.3f}" for match in _MATCHES),
                f"{_strict_float(item['equal_match_mean_m'], 'contrast mean'):.3f}",
            ]
        )
    baseline_rows = []
    for item in cast(
        list[dict[str, object]],
        _list(analysis["paired_deterministic_baseline_comparisons"], "baseline comparisons"),
    ):
        all_values = cast(dict[str, dict[str, float]], item["learned_minus_baseline"])
        means = cast(dict[str, float], item["equal_match_means_m"])
        for metric in ("ade_m", "fde_m", "xy_rmse_m"):
            values = all_values[metric]
            baseline_rows.append(
                [
                    item["information_regime"],
                    item["target_representation"],
                    item["baseline_model"],
                    metric,
                    *(f"{values[match]:.3f}" for match in _MATCHES),
                    f"{means[metric]:.3f}",
                ]
            )
    return "\n".join(
        (
            "# Amended held-out learned-model evaluation",
            "",
            "**Research-only descriptive results.** The four matches were not used for learned-model training or checkpoint selection. Deterministic baseline results on these matches were already known before the amendment. Validation results are historical checkpoint-selection evidence and are not held-out evaluation results.",
            "",
            f"Campaign manifest SHA-256: {campaign['manifest_sha256']}",
            "",
            "## Six-cell comparison",
            "",
            _format_table(
                ["Regime", "Representation", "ADE (m)", "FDE (m)", "XY RMSE (m)"], six_cells
            ),
            "",
            "## Four-match result summary",
            "",
            "Each row averages the three frozen seed values within that match. The four matches are the independent reporting units.",
            "",
            _format_table(
                [
                    "Regime",
                    "Representation",
                    "Match",
                    "ADE (m)",
                    "FDE (m)",
                    "XY RMSE (m)",
                    "Windows",
                    "Scenes",
                    "Scored points",
                    "Final targets",
                ],
                match_rows,
            ),
            "",
            "## Frozen contrasts",
            "",
            "Positive values mean lower ADE with added realized future context. These are descriptive paired match contrasts.",
            "",
            _format_table(
                ["Contrast", "Representation", *_MATCHES, "Equal-match mean (m)"], contrast_rows
            ),
            "",
            "## Paired deterministic baseline comparisons",
            "",
            "Values are learned minus baseline in metres; positive values mean the learned cell has higher error. Baseline inputs are the previously published published deterministic-baseline aggregate reference.",
            "",
            _format_table(
                [
                    "Regime",
                    "Representation",
                    "Baseline",
                    "Metric",
                    *_MATCHES,
                    "Equal-match mean (m)",
                ],
                baseline_rows,
            ),
            "",
            "## Seed variation",
            "",
            _format_table(
                ["Regime", "Representation", "Metric", "Seed values", "Sample SD"], seed_rows
            ),
            "",
            "## Horizon strata",
            "",
            _format_table(
                [
                    "Regime",
                    "Representation",
                    "Match",
                    "Horizon",
                    "ADE (m)",
                    "FDE (m)",
                    "XY RMSE (m)",
                ],
                horizon_rows,
            ),
            "",
            "## Target-quality strata",
            "",
            _format_table(
                [
                    "Regime",
                    "Representation",
                    "Match",
                    "Quality",
                    "ADE (m)",
                    "FDE (m)",
                    "XY RMSE (m)",
                ],
                quality_rows,
            ),
            "",
            "## Evaluation-match deletion sensitivity",
            "",
            "Each value is the equal-match mean after omitting the named evaluation match. This is evaluation-match deletion sensitivity; it is not training LOMO.",
            "",
            _format_table(["Regime", "Representation", "Omitted match", "ADE (m)"], deletion_rows),
            "",
            "## Reproducibility and rights boundary",
            "",
            f"- Checkpoint manifest SHA-256: {campaign['checkpoint_manifest_sha256']}",
            f"- Evaluation input SHA-256: {campaign['evaluation_input_sha256']}",
            f"- Research admission SHA-256: {campaign['research_admission_sha256']}",
            f"- Match-scoped learned receipts: {len(records)}",
            f"- Inference runtime: PyTorch {runtime['pytorch']}, CPU FP32",
            "- No raw source rows, target masks, reconstructive trajectories, or model weights are included.",
            "",
            "## Original v2 deviation and limitations",
            "",
            "- Original v2 required 216 additional training-match LOMO fits and 234 final/LOMO checkpoint manifests before its prescribed evaluation stage. The LOMO campaign remains deferred and incomplete.",
            "- This amended evaluation uses the 18 verified final-fit checkpoints only and does not complete original full prospective v2.",
            "- History-only is an ex-ante forecasting setting. Future-ball and future-opponent-plus-ball use privileged realized future information and are not deployable forecasts.",
            "- Four evaluation matches limit the independent match count to four. Repeated overlapping origins are not treated as independent observations.",
            "- No significance tests or confidence intervals are reported.",
            f"- Baseline provenance status: {campaign['baseline_comparability']}.",
            "- Any negative or null context effect is reported as observed, without post-hoc contrast changes.",
            "",
            "## Planned figures",
            "",
            "The companion SVGs show the six-cell ADE values with individual match points and the four frozen contrast values by match. Both figures use only the verified match-scoped receipts.",
            "",
        )
    )


def generate_report_bundle(campaign_directory: Path, destination: Path) -> tuple[Path, Path, Path]:
    """Render a public-safe Markdown report and two aggregate-only SVG figures."""
    campaign, records = verify_committed_campaign(campaign_directory)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("report destination already exists")
    destination.mkdir(mode=0o755, parents=True)
    report_path = destination / "report.md"
    ade_path = destination / "ade-by-match.svg"
    contrast_path = destination / "frozen-contrasts.svg"
    report_path.write_text(render_scientific_report(campaign, records), encoding="utf-8")
    ade_path.write_text(_svg_ade(campaign), encoding="utf-8")
    contrast_path.write_text(_svg_contrasts(campaign), encoding="utf-8")
    return report_path, ade_path, contrast_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    score_parser = subparsers.add_parser("score", help="run one explicitly authorized CPU campaign")
    score_parser.add_argument("--owner-authorization", type=Path, required=True)
    score_parser.add_argument("--owner-go", required=True)
    score_parser.add_argument("--checkpoint-directory", type=Path, required=True)
    score_parser.add_argument("--receipt-directory", type=Path, required=True)
    score_parser.add_argument("--research-root", type=Path, required=True)
    score_parser.add_argument("--source-root", type=Path, required=True)
    score_parser.add_argument("--output-directory", type=Path, required=True)
    report_parser = subparsers.add_parser("report", help="render a verified campaign result")
    report_parser.add_argument("--campaign-directory", type=Path, required=True)
    report_parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "score":
        result = run_authorized_campaign(
            owner_authorization_path=args.owner_authorization,
            owner_go=args.owner_go,
            checkpoint_directory=args.checkpoint_directory,
            receipt_directory=args.receipt_directory,
            research_root=args.research_root,
            source_root=args.source_root,
            output_directory=args.output_directory,
        )
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "manifest_sha256": result["manifest_sha256"],
                    "match_scoped_records": result["expected_record_count"],
                    "optimizer_steps": 0,
                },
                sort_keys=True,
            )
        )
        return 0
    paths = generate_report_bundle(args.campaign_directory, args.output_directory)
    print(json.dumps({"report_files": [str(path) for path in paths]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
