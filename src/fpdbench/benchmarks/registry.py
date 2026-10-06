"""Canonical benchmark discovery with provenance aliases kept in a separate table."""

import re

from fpdbench.benchmarks.base import BenchmarkDefinition
from fpdbench.provenance import HistoricalAlias

_CANONICAL_ID = re.compile(r"^[a-z][a-z0-9_]*(?:/[a-z][a-z0-9_]*)?$")


class BenchmarkRegistry:
    def __init__(self) -> None:
        self._benchmarks: dict[str, BenchmarkDefinition] = {}
        self._aliases: dict[str, HistoricalAlias] = {}

    def register(self, benchmark: BenchmarkDefinition) -> None:
        identifier = benchmark.identity.scientific_id
        if not _CANONICAL_ID.fullmatch(identifier):
            raise ValueError(f"not a canonical scientific benchmark ID: {identifier}")
        if identifier in self._benchmarks or identifier in self._aliases:
            raise ValueError(f"duplicate benchmark identity: {identifier}")
        self._benchmarks[identifier] = benchmark

    def register_alias(self, alias: HistoricalAlias) -> None:
        if alias.canonical_id not in self._benchmarks:
            raise KeyError(f"alias target is not registered: {alias.canonical_id}")
        if not alias.value or not alias.evidence.uri or alias.value in self._aliases:
            raise ValueError("provenance alias must be unique and complete")
        if alias.value in self._benchmarks:
            raise ValueError("a provenance alias cannot be a canonical benchmark ID")
        self._aliases[alias.value] = alias

    def lookup(self, scientific_id: str) -> BenchmarkDefinition:
        if scientific_id in self._aliases:
            raise ValueError("historical identifiers are provenance aliases, not canonical IDs")
        try:
            return self._benchmarks[scientific_id]
        except KeyError as exc:
            raise KeyError(f"unknown canonical benchmark ID: {scientific_id}") from exc

    def discover(self, family_id: str | None = None) -> tuple[BenchmarkDefinition, ...]:
        values = self._benchmarks.values()
        if family_id is not None:
            values = (item for item in values if item.identity.family_id == family_id)
        return tuple(sorted(values, key=lambda item: item.identity.scientific_id))

    def families(self) -> tuple[str, ...]:
        return tuple(sorted({item.identity.family_id for item in self._benchmarks.values()}))

    def resolve_alias(self, value: str) -> HistoricalAlias:
        return self._aliases[value]

    def aliases(self) -> tuple[HistoricalAlias, ...]:
        return tuple(sorted(self._aliases.values(), key=lambda alias: alias.value))


def default_registry() -> BenchmarkRegistry:
    """Construct the canonical scientific registry from executable definitions."""
    from fpdbench.provenance.aliases import HISTORICAL_ALIASES

    from .conditional_multi_agent_motion_prediction.absolute_position_prediction import (
        BENCHMARK as absolute_position,
    )
    from .conditional_multi_agent_motion_prediction.origin_relative_displacement_prediction import (
        BENCHMARK as displacement,
    )
    from .future_response_forecasting import BENCHMARK as future_response
    from .multimodal_state_estimation import BENCHMARK as sensor_state
    from .workload_performance_state import (
        SIGNED_TANGENTIAL_ACCELERATION_BENCHMARK,
        WHOLE_SESSION_BENCHMARK,
    )

    registry = BenchmarkRegistry()
    for definition in (
        WHOLE_SESSION_BENCHMARK,
        SIGNED_TANGENTIAL_ACCELERATION_BENCHMARK,
        sensor_state,
        future_response,
        absolute_position,
        displacement,
    ):
        registry.register(definition)
    for alias in HISTORICAL_ALIASES:
        registry.register_alias(alias)
    return registry
