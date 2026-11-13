# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""Scientific workloads the durable supervisor can drive.

``SyntheticWorkload`` is the unchanged RES643 generator path. ``FixtureWorkload`` runs the
production-path adapter (source stream -> frozen features -> frozen checkpoints -> metrics) over an
invented bundle. Neither accepts a real source or checkpoint: the fixture bundle must carry the
invented-fixture markers and is refused otherwise.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from . import res635_post_failure_evaluation as s
from . import res635_verification as v
from . import res645_checkpoints as ck
from . import res645_fixtures as fx
from . import res645_independent as ind
from . import res645_paths as paths
from . import res645_pipeline as pipe
from . import res645_source_stream as src
from . import res646_authorization as authorization

type Document = dict[str, Any]
FIXTURE_NAMESPACE = "RES645-SYNTHETIC-FIXTURE-v1"


class Workload(Protocol):
    namespace: str
    cli: list[str]

    def validate_count(self, count: int) -> None: ...
    def scope_sha256(self, count: int) -> str: ...
    def prepare(self) -> Any: ...
    def score(self, i: int, count: int, prepared: Any, check: Callable[[], None]) -> Document: ...
    def verify_prefix(self, directory: Path, count: int, seals: list[str]) -> list[Document]: ...
    def aggregate(self, receipts: list[Document]) -> Document: ...


class SyntheticWorkload:
    namespace = "RES643-SYNTHETIC-ONLY-v1"
    cli: list[str] = []

    def validate_count(self, count: int) -> None:
        if type(count) is not int or not 1 <= count <= 64:
            raise ValueError("synthetic inference count must be 1..64")

    def scope_sha256(self, count: int) -> str:
        return v.receipts_scope(count)

    def prepare(self) -> Any:
        return s.models()

    def score(self, i: int, count: int, prepared: Any, check: Callable[[], None]) -> Document:
        return s.score_match(s.MATCHES[i], count, prepared, check)

    def verify_prefix(self, directory: Path, count: int, seals: list[str]) -> list[Document]:
        return v.verify_prefix(directory, count, seals)

    def aggregate(self, receipts: list[Document]) -> Document:
        return v.aggregate(receipts)


def _tree_identity(root: Path) -> str:
    """Digest of every bundle file's relative name and bytes (owner-private fixture trees)."""
    h = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise PermissionError("fixture tree contains a symlink")
        if path.is_dir():
            continue
        h.update(str(path.relative_to(root)).encode() + b"\0")
        with os.fdopen(paths.open_regular_fd(path), "rb") as stream:
            before = os.fstat(stream.fileno())
            paths.check_regular(before, max_bytes=src.MAX_TRACKING_BYTES, require_private=False)
            for block in iter(lambda: stream.read(1 << 20), b""):
                h.update(block)
            if paths.stat_key(before) != paths.stat_key(os.fstat(stream.fileno())):
                raise ValueError("fixture tree changed while hashing")
        h.update(b"\0")
    return h.hexdigest()


