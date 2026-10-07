"""Separate benchmark identities from queryable historical research objects."""

import re

from fpdbench.benchmarks.base import (
    UNKNOWN,
    BenchmarkDefinition,
    FamilyLifecycleStatus,
    ReleaseStatus,
    ResearchFamilyDefinition,
    ResearchObjectDefinition,
    ResearchObjectType,
)
from fpdbench.provenance import HistoricalAlias

_CANONICAL_ID = re.compile(r"^[a-z][a-z0-9_]*(?:/[a-z][a-z0-9_]*)?$")
RESEARCH_FAMILY_DEFINITIONS = (
    ResearchFamilyDefinition(
        family_id="workload_performance_state",
        public_name="Workload and Performance State",
        technical_name="workload_performance_state",
        research_question=(
            "Can workload and performance state be inferred or reconstructed from observed or "
            "synthetic training and session information, and which formulations are scientifically "
            "recoverable from the historical evidence?"
        ),
        scientific_scope=(
            "Observed or synthetic training and session information, including the historical "
            "whole-session performance-state study and signed tangential-acceleration formulation."
        ),
        known_non_claims=(
            "The historical whole-session study is partial and "
            "does not define an executable benchmark.",
            "Signed tangential acceleration is an invalidated historical formulation, "
            "not a validated benchmark.",
        ),
        r1_lifecycle=FamilyLifecycleStatus.RECONSTRUCTION_PENDING,
        current_lifecycle=(FamilyLifecycleStatus.RECONSTRUCTION_COMPLETE_NO_QUALIFIED_BENCHMARK),
        release_status=ReleaseStatus.UNRELEASED,
        unresolved_task_fields=(
            ("whole_session.target_formulas", UNKNOWN),
            ("whole_session.units", UNKNOWN),
            ("whole_session.causal_boundary", UNKNOWN),
            ("whole_session.horizon", UNKNOWN),
            ("whole_session.population", UNKNOWN),
            ("whole_session.direct_model_bindings", UNKNOWN),
        ),
    ),
    ResearchFamilyDefinition(
        family_id="multimodal_state_estimation",
        public_name="Multimodal State Estimation",
        technical_name="multimodal_state_estimation",
        research_question=(
            "Can noisy, asynchronous, multirate sensor observations "
            "support reconstruction of clean or latent athlete state, and "
            "which target families are identifiable?"
        ),
        scientific_scope=(
            "Reconstruction from noisy, asynchronous, multirate sensor observations, preserving "
            "historical pilot's scoped negative result."
        ),
        known_non_claims=(
            "The historical negative result is scoped to the recovered pilot, "
            "not a universal impossibility claim.",
            "No target family was selected.",
        ),
        r1_lifecycle=FamilyLifecycleStatus.RECONSTRUCTION_PENDING,
        current_lifecycle=(
            FamilyLifecycleStatus.RECONSTRUCTION_COMPLETE_SCOPED_NEGATIVE_NO_SELECTED_BENCHMARK
        ),
        release_status=ReleaseStatus.UNRELEASED,
        unresolved_task_fields=(
            ("exact_temporal_alignment", UNKNOWN),
            ("selected_target_family", UNKNOWN),
            ("target_family_viability", UNKNOWN),
        ),
    ),
    ResearchFamilyDefinition(
        family_id="future_response_forecasting",
        public_name="Future Response Forecasting",
        technical_name="future_response_forecasting",
        research_question=(
            "Given causal history and ex-ante available future exposure, can subsequent athlete or "
            "performance response be forecast?"
        ),
        scientific_scope=(
            "Research into response forecasting from causal history and future exposure available "
            "ex ante; no historical benchmark identity has been recovered."
        ),
        known_non_claims=(
            "No recovered benchmark identity exists.",
            "Realized future opponent and ball trajectories are conditional context, "
            "not ex-ante exposure.",
            "No target, exposure definition, scorer, horizon, or population is assigned.",
        ),
        r1_lifecycle=FamilyLifecycleStatus.RECONSTRUCTION_PENDING,
        current_lifecycle=(
            FamilyLifecycleStatus.NO_RECOVERABLE_HISTORICAL_BENCHMARK_RESEARCH_INTENT
        ),
        release_status=ReleaseStatus.UNRELEASED,
        unresolved_task_fields=(
            ("benchmark_identity", UNKNOWN),
            ("history_variables", UNKNOWN),
            ("input_modalities", UNKNOWN),
            ("target", UNKNOWN),
            ("ex_ante_exposure_definition", UNKNOWN),
            ("scorer", UNKNOWN),
            ("horizon", UNKNOWN),
            ("population", UNKNOWN),
        ),
    ),
    ResearchFamilyDefinition(
        family_id="conditional_multi_agent_motion_prediction",
        public_name="Conditional Multi-Agent Motion Prediction",
        technical_name="conditional_multi_agent_motion_prediction",
        research_question=(
            "Given observed scene history plus supplied realized future opponent-team and ball "
            "trajectories, can the target team's future response be predicted?"
        ),
        scientific_scope=(
            "Conditional target-team trajectory prediction from observed scene history "
            "and supplied "
            "realized future opponent-team and ball trajectories; owns the absolute-position and "
            "origin-relative displacement benchmarks."
        ),
        known_non_claims=(
            "Supplied realized future opponent and ball trajectories are conditional context, "
            "not information observed at the forecast origin.",
            "The displacement reconstruction remains partial; "
            "its scorer/result parity is unresolved.",
        ),
        r1_lifecycle=FamilyLifecycleStatus.RECOVERED_BENCHMARKS_AVAILABLE,
        current_lifecycle=FamilyLifecycleStatus.RECOVERED_BENCHMARKS_AVAILABLE,
        release_status=ReleaseStatus.UNRELEASED,
        unresolved_task_fields=(("displacement.scorer_result_parity", UNKNOWN),),
    ),
)
RESEARCH_FAMILY_IDS = tuple(definition.family_id for definition in RESEARCH_FAMILY_DEFINITIONS)


