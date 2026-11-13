# pyright: reportPrivateUsage=false
"""Verify separately signed owner approval; this module does not reserve execution."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from importlib import resources
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