class FixtureWorkload:
    namespace = FIXTURE_NAMESPACE

    def __init__(self, bundle: Path) -> None:
        paths.reject_unsafe_path(bundle)
        self.bundle = bundle
        self.cli = ["--fixture-bundle", str(bundle)]
        self.specs, self.manifest, self.checkpoints = fx.read_bundle(bundle)
        self.receipts = bundle / "receipts"
        raw, _ = paths.read_regular_file(bundle / "bundle.json", max_bytes=1 << 20)
        self.declared = [m["eligible_windows"] for m in json.loads(raw)["matches"]]
        if len(self.declared) != 4 or any(type(n) is not int or n < 1 for n in self.declared):
            raise ValueError("fixture bundle must declare window counts for four matches")
        # The campaign "count" is the total declared eligible windows across the four matches.
        self.windows = sum(self.declared)

    def validate_count(self, count: int) -> None:
        if count != self.windows:
            raise ValueError("count must equal the bundle's declared eligible window total")

    def scope_sha256(self, count: int) -> str:
        self.validate_count(count)
        return s.digest(
            {
                "namespace": self.namespace,
                "declared_windows": self.declared,
                "bundle_tree_sha256": _tree_identity(self.bundle),
                "protocol_sha256": s.PROTOCOL_SHA256,
                "code_sha256": pipe.provenance([], "")["code_sha256"],
            }
        )

    def prepare(self) -> ck.FrozenModelSet:
        return ck.load_models(self.manifest, self.checkpoints, "synthetic", self.receipts)

    def score(
        self, i: int, count: int, prepared: ck.FrozenModelSet, check: Callable[[], None]
    ) -> Document:
        match = src.SourceMatch(self.specs[i], "synthetic")
        match.prepare(check)
        body = pipe.score_stream(
            self.specs[i].label,
            self.specs[i].match_id,
            match.windows(check),
            prepared,
            self.declared[i],
            check,
        )
        return {**body, "source": match.source_document()}

    def verify_prefix(self, directory: Path, count: int, seals: list[str]) -> list[Document]:
        if not 0 <= len(seals) <= 4:
            raise ValueError("invalid receipt prefix")
        if any(directory.glob("*.tmp")) or any(directory.glob(".*.tmp")):
            raise ValueError("partial receipt write present")
        names = sorted(p.name for p in directory.glob("match-*.json"))
        if names != [f"match-{i}.json" for i in range(len(seals))]:
            raise ValueError("partial, extra, duplicated or missing receipt")
        scope, previous, receipts = self.scope_sha256(count), "0" * 64, []
        for i, seal in enumerate(seals):
            path = directory / f"match-{i}.json"
            if path.is_symlink() or path.stat().st_size > 2_000_000:
                raise ValueError("invalid receipt file")
            receipt = json.loads(path.read_bytes())
            if s.digest(receipt) != seal or receipt["previous_sha256"] != previous:
                raise ValueError("altered or forged receipt chain")
            if receipt["match"] != s.MATCHES[i] or receipt["scope_sha256"] != scope:
                raise ValueError("wrong match or synthetic scope")
            self.check_receipt(i, count, receipt)
            previous = seal
            receipts.append(receipt)
        return receipts

    def check_receipt(self, i: int, count: int, receipt: Document) -> None:
        """Independent raw eligibility, features and metric arithmetic from raw files."""
        spec = self.specs[i]
        expected = ind.match_body(
            self.bundle / spec.directory.name,
            spec.label,
            self.manifest,
            self.checkpoints,
            self.receipts,
        )
        identity = receipt["identity"]
        for key, value in expected["identity"].items():
            if identity[key] != value:
                raise ValueError(f"independent identity differs: {key}")
        if identity["windows"] != self.declared[i]:
            raise ValueError("window count differs from the declared scope")
        from . import res635_verification as verification

        verification.assert_equivalent(receipt["records"], expected["records"])
        if receipt["provenance"]["checkpoint_bindings"] != expected["bindings"]:
            raise ValueError("checkpoint binding differs from independent readback")
        if any(receipt["source"][k] != v_ for k, v_ in expected["raw_sha256"].items()):
            raise ValueError("source identity differs from independent readback")
        if receipt["provenance"] != pipe.provenance(
            ck.load_models(self.manifest, self.checkpoints, "synthetic", self.receipts).bindings,
            ck.validate_manifest(self.manifest, "synthetic"),
        ):
            raise ValueError("provenance differs")

    def aggregate(self, receipts: list[Document]) -> Document:
        return v.aggregate(receipts)


