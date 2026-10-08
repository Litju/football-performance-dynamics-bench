"""Canonical match roles, LOMO assignment, and cross-match uncertainty semantics."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from fpdbench.data import SplitProtocolDescriptor
from fpdbench.provenance import EvidenceReference, validate_evidence_reference_shape

ABSOLUTE_POSITION_BENCHMARK_ID = (
    "conditional_multi_agent_motion_prediction/absolute_position_prediction"
)
DISPLACEMENT_BENCHMARK_ID = (
    "conditional_multi_agent_motion_prediction/origin_relative_displacement_prediction"
)
BENCHMARK_IDS = (ABSOLUTE_POSITION_BENCHMARK_ID, DISPLACEMENT_BENCHMARK_ID)
PUBLIC_TRAIN_MATCHES = ("J03WOH", "J03WOY", "J03WPY", "J03WQQ", "J03WR9")
PUBLIC_VALIDATION_MATCHES = ("J03WN1",)
HISTORICAL_PRIVATE_MATCHES = ("J03WMX",)
HISTORICAL_TRAINING_SEEDS = (20260911, 20260912, 20260913)


class MatchRole(StrEnum):
    PUBLIC_TRAIN = "PUBLIC_TRAIN"
    PUBLIC_VALIDATION = "PUBLIC_VALIDATION"
    HISTORICAL_PRIVATE_QUALIFICATION = "HISTORICAL_PRIVATE_QUALIFICATION"
    PUBLIC_TEST = "PUBLIC_TEST"
    LOMO_HELDOUT = "LOMO_HELDOUT"


class RoleAvailability(StrEnum):
    AVAILABLE = "available"
    METADATA_ONLY = "metadata_only"
    NOT_DEFINED = "not_defined"


class TruthAccess(StrEnum):
    PUBLIC = "public"
    PRIVATE_NOT_OPENED = "private_not_opened"
    NOT_APPLICABLE = "not_applicable"


class ModelSelectionUse(StrEnum):
    UNKNOWN_HISTORICAL = "unknown_historical"
    DECLARED_PER_EXPERIMENT = "declared_per_experiment"


class AnalysisUnit(StrEnum):
    MATCH = "match"
    PHYSICAL_WINDOW = "physical_window"
    DIRECTED_SCENE = "directed_scene"
    TRAINING_SEED = "training_seed"


class AggregationRule(StrEnum):
    FULL_MATCH_POPULATION = "full_match_population"
    EQUAL_MEAN_ACROSS_MATCHES = "equal_mean_across_match_summaries"


class UncertaintyStatus(StrEnum):
    ESTIMABLE = "estimable"
    NOT_ESTIMABLE = "not_estimable"


@dataclass(frozen=True, slots=True)
class RoleAssignment:
    role: MatchRole
    match_ids: tuple[str, ...]
    availability: RoleAvailability
    truth_access: TruthAccess

    def __post_init__(self) -> None:
        object.__setattr__(self, "match_ids", tuple(self.match_ids))
        if len(set(self.match_ids)) != len(self.match_ids) or any(
            not item for item in self.match_ids
        ):
            raise ValueError("role match IDs must be unique and nonempty")
        if self.availability is RoleAvailability.NOT_DEFINED and self.match_ids:
            raise ValueError("undefined roles cannot contain matches")
        if self.availability is RoleAvailability.AVAILABLE and not self.match_ids:
            raise ValueError("available roles require matches")


def match_role_assignment_sha256(assignments: Sequence[RoleAssignment]) -> str:
    """Hash role-to-match assignment only; access and evaluator state are separate."""
    by_role = {item.role.value: sorted(item.match_ids) for item in assignments}
    if len(by_role) != len(assignments):
        raise ValueError("role assignments must be unique")
    payload = json.dumps(by_role, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class MatchRoleProtocol:
    descriptor: SplitProtocolDescriptor
    population_semantics: str
    assignments: tuple[RoleAssignment, ...]
    experimental_unit: AnalysisUnit = AnalysisUnit.MATCH
    measurement_unit: AnalysisUnit = AnalysisUnit.DIRECTED_SCENE
    aggregation_unit: AnalysisUnit = AnalysisUnit.MATCH
    uncertainty_unit: AnalysisUnit = AnalysisUnit.MATCH

    def __post_init__(self) -> None:
        object.__setattr__(self, "assignments", tuple(self.assignments))
        if self.descriptor.grouping != "match":
            raise ValueError("conditional-motion roles are grouped by physical match")
        by_role = {item.role: item for item in self.assignments}
        expected_matches = {
            MatchRole.PUBLIC_TRAIN: PUBLIC_TRAIN_MATCHES,
            MatchRole.PUBLIC_VALIDATION: PUBLIC_VALIDATION_MATCHES,
            MatchRole.HISTORICAL_PRIVATE_QUALIFICATION: HISTORICAL_PRIVATE_MATCHES,
            MatchRole.PUBLIC_TEST: (),
        }
        if set(by_role) != set(expected_matches):
            raise ValueError("canonical role protocol must define the four base roles")
        if any(by_role[role].match_ids != matches for role, matches in expected_matches.items()):
            raise ValueError("canonical role assignment differs from the repaired-state authority")
        assigned = tuple(match for item in self.assignments for match in item.match_ids)
        if len(assigned) != len(set(assigned)):
            raise ValueError("a match cannot appear in more than one base role")
        expected_metadata = {
            MatchRole.PUBLIC_TRAIN: (RoleAvailability.AVAILABLE, TruthAccess.PUBLIC),
            MatchRole.PUBLIC_VALIDATION: (RoleAvailability.AVAILABLE, TruthAccess.PUBLIC),
            MatchRole.HISTORICAL_PRIVATE_QUALIFICATION: (
                RoleAvailability.METADATA_ONLY,
                TruthAccess.PRIVATE_NOT_OPENED,
            ),
            MatchRole.PUBLIC_TEST: (RoleAvailability.NOT_DEFINED, TruthAccess.NOT_APPLICABLE),
        }
        if any(
            (by_role[role].availability, by_role[role].truth_access) != metadata
            for role, metadata in expected_metadata.items()
        ):
            raise ValueError("canonical role availability or truth access changed")
        if not self.descriptor.protocol_id or not self.population_semantics:
            raise ValueError("role protocol identity and population semantics are required")
        if self.descriptor.assignment_sha256 != match_role_assignment_sha256(self.assignments):
            raise ValueError("role protocol hash must cover role-to-match assignment only")
        if (
            self.experimental_unit is not AnalysisUnit.MATCH
            or self.measurement_unit is not AnalysisUnit.DIRECTED_SCENE
            or self.aggregation_unit is not AnalysisUnit.MATCH
            or self.uncertainty_unit is not AnalysisUnit.MATCH
        ):
            raise ValueError("conditional-motion inference and aggregation are match-grouped")

    @property
    def assignment_sha256(self) -> str:
        return self.descriptor.assignment_sha256

    @property
    def protocol_id(self) -> str:
        return self.descriptor.protocol_id

    @property
    def version(self) -> str:
        return self.descriptor.version

    @property
    def public_test_defined(self) -> bool:
        return False

    def assignment(self, role: MatchRole) -> RoleAssignment:
        return next(item for item in self.assignments if item.role is role)

    def available_matches(self, role: MatchRole) -> tuple[str, ...]:
        assignment = self.assignment(role)
        if assignment.availability is not RoleAvailability.AVAILABLE:
            raise ValueError(f"{role.value} has no available public match membership")
        return assignment.match_ids


_BASE_ROLE_ASSIGNMENTS = (
    RoleAssignment(
        MatchRole.PUBLIC_TRAIN,
        PUBLIC_TRAIN_MATCHES,
        RoleAvailability.AVAILABLE,
        TruthAccess.PUBLIC,
    ),
    RoleAssignment(
        MatchRole.PUBLIC_VALIDATION,
        PUBLIC_VALIDATION_MATCHES,
        RoleAvailability.AVAILABLE,
        TruthAccess.PUBLIC,
    ),
    RoleAssignment(
        MatchRole.HISTORICAL_PRIVATE_QUALIFICATION,
        HISTORICAL_PRIVATE_MATCHES,
        RoleAvailability.METADATA_ONLY,
        TruthAccess.PRIVATE_NOT_OPENED,
    ),
    RoleAssignment(
        MatchRole.PUBLIC_TEST,
        (),
        RoleAvailability.NOT_DEFINED,
        TruthAccess.NOT_APPLICABLE,
    ),
)
CANONICAL_MATCH_ROLE_PROTOCOL = MatchRoleProtocol(
    descriptor=SplitProtocolDescriptor(
        protocol_id="conditional_motion.match_role_assignment.r3",
        version="1.0.0",
        assignment_sha256=match_role_assignment_sha256(_BASE_ROLE_ASSIGNMENTS),
        grouping="match",
        access_policy=(
            "public training/validation; private qualification metadata only; no public test"
        ),
    ),
    population_semantics=(
        "Conditional-motion trajectories from physical matches; each physical window yields "
        "paired directed scenes."
    ),
    experimental_unit=AnalysisUnit.MATCH,
    measurement_unit=AnalysisUnit.DIRECTED_SCENE,
    aggregation_unit=AnalysisUnit.MATCH,
    uncertainty_unit=AnalysisUnit.MATCH,
    assignments=_BASE_ROLE_ASSIGNMENTS,
)


@dataclass(frozen=True, slots=True)
class LomoFold:
    fold_id: str
    training_matches: tuple[str, ...]
    held_out_match: str
    evaluation_role: MatchRole = MatchRole.LOMO_HELDOUT

    def __post_init__(self) -> None:
        object.__setattr__(self, "training_matches", tuple(self.training_matches))
        if not self.fold_id or not self.held_out_match:
            raise ValueError("LOMO fold and held-out match identities are required")
        if len(self.training_matches) != 4 or len(set(self.training_matches)) != 4:
            raise ValueError("each canonical LOMO fold trains on four unique matches")
        if self.held_out_match in self.training_matches:
            raise ValueError("the held-out match cannot appear in its training fold")
        if self.evaluation_role is not MatchRole.LOMO_HELDOUT:
            raise ValueError("LOMO held-out matches use the LOMO_HELDOUT evaluation role")


def make_lomo_folds(training_matches: Sequence[str]) -> tuple[LomoFold, ...]:
    """Deterministically hold out each of the five public-training matches once."""
    matches = tuple(sorted(training_matches))
    if len(matches) != 5 or set(matches) != set(PUBLIC_TRAIN_MATCHES):
        raise ValueError("LOMO accepts exactly the five PUBLIC_TRAIN matches")
    return tuple(
        LomoFold(
            fold_id=f"fold-{index + 1}",
            training_matches=tuple(match for match in matches if match != held_out),
            held_out_match=held_out,
        )
        for index, held_out in enumerate(matches)
    )


def lomo_split_sha256(folds: Sequence[LomoFold]) -> str:
    """Hash fold IDs and held-out matches only; seeds and evaluators are not inputs."""
    fold_ids = [fold.fold_id for fold in folds]
    if len(fold_ids) != len(set(fold_ids)):
        raise ValueError("LOMO fold IDs must be unique")
    assignment = sorted((fold.fold_id, fold.held_out_match) for fold in folds)
    payload = json.dumps(assignment, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class LomoProtocol:
    descriptor: SplitProtocolDescriptor
    benchmark_ids: tuple[str, ...]
    folds: tuple[LomoFold, ...]
    excluded_matches: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "benchmark_ids", tuple(self.benchmark_ids))
        object.__setattr__(self, "folds", tuple(self.folds))
        object.__setattr__(self, "excluded_matches", tuple(self.excluded_matches))
        if self.descriptor.grouping != "match":
            raise ValueError("LOMO folds are grouped by physical match")
        expected_folds = make_lomo_folds(PUBLIC_TRAIN_MATCHES)
        if self.benchmark_ids != BENCHMARK_IDS or self.folds != expected_folds:
            raise ValueError("canonical LOMO must bind both benchmarks and five public-train folds")
        if self.excluded_matches != (*PUBLIC_VALIDATION_MATCHES, *HISTORICAL_PRIVATE_MATCHES):
            raise ValueError("validation and historical-private matches are excluded from LOMO")
        if not self.descriptor.protocol_id:
            raise ValueError("LOMO protocol identity and version are required")
        if self.descriptor.assignment_sha256 != lomo_split_sha256(self.folds):
            raise ValueError("LOMO split hash must cover fold assignment only")

    @property
    def split_sha256(self) -> str:
        return self.descriptor.assignment_sha256

    @property
    def protocol_id(self) -> str:
        return self.descriptor.protocol_id

    @property
    def version(self) -> str:
        return self.descriptor.version


CANONICAL_LOMO_PROTOCOL = LomoProtocol(
    descriptor=SplitProtocolDescriptor(
        protocol_id="conditional_motion.public_train_lomo.r3",
        version="1.0.0",
        assignment_sha256=lomo_split_sha256(make_lomo_folds(PUBLIC_TRAIN_MATCHES)),
        grouping="match",
        access_policy="five public-training matches; validation/private qualification excluded",
    ),
    benchmark_ids=BENCHMARK_IDS,
    folds=make_lomo_folds(PUBLIC_TRAIN_MATCHES),
    excluded_matches=(*PUBLIC_VALIDATION_MATCHES, *HISTORICAL_PRIVATE_MATCHES),
)


def _evidence(sha256: str, description: str) -> EvidenceReference:
    return EvidenceReference(f"registry://sha256/{sha256}", sha256, description)


_ABSOLUTE_SPLIT_EVIDENCE = _evidence(
    "854d709005571fe77dbc79fe6d4a3ce4c6302d797400a46c385801ffb5cd561d",
    "absolute-position split populations",
)
_DISPLACEMENT_ROLE_EVIDENCE = _evidence(
    "2fe0fb974931b2fb691c56aa50c66689f37a184c1a923f77d34ed1343f5e03b3",
    "displacement match roles and population counts",
)
_DISPLACEMENT_SPLIT_EVIDENCE = _evidence(
    "5e060c84952cd4544fde6b80a93675c02c06036440ef9d2c97aa96eec618709c",
    "displacement public split manifest",
)
_POPULATION_RECORD_EVIDENCE = _evidence(
    "6a86019ed3e474816dfc5188aa5cbb6a36cbf841a582a6b7a3515fb02e4dc15f",
    "source, repaired-state, and fixture population records",
)
_DISPLACEMENT_FIXTURE_EVIDENCE = _evidence(
    "134cfd7a6a3b5bcdf04d1d03772e8674c37b2da301e81245aabe2be5b11519b4",
    "displacement public fixture manifest",
)


@dataclass(frozen=True, slots=True)
class BenchmarkMembership:
    benchmark_id: str
    membership_id: str
    target_representation: str
    data_state_id: str
    train_physical_windows: int
    train_directed_rows: int
    validation_physical_windows: int
    validation_directed_rows: int
    fixture_manifest_sha256: str
    split_manifest_sha256: str
    historical_membership_states: tuple[str, ...]
    row_crosswalk_status: str
    evidence: tuple[EvidenceReference, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "historical_membership_states", tuple(self.historical_membership_states)
        )
        object.__setattr__(self, "evidence", tuple(self.evidence))
        if not all(
            (
                self.benchmark_id,
                self.membership_id,
                self.target_representation,
                self.data_state_id,
                self.historical_membership_states,
                self.row_crosswalk_status,
                self.evidence,
            )
        ):
            raise ValueError("benchmark membership identity, history, and evidence are required")
        if self.train_physical_windows <= 0 or self.validation_physical_windows <= 0:
            raise ValueError("public membership counts must be positive")
        if self.train_directed_rows != 2 * self.train_physical_windows:
            raise ValueError("each public train window must have two directed rows")
        if self.validation_directed_rows != 2 * self.validation_physical_windows:
            raise ValueError("each public validation window must have two directed rows")
        for digest in (self.fixture_manifest_sha256, self.split_manifest_sha256):
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise ValueError("membership manifest references must be lowercase SHA-256")


ABSOLUTE_POSITION_MEMBERSHIP = BenchmarkMembership(
    benchmark_id=ABSOLUTE_POSITION_BENCHMARK_ID,
    membership_id="absolute-position-repaired-public-membership",
    target_representation="absolute pitch-normalized XY",
    data_state_id="repaired_position_measurement_state",
    train_physical_windows=17_386,
    train_directed_rows=34_772,
    validation_physical_windows=215,
    validation_directed_rows=430,
    fixture_manifest_sha256="bac933675d6ce7fa36e49ac69d6a1b5a7321020d1e5eac31a1a1d7b0be5a625a",
    split_manifest_sha256="1f32aed909c471b83fab86a7ac38da59076ceb107182a612d8746d33bbeda22b",
    historical_membership_states=(
        "original absolute-position population",
        "repaired-state absolute-position population",
    ),
    row_crosswalk_status="unresolved between original and repaired-state populations",
    evidence=(_ABSOLUTE_SPLIT_EVIDENCE, _POPULATION_RECORD_EVIDENCE),
)
DISPLACEMENT_MEMBERSHIP = BenchmarkMembership(
    benchmark_id=DISPLACEMENT_BENCHMARK_ID,
    membership_id="displacement-repaired-public-fixture-membership",
    target_representation="origin-relative displacement",
    data_state_id="repaired_position_measurement_state",
    train_physical_windows=17_386,
    train_directed_rows=34_772,
    validation_physical_windows=215,
    validation_directed_rows=430,
    fixture_manifest_sha256="134cfd7a6a3b5bcdf04d1d03772e8674c37b2da301e81245aabe2be5b11519b4",
    split_manifest_sha256="5e060c84952cd4544fde6b80a93675c02c06036440ef9d2c97aa96eec618709c",
    historical_membership_states=("final public displacement fixture population",),
    row_crosswalk_status="benchmark-specific fixture membership",
    evidence=(
        _DISPLACEMENT_ROLE_EVIDENCE,
        _DISPLACEMENT_SPLIT_EVIDENCE,
        _POPULATION_RECORD_EVIDENCE,
        _DISPLACEMENT_FIXTURE_EVIDENCE,
    ),
)


@dataclass(frozen=True, slots=True)
class BenchmarkProtocolBinding:
    benchmark_id: str
    membership: BenchmarkMembership
    role_protocol_id: str
    lomo_protocol_id: str
    evaluation_populations: tuple[MatchRole, ...]
    public_validation_aggregation: AggregationRule
    lomo_aggregation: AggregationRule
    public_validation_evaluated_historically: bool
    historical_model_selection_use: ModelSelectionUse
    future_model_selection_use: ModelSelectionUse
    evaluator_ids: tuple[str, ...]
    calibrated_scorer_status: str
    historical_split_protocols: tuple[tuple[str, str], ...]
    historical_scientific_lock_hashes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "evaluation_populations", tuple(self.evaluation_populations))
        object.__setattr__(self, "evaluator_ids", tuple(self.evaluator_ids))
        object.__setattr__(
            self, "historical_split_protocols", tuple(self.historical_split_protocols)
        )
        object.__setattr__(
            self, "historical_scientific_lock_hashes", tuple(self.historical_scientific_lock_hashes)
        )
        if self.membership.benchmark_id != self.benchmark_id:
            raise ValueError("benchmark binding and membership identities must match")
        if self.evaluation_populations != (MatchRole.PUBLIC_VALIDATION, MatchRole.LOMO_HELDOUT):
            raise ValueError(
                "only public validation and LOMO held-out matches are evaluation populations"
            )
        if (
            self.public_validation_aggregation is not AggregationRule.FULL_MATCH_POPULATION
            or self.lomo_aggregation is not AggregationRule.EQUAL_MEAN_ACROSS_MATCHES
        ):
            raise ValueError("evaluation aggregation must preserve match-level populations")
        if not self.public_validation_evaluated_historically:
            raise ValueError("historical public-validation evaluation is known")
        if self.historical_model_selection_use is not ModelSelectionUse.UNKNOWN_HISTORICAL:
            raise ValueError("historical model-selection use remains unknown")
        if self.future_model_selection_use is not ModelSelectionUse.DECLARED_PER_EXPERIMENT:
            raise ValueError("future model-selection use is declared per experiment")
        if not self.evaluator_ids or len(set(self.evaluator_ids)) != len(self.evaluator_ids):
            raise ValueError("benchmark evaluator bindings must be unique and nonempty")

    def require_evaluation_population(self, role: MatchRole) -> MatchRole:
        if role not in self.evaluation_populations:
            raise ValueError(f"{role.value} is not an available public evaluation population")
        return role


ABSOLUTE_POSITION_PROTOCOL_BINDING = BenchmarkProtocolBinding(
    benchmark_id=ABSOLUTE_POSITION_BENCHMARK_ID,
    membership=ABSOLUTE_POSITION_MEMBERSHIP,
    role_protocol_id=CANONICAL_MATCH_ROLE_PROTOCOL.protocol_id,
    lomo_protocol_id=CANONICAL_LOMO_PROTOCOL.protocol_id,
    evaluation_populations=(MatchRole.PUBLIC_VALIDATION, MatchRole.LOMO_HELDOUT),
    public_validation_aggregation=AggregationRule.FULL_MATCH_POPULATION,
    lomo_aggregation=AggregationRule.EQUAL_MEAN_ACROSS_MATCHES,
    public_validation_evaluated_historically=True,
    historical_model_selection_use=ModelSelectionUse.UNKNOWN_HISTORICAL,
    future_model_selection_use=ModelSelectionUse.DECLARED_PER_EXPERIMENT,
    evaluator_ids=(
        "absolute_position.population_sre_targets",
        "absolute_position.per_target_progress",
        "absolute_position.historical_continuous_pwl_v3",
        "physical_trajectory.ade_fde_xy_rmse",
    ),
    calibrated_scorer_status="historical scorer available",
    historical_split_protocols=(
        ("absolute-position original population snapshot", "historical"),
        ("absolute-position repaired-state population snapshot", "historical"),
    ),
)
DISPLACEMENT_PROTOCOL_BINDING = BenchmarkProtocolBinding(
    benchmark_id=DISPLACEMENT_BENCHMARK_ID,
    membership=DISPLACEMENT_MEMBERSHIP,
    role_protocol_id=CANONICAL_MATCH_ROLE_PROTOCOL.protocol_id,
    lomo_protocol_id=CANONICAL_LOMO_PROTOCOL.protocol_id,
    evaluation_populations=(MatchRole.PUBLIC_VALIDATION, MatchRole.LOMO_HELDOUT),
    public_validation_aggregation=AggregationRule.FULL_MATCH_POPULATION,
    lomo_aggregation=AggregationRule.EQUAL_MEAN_ACROSS_MATCHES,
    public_validation_evaluated_historically=True,
    historical_model_selection_use=ModelSelectionUse.UNKNOWN_HISTORICAL,
    future_model_selection_use=ModelSelectionUse.DECLARED_PER_EXPERIMENT,
    evaluator_ids=(
        "origin_relative_displacement_raw_population_sre",
        "physical_trajectory.ade_fde_xy_rmse",
    ),
    calibrated_scorer_status="unavailable",
    historical_split_protocols=(
        ("match_grouped_displacement_public_split", "1.0.0"),
        ("match_grouped_cross_match_split", "1.0.0"),
    ),
    historical_scientific_lock_hashes=(
        "d56ef8e1ff37276e258d516fa9ce26231403222e549296777ee27e5f38cfeedc",
        "572e28bb5b4675a1fac91eb7c2c2c9cd4f00b28119aa447dd563c080a704cfd0",
    ),
)
BENCHMARK_PROTOCOL_BINDINGS = (
    ABSOLUTE_POSITION_PROTOCOL_BINDING,
    DISPLACEMENT_PROTOCOL_BINDING,
)


@dataclass(frozen=True, slots=True)
class MatchUncertaintySummary:
    n_match: int
    point_estimate: float
    between_match_standard_deviation: float | None
    between_match_standard_error: float | None
    status: UncertaintyStatus
    reason: str | None
    confidence_interval: tuple[float, float] | None = None
    confidence_interval_status: str = "method not declared"

    @property
    def unit(self) -> AnalysisUnit:
        return AnalysisUnit.MATCH


def summarize_match_scores(match_scores: Mapping[str, float]) -> MatchUncertaintySummary:
    """Summarize one score per match; rows and directed scenes are never units here."""
    if not match_scores:
        raise ValueError("match uncertainty requires finite scores for at least one match")
    known_matches = set((*PUBLIC_TRAIN_MATCHES, *PUBLIC_VALIDATION_MATCHES))
    if set(match_scores) - known_matches:
        raise ValueError("uncertainty keys must be known public match IDs, not rows or scenes")
    if any(not math.isfinite(score) for score in match_scores.values()):
        raise ValueError("match uncertainty requires finite scores for at least one match")
    values = tuple(match_scores.values())
    point = math.fsum(values) / len(values)
    if len(values) == 1:
        return MatchUncertaintySummary(
            n_match=1,
            point_estimate=point,
            between_match_standard_deviation=None,
            between_match_standard_error=None,
            status=UncertaintyStatus.NOT_ESTIMABLE,
            reason="between-match uncertainty requires at least two matches",
        )
    mean_square_deviation = math.fsum((value - point) ** 2 for value in values) / (len(values) - 1)
    standard_deviation = math.sqrt(mean_square_deviation)
    return MatchUncertaintySummary(
        n_match=len(values),
        point_estimate=point,
        between_match_standard_deviation=standard_deviation,
        between_match_standard_error=standard_deviation / math.sqrt(len(values)),
        status=UncertaintyStatus.ESTIMABLE,
        reason=None,
    )


@dataclass(frozen=True, slots=True)
class SeedSensitivitySummary:
    n_seeds: int
    seed_level_means: tuple[tuple[int, float], ...]
    mean: float
    sample_standard_deviation: float | None
    unit: AnalysisUnit = AnalysisUnit.TRAINING_SEED
    interpretation: str = "seed sensitivity only; not independent match uncertainty"


@dataclass(frozen=True, slots=True)
class LomoResultSummary:
    per_match_means: tuple[tuple[str, float], ...]
    generalization: MatchUncertaintySummary
    seed_sensitivity: SeedSensitivitySummary
    balanced_grand_mean: float


def summarize_lomo_scores(
    scores_by_seed: Mapping[int, Mapping[str, float]],
) -> LomoResultSummary:
    """Average repeated seeds within match, then infer across the five match summaries."""
    expected_matches = set(PUBLIC_TRAIN_MATCHES)
    if not scores_by_seed:
        raise ValueError("LOMO summary requires at least one seed")
    for scores in scores_by_seed.values():
        if set(scores) != expected_matches:
            raise ValueError("each LOMO seed must score exactly the five held-out matches")
        if any(not math.isfinite(score) for score in scores.values()):
            raise ValueError("LOMO scores must be finite")

    seeds = tuple(sorted(scores_by_seed))
    per_match = tuple(
        (
            match,
            math.fsum(scores_by_seed[seed][match] for seed in seeds) / len(seeds),
        )
        for match in PUBLIC_TRAIN_MATCHES
    )
    seed_means = tuple(
        (
            seed,
            math.fsum(scores_by_seed[seed][match] for match in PUBLIC_TRAIN_MATCHES)
            / len(PUBLIC_TRAIN_MATCHES),
        )
        for seed in seeds
    )
    seed_values = tuple(value for _, value in seed_means)
    seed_sd = None
    if len(seed_values) >= 2:
        seed_mean = math.fsum(seed_values) / len(seed_values)
        seed_sd = math.sqrt(
            math.fsum((value - seed_mean) ** 2 for value in seed_values) / (len(seed_values) - 1)
        )
    cells = tuple(scores_by_seed[seed][match] for seed in seeds for match in PUBLIC_TRAIN_MATCHES)
    return LomoResultSummary(
        per_match_means=per_match,
        generalization=summarize_match_scores(dict(per_match)),
        seed_sensitivity=SeedSensitivitySummary(
            n_seeds=len(seeds),
            seed_level_means=seed_means,
            mean=math.fsum(seed_values) / len(seed_values),
            sample_standard_deviation=seed_sd,
        ),
        balanced_grand_mean=math.fsum(cells) / len(cells),
    )


@dataclass(frozen=True, slots=True)
class DirectedScenePartition:
    match_id: str
    physical_window_id: str
    directed_scene_id: str
    partition_id: str

    def __post_init__(self) -> None:
        if not all(
            (self.match_id, self.physical_window_id, self.directed_scene_id, self.partition_id)
        ):
            raise ValueError(
                "scene partition assignments require match, window, scene, and partition IDs"
            )


def validate_match_group_assignments(scenes: Sequence[DirectedScenePartition]) -> None:
    """Reject cross-role/fold match leakage and split directed pairs."""
    if not scenes:
        raise ValueError("at least one directed scene assignment is required")
    by_window: dict[tuple[str, str], tuple[set[str], set[str], set[str]]] = {}
    match_partitions: dict[str, set[str]] = {}
    seen_scenes: set[tuple[str, str, str]] = set()
    for scene in scenes:
        scene_key = (scene.match_id, scene.physical_window_id, scene.directed_scene_id)
        if scene_key in seen_scenes:
            raise ValueError("directed scene assignments must be unique per physical window")
        seen_scenes.add(scene_key)
        matches, partitions, scene_ids = by_window.setdefault(
            (scene.match_id, scene.physical_window_id), (set(), set(), set())
        )
        matches.add(scene.match_id)
        partitions.add(scene.partition_id)
        scene_ids.add(scene.directed_scene_id)
        match_partitions.setdefault(scene.match_id, set()).add(scene.partition_id)
    for matches, partitions, scene_ids in by_window.values():
        if len(matches) != 1 or len(partitions) != 1:
            raise ValueError(
                "both directed scenes from one physical window must share one match partition"
            )
        if len(scene_ids) != 2:
            raise ValueError("each physical window must retain its pair of directed scenes")
    if any(len(partitions) != 1 for partitions in match_partitions.values()):
        raise ValueError("all windows from one match must stay in one role or LOMO fold")


def canonical_protocol_evidence_references() -> tuple[EvidenceReference, ...]:
    """Return unique references consumed by the canonical split/population definitions."""
    references = {
        item.uri: item
        for binding in BENCHMARK_PROTOCOL_BINDINGS
        for item in binding.membership.evidence
    }
    return tuple(references[key] for key in sorted(references))


def validate_canonical_protocols() -> tuple[str, ...]:
    errors: list[str] = []
    if tuple(binding.benchmark_id for binding in BENCHMARK_PROTOCOL_BINDINGS) != BENCHMARK_IDS:
        errors.append(
            "canonical protocols must bind exactly the absolute and displacement benchmarks"
        )
    if ABSOLUTE_POSITION_MEMBERSHIP.membership_id == DISPLACEMENT_MEMBERSHIP.membership_id:
        errors.append("benchmark-specific public fixture memberships must remain distinct")
    for reference in canonical_protocol_evidence_references():
        errors.extend(validate_evidence_reference_shape(reference))
    for binding in BENCHMARK_PROTOCOL_BINDINGS:
        if binding.role_protocol_id != CANONICAL_MATCH_ROLE_PROTOCOL.protocol_id:
            errors.append(f"{binding.benchmark_id}: wrong shared role protocol binding")
        if binding.lomo_protocol_id != CANONICAL_LOMO_PROTOCOL.protocol_id:
            errors.append(f"{binding.benchmark_id}: wrong canonical LOMO protocol binding")
    return tuple(sorted(set(errors)))


__all__ = [
    "ABSOLUTE_POSITION_BENCHMARK_ID",
    "ABSOLUTE_POSITION_MEMBERSHIP",
    "ABSOLUTE_POSITION_PROTOCOL_BINDING",
    "AggregationRule",
    "AnalysisUnit",
    "BENCHMARK_IDS",
    "BENCHMARK_PROTOCOL_BINDINGS",
    "BenchmarkMembership",
    "BenchmarkProtocolBinding",
    "CANONICAL_LOMO_PROTOCOL",
    "CANONICAL_MATCH_ROLE_PROTOCOL",
    "DISPLACEMENT_BENCHMARK_ID",
    "DISPLACEMENT_MEMBERSHIP",
    "DISPLACEMENT_PROTOCOL_BINDING",
    "HISTORICAL_PRIVATE_MATCHES",
    "HISTORICAL_TRAINING_SEEDS",
    "LomoFold",
    "LomoProtocol",
    "LomoResultSummary",
    "MatchRole",
    "MatchRoleProtocol",
    "MatchUncertaintySummary",
    "ModelSelectionUse",
    "PUBLIC_TRAIN_MATCHES",
    "PUBLIC_VALIDATION_MATCHES",
    "RoleAssignment",
    "RoleAvailability",
    "SeedSensitivitySummary",
    "TruthAccess",
    "UncertaintyStatus",
    "canonical_protocol_evidence_references",
    "lomo_split_sha256",
    "make_lomo_folds",
    "match_role_assignment_sha256",
    "summarize_lomo_scores",
    "summarize_match_scores",
    "validate_canonical_protocols",
    "validate_match_group_assignments",
    "DirectedScenePartition",
]
