"""Runs, results, and governance release records stay independent of locks."""

from dataclasses import dataclass

from fpdbench.models import ModelCheckpoint

type MetricValues = tuple[tuple[str, float], ...]


@dataclass(frozen=True, slots=True)
class ExperimentRun:
    run_id: str
    benchmark_id: str
    scientific_lock_hash: str
    model: ModelCheckpoint
    split_protocol_id: str
    configuration_sha256: str


@dataclass(frozen=True, slots=True)
class ResultRecord:
    run_id: str
    scientific_lock_hash: str
    model_checkpoint_sha256: str
    metrics: MetricValues
    output_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class PublicReleaseManifest:
    """Governance and hosting metadata; this object is never input to a scientific lock."""

    scientific_lock_hash: str
    legal_status: str
    license_status: str
    publication_status: str
    public_release_authority: str | None = None
    artifact_availability: str | None = None
    license_clearance_snapshot: str | None = None
    artifact_uris: tuple[str, ...] = ()
    hosting_provider: str | None = None
    release_timestamp: str | None = None
