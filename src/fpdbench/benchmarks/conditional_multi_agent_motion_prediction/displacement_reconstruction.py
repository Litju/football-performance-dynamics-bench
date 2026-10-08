"""Hash-bound historical state for the origin-relative displacement benchmark."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from fpdbench.benchmarks.base import UNKNOWN, UnknownValue
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    absolute_position_prediction,
    origin_relative_displacement_prediction,
)
from fpdbench.benchmarks.transitions import (
    IdentityConsequence,
    ScientificTransition,
    TransitionEndpoint,
    TransitionKind,
    TransitionStatus,
)
from fpdbench.data import SplitProtocolDescriptor
from fpdbench.evaluation.metrics.trajectory import PHYSICAL_TRAJECTORY_EVALUATOR
from fpdbench.experiments import (
    EvaluatorState,
    ProvenanceCompleteness,
    ResultPopulation,
    ResultRecord,
    ResultValidity,
)
from fpdbench.provenance import (
    EvidenceReference,
    HistoricalAlias,
    build_scientific_lock,
    canonical_scientific_bytes,
)
from fpdbench.provenance.aliases import DISPLACEMENT_HISTORICAL_ALIASES

BENCHMARK_ID = origin_relative_displacement_prediction.BENCHMARK_ID
HISTORICAL_FINAL_MODEL_ID = origin_relative_displacement_prediction.HISTORICAL_FINAL_MODEL_ID


class HistoricalModelRole(StrEnum):
    FINAL_PUBLIC_REFERENCE = "historical_final_public_reference"


class SystemEvidenceRole(StrEnum):
    PREFLIGHT = "preflight_system_validation"
    RELEASE_ENGINEERING = "release_engineering_validation"


def _evidence(sha256: str, description: str) -> EvidenceReference:
    return EvidenceReference(f"registry://sha256/{sha256}", sha256, description)


_ABSOLUTE_DEFINITION = _evidence(
    "a6892d5158b424db5f8a4903fc5c01b687429246c24056d7a5b03007f9dec23a",
    "predecessor benchmark contract",
)
_ABSOLUTE_INPUTS = _evidence(
    "66a9edb3feac5a3cbffa3cfefd6138f70fac9f127ebd978d1610a1d0f0dc661d",
    "predecessor scene and input contract",
)
_ABSOLUTE_BOUNDARY = _evidence(
    "f31e6a54f677fce70d494ca0680d580ce7846486eb8956110deb703151871770",
    "predecessor information boundary",
)
_ABSOLUTE_TEMPORAL = _evidence(
    "3de6fc6e9ea566379bc7a7197cf6b1106571bc01c1e94c64498a1e43998f5947",
    "predecessor sampling and measurement contract",
)
_ABSOLUTE_DATA_STATE = _evidence(
    "a13db1d01e70f4d4b1aece6b5ea3e578eba7bbb473dcb231fea2ea40f1dd6ec7",
    "predecessor repaired measurement state",
)
_ABSOLUTE_SPLITS = _evidence(
    "854d709005571fe77dbc79fe6d4a3ce4c6302d797400a46c385801ffb5cd561d",
    "predecessor split populations",
)
_DISPLACEMENT_FIXTURE = _evidence(
    "134cfd7a6a3b5bcdf04d1d03772e8674c37b2da301e81245aabe2be5b11519b4",
    "displacement public fixture manifest",
)
_DISPLACEMENT_TARGET_SCHEMA = _evidence(
    "3cbc2b3cbdc800e4cf2c9bee3c6478f28f486d700472cf363450d8bc5a8fa891",
    "displacement target schema",
)
_DISPLACEMENT_PUBLIC_SCHEMA = _evidence(
    "7d2a117d0fbb4d3ed3b2d29b8f2ae6103fc13d37bf4cd306bb1886d461218ca7",
    "displacement public feature schema",
)
_TRANSITION_EVIDENCE = _evidence(
    "68f194e0465a1a13a4f432d8e33f0d997089c4e396b4d155f25d238ef2bcc4b2",
    "absolute-to-displacement target transition",
)
_DATA_ASSET_EVIDENCE = _evidence(
    "6a86019ed3e474816dfc5188aa5cbb6a36cbf841a582a6b7a3515fb02e4dc15f",
    "source, repaired state, and fixture population records",
)
_SPLIT_EVIDENCE = _evidence(
    "2fe0fb974931b2fb691c56aa50c66689f37a184c1a923f77d34ed1343f5e03b3",
    "match roles and population counts",
)
_SCORER_EVIDENCE = _evidence(
    "4518e928fd09eee940e4093329ddf35cbaf6ea537bfde817cc454ce8f5b6313a",
    "raw and calibrated scorer state summary",
)
_SCORER_BINDING_EVIDENCE = _evidence(
    "c0fb665c7c2ea75c770ef4695e4d9f0fd19332505e35a681684444bf2017b3fb",
    "benchmark-to-scorer bindings",
)


def _parity(
    field: str,
    status: TransitionStatus,
    explanation: str,
    evidence: tuple[EvidenceReference, ...],
) -> ScientificTransition:
    return ScientificTransition(
        transition_id=f"absolute_position_to_displacement:{field}",
        transition_group_id="absolute_position_to_displacement",
        source=TransitionEndpoint(absolute_position_prediction.BENCHMARK_ID, "benchmark"),
        target=TransitionEndpoint(
            origin_relative_displacement_prediction.BENCHMARK_ID, "benchmark"
        ),
        transition_kind=TransitionKind.BENCHMARK_PARITY,
        layer=field,
        status=status,
        explanation=explanation,
        evidence=evidence,
        identity_consequence=IdentityConsequence.NEW_BENCHMARK_IDENTITY,
        data_state_consequence=(
            status if field == "data_state" else TransitionStatus.NOT_APPLICABLE
        ),
        evaluator_consequence=(
            status
            if field in {"evaluator_scorer", "calibration"}
            else TransitionStatus.NOT_APPLICABLE
        ),
    )


PARITY_FIELDS = (
    "benchmark_identity",
    "research_question",
    "scientific_task_type",
    "scene_history_inputs",
    "supplied_realized_future_context",
    "information_boundary",
    "history_duration",
    "history_cadence",
    "horizon_duration",
    "horizon_cadence",
    "target_cadence",
    "target_entities",
    "population_semantics",
    "data_source",
    "data_state",
    "split_protocol",
    "target_representation",
    "reference_frame",
    "raw_metric_family",
    "evaluator_scorer",
    "calibration",
    "baseline_ladder",
    "model_architecture",
    "model_selection_protocol",
)

PREDECESSOR_PARITY = (
    _parity(
        "benchmark_identity",
        TransitionStatus.CHANGED,
        "The target/reference frame changes, so these remain distinct benchmark identities.",
        (_ABSOLUTE_DEFINITION, _TRANSITION_EVIDENCE, _DISPLACEMENT_TARGET_SCHEMA),
    ),
    _parity(
        "research_question",
        TransitionStatus.CHANGED,
        "The predicted response changes from absolute future XY to origin-relative displacement.",
        (_ABSOLUTE_DEFINITION, _TRANSITION_EVIDENCE, _DISPLACEMENT_TARGET_SCHEMA),
    ),
    _parity(
        "scientific_task_type",
        TransitionStatus.SAME,
        "Both are conditional multi-agent target-team response prediction.",
        (_ABSOLUTE_DEFINITION, _TRANSITION_EVIDENCE),
    ),
    _parity(
        "scene_history_inputs",
        TransitionStatus.SAME,
        "Both use observed target-team, opponent-team, and ball scene history.",
        (_ABSOLUTE_INPUTS, _DISPLACEMENT_PUBLIC_SCHEMA),
    ),
    _parity(
        "supplied_realized_future_context",
        TransitionStatus.SAME,
        "Both condition on realized future opponent-team XY and ball XY.",
        (_ABSOLUTE_INPUTS, _DISPLACEMENT_PUBLIC_SCHEMA),
    ),
    _parity(
        "information_boundary",
        TransitionStatus.SAME,
        "Future target-team values are withheld; realized opponent and ball paths remain context.",
        (_ABSOLUTE_BOUNDARY, _DISPLACEMENT_TARGET_SCHEMA),
    ),
    _parity(
        "history_duration",
        TransitionStatus.SAME,
        "Both use five seconds of history.",
        (_ABSOLUTE_TEMPORAL, _DISPLACEMENT_FIXTURE),
    ),
    _parity(
        "history_cadence",
        TransitionStatus.SAME,
        "Both use 25 history steps at five hertz from the repaired measurement state.",
        (_ABSOLUTE_TEMPORAL, _DISPLACEMENT_FIXTURE),
    ),
    _parity(
        "horizon_duration",
        TransitionStatus.SAME,
        "Both use a three-second forecast horizon.",
        (_ABSOLUTE_DEFINITION, _DISPLACEMENT_FIXTURE),
    ),
    _parity(
        "horizon_cadence",
        TransitionStatus.SAME,
        "Both use 15 forecast steps at five hertz.",
        (_ABSOLUTE_DEFINITION, _DISPLACEMENT_FIXTURE),
    ),
    _parity(
        "target_cadence",
        TransitionStatus.SAME,
        "Both target the canonical five-hertz grid.",
        (_ABSOLUTE_DEFINITION, _DISPLACEMENT_TARGET_SCHEMA),
    ),
    _parity(
        "target_entities",
        TransitionStatus.SAME,
        "Both predict 11 target-team players and two coordinates per step.",
        (_ABSOLUTE_DEFINITION, _DISPLACEMENT_TARGET_SCHEMA),
    ),
    _parity(
        "population_semantics",
        TransitionStatus.SAME,
        "Both use two directed target-team scenes per physical match window.",
        (_ABSOLUTE_DEFINITION, _DISPLACEMENT_FIXTURE),
    ),
    _parity(
        "data_source",
        TransitionStatus.SAME,
        "Both derive from the same seven-match DFL/IDSSE source population.",
        (_ABSOLUTE_DATA_STATE, _DATA_ASSET_EVIDENCE),
    ),
    _parity(
        "data_state",
        TransitionStatus.SAME,
        (
            "The repaired position and causal-velocity measurement state is reused; displacement "
            "is a target transform, not a new measurement state."
        ),
        (_ABSOLUTE_DATA_STATE, _DATA_ASSET_EVIDENCE, _DISPLACEMENT_FIXTURE),
    ),
    _parity(
        "split_protocol",
        TransitionStatus.SAME,
        (
            "Train, public validation, and historical-private match roles are the same; "
            "displacement has regenerated target fixtures and its own manifest."
        ),
        (_ABSOLUTE_SPLITS, _SPLIT_EVIDENCE, _DISPLACEMENT_FIXTURE),
    ),
    _parity(
        "target_representation",
        TransitionStatus.CHANGED,
        (
            "Absolute pitch XY is replaced by each player's future XY minus exact causal-origin "
            "XY, scaled by pitch dimensions."
        ),
        (_ABSOLUTE_DEFINITION, _DISPLACEMENT_TARGET_SCHEMA, _TRANSITION_EVIDENCE),
    ),
    _parity(
        "reference_frame",
        TransitionStatus.CHANGED,
        (
            "The predecessor uses the pitch frame; displacement uses each target player's "
            "observed origin frame."
        ),
        (_ABSOLUTE_DEFINITION, _DISPLACEMENT_TARGET_SCHEMA),
    ),
    _parity(
        "raw_metric_family",
        TransitionStatus.SAME,
        "Both records identify per-scalar evaluation-population SRE with equal target weights.",
        (_SCORER_EVIDENCE, _SCORER_BINDING_EVIDENCE),
    ),
    _parity(
        "evaluator_scorer",
        TransitionStatus.UNKNOWN,
        (
            "The raw SRE kernel is shared; the exact predecessor-to-generated-wrapper "
            "relationship is not fully recoverable."
        ),
        (_SCORER_EVIDENCE, _SCORER_BINDING_EVIDENCE),
    ),
    _parity(
        "calibration",
        TransitionStatus.UNKNOWN,
        "The displacement GeneratedCalibration lock and its reference vectors are absent.",
        (_SCORER_EVIDENCE, _SCORER_BINDING_EVIDENCE),
    ),
    _parity(
        "baseline_ladder",
        TransitionStatus.UNKNOWN,
        (
            "Some public-validation baselines survive, but a complete predecessor-matched "
            "ladder is not recovered."
        ),
        (_ABSOLUTE_DEFINITION, _DISPLACEMENT_FIXTURE),
    ),
    _parity(
        "model_architecture",
        TransitionStatus.UNKNOWN,
        "Both lineages name the CCT family; exact architecture parity is not established.",
        (_ABSOLUTE_DEFINITION, _DISPLACEMENT_FIXTURE),
    ),
    _parity(
        "model_selection_protocol",
        TransitionStatus.UNKNOWN,
        "The displacement public confirmation is recovered, but exact selection parity is not.",
        (_ABSOLUTE_DEFINITION, _DISPLACEMENT_FIXTURE),
    ),
)


TRAIN_MATCHES = ("J03WOH", "J03WOY", "J03WPY", "J03WQQ", "J03WR9")
PUBLIC_VALIDATION_MATCHES = ("J03WN1",)
HISTORICAL_PRIVATE_MATCHES = ("J03WMX",)


@dataclass(frozen=True, slots=True)
class PopulationDefinition:
    population: ResultPopulation
    match_ids: tuple[str, ...]
    physical_windows: int
    directed_rows: int
    content_access: str
    evidence: tuple[EvidenceReference, ...]

    def __post_init__(self) -> None:
        if not self.match_ids or self.physical_windows <= 0:
            raise ValueError("population requires matches and physical windows")
        if self.directed_rows != 2 * self.physical_windows:
            raise ValueError("each physical window must produce two directed scenes")
        if not self.evidence:
            raise ValueError("population counts require source evidence")
        object.__setattr__(self, "match_ids", tuple(self.match_ids))
        object.__setattr__(self, "evidence", tuple(self.evidence))


PUBLIC_TRAIN = PopulationDefinition(
    ResultPopulation.PUBLIC_TRAIN,
    TRAIN_MATCHES,
    17_386,
    34_772,
    "public",
    (_SPLIT_EVIDENCE, _DATA_ASSET_EVIDENCE, _DISPLACEMENT_FIXTURE),
)
PUBLIC_VALIDATION = PopulationDefinition(
    ResultPopulation.PUBLIC_VALIDATION,
    PUBLIC_VALIDATION_MATCHES,
    215,
    430,
    "public",
    (_SPLIT_EVIDENCE, _DATA_ASSET_EVIDENCE, _DISPLACEMENT_FIXTURE),
)
HISTORICAL_PRIVATE = PopulationDefinition(
    ResultPopulation.HISTORICAL_PRIVATE,
    HISTORICAL_PRIVATE_MATCHES,
    457,
    914,
    "historical private metadata only; challenge truth remains unopened",
    (_SPLIT_EVIDENCE, _DATA_ASSET_EVIDENCE),
)

DISPLACEMENT_DATA_STATE = absolute_position_prediction.REPAIRED_POSITION_DATA_STATE
DISPLACEMENT_FEATURE_COUNT = 8_404
DISPLACEMENT_TARGET_COUNT = 330
DISPLACEMENT_FIXTURE_MANIFEST_SHA256 = (
    "134cfd7a6a3b5bcdf04d1d03772e8674c37b2da301e81245aabe2be5b11519b4"
)
DISPLACEMENT_SPLIT_MANIFEST_SHA256 = (
    "5e060c84952cd4544fde6b80a93675c02c06036440ef9d2c97aa96eec618709c"
)
DISPLACEMENT_TARGET_SCHEMA_SHA256 = (
    "3cbc2b3cbdc800e4cf2c9bee3c6478f28f486d700472cf363450d8bc5a8fa891"
)
DISPLACEMENT_PUBLIC_SCHEMA_SHA256 = (
    "7d2a117d0fbb4d3ed3b2d29b8f2ae6103fc13d37bf4cd306bb1886d461218ca7"
)
DISPLACEMENT_SPLIT = SplitProtocolDescriptor(
    protocol_id="match_grouped_displacement_public_split",
    version="1.0.0",
    assignment_sha256=DISPLACEMENT_SPLIT_MANIFEST_SHA256,
    grouping="match",
    access_policy="public training and validation; private qualification remains historical",
)
POSITION_MEASUREMENT_SEMANTICS = (
    "Select exact 25 Hz positions with xy[::5], without interpolation. Estimate endpoint "
    "velocity by float64 local-quadratic OLS on 11 samples from t-0.4 s through t, using "
    "only samples at or before t; omit until the full support exists."
)
POSITION_MEASUREMENT_EVIDENCE = (
    _ABSOLUTE_TEMPORAL,
    _ABSOLUTE_DATA_STATE,
    _DATA_ASSET_EVIDENCE,
    _DISPLACEMENT_PUBLIC_SCHEMA,
)
TARGET_TEAM_ORIENTATION_SEMANTICS = (
    "Each directed scene assigns one selected team to the 11 target slots and the other team "
    "to opponent slots. Target coordinates use pitch-normalized x/y; no separate team-relative "
    "rotation rule is recovered."
)
TARGET_TEAM_ORIENTATION_EVIDENCE = (
    _ABSOLUTE_INPUTS,
    _DISPLACEMENT_PUBLIC_SCHEMA,
    _DISPLACEMENT_TARGET_SCHEMA,
)
DISPLACEMENT_DATA_STATE_EVIDENCE = (
    _ABSOLUTE_DATA_STATE,
    _DATA_ASSET_EVIDENCE,
    _DISPLACEMENT_FIXTURE,
)


(
    _PREFLIGHT_ALIAS,
    _FIRST_LOMO_ALIAS,
    _SECOND_LOMO_ALIAS,
    _FINAL_MODEL_ALIAS,
    _CORRECTION_ALIAS,
    _SYSTEM_PREFLIGHT_ALIAS,
    _RELEASE_HANDOFF_ALIAS,
) = DISPLACEMENT_HISTORICAL_ALIASES


@dataclass(frozen=True, slots=True)
class LomoCampaign:
    alias: HistoricalAlias
    seeds: tuple[int, ...]
    fold_count: int
    original_aggregate_validity: ResultValidity
    training_reexecuted_for_recovery: bool
    evidence: tuple[EvidenceReference, ...]

    def __post_init__(self) -> None:
        if self.fold_count != 5 * len(self.seeds) or not self.evidence:
            raise ValueError("cross-match campaigns require five evidence-backed folds per seed")
        object.__setattr__(self, "seeds", tuple(self.seeds))
        object.__setattr__(self, "evidence", tuple(self.evidence))


FIRST_LOMO_CAMPAIGN = LomoCampaign(
    _FIRST_LOMO_ALIAS,
    (20260911,),
    5,
    ResultValidity.RECORDED,
    False,
    (
        _evidence(
            "8daaa00acd1a6b8477c5a9bf9daac9703b8671165641a584fe0c2408d2eaee1f",
            "five-fold campaign manifest",
        ),
        _evidence(
            "f09dc83c1c9d121ed97cf001620658a6757b0fa4c35e704a652b84ffb0e4aec2",
            "five-fold campaign result",
        ),
    ),
)
SECOND_LOMO_CAMPAIGN = LomoCampaign(
    _SECOND_LOMO_ALIAS,
    (20260912, 20260913),
    10,
    ResultValidity.INVALIDATED,
    False,
    (
        _evidence(
            "772b4adf4326c6f6fdfef2e13dcafc2bb2087c48ede71cfc62ed8bc5aae347b9",
            "immutable ten-fold manifest",
        ),
        _evidence(
            "6bf6416609942c0b32af290fec94c36fef3e0362afee92981ff053950d45a2a2",
            "original aggregate invalidation",
        ),
    ),
)


def _payload_hash(payload: dict[str, str]) -> str:
    return hashlib.sha256(canonical_scientific_bytes(payload)).hexdigest()


_LOMO_ASSIGNMENT_HASH = _payload_hash(
    {
        "fold_order": ",".join(TRAIN_MATCHES),
        "heldout_rule": "one public training match held out per fold",
        "seeds": "20260911,20260912,20260913",
    }
)
LOMO_SPLIT = SplitProtocolDescriptor(
    protocol_id="match_grouped_cross_match_split",
    version="1.0.0",
    assignment_sha256=_LOMO_ASSIGNMENT_HASH,
    grouping="match",
    access_policy=(
        "five public training matches only; public validation and private qualification excluded"
    ),
)
_BENCHMARK_DEFINITION_STATE = {
    "benchmark_id": BENCHMARK_ID,
    "data_source": "DFL/IDSSE tracking and event source",
    "history": "5 seconds; 25 steps at 5 Hz",
    "horizon": "3 seconds; 15 steps at 5 Hz",
    "information_boundary": "future target withheld; realized future opponent and ball supplied",
    "population_semantics": "two directed target-team scenes per physical match window",
    "reference_frame": "each target player's exact observed causal-origin XY",
    "scientific_task_type": "conditional multi-agent target-team response prediction",
    "target": "(future XY - exact causal-origin XY) / [52.5, 34.0]",
    "target_shape": "[15, 11, 2]",
}
_SCHEMA_HASH = hashlib.sha256(
    f"{DISPLACEMENT_PUBLIC_SCHEMA_SHA256}\n{DISPLACEMENT_TARGET_SCHEMA_SHA256}".encode()
).hexdigest()
_LOMO_TRAIN_FIXTURE_MEMBERS = (
    (
        "data/train/part-000.parquet",
        "0fc6c73ead81703c7f903e23aebedd1bb014725865a2c881f385073540497c09",
    ),
    (
        "data/train/part-001.parquet",
        "cfc387102b3bca15d4267dee1f00c676d1cecca61afcc599a952ed27f7d54a63",
    ),
    (
        "data/train/part-002.parquet",
        "2b37f03650e19bcea6efd978360d23a8a004a2bc71305ddb02ef577153c07bd9",
    ),
    (
        "data/train/part-003.parquet",
        "6ce3562d0599dc50f50d2572fa606681364cb89c0ed97e7cb8b6a7e9668935b0",
    ),
    (
        "data/train/part-004.parquet",
        "217be8efb71158fce7db3d040674e0a6e15c22eabf0bdbcfa5d3aad8d8e47878",
    ),
    (
        "data/train/part-005.parquet",
        "9235845c95190d78e68637ec8b6404fa3ffc8121be7c114453f32d8462b77d3c",
    ),
    (
        "data/train/part-006.parquet",
        "47001b3862af99a38b0b07cafab3292012562b4599b36d6e36eeba5fa66a9993",
    ),
    (
        "data/train/part-007.parquet",
        "86ccf6b83070c5381693ea3c47d8dc76edf4c9cc3ef383dabf1473c849989288",
    ),
    (
        "data/train/part-008.parquet",
        "c1ec8b9e245383b5792c6bc9f1084d68b86debe92199313260acada197f21041",
    ),
)
_LOMO_FIXTURE_MANIFEST_SHA256 = _payload_hash(
    {
        "files": "\n".join(f"{path}:{digest}" for path, digest in _LOMO_TRAIN_FIXTURE_MEMBERS),
        "public_schema_sha256": DISPLACEMENT_PUBLIC_SCHEMA_SHA256,
        "target_schema_sha256": DISPLACEMENT_TARGET_SCHEMA_SHA256,
    }
)
_PUBLIC_DATA_MANIFEST_SHA256 = _payload_hash(
    {
        "data_state_id": DISPLACEMENT_DATA_STATE.state_id,
        "fixture_manifest_sha256": DISPLACEMENT_FIXTURE_MANIFEST_SHA256,
        "match_ids": ",".join((*TRAIN_MATCHES, *PUBLIC_VALIDATION_MATCHES)),
        "measurement_semantics": POSITION_MEASUREMENT_SEMANTICS,
    }
)
_LOMO_DATA_MANIFEST_SHA256 = _payload_hash(
    {
        "data_state_id": DISPLACEMENT_DATA_STATE.state_id,
        "fixture_manifest_sha256": _LOMO_FIXTURE_MANIFEST_SHA256,
        "match_ids": ",".join(TRAIN_MATCHES),
        "measurement_semantics": POSITION_MEASUREMENT_SEMANTICS,
    }
)
_RAW_EVALUATOR_SOURCE = (
    "registry://sha256/cd20733d029a4d78ed8bccf7dd6f5cde51211fc591914f81c7776de2cf415773"
)
_MEASUREMENT_STATE_SOURCE = (
    "registry://sha256/3de6fc6e9ea566379bc7a7197cf6b1106571bc01c1e94c64498a1e43998f5947"
)
_PUBLIC_VALIDATION_RAW_PROVENANCE_CITATIONS = (
    _MEASUREMENT_STATE_SOURCE,
    "registry://sha256/134cfd7a6a3b5bcdf04d1d03772e8674c37b2da301e81245aabe2be5b11519b4",
    "registry://sha256/5e060c84952cd4544fde6b80a93675c02c06036440ef9d2c97aa96eec618709c",
    f"registry://sha256/{DISPLACEMENT_PUBLIC_SCHEMA_SHA256}",
    f"registry://sha256/{DISPLACEMENT_TARGET_SCHEMA_SHA256}",
    _RAW_EVALUATOR_SOURCE,
)
_LOMO_RAW_PROVENANCE_CITATIONS = (
    _MEASUREMENT_STATE_SOURCE,
    *(f"registry://sha256/{digest}" for _, digest in _LOMO_TRAIN_FIXTURE_MEMBERS),
    f"registry://sha256/{DISPLACEMENT_PUBLIC_SCHEMA_SHA256}",
    f"registry://sha256/{DISPLACEMENT_TARGET_SCHEMA_SHA256}",
    _RAW_EVALUATOR_SOURCE,
)


def _provenance_snapshot(snapshot_id: str, citations: tuple[str, ...]) -> dict[str, object]:
    return {
        "snapshot_id": snapshot_id,
        "snapshot_hash": _payload_hash(
            {"citations": "\n".join(citations), "snapshot_id": snapshot_id}
        ),
        "citations": list(citations),
    }


_PUBLIC_VALIDATION_RAW_PROVENANCE = _provenance_snapshot(
    "displacement_public_validation_raw_execution_sources",
    _PUBLIC_VALIDATION_RAW_PROVENANCE_CITATIONS,
)
_PUBLIC_VALIDATION_PHYSICAL_PROVENANCE_CITATIONS = tuple(
    sorted(set(_PUBLIC_VALIDATION_RAW_PROVENANCE_CITATIONS) - {_RAW_EVALUATOR_SOURCE})
)
_PUBLIC_VALIDATION_PHYSICAL_PROVENANCE = _provenance_snapshot(
    "displacement_public_validation_physical_diagnostic_sources",
    _PUBLIC_VALIDATION_PHYSICAL_PROVENANCE_CITATIONS,
)
_LOMO_RAW_PROVENANCE = _provenance_snapshot(
    "displacement_lomo_raw_execution_sources",
    _LOMO_RAW_PROVENANCE_CITATIONS,
)


def _build_raw_scientific_lock(
    split: SplitProtocolDescriptor,
    data_release_id: str,
    data_manifest_hash: str,
    fixture_manifest_hash: str,
    scientific_provenance_snapshot: dict[str, object],
    evaluator: origin_relative_displacement_prediction.RawDisplacementEvaluatorConfiguration,
) -> dict[str, object]:
    return build_scientific_lock(
        {
            "lock_schema_version": "fpdbench-scientific-lock.v1",
            "benchmark_id": BENCHMARK_ID,
            "benchmark_definition_hash": _payload_hash(_BENCHMARK_DEFINITION_STATE),
            "data_release_id": data_release_id,
            "data_release_version": "0.0.0",
            "data_manifest_hash": data_manifest_hash,
            "data_state_id": DISPLACEMENT_DATA_STATE.state_id,
            "split_protocol_id": split.protocol_id,
            "split_protocol_version": split.version,
            "split_protocol_hash": split.assignment_sha256,
            "evaluator_id": "origin_relative_displacement_raw_population_sre",
            "evaluator_version": "1.0.0",
            "evaluator_hash": origin_relative_displacement_prediction.raw_evaluator_hash(evaluator),
            "schema_version": "displacement_public_schema.v1",
            "schema_hash": _SCHEMA_HASH,
            "fixture_manifest_hash": fixture_manifest_hash,
            "scientific_provenance_snapshot": scientific_provenance_snapshot,
        }
    )


def build_public_validation_raw_scientific_lock(
    split: SplitProtocolDescriptor = DISPLACEMENT_SPLIT,
    evaluator: origin_relative_displacement_prediction.RawDisplacementEvaluatorConfiguration = (
        origin_relative_displacement_prediction.RAW_DISPLACEMENT_EVALUATOR
    ),
) -> dict[str, object]:
    return _build_raw_scientific_lock(
        split,
        "historical_public_displacement_fixtures",
        _PUBLIC_DATA_MANIFEST_SHA256,
        DISPLACEMENT_FIXTURE_MANIFEST_SHA256,
        _PUBLIC_VALIDATION_RAW_PROVENANCE,
        evaluator,
    )


def build_lomo_raw_scientific_lock(
    split: SplitProtocolDescriptor = LOMO_SPLIT,
    evaluator: origin_relative_displacement_prediction.RawDisplacementEvaluatorConfiguration = (
        origin_relative_displacement_prediction.RAW_DISPLACEMENT_EVALUATOR
    ),
) -> dict[str, object]:
    return _build_raw_scientific_lock(
        split,
        "historical_public_displacement_train_fixtures",
        _LOMO_DATA_MANIFEST_SHA256,
        _LOMO_FIXTURE_MANIFEST_SHA256,
        _LOMO_RAW_PROVENANCE,
        evaluator,
    )


PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK = build_public_validation_raw_scientific_lock()
PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK_HASH = cast(
    str, PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK["scientific_lock_hash"]
)


def build_public_validation_physical_scientific_lock(
    evaluator_hash: str = PHYSICAL_TRAJECTORY_EVALUATOR.scientific_config_sha256,
) -> dict[str, object]:
    """Build a separate historical R2 lock for public physical diagnostics."""
    raw_lock = PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK
    return build_scientific_lock(
        {
            "lock_schema_version": "fpdbench-scientific-lock.v1",
            "benchmark_id": raw_lock["benchmark_id"],
            "benchmark_definition_hash": raw_lock["benchmark_definition_hash"],
            "data_release_id": raw_lock["data_release_id"],
            "data_release_version": raw_lock["data_release_version"],
            "data_manifest_hash": raw_lock["data_manifest_hash"],
            "data_state_id": raw_lock["data_state_id"],
            "split_protocol_id": DISPLACEMENT_SPLIT.protocol_id,
            "split_protocol_version": DISPLACEMENT_SPLIT.version,
            "split_protocol_hash": DISPLACEMENT_SPLIT.assignment_sha256,
            "evaluator_id": "physical_trajectory.ade_fde_xy_rmse",
            "evaluator_version": "1.0.0",
            "evaluator_hash": evaluator_hash,
            "schema_version": raw_lock["schema_version"],
            "schema_hash": raw_lock["schema_hash"],
            "fixture_manifest_hash": raw_lock["fixture_manifest_hash"],
            "scientific_provenance_snapshot": _PUBLIC_VALIDATION_PHYSICAL_PROVENANCE,
        }
    )


PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK = build_public_validation_physical_scientific_lock()
PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK_HASH = cast(
    str, PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK["scientific_lock_hash"]
)
LOMO_RAW_SCIENTIFIC_LOCK = build_lomo_raw_scientific_lock()
LOMO_RAW_SCIENTIFIC_LOCK_HASH = cast(str, LOMO_RAW_SCIENTIFIC_LOCK["scientific_lock_hash"])


@dataclass(frozen=True, slots=True)
class LomoFoldResult:
    campaign: HistoricalAlias
    seed: int
    held_out_match: str
    checkpoint_sha256: str
    result: ResultRecord


_RECOVERY_RESULT_SHA256 = "eb83130616d3d77c6d0d49c7d9ebe89ed8099741fa5c6163b295a084d73ac527"
_PHASE_A_RESULT_SHA256 = "f09dc83c1c9d121ed97cf001620658a6757b0fa4c35e704a652b84ffb0e4aec2"
_FOLD_ROWS = (
    (
        20260911,
        "J03WOH",
        0.25932555860260476,
        "97c3645694f234d6360bf0540f33f4a3036f34b7fa3df5e3f2be31f7af188e12",
        "3c08e3d6dbadd34fb9a14eeb581541cdd44c0601deee2c3bf54cea65885303a1",
    ),
    (
        20260911,
        "J03WOY",
        0.27084781435275795,
        "a305eb1d70021170edace7baa8f491674e3a558e9e508199b67a582ca03d9d12",
        "596f85851ec9d9fd7f393b0042554ed530204abdafe55ad630ac2d2d5e3fb25d",
    ),
    (
        20260911,
        "J03WPY",
        0.2643390758994499,
        "84b8c129642f08ec3fac558070ec52338d5bee1f88769f3bccf2d6d4295b8447",
        "22e04574cae94586e95960032e82b34e51d4aa79aa273795ab034528967c0a79",
    ),
    (
        20260911,
        "J03WQQ",
        0.27932539079736074,
        "b3265a984c9ee66bd12b608ec816cc50fee212e6b01d33c8d8770ef7e83cd7da",
        "9377d343b2a3f042530ae4756903222b2e47d37ecb4296462e68a7b34c0c445e",
    ),
    (
        20260911,
        "J03WR9",
        0.2865676739216841,
        "0a1a9a2f4e5142ea5d3fdb50cf085043d6e635b748cbd036f68ef08d4f7e040c",
        "4d9aceb52ed2a554eae81657c3174f5f2dbe9c7fd5717c7ac08958b881053f14",
    ),
    (
        20260912,
        "J03WOH",
        0.26058048135008149,
        "7b4f4090b005912dbe14acad2a58a6c2a8c96b1c214c5157e82784a7093b311f",
        "be4b13493fe85c5fb2eb78686ca19a933aa1eae459ede77b2f525bd15d4e8656",
    ),
    (
        20260912,
        "J03WOY",
        0.2725670967290143,
        "c050b060a62e6f7923b36dbcc8c45c7f622d76c6a334506d5c8f1c06444c2d5a",
        "711e0cedecde715d9ce2bdbf66d343ce53964e3561a9165b5394fd6667e3fc77",
    ),
    (
        20260912,
        "J03WPY",
        0.25903773803950331,
        "0d015c589b96fcc4c28f9121a15f70fe919db1e7f5140f9720de2ada98446963",
        "70839d48be43b327dc63b6b693833a3a84c3e05fd5166f5b5e4a8d9e23e4165a",
    ),
    (
        20260912,
        "J03WQQ",
        0.27279057262924333,
        "caacaf7ac60701a2fe01953326ac8988d602ecd2e3289aab902bbe3d7f952d02",
        "0399fb930f34bf7a222637d5a4e9d27c7930585e8ceffc6d4d7079b326f0e138",
    ),
    (
        20260912,
        "J03WR9",
        0.28237190227460079,
        "da45e7d902d59d910311715354ea3e86c4fbf94d06094243b427ab420540bee8",
        "2bea9735b6d9456a8b182d574e32a16a67d257e8de040b66e50c470578ce5270",
    ),
    (
        20260913,
        "J03WOH",
        0.25916422292514346,
        "274d636740a37fd5ca5ab927b0b56e65136450972b94eee43cdbca3f1d4e75a7",
        "b8fb9a9acaa5e3c0b2911eab1700606dd943d4ea239cff1f6c5e332f96620966",
    ),
    (
        20260913,
        "J03WOY",
        0.26984699158479752,
        "bd1dcf3a25866df55e4e2b2cc27931cb425463bb53027298c7153db49bf99daf",
        "6eca397b1c54fa77233da43792fb1774b5b35af2a4a5feb82beea5e7548163a5",
    ),
    (
        20260913,
        "J03WPY",
        0.25899030479000612,
        "b6a016e0b77de4ef8fa604c79457a9816d653cb44f9df03a7ac5973fbd46752a",
        "79fca149ae8d63cfcd841c4fc17e055153457279562783213b918399ebd7e4c2",
    ),
    (
        20260913,
        "J03WQQ",
        0.27224452546238836,
        "f1a5071f9861bd20b7b8ccbb5672f712326a6b8a715fc7e7ba221e207cfffc5b",
        "57b6e06b505ea827a149534db3e2e1c70ecfa9f9ca0e52d61a8b3e89659e4bed",
    ),
    (
        20260913,
        "J03WR9",
        0.28207571636248507,
        "c7f838b8b675fc840a2c27a603cba3188cc69ff03ebea68231165da04c3beb2c",
        "350dfa42c7b44b9ae3e2362496703b8b3ba86604a44a980ce0d2be633f2fdcc6",
    ),
)


def _fold_record(row: tuple[int, str, float, str, str]) -> LomoFoldResult:
    seed, match, raw_sre, checkpoint_sha256, fold_sha256 = row
    campaign = _FIRST_LOMO_ALIAS if seed == 20260911 else _SECOND_LOMO_ALIAS
    evidence = [
        _evidence(fold_sha256, "immutable match-heldout fold output"),
        _evidence(_RECOVERY_RESULT_SHA256, "corrected three-seed aggregation source"),
    ]
    if seed == 20260911:
        evidence.append(_evidence(_PHASE_A_RESULT_SHA256, "reused five-fold campaign result"))
    result = ResultRecord(
        run_id=f"cross_match_seed_{seed}_{match.casefold()}",
        scientific_lock_hash=LOMO_RAW_SCIENTIFIC_LOCK_HASH,
        model_checkpoint_sha256=checkpoint_sha256,
        metrics=(("raw_sre", raw_sre),),
        population=ResultPopulation.LOMO_CROSS_MATCH,
        evaluator_state=EvaluatorState.RAW_EVALUATION,
        validity=(ResultValidity.RECORDED if seed == 20260911 else ResultValidity.RECOVERED),
        output_sha256=fold_sha256,
        evidence=tuple(evidence),
        provenance_completeness=ProvenanceCompleteness.HISTORICAL_EVIDENCE_BOUND,
    )
    return LomoFoldResult(campaign, seed, match, checkpoint_sha256, result)


LOMO_FOLD_RESULTS = tuple(_fold_record(row) for row in _FOLD_ROWS)
CORRECTED_LOMO_GRAND_MEAN_RAW_SRE = 0.27000500438140806
CORRECTED_LOMO_AGGREGATE = ResultRecord(
    run_id="cross_match_three_seed_aggregate",
    scientific_lock_hash=LOMO_RAW_SCIENTIFIC_LOCK_HASH,
    model_checkpoint_sha256=None,
    metrics=(("grand_mean_raw_sre", CORRECTED_LOMO_GRAND_MEAN_RAW_SRE),),
    population=ResultPopulation.LOMO_CROSS_MATCH,
    evaluator_state=EvaluatorState.RAW_EVALUATION,
    validity=ResultValidity.RECOMPUTED,
    output_sha256=_RECOVERY_RESULT_SHA256,
    evidence=(_evidence(_RECOVERY_RESULT_SHA256, "corrected aggregation result"),),
    provenance_completeness=ProvenanceCompleteness.HISTORICAL_EVIDENCE_BOUND,
)
FIRST_LOMO_MEAN_RAW_SRE = 0.2720811027147715
FIRST_LOMO_AGGREGATE = ResultRecord(
    run_id="cross_match_first_campaign_aggregate",
    scientific_lock_hash=LOMO_RAW_SCIENTIFIC_LOCK_HASH,
    model_checkpoint_sha256=None,
    metrics=(("mean_raw_sre", FIRST_LOMO_MEAN_RAW_SRE),),
    population=ResultPopulation.LOMO_CROSS_MATCH,
    evaluator_state=EvaluatorState.RAW_EVALUATION,
    validity=ResultValidity.RECORDED,
    output_sha256=_PHASE_A_RESULT_SHA256,
    evidence=(_evidence(_PHASE_A_RESULT_SHA256, "five-fold aggregation result"),),
    provenance_completeness=ProvenanceCompleteness.HISTORICAL_EVIDENCE_BOUND,
)


@dataclass(frozen=True, slots=True)
class AggregateAdjudication:
    campaign: HistoricalAlias
    aggregate_validity: ResultValidity
    tuple_order_bug: bool
    failure: str
    evidence: EvidenceReference


INVALIDATED_SECOND_CAMPAIGN_AGGREGATE = AggregateAdjudication(
    _SECOND_LOMO_ALIAS,
    ResultValidity.INVALIDATED,
    True,
    "verify_entry returned (verified, phase_a, gate), but run assigned verified to phase_a",
    _evidence(
        "6bf6416609942c0b32af290fec94c36fef3e0362afee92981ff053950d45a2a2",
        "original aggregation invalidation record",
    ),
)
CORRECTED_AGGREGATION = AggregateAdjudication(
    _CORRECTION_ALIAS,
    ResultValidity.RECOMPUTED,
    False,
    "aggregation-only recomputation from preserved fold results and checkpoint hashes",
    _evidence(_RECOVERY_RESULT_SHA256, "corrected aggregation result and provenance"),
)
CORRECTED_AGGREGATION_REEXECUTED_TRAINING = False


@dataclass(frozen=True, slots=True)
class HistoricalModelRecord:
    model_id: str
    alias: HistoricalAlias
    role: HistoricalModelRole
    checkpoint_sha256: str
    seed: int
    parameter_count: int
    epochs: int
    optimization_steps: int
    architecture_family: str
    architecture_config_sha256: str
    training_matches: tuple[str, ...]
    training_directed_rows: int
    public_validation_matches: tuple[str, ...]
    public_validation_directed_rows: int
    scorer_calibration_reference: bool
    model_selection_protocol: UnknownValue
    evidence: tuple[EvidenceReference, ...]


FINAL_PUBLIC_MODEL = HistoricalModelRecord(
    model_id=HISTORICAL_FINAL_MODEL_ID,
    alias=_FINAL_MODEL_ALIAS,
    role=HistoricalModelRole.FINAL_PUBLIC_REFERENCE,
    checkpoint_sha256="3c5297b7c53f07e288c239d1f59b6df003ba349ea227c97377ba58d4cbac53c6",
    seed=20260912,
    parameter_count=936_962,
    epochs=42,
    optimization_steps=22_848,
    architecture_family="Context-Conditioned Transformer",
    architecture_config_sha256="5de99f809def5f85b1ee1b59d2568e0f6fd03c0f567e2c19216c203da5c0db55",
    training_matches=TRAIN_MATCHES,
    training_directed_rows=34_772,
    public_validation_matches=PUBLIC_VALIDATION_MATCHES,
    public_validation_directed_rows=430,
    scorer_calibration_reference=False,
    model_selection_protocol=UNKNOWN,
    evidence=(
        _evidence(
            "7cefe9ce4bf4e27596f7d215ac5bc93bfb84172b302ae2d677a4bbf90944d887",
            "checkpoint and parameter inventory",
        ),
        _evidence(
            "13a92c677cc9a11b2e492a8efe7ae81bb3b744b54195a096da19ff7c2380ed62",
            "immutable checkpoint freeze",
        ),
        _evidence(
            "b29250984c897c1184cb1208a390c6fdeb2a4764cfe5ee530c73c0a1c9269528",
            "public validation confirmation",
        ),
    ),
)

PUBLIC_VALIDATION_RAW_RESULT = ResultRecord(
    run_id="selected_model_public_validation_raw",
    scientific_lock_hash=PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK_HASH,
    model_checkpoint_sha256=FINAL_PUBLIC_MODEL.checkpoint_sha256,
    metrics=(("raw_sre", 0.25698394782524847),),
    population=ResultPopulation.PUBLIC_VALIDATION,
    evaluator_state=EvaluatorState.RAW_EVALUATION,
    validity=ResultValidity.RECORDED,
    output_sha256="b29250984c897c1184cb1208a390c6fdeb2a4764cfe5ee530c73c0a1c9269528",
    evidence=(
        _evidence(
            "b29250984c897c1184cb1208a390c6fdeb2a4764cfe5ee530c73c0a1c9269528",
            "public validation confirmation",
        ),
        _evidence(
            "13a92c677cc9a11b2e492a8efe7ae81bb3b744b54195a096da19ff7c2380ed62",
            "checkpoint frozen before validation",
        ),
    ),
    provenance_completeness=ProvenanceCompleteness.HISTORICAL_EVIDENCE_BOUND,
)
PUBLIC_VALIDATION_PHYSICAL_RESULT = ResultRecord(
    run_id="selected_model_public_validation_physical_diagnostics",
    scientific_lock_hash=PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK_HASH,
    model_checkpoint_sha256=FINAL_PUBLIC_MODEL.checkpoint_sha256,
    metrics=(
        ("ade_m", 0.7728278283223137),
        ("fde_m", 1.745128730406117),
        ("xy_rmse_m", 0.8841436584705827),
    ),
    population=ResultPopulation.PUBLIC_VALIDATION,
    evaluator_state=EvaluatorState.PHYSICAL_DIAGNOSTIC,
    validity=ResultValidity.RECORDED,
    output_sha256="b29250984c897c1184cb1208a390c6fdeb2a4764cfe5ee530c73c0a1c9269528",
    evidence=(
        _evidence(
            "b29250984c897c1184cb1208a390c6fdeb2a4764cfe5ee530c73c0a1c9269528",
            "public validation physical metrics",
        ),
    ),
    provenance_completeness=ProvenanceCompleteness.HISTORICAL_EVIDENCE_BOUND,
)


@dataclass(frozen=True, slots=True)
class SystemValidationEvidence:
    alias: HistoricalAlias
    role: SystemEvidenceRole
    population: ResultPopulation
    evaluator_state: EvaluatorState
    quality_bearing: bool
    evidence: EvidenceReference


SYSTEM_VALIDATION_EVIDENCE = (
    SystemValidationEvidence(
        _PREFLIGHT_ALIAS,
        SystemEvidenceRole.PREFLIGHT,
        ResultPopulation.RELEASE_SYSTEM_VALIDATION,
        EvaluatorState.RELEASE_ENGINEERING,
        False,
        _evidence(
            "fe8c6644d24644cfb4b99fe2b8acfde28621e013ab69735228a94086a1970a59",
            "runtime-only synthetic preflight",
        ),
    ),
    SystemValidationEvidence(
        _SYSTEM_PREFLIGHT_ALIAS,
        SystemEvidenceRole.PREFLIGHT,
        ResultPopulation.RELEASE_SYSTEM_VALIDATION,
        EvaluatorState.RELEASE_ENGINEERING,
        False,
        _evidence(
            "03a492e8dded161344cb979d8f194a6bbcd1978ae0a49fe600098126b2146b7e",
            "preflight role has no quality result",
        ),
    ),
    SystemValidationEvidence(
        _RELEASE_HANDOFF_ALIAS,
        SystemEvidenceRole.RELEASE_ENGINEERING,
        ResultPopulation.RELEASE_SYSTEM_VALIDATION,
        EvaluatorState.RELEASE_ENGINEERING,
        False,
        _evidence(
            "c2fa14ec4e8e424825e57d6dca0f80c32d6b9ba4ce642809668e3d317ba38a56",
            "release engineering handoff inventory",
        ),
    ),
)


HISTORICAL_RESULTS = tuple(fold.result for fold in LOMO_FOLD_RESULTS) + (
    CORRECTED_LOMO_AGGREGATE,
    FIRST_LOMO_AGGREGATE,
    PUBLIC_VALIDATION_RAW_RESULT,
    PUBLIC_VALIDATION_PHYSICAL_RESULT,
)
PRIVATE_RESULT_RECORDS: tuple[ResultRecord, ...] = ()
TRAINING_REEXECUTED_DURING_RECONSTRUCTION = False
