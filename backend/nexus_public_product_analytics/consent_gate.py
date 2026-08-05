"""Consent gate for product analytics (default denied)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from backend.nexus_public_product_analytics.constants import CONSENT_PURPOSE
from backend.nexus_public_product_analytics.hard_bans import HardBanViolation


@dataclass
class ConsentLedger:
    """Local consent ledger — not a production customer database."""

    _grants: Dict[str, Dict[str, bool]] = field(default_factory=dict)

    def set(self, subject_id: str, purpose: str, *, granted: bool) -> None:
        if purpose != CONSENT_PURPOSE and purpose not in {
            "terms_of_service",
            "privacy_policy",
            "research_participation",
        }:
            raise HardBanViolation(f"unknown consent purpose: {purpose}")
        bucket = self._grants.setdefault(subject_id, {})
        bucket[purpose] = bool(granted)

    def granted(self, subject_id: str, purpose: str = CONSENT_PURPOSE) -> bool:
        return bool(self._grants.get(subject_id, {}).get(purpose, False))

    def require(self, subject_id: str, purpose: str = CONSENT_PURPOSE) -> None:
        if not self.granted(subject_id, purpose):
            raise HardBanViolation(f"HARD BAN: tracking without consent ({purpose})")
