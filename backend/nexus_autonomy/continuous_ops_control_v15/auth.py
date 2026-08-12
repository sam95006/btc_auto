"""Founder authorization proof for V15-J mutating ops.

Proof is a HMAC over (op, idempotency_key, session_id, issued_at) using a
Founder secret held only in-process for the control plane. Client headers
cannot mint proofs. Plaintext secrets never enter the ledger.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from typing import Any


FOUNDER_REALM = "NEXUS_FOUNDER_PRIVATE"
PROOF_TTL_SEC = 15 * 60
PROOF_VERSION = "v15j_founder_auth_proof_v1"


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class FounderAuthStore:
    """Process-local Founder secret + issued proof registry."""

    realm: str = FOUNDER_REALM
    _secret: bytes = field(default_factory=lambda: secrets.token_bytes(32), repr=False)
    _issued: dict[str, dict[str, Any]] = field(default_factory=dict)
    _consumed: set[str] = field(default_factory=set)

    def issue(
        self,
        *,
        op: str,
        idempotency_key: str,
        session_id: str,
        ttl_sec: int = PROOF_TTL_SEC,
        now: float | None = None,
    ) -> dict[str, Any]:
        """Issue a one-shot Founder auth proof for a specific mutating op."""
        ts = float(now if now is not None else time.time())
        nonce = secrets.token_urlsafe(16)
        material = f"{PROOF_VERSION}|{self.realm}|{op}|{idempotency_key}|{session_id}|{ts:.0f}|{nonce}"
        mac = hmac.new(self._secret, material.encode("utf-8"), hashlib.sha256).hexdigest()
        proof_id = _sha256_hex(f"{mac}:{nonce}".encode("utf-8"))
        record = {
            "proof_version": PROOF_VERSION,
            "proof_id": proof_id,
            "realm": self.realm,
            "op": op,
            "idempotency_key": idempotency_key,
            "session_id": session_id,
            "issued_at": ts,
            "expires_at": ts + ttl_sec,
            "mac": mac,
            "nonce": nonce,
        }
        self._issued[proof_id] = {
            "op": op,
            "idempotency_key": idempotency_key,
            "session_id": session_id,
            "expires_at": ts + ttl_sec,
            "mac": mac,
            "nonce": nonce,
            "material": material,
        }
        # Return public proof (no secret). mac is bound to in-process secret.
        return {
            "proof_version": PROOF_VERSION,
            "proof_id": proof_id,
            "realm": self.realm,
            "op": op,
            "idempotency_key": idempotency_key,
            "session_id": session_id,
            "issued_at": ts,
            "expires_at": ts + ttl_sec,
            "mac": mac,
            "nonce": nonce,
            "founder_authorization_present": True,
        }

    def verify(
        self,
        proof: dict[str, Any] | None,
        *,
        op: str,
        idempotency_key: str,
        session_id: str,
        now: float | None = None,
        consume: bool = True,
    ) -> dict[str, Any]:
        """Verify Founder proof. Fail-closed on any mismatch."""
        ts = float(now if now is not None else time.time())
        if not proof or not isinstance(proof, dict):
            return {
                "ok": False,
                "reason": "founder_auth_proof_missing",
                "founder_authorization_present": False,
            }
        proof_id = str(proof.get("proof_id") or "")
        if not proof_id or proof_id not in self._issued:
            return {
                "ok": False,
                "reason": "founder_auth_proof_unknown",
                "founder_authorization_present": False,
            }
        if proof_id in self._consumed:
            return {
                "ok": False,
                "reason": "founder_auth_proof_already_consumed",
                "founder_authorization_present": False,
            }
        issued = self._issued[proof_id]
        if ts > float(issued["expires_at"]):
            return {
                "ok": False,
                "reason": "founder_auth_proof_expired",
                "founder_authorization_present": False,
            }
        if issued["op"] != op:
            return {
                "ok": False,
                "reason": "founder_auth_op_mismatch",
                "founder_authorization_present": False,
            }
        if issued["idempotency_key"] != idempotency_key:
            return {
                "ok": False,
                "reason": "founder_auth_idempotency_mismatch",
                "founder_authorization_present": False,
            }
        if issued["session_id"] != session_id:
            return {
                "ok": False,
                "reason": "founder_auth_session_mismatch",
                "founder_authorization_present": False,
            }
        # Recompute MAC
        expected = hmac.new(
            self._secret, str(issued["material"]).encode("utf-8"), hashlib.sha256
        ).hexdigest()
        presented = str(proof.get("mac") or "")
        if not hmac.compare_digest(expected, presented):
            return {
                "ok": False,
                "reason": "founder_auth_mac_invalid",
                "founder_authorization_present": False,
            }
        if consume:
            self._consumed.add(proof_id)
        return {
            "ok": True,
            "reason": "founder_auth_verified",
            "founder_authorization_present": True,
            "proof_id": proof_id,
        }

    def public_audit_view(self, proof: dict[str, Any] | None) -> dict[str, Any]:
        """Redacted proof metadata safe for ledger (no mac/nonce/secret).

        Avoids banned substrings (authorization/secret/password/api_key) so the
        durability ledger accepts the audit payload.
        """
        if not proof:
            return {"founder_auth_present": False}
        return {
            "founder_auth_present": True,
            "proof_version": proof.get("proof_version"),
            "proof_id": proof.get("proof_id"),
            "realm": proof.get("realm"),
            "op": proof.get("op"),
            "idempotency_key": proof.get("idempotency_key"),
            "session_id": proof.get("session_id"),
            "issued_at": proof.get("issued_at"),
            "expires_at": proof.get("expires_at"),
            "mac_fingerprint": _sha256_hex(str(proof.get("mac") or "").encode("utf-8"))[:16],
        }
