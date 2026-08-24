"""DEMO_AUTONOMOUS_6H_V2_BOUNDED_VALIDATION policy constants (readiness only).

Live Validation runtime remains frozen; these constants are for dry-run / CI / Draft PR.
Do not lower MIN_NET_REWARD_RISK_RATIO or enable exchange write from this module.

Deployment identity is env-resolved only — never a hardcoded historical commit.
"""
from __future__ import annotations

import os

SESSION_GATE_NAME = "DEMO_AUTONOMOUS_6H_V2_BOUNDED_VALIDATION"
POLICY_VERSION = "demo-autonomous-6h-v2-bounded-v1"
SCHEMA_VERSION = "demo_validation_session_v2"
DECISION_LABEL = "RULE_BASED"

SESSION_DURATION_SEC = 6 * 60 * 60
AUTOMATIC_EXTENSION = False

MAX_CONCURRENT_POSITIONS = 1
MAX_PENDING_ORDERS = 1
MAX_TOTAL_ENTRY_ORDERS = 6
MAX_COMPLETED_TRADE_CASES = 6
MARGIN_PER_TRADE_CAP = 20.0
MIN_MARGIN_IF_RISK_SAFE = 20.0
FIXED_LEVERAGE = 25
MARGIN_MODE = "ISOLATED"

MAX_SESSION_NET_LOSS = 10.0
MAX_SINGLE_TRADE_NET_LOSS = 3.0
MAX_CONSECUTIVE_LOSSES = 3
MAX_BAD_PROCESS_OUTCOMES = 1
MAX_UNPROTECTED = 0
MAX_DUPLICATE_ORDERS = 0
MAX_RECONCILIATION_INCIDENTS = 0
MAX_CONTROLLER_OWNERS = 1

ACCOUNT_SNAPSHOT_MAX_AGE_SEC = 30
PROTECTION_VERIFY_DEADLINE_SEC = 5
MAX_HOLD_SEC = 30 * 60

# Hard gates — must not be lowered for fill rate.
MIN_NET_REWARD_TO_COST = 1.5
MIN_NET_REWARD_RISK_RATIO = 1.2

# Fee Founder policy (conservative Demo)
TAKER_FEE_RATE = 0.00055
MAKER_FEE_RATE = 0.00020
PRETRADE_ROUND_TRIP_FEE_RATE = 0.00110
FEE_REVIEW_BY = "2026-08-31"
FEE_VERSION = "founder-conservative-v1-2026-07-31"

# Historical bake (PR24) — NEVER report as current live deployment identity.
_HISTORICAL_DEPLOYMENT_COMMIT_PR24 = "81b0d14e2ffb6c5b5e92eeedd7962ed60dd00bc0"
_HISTORICAL_DEPLOY_RUN_PR24 = "30692231025"
_REJECTED_IDENTITY_MARKERS = frozenset(
    {
        _HISTORICAL_DEPLOYMENT_COMMIT_PR24,
        _HISTORICAL_DEPLOYMENT_COMMIT_PR24[:12],
        "unknown",
        "missing",
        "",
    }
)


def resolve_runtime_deployment_commit() -> str:
    """Current deployment identity: env only; never a stale hardcoded SHA."""
    for key in (
        "NEXUS_DEPLOYMENT_COMMIT",
        "NEXUS_SOURCE_COMMIT",
        "GITHUB_SHA",
        "ZEABUR_GIT_COMMIT_SHA",
        "ZEABUR_ENV_GITHUB_SHA",
        "ZEABUR_ENV_ZEABUR_GIT_COMMIT_SHA",
    ):
        value = (os.environ.get(key) or "").strip()
        if not value:
            continue
        lowered = value.lower()
        if lowered in _REJECTED_IDENTITY_MARKERS or value in _REJECTED_IDENTITY_MARKERS:
            continue
        if value.startswith(_HISTORICAL_DEPLOYMENT_COMMIT_PR24[:12]):
            continue
        return value
    return "UNKNOWN"


def resolve_runtime_deploy_run() -> str:
    """Current deploy run id from env; never the historical PR24 run id."""
    for key in ("NEXUS_DEPLOY_RUN_ID", "GITHUB_RUN_ID"):
        value = (os.environ.get(key) or "").strip()
        if not value or value == _HISTORICAL_DEPLOY_RUN_PR24:
            continue
        if value.lower() in {"unknown", "missing"}:
            continue
        return value
    return "UNKNOWN"


# Back-compat names: previously constants; now resolve dynamically (never stale SHA).
def __getattr__(name: str) -> str:
    if name == "RUNTIME_DEPLOYMENT_COMMIT_SOT":
        return resolve_runtime_deployment_commit()
    if name == "RUNTIME_DEPLOY_RUN_SOT":
        return resolve_runtime_deploy_run()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


SIX_ROLES = (
    "market_context",
    "market_structure",
    "risk_critic",
    "portfolio_manager",
    "performance_analyst",
    "reflection_analyst",
)

OUTCOME_LABELS = (
    "GOOD_PROCESS_WIN",
    "GOOD_PROCESS_LOSS",
    "BAD_PROCESS_WIN",
    "BAD_PROCESS_LOSS",
    "INCOMPLETE_EVIDENCE",
)

REFLECTION_ACTIONS = (
    "NO_CHANGE_JUSTIFIED",
    "EXACT_SETUP_COOLDOWN",
    "REQUIRE_EXTRA_CONFIRMATION",
    "SIMILAR_CASE_SCORE_PENALTY",
    "BLOCK_COST_DOMINATED_SETUP",
    "BLOCK_REPEATED_BAD_PROCESS",
    "BOUNDED_PATCH_PROPOSAL",
)

PATCH_MAX_STATUS = "REPLAY_VALIDATED"
FORBIDDEN_PATCH_STATUS = frozenset({"LIVE_APPLIED", "AUTO_PROMOTED", "PRODUCTION_PROMOTED"})