class RealWorkload:
    """The existing streaming scorer, with signed scope and independently audited predictions.

    A synthetic Campaign uses invented source identities and fake weights but the identical
    authorization, reservation, worker, receipt, continuation and verification code paths.
    """

    def __init__(self, config: Path) -> None:
        self.campaign = authorization.Campaign(config)
        self.namespace = self.campaign.namespace
        self.cli = ["--campaign-config", str(config)]
        self.windows = sum(self.campaign.declared)

    def validate_count(self, count: int) -> None:
        if type(count) is not int or count != self.windows:
            raise ValueError("count must equal signed campaign window inventory")

    def scope_sha256(self, count: int) -> str:
        self.validate_count(count)
        self.campaign.verify()
        return self.campaign.scope

    def prepare(self) -> ck.FrozenModelSet:
        campaign = self.campaign
        campaign.require_worker()
        return ck.load_models(
            campaign.manifest,
            campaign.checkpoints,
            "frozen" if self.namespace == authorization.REAL else "synthetic",
            campaign.receipts,
            campaign=campaign,
        )

    def score(
        self, i: int, count: int, prepared: ck.FrozenModelSet, check: Callable[[], None]
    ) -> Document:
        self.validate_count(count)
        campaign = self.campaign
        campaign.require_worker()
        spec = campaign.specs[i]
        match = src.SourceMatch(
            spec,
            "frozen" if self.namespace == authorization.REAL else "synthetic",
            campaign,
        )
        match.prepare(check)
        body = pipe.score_stream(
            spec.label,
            spec.match_id,
            match.windows(check),
            prepared,
            campaign.declared[i],
            check,
            source_audit=ind.SourcePredictionAudit(
                spec.directory,
                spec.label,
                spec.locked_path,
                campaign if self.namespace == authorization.REAL else None,
            ),
        )
        source = match.source_document()
        if campaign.inventory is not None and any(
            source[k] != value for k, value in campaign.inventory[i].items()
        ):
            raise ValueError("source bytes differ from signed inventory")
        body["provenance"] = pipe.provenance(
            prepared.bindings,
            prepared.manifest_sha256,
            real=self.namespace == authorization.REAL,
        )
        # Real-format receipts always bind the four frozen study cells; synthetic source IDs
        # remain explicit in provenance and never acquire permission to open real data.
        return {**body, "match": v.EVALUATION_MATCHES[i], "source": source}

    def verify_prefix(self, directory: Path, count: int, seals: list[str]) -> list[Document]:
        self.validate_count(count)
        campaign = self.campaign
        ledger = campaign.record()
        if directory != campaign.output or seals != ledger["seals"]:
            raise PermissionError("receipt seals must come from the signed campaign ledger")
        if (
            not 0 <= len(seals) <= 4
            or sorted(p.name for p in directory.glob("match-*.json"))
            != [f"match-{i}.json" for i in range(len(seals))]
            or list(directory.glob(".*.tmp"))
        ):
            raise ValueError("incomplete or partial receipt prefix")
        receipts: list[Document] = []
        previous = "0" * 64
        expected_records = ck.validate_records(campaign.manifest)
        for i, seal in enumerate(seals):
            raw, _ = paths.read_regular_file(
                directory / f"match-{i}.json",
                max_bytes=2_000_000,
                require_private=True,
            )
            receipt = json.loads(raw)
            if (
                s.digest(receipt) != seal
                or receipt["previous_sha256"] != previous
                or (receipt["scope_sha256"], receipt["match"])
                != (campaign.scope, v.EVALUATION_MATCHES[i])
            ):
                raise ValueError("receipt seal, scope or match differs")
            audit = receipt["independent_audit"]
            v.assert_equivalent(receipt["records"], audit["records"])
            if receipt["independent_records_sha256"] != s.digest(audit["records"]):
                raise ValueError("independent metric audit identity differs")
            if any(receipt["identity"][k] != value for k, value in audit["identity"].items()):
                raise ValueError("independent denominator or source identity differs")
            if receipt["identity"]["windows"] != campaign.declared[i]:
                raise ValueError("receipt window count differs from signed inventory")
            bindings = receipt["provenance"]["checkpoint_bindings"]
            if [b["cell"] for b in bindings] != [list(c) for c in s.CELLS]:
                raise ValueError("checkpoint binding inventory differs")
            for binding, cell in zip(bindings, s.CELLS, strict=True):
                record = expected_records[cell]
                if any(
                    binding[k] != record[k]
                    for k in (
                        "checkpoint_sha256",
                        "configuration_sha256",
                        "selected_step",
                    )
                ):
                    raise ValueError("checkpoint provenance differs from signed manifest")
            expected = pipe.provenance(
                [],
                ck.validate_manifest(
                    campaign.manifest,
                    "frozen" if self.namespace == authorization.REAL else "synthetic",
                ),
                real=self.namespace == authorization.REAL,
            )
            expected["checkpoint_bindings"] = bindings
            if receipt["provenance"] != expected:
                raise ValueError("scorer, verifier or runtime provenance differs")
            if campaign.inventory is not None and any(
                receipt["source"][k] != value for k, value in campaign.inventory[i].items()
            ):
                raise ValueError("source provenance differs from signed inventory")
            previous = seal
            receipts.append(receipt)
        return receipts

    def aggregate(self, receipts: list[Document]) -> Document:
        return v.aggregate(receipts, matches=v.EVALUATION_MATCHES)


def make(bundle: Path | None, config: Path | None = None) -> Workload:
    if config is not None:
        if bundle is not None:
            raise ValueError("campaign and fixture modes are mutually exclusive")
        return RealWorkload(config)
    return SyntheticWorkload() if bundle is None else FixtureWorkload(bundle)
