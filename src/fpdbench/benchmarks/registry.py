"""Separate benchmark identities from queryable historical research objects."""

import re

from fpdbench.benchmarks.base import (
    BenchmarkDefinition,
    ResearchObjectDefinition,
    ResearchObjectType,
)
from fpdbench.provenance import HistoricalAlias

_CANONICAL_ID = re.compile(r"^[a-z][a-z0-9_]*(?:/[a-z][a-z0-9_]*)?$")
RESEARCH_FAMILY_IDS = (
    "conditional_multi_agent_motion_prediction",
    "future_response_forecasting",
    "multimodal_state_estimation",
    "workload_performance_state",
)


class BenchmarkRegistry:
    def __init__(self) -> None:
        self._research_objects: dict[str, ResearchObjectDefinition] = {}
        self._benchmarks: dict[str, BenchmarkDefinition] = {}
        self._aliases: dict[str, HistoricalAlias] = {}

    def register(self, research_object: ResearchObjectDefinition) -> None:
        identifier = research_object.identity.scientific_id
        if not _CANONICAL_ID.fullmatch(identifier):
            raise ValueError(f"not a canonical scientific research-object ID: {identifier}")
        if research_object.identity.family_id not in RESEARCH_FAMILY_IDS:
            raise ValueError(f"unknown research family: {research_object.identity.family_id}")
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

    def families(self) -> tuple[str, ...]:
        return RESEARCH_FAMILY_IDS

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
    from .future_response_forecasting import RESEARCH_OBJECT as future_response
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
        future_response,
        absolute_position,
        displacement,
    ):
        registry.register(research_object)
    for alias in HISTORICAL_ALIASES:
        registry.register_alias(alias)
    return registry
