"""Consent-aware product analytics tracker (scaffolding)."""
from __future__ import annotations

from typing import Any, Mapping

from backend.nexus_public_product_analytics.consent_gate import ConsentLedger
from backend.nexus_public_product_analytics.constants import (
    CONSENT_PURPOSE,
    EVENT_CATALOG,
    FABRICATED_VALUE_MARKERS,
)
from backend.nexus_public_product_analytics.hard_bans import HardBanViolation, refuse_fabrication
from backend.nexus_public_product_analytics.privacy import (
    PrivacyViolation,
    hash_subject_id,
    scrub_props,
)
from backend.nexus_public_product_analytics.store import AnalyticsEvent, LocalAnalyticsStore


class ProductAnalyticsTracker:
    """Privacy-aware tracker. Drops events without consent; never fabricates."""

    def __init__(
        self,
        *,
        store: LocalAnalyticsStore | None = None,
        consent: ConsentLedger | None = None,
        subject_salt: str = "nexus-pub2-i-local-salt",
    ) -> None:
        self.store = store or LocalAnalyticsStore()
        self.consent = consent or ConsentLedger()
        self.subject_salt = subject_salt
        self.dropped_without_consent = 0
        self.recorded = 0

    def track(
        self,
        event_name: str,
        *,
        raw_subject_id: str,
        props: Mapping[str, Any] | None = None,
    ) -> AnalyticsEvent | None:
        if event_name not in EVENT_CATALOG:
            raise HardBanViolation(f"unknown analytics event: {event_name}")

        # Fabrication markers in subject or props are hard-refused.
        if any(tok in (raw_subject_id or "").lower() for tok in FABRICATED_VALUE_MARKERS):
            refuse_fabrication(f"subject marker in {event_name}")
        for key, value in (props or {}).items():
            blob = f"{key}={value}".lower()
            if any(tok in blob for tok in FABRICATED_VALUE_MARKERS):
                refuse_fabrication(f"prop marker in {event_name}:{key}")

        meta = EVENT_CATALOG[event_name]
        allowed = set(meta["allowed_props"])  # type: ignore[arg-type]
        try:
            cleaned = scrub_props(props)
        except PrivacyViolation as exc:
            raise HardBanViolation(str(exc)) from exc
        unknown = set(cleaned) - allowed
        if unknown:
            raise HardBanViolation(f"disallowed props for {event_name}: {sorted(unknown)}")

        subject_hash = hash_subject_id(raw_subject_id, salt=self.subject_salt)

        if not self.consent.granted(raw_subject_id, CONSENT_PURPOSE):
            # Soft-drop: privacy-first; do not raise on every UI tick.
            self.dropped_without_consent += 1
            return None

        ev = self.store.append(
            event_name=event_name,
            subject_hash=subject_hash,
            props=cleaned,
        )
        self.recorded += 1
        return ev

    def grant_consent(self, raw_subject_id: str) -> None:
        self.consent.set(raw_subject_id, CONSENT_PURPOSE, granted=True)

    def deny_consent(self, raw_subject_id: str) -> None:
        self.consent.set(raw_subject_id, CONSENT_PURPOSE, granted=False)
