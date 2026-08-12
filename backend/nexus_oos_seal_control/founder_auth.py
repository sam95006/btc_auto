"""Founder authorization proof for V15-G OOS seal control."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.nexus_oos_seal_control.constants import FOUNDER_AUTH_SCOPE
from backend.nexus_oos_seal_control.intervals import sha_obj


@dataclass
class FounderAuthorizationGate:
    authorized: bool = False
    reason: str = "FOUNDER_AUTHORIZATION_MISSING"
    required_scope: str = FOUNDER_AUTH_SCOPE
    _binding_secret: str = field(default="v15_g_oos_seal_founder_gate_binding_v1", repr=False)

    def _binding_payload(self, body: dict[str, Any]) -> dict[str, Any]:
        return {
            "authorized": bool(body.get("authorized")),
            "reason": str(body.get("reason") or ""),
            "required_scope": str(body.get("required_scope") or self.required_scope),
            "binding_domain": self._binding_secret,
        }

    def bind_result(self, body: dict[str, Any]) -> str:
        return sha_obj(self._binding_payload(body))

    def evaluate(self) -> dict[str, Any]:
        """Default gate: Founder authorization absent; real reservation blocked."""
        body = {
            "authorized": False,
            "reason": self.reason,
            "required_scope": self.required_scope,
            "real_oos_reservation_permitted": False,
            "oos_reserved": False,
            "oos_downloaded": False,
            "oos_executed": False,
            "oos_consumed": False,
        }
        body["auth_proof"] = self.bind_result(body)
        return body

    def verify_bound_result(self, body: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(body, dict):
            return {
                "valid": False,
                "authorized": False,
                "reason": "FOUNDER_AUTH_PROOF_MISSING",
                "spoof_rejected": False,
            }
        claimed = dict(body)
        proof = claimed.get("auth_proof") or claimed.get("auth_binding")
        expected = self.bind_result(claimed)
        if proof != expected:
            return {
                "valid": False,
                "authorized": False,
                "reason": "FOUNDER_AUTH_PROOF_INVALID_OR_SPOOFED",
                "spoof_rejected": bool(claimed.get("authorized") is True),
                "expected_auth_proof": expected,
                "provided_auth_proof": proof,
            }
        # Even a valid binding never grants real OOS reservation in V15-G.
        return {
            "valid": True,
            "authorized": False,
            "reason": "FOUNDER_AUTH_VALID_BUT_REAL_RESERVATION_STILL_BANNED",
            "spoof_rejected": False,
            "real_oos_reservation_permitted": False,
            "oos_reserved": False,
        }

    def attempt_spoof_authorized(self) -> dict[str, Any]:
        """Adversarial: claim authorized=True without valid proof."""
        spoof = {
            "authorized": True,
            "reason": "SPOOFED",
            "required_scope": self.required_scope,
            "auth_proof": "deadbeef",
        }
        return self.verify_bound_result(spoof)
