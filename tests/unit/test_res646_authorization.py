"""Only artificial signing keys and invented scope bindings are used here."""

from __future__ import annotations

import copy
import subprocess
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import res646_authorization as a
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import res646_preflight as p
from fpdbench.data_sources import protected_skillcorner as protected
from fpdbench.data_sources.skillcorner import canonical_bytes


def build_auth() -> dict[str, Any]:
    def value(spec: dict[str, Any]) -> Any:
        if "const" in spec:
            return spec["const"]
        if spec.get("type") == "object":
            return {name: value(spec["properties"][name]) for name in spec["required"]}
        if spec.get("type") == "string":
            return "owner"
        if "$ref" in spec or "allOf" in spec:
            return "a" * 64
        raise AssertionError(spec)

    return value(a._schema())


@pytest.fixture
def signed(tmp_path: Path) -> tuple[dict[str, Any], bytes, dict[str, str], Path]:
    key = tmp_path / "synthetic-key"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
    signers = a.PRINCIPAL.encode() + b" " + key.with_suffix(".pub").read_bytes().split()[0] + b" "
    signers += key.with_suffix(".pub").read_bytes().split()[1] + b"\n"
    bindings = {
        f"{name}_sha256": "a" * 64
        for name in (
            "source",
            "scorer",
            "verifier",
            "runtime",
            "ledger",
            "output",
            "independent_report",
        )
    }
    bindings["output_sha256"] = "b" * 64
    auth = build_auth()
    auth.update(
        new_scope_sha256=p.proposed_scope(bindings),
        scorer_code_sha256=bindings["scorer_sha256"],
        ledger_root_identity_sha256=bindings["ledger_sha256"],
        independent_verifier_identity=bindings["verifier_sha256"],
        independent_validation_report_sha256=bindings["independent_report_sha256"],
        authorized_at_utc=(datetime.now(UTC) - timedelta(minutes=1))
        .isoformat()
        .replace("+00:00", "Z"),
    )
    body = {
        "schema": a.ENVELOPE,
        "namespace": a.SYNTHETIC,
        "authorization": auth,
        "identities": bindings,
        "expires_at_utc": (datetime.now(UTC) + timedelta(minutes=5))
        .isoformat()
        .replace("+00:00", "Z"),
        "key_fingerprint": next(iter(protected._signer_fingerprints(signers, a.PRINCIPAL))),
    }
    return body, signers, bindings, key


def sign(body: dict[str, Any], key: Path) -> bytes:
    return subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", str(key), "-n", a.NAMESPACE],
        input=canonical_bytes(body),
        capture_output=True,
        check=True,
    ).stdout


def test_signed_synthetic_and_forgery(
    signed: tuple[dict[str, Any], bytes, dict[str, str], Path],
) -> None:
    body, signers, bindings, key = signed
    payload, signature = canonical_bytes(body), sign(body, key)
    a.verify_synthetic(payload, signature, bindings, signers)
    with pytest.raises(ValueError, match="not authenticated"):
        a.verify_synthetic(payload, signature.replace(b"A", b"B"), bindings, signers)
    with pytest.raises(ValueError, match="identities"):
        a.verify_synthetic(payload, signature, {**bindings, "output_sha256": "c" * 64}, signers)
    altered = copy.deepcopy(body)
    altered["authorization"]["new_scope_sha256"] = p.CONSUMED_SCOPE
    with pytest.raises(ValueError, match="schema"):
        a.verify_synthetic(canonical_bytes(altered), sign(altered, key), bindings, signers)
    altered = copy.deepcopy(body)
    altered["expires_at_utc"] = "2020-01-01T00:00:00Z"
    with pytest.raises(ValueError, match="currently valid"):
        a.verify_synthetic(canonical_bytes(altered), sign(altered, key), bindings, signers)
    altered = copy.deepcopy(body)
    altered["namespace"] = a.REAL
    with pytest.raises(ValueError, match="namespace"):
        a.verify_synthetic(canonical_bytes(altered), sign(altered, key), bindings, signers)


def test_real_missing_trust_is_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def missing() -> Any:
        raise FileNotFoundError
        yield

    monkeypatch.setattr(protected, "_trusted_directory", missing)
    with pytest.raises(ValueError, match="trust bundle unavailable"):
        a.verify_real(b"{}", b"", {})


def test_wrong_owner_key_and_unsigned_payload_rejected(
    signed: tuple[dict[str, Any], bytes, dict[str, str], Path], tmp_path: Path
) -> None:
    body, signers, bindings, key = signed
    other = tmp_path / "untrusted-key"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(other)], check=True)
    payload = canonical_bytes(body)
    with pytest.raises(ValueError, match="not authenticated"):
        a.verify_synthetic(payload, sign(body, other), bindings, signers)
    with pytest.raises(ValueError, match="not authenticated"):
        a.verify_synthetic(payload, b"", bindings, signers)
    with pytest.raises(ValueError, match="canonical"):
        a.verify_synthetic(payload + b"\n", sign(body, key), bindings, signers)
