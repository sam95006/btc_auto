"""NEXUS Founder-private Observability SLO V11.1 (READ-ONLY).

Covers Decision/Session lifecycle, risk gates, execution simulator,
Provider health, Reflection queue, Lesson gate, ledger/snapshot/checkpoint/
Microstructure health, storage budget, kill-switch readiness, and
qualification block state.

Hard bans: no public routes, no account secrets, no execution mutation endpoint.
"""
from __future__ import annotations

from backend.nexus_observability.aggregator import (
    apply_pass2_adversarial_overrides,
    build_private_observability_slo,
    hard_bans_document,
)
from backend.nexus_observability.alerts import collect_alerts
from backend.nexus_observability.constants import (
    ALERT_CLASSES,
    HARD_BANS,
    OBSERVABILITY_DOMAINS,
    OWNED_PATHS,
)
from backend.nexus_observability.slo import definitions_document, evaluate_slos, slo_catalog

__all__ = [
    "ALERT_CLASSES",
    "HARD_BANS",
    "OBSERVABILITY_DOMAINS",
    "OWNED_PATHS",
    "apply_pass2_adversarial_overrides",
    "build_private_observability_slo",
    "collect_alerts",
    "definitions_document",
    "evaluate_slos",
    "hard_bans_document",
    "slo_catalog",
]
