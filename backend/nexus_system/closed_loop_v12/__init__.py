"""V12-A Founder-private closed-loop proof (simulated only).

Canonical path:
  Candidate → Decision → Risk → Simulated Intent → Simulated Order → Fill
  → Position → Exit → Reflection → Lesson Gate → Closure

Hard bans: no exchange write, no Demo/Shadow/mainnet/real money, no formal
WF/OOS, no profitability claims, no auto-integrate into PR27.
"""
from __future__ import annotations

from backend.nexus_system.closed_loop_v12.campaign import (
    CANONICAL_PATH,
    FROZEN_SEED,
    HARD_BANS,
    PASS_STATUS,
    REQUIRED_ONTOLOGY,
    SCHEMA,
    TARGET_CANDIDATES,
    TARGET_COMPLETED_LIFECYCLES,
    build_historical_candidates,
    campaign_digest,
    run_v12_closed_loop_campaign,
)

__all__ = [
    "CANONICAL_PATH",
    "FROZEN_SEED",
    "HARD_BANS",
    "PASS_STATUS",
    "REQUIRED_ONTOLOGY",
    "SCHEMA",
    "TARGET_CANDIDATES",
    "TARGET_COMPLETED_LIFECYCLES",
    "build_historical_candidates",
    "campaign_digest",
    "run_v12_closed_loop_campaign",
]
