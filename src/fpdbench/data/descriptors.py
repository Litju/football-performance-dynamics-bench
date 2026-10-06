"""Immutable data, population, membership, split, and artifact descriptors."""

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from collections.abc import Iterable

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _require_sha256(value: str, field: str) -> None:
    if not _SHA256.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    uri: str
    sha256: str
    size_bytes: int | None = None

    def __post_init__(self) -> None:
        if not self.uri:
            raise ValueError("artifact URI must not be empty")
        _require_sha256(self.sha256, "artifact sha256")
        if self.size_bytes is not None and self.size_bytes < 0:
            raise ValueError("artifact size must be nonnegative")

    def verify(self, path: Path) -> bool:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest() == self.sha256


@dataclass(frozen=True, slots=True)
class DataStateDescriptor:
    state_id: str
    version: str
    transformation: str
    artifacts: tuple[ArtifactReference, ...] = ()
    manifest_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.state_id or not self.version or not self.transformation:
            raise ValueError("data state identity, version, and transformation are required")
        if self.manifest_sha256 is not None:
            _require_sha256(self.manifest_sha256, "manifest_sha256")


@dataclass(frozen=True, slots=True)
class PopulationSemantics:
    population_id: str
    definition: str

    def __post_init__(self) -> None:
        if not self.population_id or not self.definition:
            raise ValueError("population identity and definition are required")


@dataclass(frozen=True, slots=True)
class DatasetMembership:
    membership_id: str
    sample_count: int
    membership_sha256: str

    def __post_init__(self) -> None:
        if not self.membership_id or self.sample_count < 0:
            raise ValueError("dataset membership identity and nonnegative count are required")
        _require_sha256(self.membership_sha256, "membership_sha256")


@dataclass(frozen=True, slots=True)
class SplitProtocolDescriptor:
    protocol_id: str
    version: str
    assignment_sha256: str
    grouping: str
    access_policy: str

    def __post_init__(self) -> None:
        if not all((self.protocol_id, self.version, self.grouping, self.access_policy)):
            raise ValueError("split protocol fields must not be empty")
        _require_sha256(self.assignment_sha256, "assignment_sha256")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def membership_digest(sample_ids: Iterable[str]) -> str:
    """Hash ordered dataset membership without asserting a target population."""
    digest = hashlib.sha256()
    for sample_id in sample_ids:
        if not sample_id:
            raise ValueError("sample identifiers must not be empty")
        digest.update(sample_id.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()
