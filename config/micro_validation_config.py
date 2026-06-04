"""Phase 3.0 — Controlled Micro Entry Validation (narrow path, Defensive stays ON)."""

import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except Exception:
        return default


MICRO_VALIDATION_ENABLED = _env_bool("NEXUS_MICRO_VALIDATION_ENABLED", False)
MICRO_VALIDATION_SYMBOL = str(os.getenv("NEXUS_MICRO_VALIDATION_SYMBOL", "ETHUSDT") or "ETHUSDT").upper()
MICRO_VALIDATION_SIDE = str(os.getenv("NEXUS_MICRO_VALIDATION_SIDE", "BUY") or "BUY").upper()
MICRO_VALIDATION_FLEET = str(os.getenv("NEXUS_MICRO_VALIDATION_FLEET", "ETH") or "ETH").upper()
MICRO_VALIDATION_MAX_MARGIN_USD = _env_float("NEXUS_MICRO_VALIDATION_MAX_MARGIN_USD", 20.0)
MICRO_VALIDATION_MAX_LEVERAGE = int(_env_float("NEXUS_MICRO_VALIDATION_MAX_LEVERAGE", 5))
MICRO_VALIDATION_SL_USD = _env_float("NEXUS_MICRO_VALIDATION_SL_USD", 2.0)
MICRO_VALIDATION_TP_ENABLED = _env_bool("NEXUS_MICRO_VALIDATION_TP_ENABLED", False)
MICRO_VALIDATION_TP_USD = _env_float("NEXUS_MICRO_VALIDATION_TP_USD", 0.0)
MICRO_VALIDATION_MAX_HOLD_MIN = _env_float("NEXUS_MICRO_VALIDATION_MAX_HOLD_MIN", 30.0)
MICRO_VALIDATION_REQUIRE_REFLECTION = _env_bool("NEXUS_MICRO_VALIDATION_REQUIRE_REFLECTION", True)
MICRO_VALIDATION_PAUSE_AI_ENTRIES = _env_bool("NEXUS_MICRO_VALIDATION_PAUSE_AI_ENTRIES", True)
MICRO_VALIDATION_EMERGENCY_CLOSE = _env_bool("NEXUS_MICRO_VALIDATION_EMERGENCY_CLOSE", True)
MICRO_VALIDATION_ALLOW_REARM = _env_bool("NEXUS_MICRO_VALIDATION_ALLOW_REARM", False)
MICRO_VALIDATION_ALLOW_PARTIAL = _env_bool("NEXUS_MICRO_VALIDATION_ALLOW_PARTIAL", False)
MICRO_VALIDATION_DECISION_SOURCE = "micro_validation_p30"
MICRO_VALIDATION_STRATEGY_KEY = "micro_validation_p30"

ALLOWED_MICRO_SYMBOLS = frozenset({"BTCUSDT", "ETHUSDT"})
BLOCKED_MICRO_FLEETS = frozenset({"RADAR", "PEPE"})


def micro_validation_active() -> bool:
    return bool(MICRO_VALIDATION_ENABLED)


def is_micro_validation_entry(proposal) -> bool:
    proposal = dict(proposal or {})
    source = str(proposal.get("decision_source") or proposal.get("proposer") or "")
    if source == MICRO_VALIDATION_DECISION_SOURCE:
        return True
    if str(proposal.get("strategy_key") or "") == MICRO_VALIDATION_STRATEGY_KEY:
        return True
    return False


def is_micro_sizing_request(proposal) -> bool:
    """True when micro sizing override applies (Phase 3.1)."""
    proposal = dict(proposal or {})
    if is_micro_validation_entry(proposal):
        return True
    if str(proposal.get("micro_validation_session_id") or "").strip():
        return True
    return False


def is_micro_governance_live_exception(proposal) -> bool:
    """Phase 3.4.1 — micro validation only: bypass governance shadow mode for live execute."""
    return is_micro_sizing_request(proposal)


def is_micro_regime_governance_exception(proposal) -> bool:
    """Phase 3.5.1 — micro validation only: bypass regime HIGH_RISK_MACRO new-entry block."""
    return is_micro_sizing_request(proposal)


def is_micro_fee_churn_exception(proposal) -> bool:
    """Phase 3.5.2 — micro validation session only: bypass FeeChurnGuard.allow_open()."""
    if not micro_validation_active():
        return False
    return is_micro_sizing_request(proposal)
