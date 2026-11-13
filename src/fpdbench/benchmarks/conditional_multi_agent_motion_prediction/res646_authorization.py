# pyright: reportPrivateUsage=false
"""Verify separately signed owner approval; this module does not reserve execution."""

from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from fpdbench.data_sources import protected_skillcorner as protected
from fpdbench.data_sources.skillcorner import canonical_bytes

from . import res646_preflight as preflight
from .res645_source_stream import parse_json

SCHEMA_SHA256 = "5472f0c9ca87dcbffe0eb97b892126a3c6758dc520ae0a6d2a7aa1081c4037af"
ENVELOPE = "fpdbench.res646.owner-approval/1"
REAL = "RES646-REAL-v1"
SYNTHETIC = "RES646-SYNTHETIC-v1"
PRINCIPAL = "res646-owner"
NAMESPACE = "fpdbench-res646-owner-go-v1"
TRUST_FILE = "res646-owner-signers"


def _schema() -> dict[str, Any]:
    root = resources.files("fpdbench.benchmarks.conditional_multi_agent_motion_prediction")
    raw = root.joinpath("res635_owner_authorization_v1.schema.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != SCHEMA_SHA256:
        raise ValueError("authorization schema identity differs")
    return json.loads(raw)


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("authorization timestamp must be UTC")
    try:
        result = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise ValueError("invalid authorization timestamp") from None
    return result


def _verify(
    payload: bytes,
    signature: bytes,
    signers: bytes,
    namespace: str,
    expected_identities: dict[str, str],
    now: datetime,
) -> None:
    if len(payload) > 131072 or len(signature) > 16384 or len(signers) > 4096:
        raise ValueError("oversized authorization")
    raw = parse_json(payload)
    if not isinstance(raw, dict):
        raise ValueError("invalid authorization envelope")
    body = cast(dict[str, Any], raw)
    if set(body) != {
        "schema",
        "namespace",
        "authorization",
        "identities",
        "expires_at_utc",
        "key_fingerprint",
    }:
        raise ValueError("invalid authorization envelope")
    if canonical_bytes(body) != payload:
        raise ValueError("authorization must use canonical bytes")
    if body["schema"] != ENVELOPE or body["namespace"] != namespace:
        raise ValueError("authorization namespace differs")
    fields = signers.split()
    if len(fields) != 3 or fields[:2] != [PRINCIPAL.encode(), b"ssh-ed25519"]:
        raise ValueError("exactly one trusted Ed25519 owner key is required")
    fingerprints = protected._signer_fingerprints(signers, PRINCIPAL)
    if not isinstance(body["key_fingerprint"], str) or fingerprints != frozenset(
        [body["key_fingerprint"]]
    ):
        raise ValueError("owner key fingerprint differs")
    if body["identities"] != expected_identities:
        raise ValueError("execution identities differ")
    scope = preflight.proposed_scope(expected_identities)
    auth: Any = body["authorization"]
    try:
        validator: Any = Draft202012Validator(_schema(), format_checker=FormatChecker())
        validator.validate(auth)
    except ValidationError:
        raise ValueError("authorization violates frozen schema") from None
    if not isinstance(auth, dict):
        raise ValueError("authorization scope binding differs")
    auth = cast(dict[str, Any], auth)
    if any(
        auth.get(field) != value
        for field, value in {
            "new_scope_sha256": scope,
            "scorer_code_sha256": expected_identities["scorer_sha256"],
            "ledger_root_identity_sha256": expected_identities["ledger_sha256"],
            "independent_verifier_identity": expected_identities["verifier_sha256"],
            "independent_validation_report_sha256": expected_identities[
                "independent_report_sha256"
            ],
        }.items()
    ):
        raise ValueError("authorization scope binding differs")
    if now.tzinfo is None or not _utc(auth["authorized_at_utc"]) <= now < _utc(
        body["expires_at_utc"]
    ):
        raise ValueError("authorization is not currently valid")
    protected._verify_ssh_signature(payload, signature, signers, PRINCIPAL, NAMESPACE)


def verify_real(payload: bytes, signature: bytes, expected_identities: dict[str, str]) -> None:
    """Verify using only the root-owned protected trust location; missing trust fails closed."""
    try:
        with protected._trusted_directory() as directory:
            signers = protected._trusted_file(directory, TRUST_FILE, limit=4096)
        _verify(payload, signature, signers, REAL, expected_identities, datetime.now(UTC))
    except OSError:
        raise ValueError("owner trust bundle unavailable") from None


def verify_synthetic(
    payload: bytes, signature: bytes, expected_identities: dict[str, str], signers: bytes
) -> None:
    """Fixture-only verification; its namespace can never authenticate a real campaign."""
    _verify(payload, signature, signers, SYNTHETIC, expected_identities, datetime.now(UTC))


class CampaignPlan:
    """Metadata-only scope description. This object grants no input or execution permission."""

    def __init__(self, path: Path) -> None:
        from . import res635_post_failure_evaluation as s
        from . import res645_checkpoints as ck
        from . import res645_fixtures as fx
        from . import res645_paths as paths
        from . import res645_pipeline as pipeline

        self.path = path
        raw, _ = paths.read_regular_file(path, max_bytes=131072, require_private=True)
        self.raw = raw
        document = parse_json(raw)
        if not isinstance(document, dict):
            raise ValueError("campaign configuration must be an object")
        self.config = cast(dict[str, Any], document)
        common = {
            "schema",
            "namespace",
            "ledger_root",
            "output",
            "independent_report_sha256",
        }
        self.namespace: str = self.config["namespace"]
        if self.config.get("schema") != "fpdbench.res646.campaign/1":
            raise ValueError("invalid campaign configuration")
        if self.namespace == SYNTHETIC:
            if set(self.config) != common | {"fixture_bundle"}:
                raise ValueError("invalid synthetic campaign configuration")
            bundle = Path(self.config["fixture_bundle"])
            self.specs, self.manifest, self.checkpoints = fx.read_bundle(bundle)
            self.receipts = bundle / "receipts"
            declared, _ = paths.read_regular_file(bundle / "bundle.json", max_bytes=1 << 20)
            self.declared = [m["eligible_windows"] for m in json.loads(declared)["matches"]]
            self.inventory = None
        elif self.namespace == REAL:
            if set(self.config) != common | {
                "matches",
                "checkpoint_directory",
                "receipt_directory",
                "admission",
            }:
                raise ValueError("invalid real campaign configuration")
            from . import res645_source_stream as source
            from .res635_verification import EVALUATION_MATCHES

            matches = self.config["matches"]
            if [m["match_id"] for m in matches] != list(EVALUATION_MATCHES):
                raise ValueError("exact frozen match inventory required")
            if any(
                set(m)
                != {
                    "match_id",
                    "directory",
                    "locked_path",
                    "eligible_windows",
                    "sha256",
                }
                or set(m["sha256"])
                != {
                    "metadata_sha256",
                    "phases_sha256",
                    "tracking_raw_sha256",
                    "locked_sha256",
                }
                for m in matches
            ):
                raise ValueError("incomplete source inventory")
            self.specs = [
                source.SourceMatchSpec(
                    m["match_id"],
                    m["match_id"],
                    Path(m["directory"]),
                    locked_path=Path(m["locked_path"]),
                )
                for m in matches
            ]
            self.declared = [m["eligible_windows"] for m in matches]
            self.inventory = [m["sha256"] for m in matches]
            self.manifest = ck.frozen_manifest()
            self.checkpoints = Path(self.config["checkpoint_directory"])
            self.receipts = Path(self.config["receipt_directory"])
        else:
            raise PermissionError("unknown campaign namespace")
        if len(self.declared) != 4 or any(type(n) is not int or n < 1 for n in self.declared):
            raise ValueError("four positive declared window counts required")
        self.root, self.output = Path(self.config["ledger_root"]), Path(self.config["output"])
        if (
            self.root == self.output
            or self.root in self.output.parents
            or self.output in self.root.parents
        ):
            raise PermissionError("ledger and output trees must be separate")
        code = pipeline.provenance([], "")["code_sha256"]
        from .res645_workloads import _tree_identity

        self.identities = {
            "source_sha256": s.digest(
                {
                    "config": self.config,
                    "fixture_sha256": _tree_identity(Path(self.config["fixture_bundle"]))
                    if self.namespace == SYNTHETIC
                    else None,
                }
            ),
            "scorer_sha256": s.digest(code),
            "verifier_sha256": s.digest(
                {
                    k: code[k]
                    for k in (
                        "res645_independent.py",
                        "res635_verification.py",
                    )
                }
            ),
            "runtime_sha256": s.digest(pipeline.provenance([], "")["runtime"]),
            "ledger_sha256": self.directory_identity(self.root),
            "output_sha256": self.directory_identity(self.output),
            "independent_report_sha256": self.config["independent_report_sha256"],
        }
        self.scope = preflight.proposed_scope(self.identities)

    @staticmethod
    def directory_identity(path: Path) -> str:
        from . import res635_post_failure_evaluation as s
        from . import res645_paths as paths

        fd = paths.open_directory_fd(path, require_private=True)
        try:
            info = os.fstat(fd)
            return s.digest(
                {
                    "path": str(path),
                    "device": info.st_dev,
                    "inode": info.st_ino,
                    "uid": info.st_uid,
                    "mode": info.st_mode,
                }
            )
        finally:
            os.close(fd)


class Campaign(CampaignPlan):
    """Signed authority for the existing supervisor; production trust is provisioned out of band.

    The owner UID protects the stable ledger from output writers. Its directory identity is
    signed by the protected owner key; output hashes/HMACs alone establish no independent trust.
    """

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.verify()
        if self.namespace == REAL:
            from . import res645_pipeline as pipeline

            counts = preflight.verify_admission(Path(self.config["admission"]))
            if [counts[spec.match_id] for spec in self.specs] != self.declared:
                raise ValueError("declared counts differ from research admission")
            runtime = pipeline.provenance([], "")["runtime"]
            if (runtime["python"], runtime["numpy"], runtime["torch"]) != (
                "3.12.8",
                "2.2.4",
                "2.6.0+cpu",
            ):
                raise ValueError("real execution runtime differs from frozen runtime")

    def verify(self) -> None:
        from . import res635_post_failure_evaluation as s
        from . import res645_paths as paths
        from . import res645_pipeline as pipeline

        raw, _ = paths.read_regular_file(self.path, max_bytes=131072, require_private=True)
        if (
            raw != self.raw
            or self.directory_identity(self.root) != self.identities["ledger_sha256"]
            or (self.directory_identity(self.output) != self.identities["output_sha256"])
        ):
            raise ValueError("campaign configuration or directory identity changed")
        if s.digest(pipeline.provenance([], "")["code_sha256"]) != self.identities["scorer_sha256"]:
            raise ValueError("campaign code changed after authorization")
        payload, _ = paths.read_regular_file(
            self.path.with_suffix(".approval.json"),
            max_bytes=131072,
            require_private=True,
        )
        signature, _ = paths.read_regular_file(
            self.path.with_suffix(".approval.sig"),
            max_bytes=16384,
            require_private=True,
        )
        if self.namespace == REAL:
            verify_real(payload, signature, self.identities)
        else:
            signers, _ = paths.read_regular_file(
                self.path.with_suffix(".synthetic-signers"),
                max_bytes=4096,
                require_private=True,
            )
            verify_synthetic(payload, signature, self.identities, signers)

    def record(self) -> dict[str, Any]:
        from . import res635_execution as execution
        from . import res635_post_failure_evaluation as s
        from . import res645_paths as paths

        self.verify()
        raw, _ = paths.read_regular_file(
            execution.ledger_path(self.root, self.scope), max_bytes=2_000_000, require_private=True
        )
        record = cast(dict[str, Any], parse_json(raw))
        if record.get("record_sha256") != s.digest(
            {k: value for k, value in record.items() if k != "record_sha256"}
        ):
            raise ValueError("ledger record hash differs")
        approval, _ = paths.read_regular_file(
            self.path.with_suffix(".approval.json"), max_bytes=131072, require_private=True
        )
        if (
            record.get("authorization_sha256") != hashlib.sha256(approval).hexdigest()
            or record.get("namespace") != self.namespace
            or record.get("scope_sha256") != self.scope
        ):
            raise PermissionError("ledger is not bound to signed authorization")
        if record.get("output") != str(self.output):
            raise PermissionError("ledger output differs")
        budget = record.get("budget", {})
        if (
            record.get("count") != sum(self.declared)
            or set(budget) != set(execution.REAL_BUDGET)
            or any(
                type(budget[k]) not in (int, float)
                or not math.isfinite(budget[k])
                or not 0 < budget[k] <= ceiling
                for k, ceiling in execution.REAL_BUDGET.items()
            )
        ):
            raise ValueError("ledger count or budget exceeds signed authorization")
        return record

    def require_worker(self) -> None:
        from . import res635_execution as execution

        record = self.record()
        claim = execution.read(self.root / f"{self.scope}.worker-{record['attempt']}")
        if (
            record["status"] != "RUNNING"
            or claim
            != {
                "pid": os.getpid(),
                "parent": os.getppid(),
                "scope": self.scope,
            }
            or os.getppid() != record.get("supervisor_pid")
        ):
            raise PermissionError("only the reserved supervised worker may open scoring inputs")

    def allow_source(self, spec: object) -> None:
        self.require_worker()
        if self.namespace != REAL or spec not in self.specs:
            raise PermissionError("source is outside signed real campaign")

    def allow_models(self, manifest: object, directory: Path, receipts: Path) -> None:
        self.require_worker()
        if self.namespace != REAL or (manifest, directory, receipts) != (
            self.manifest,
            self.checkpoints,
            self.receipts,
        ):
            raise PermissionError("checkpoints are outside signed real campaign")

    def allow_input(self, path: Path) -> None:
        self.require_worker()
        if self.namespace != REAL:
            raise PermissionError("synthetic authority cannot open real inputs")
        allowed = {self.checkpoints, self.receipts}
        for record in cast(list[dict[str, Any]], self.manifest["checkpoints"]):
            allowed.add(self.checkpoints / f"{record['checkpoint_sha256']}.pt")
            allowed.add(self.receipts / f"{record['receipt_sha256']}.json")
        for spec in self.specs:
            allowed.update(
                spec.directory / name
                for name in (
                    "metadata.json",
                    "phases.json",
                    "tracking.jsonl",
                )
            )
            allowed.add(spec.locked_path or spec.directory / "locked.jsonl")
        if path not in allowed:
            raise PermissionError("input path is outside signed campaign inventory")


def require_campaign(value: object) -> Campaign:
    """Reject duck-typed/subclass authority before calling any caller-supplied method."""
    if type(value) is not Campaign:
        raise PermissionError("a verified RES646 Campaign authority is required")
    return value