class BenchmarkRegistry:
    def __init__(self) -> None:
        self._families = {
            definition.family_id: definition for definition in RESEARCH_FAMILY_DEFINITIONS
        }
        self._research_objects: dict[str, ResearchObjectDefinition] = {}
        self._benchmarks: dict[str, BenchmarkDefinition] = {}
        self._aliases: dict[str, HistoricalAlias] = {}

    def register(self, research_object: ResearchObjectDefinition) -> None:
        identifier = research_object.identity.scientific_id
        if not _CANONICAL_ID.fullmatch(identifier):
            raise ValueError(f"not a canonical scientific research-object ID: {identifier}")
        if research_object.identity.family_id not in self._families:
            raise ValueError(f"unknown research family: {research_object.identity.family_id}")
        if identifier in self._families:
            raise ValueError(f"research-object ID conflicts with research family: {identifier}")
        if identifier in self._research_objects or identifier in self._aliases:
            raise ValueError(f"duplicate research-object identity: {identifier}")
        if research_object.descriptor.research_object_type is ResearchObjectType.BENCHMARK:
            if not isinstance(research_object, BenchmarkDefinition):
                raise TypeError("benchmark objects must use BenchmarkDefinition")
            self._benchmarks[identifier] = research_object
        self._research_objects[identifier] = research_object

    def register_alias(self, alias: HistoricalAlias) -> None:
        if alias.canonical_id not in self._research_objects:
            raise KeyError(f"alias target is not registered: {alias.canonical_id}")
        if not alias.value or not alias.evidence.uri or alias.value in self._aliases:
            raise ValueError("provenance alias must be unique and complete")
        if alias.value in self._research_objects:
            raise ValueError("a provenance alias cannot be a canonical research-object ID")
        if alias.value in self._families:
            raise ValueError("a provenance alias cannot be a research-family ID")
        self._aliases[alias.value] = alias

    def lookup(self, scientific_id: str) -> BenchmarkDefinition:
        if scientific_id in self._aliases:
            raise ValueError("historical identifiers are provenance aliases, not canonical IDs")
        try:
            return self._benchmarks[scientific_id]
        except KeyError as exc:
            if scientific_id in self._research_objects:
                raise KeyError(f"research object is not a benchmark: {scientific_id}") from exc
            raise KeyError(f"unknown canonical benchmark ID: {scientific_id}") from exc

    def lookup_research_object(self, scientific_id: str) -> ResearchObjectDefinition:
        if scientific_id in self._aliases:
            raise ValueError("historical identifiers are provenance aliases, not canonical IDs")
        try:
            return self._research_objects[scientific_id]
        except KeyError as exc:
            raise KeyError(f"unknown canonical research-object ID: {scientific_id}") from exc

    def discover(self, family_id: str | None = None) -> tuple[BenchmarkDefinition, ...]:
        values = self._benchmarks.values()
        if family_id is not None:
            values = (item for item in values if item.identity.family_id == family_id)
        return tuple(sorted(values, key=lambda item: item.identity.scientific_id))

    def research_objects(
        self, family_id: str | None = None
    ) -> tuple[ResearchObjectDefinition, ...]:
        values = self._research_objects.values()
        if family_id is not None:
            values = (item for item in values if item.identity.family_id == family_id)
        return tuple(sorted(values, key=lambda item: item.identity.scientific_id))

    def families(self) -> tuple[ResearchFamilyDefinition, ...]:
        return tuple(self._families.values())

    def family_ids(self) -> tuple[str, ...]:
        return tuple(self._families)

    def lookup_family(self, family_id: str) -> ResearchFamilyDefinition:
        try:
            return self._families[family_id]
        except KeyError as exc:
            raise KeyError(f"unknown research family: {family_id}") from exc

    def resolve_alias(self, value: str) -> HistoricalAlias:
        return self._aliases[value]

    def aliases(self) -> tuple[HistoricalAlias, ...]:
        return tuple(sorted(self._aliases.values(), key=lambda alias: alias.value))


def default_registry() -> BenchmarkRegistry:
    """Construct the canonical research-object registry and its benchmark subset."""
    from fpdbench.provenance.aliases import HISTORICAL_ALIASES

    from .conditional_multi_agent_motion_prediction.absolute_position_prediction import (
        BENCHMARK as absolute_position,
    )
    from .conditional_multi_agent_motion_prediction.origin_relative_displacement_prediction import (
        BENCHMARK as displacement,
    )
    from .multimodal_state_estimation import RESEARCH_OBJECT as sensor_state
    from .workload_performance_state import (
        SIGNED_TANGENTIAL_ACCELERATION_RESEARCH_OBJECT,
        WHOLE_SESSION_RESEARCH_OBJECT,
    )

    registry = BenchmarkRegistry()
    for research_object in (
        WHOLE_SESSION_RESEARCH_OBJECT,
        SIGNED_TANGENTIAL_ACCELERATION_RESEARCH_OBJECT,
        sensor_state,
        absolute_position,
        displacement,
    ):
        registry.register(research_object)
    for alias in HISTORICAL_ALIASES:
        registry.register_alias(alias)
    return registry
