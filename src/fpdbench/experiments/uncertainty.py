"""Descriptive dispersion, inferential uncertainty, and seed sensitivity."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import ClassVar, Protocol

from fpdbench.experiments.provenance import stable_manifest_hash


class InferentialStatus(StrEnum):
    ESTIMABLE = "estimable"
    NOT_ESTIMABLE = "not_estimable"
    NOT_DECLARED = "not_declared"


def _finite(value: float | None, field: str) -> None:
    if value is not None and not math.isfinite(value):
        raise ValueError(f"{field} must be finite")


@dataclass(frozen=True, slots=True)
class DescriptiveDispersion:
    unit: str
    n_units: int
    sample_standard_deviation: float | None

    def __post_init__(self) -> None:
        if not self.unit or self.n_units < 1:
            raise ValueError("descriptive dispersion requires a unit and positive sample count")
        _finite(self.sample_standard_deviation, "descriptive sample standard deviation")
        if self.sample_standard_deviation is not None and self.sample_standard_deviation < 0:
            raise ValueError("descriptive sample standard deviation must be nonnegative")
        if self.n_units == 1 and self.sample_standard_deviation is not None:
            raise ValueError("sample standard deviation is unavailable for one unit")

    def identity_payload(self) -> dict[str, object]:
        return {
            "unit": self.unit,
            "n_units": self.n_units,
            "sample_standard_deviation": (
                None
                if self.sample_standard_deviation is None
                else float(self.sample_standard_deviation).hex()
            ),
        }


@dataclass(frozen=True, slots=True)
class InferentialUncertainty:
    method_id: str | None
    status: InferentialStatus
    standard_error: float | None = None
    confidence_interval: tuple[float, float] | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        _finite(self.standard_error, "inferential standard error")
        if self.standard_error is not None and self.standard_error < 0:
            raise ValueError("inferential standard error must be nonnegative")
        if self.confidence_interval is not None:
            low, high = self.confidence_interval
            if not math.isfinite(low) or not math.isfinite(high) or low > high:
                raise ValueError("confidence interval must contain finite ordered bounds")
            object.__setattr__(self, "confidence_interval", (float(low), float(high)))
        if self.status is InferentialStatus.ESTIMABLE:
            if not self.method_id or (
                self.standard_error is None and self.confidence_interval is None
            ):
                raise ValueError(
                    "estimable inference requires a method and SE or confidence interval"
                )
        elif self.standard_error is not None or self.confidence_interval is not None:
            raise ValueError("unavailable inference cannot carry SE or confidence interval values")
        elif not self.reason:
            raise ValueError("unavailable inference requires a reason")

    def identity_payload(self) -> dict[str, object]:
        return {
            "method_id": self.method_id,
            "status": self.status.value,
            "standard_error": (
                None if self.standard_error is None else float(self.standard_error).hex()
            ),
            "confidence_interval": (
                None
                if self.confidence_interval is None
                else [float(value).hex() for value in self.confidence_interval]
            ),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class AlgorithmicSensitivity:
    unit: str
    n_units: int
    unit_means: tuple[tuple[str, float], ...]
    mean: float
    sample_standard_deviation: float | None

    def __post_init__(self) -> None:
        if not self.unit or self.n_units < 1 or len(self.unit_means) != self.n_units:
            raise ValueError("algorithmic sensitivity requires one mean per unit")
        if len({key for key, _ in self.unit_means}) != self.n_units:
            raise ValueError("algorithmic sensitivity unit IDs must be unique")
        _finite(self.mean, "algorithmic sensitivity mean")
        _finite(self.sample_standard_deviation, "algorithmic sample standard deviation")
        if self.sample_standard_deviation is not None and self.sample_standard_deviation < 0:
            raise ValueError("algorithmic sample standard deviation must be nonnegative")
        if any(not key or not math.isfinite(value) for key, value in self.unit_means):
            raise ValueError("algorithmic unit means must have IDs and finite values")
        object.__setattr__(self, "unit_means", tuple(sorted(self.unit_means)))

    def identity_payload(self) -> dict[str, object]:
        return {
            "unit": self.unit,
            "n_units": self.n_units,
            "unit_means": [[key, float(value).hex()] for key, value in self.unit_means],
            "mean": float(self.mean).hex(),
            "sample_standard_deviation": (
                None
                if self.sample_standard_deviation is None
                else float(self.sample_standard_deviation).hex()
            ),
        }


@dataclass(frozen=True, slots=True)
class UncertaintyReport:
    point_estimate: float
    descriptive_dispersion: DescriptiveDispersion
    inferential_uncertainty: InferentialUncertainty
    algorithmic_sensitivity: AlgorithmicSensitivity | None = None

    SCHEMA_ID: ClassVar[str] = "fpdbench.uncertainty-report"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if not math.isfinite(self.point_estimate):
            raise ValueError("uncertainty point estimate must be finite")

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema_id": self.SCHEMA_ID,
            "schema_version": self.SCHEMA_VERSION,
            "point_estimate": float(self.point_estimate).hex(),
            "descriptive_dispersion": self.descriptive_dispersion.identity_payload(),
            "inferential_uncertainty": self.inferential_uncertainty.identity_payload(),
            "algorithmic_sensitivity": (
                None
                if self.algorithmic_sensitivity is None
                else self.algorithmic_sensitivity.identity_payload()
            ),
        }

    @property
    def manifest_hash(self) -> str:
        return stable_manifest_hash(self.identity_payload())


class _MatchSummary(Protocol):
    n_match: int
    point_estimate: float
    between_match_standard_deviation: float | None
    between_match_standard_error: float | None
    reason: str | None
    standard_error_method: object | None
    confidence_interval: tuple[float, float] | None


class _SeedSensitivitySummary(Protocol):
    n_seeds: int
    seed_level_means: tuple[tuple[int, float], ...]
    mean: float
    sample_standard_deviation: float | None


class _LomoSummary(Protocol):
    generalization: _MatchSummary
    seed_sensitivity: _SeedSensitivitySummary


def _value(value: object) -> str | None:
    if value is None:
        return None
    enum_value = getattr(value, "value", value)
    return str(enum_value)


def from_match_summary(summary: _MatchSummary, *, unit: str = "match") -> UncertaintyReport:
    """Adapt a match summary without importing protocols at runtime."""
    method_id = _value(summary.standard_error_method)
    inferential_status = (
        InferentialStatus.ESTIMABLE
        if summary.between_match_standard_error is not None
        or summary.confidence_interval is not None
        else InferentialStatus.NOT_ESTIMABLE
    )
    reason = None if inferential_status is InferentialStatus.ESTIMABLE else summary.reason
    if reason is None and inferential_status is InferentialStatus.NOT_ESTIMABLE:
        reason = "no inferential uncertainty was provided"
    return UncertaintyReport(
        point_estimate=summary.point_estimate,
        descriptive_dispersion=DescriptiveDispersion(
            unit,
            summary.n_match,
            summary.between_match_standard_deviation,
        ),
        inferential_uncertainty=InferentialUncertainty(
            method_id,
            inferential_status,
            summary.between_match_standard_error,
            summary.confidence_interval,
            reason,
        ),
    )


def from_lomo_summary(summary: _LomoSummary) -> UncertaintyReport:
    """Adapt LOMO dispersion and seed sensitivity as separate axes."""
    base = from_match_summary(summary.generalization, unit="held_out_match")
    seeds = summary.seed_sensitivity
    sensitivity = AlgorithmicSensitivity(
        unit="training_seed",
        n_units=seeds.n_seeds,
        unit_means=tuple((str(seed), value) for seed, value in seeds.seed_level_means),
        mean=seeds.mean,
        sample_standard_deviation=seeds.sample_standard_deviation,
    )
    return replace(base, algorithmic_sensitivity=sensitivity)


__all__ = [
    "AlgorithmicSensitivity",
    "DescriptiveDispersion",
    "InferentialStatus",
    "InferentialUncertainty",
    "UncertaintyReport",
    "from_lomo_summary",
    "from_match_summary",
]
