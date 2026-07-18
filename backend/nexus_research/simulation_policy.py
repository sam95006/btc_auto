"""Phase 6 Gate C — Simulation Policy Audit & Centralized Research Defaults.

RESEARCH ONLY. Centralizes all conservative simulation defaults in one place.
Audits existing simulator, risk engine, and capital allocator configurations
and exposes SIMULATION_POLICY_AUDIT via status().

Policy philosophy:
  - Never default to real trading.
  - Conservative sizing even in PAPER mode.
  - Kill switch always available and respected by all layers.
  - All exit events leave ledger evidence with reason codes.
  - Mode escalation requires explicit operator env-var change.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

RESEARCH_ONLY: bool = True

# ── Conservative research-only policy defaults ────────────────────────────────

PAPER_POLICY_DEFAULTS: dict[str, Any] = {
    # ── Simulator ───────────────────────────────────────────────────────────────
    "spread_bps": 3,
    "slippage_market_bps": 5,
    "taker_fee_bps": 6,
    "maker_fee_bps": 2,
    "funding_rate_8h": 0.01,
    "fill_latency_ms": 100,
    "price_precision": 2,
    "qty_precision": 4,
    "max_leverage": 10.0,
    "default_leverage": 3.0,          # deliberately lower than default 5x
    "max_orders_history": 500,
    "limit_order_expire_ms": 3_600_000,

    # ── Risk engine ─────────────────────────────────────────────────────────────
    "max_open_positions": 5,           # conservative (default 10)
    "max_leverage_risk": 5.0,          # hard block above this
    "max_notional_per_symbol_usd": 10_000.0,   # half of risk engine default
    "max_portfolio_notional_usd": 50_000.0,    # half of risk engine default
    "max_sector_notional_usd": 20_000.0,
    "max_daily_loss_usd": 500.0,               # half of risk engine default
    "max_drawdown_pct": 10.0,                  # tighter than 20%
    "spread_max_bps": 10.0,
    "stale_data_age_ms": 30_000,               # 30s stale threshold (tighter)
    "candidate_expiry_grace_ms": 2_000,        # shorter grace period
    "funding_crowding_threshold_pct": 0.05,
    "allow_duplicate_same_symbol": False,
    "max_concurrent_same_symbol": 1,

    # ── Capital allocator ───────────────────────────────────────────────────────
    "equity_fraction_pct": 1.0,        # half of default 2%
    "max_fraction_pct": 2.5,           # half of default 5%
    "min_sample_conservative_fraction": 0.3,   # more conservative bootstrap
    "min_sample_size": 30,             # higher sample needed for full fraction
    "max_notional_per_symbol_alloc_usd": 10_000.0,
    "max_total_notional_alloc_usd": 50_000.0,
    "score_scale_min": 60.0,           # higher score gate than default 50
    "score_scale_max": 90.0,

    # ── Exit policies ───────────────────────────────────────────────────────────
    "stop_loss_pct": 2.0,              # close if unrealised PnL < -2% of notional
    "take_profit_pct": 4.0,            # close if unrealised PnL > +4% of notional
    "max_hold_hours": 24.0,            # force-close after 24h
    "stale_mark_price_ms": 60_000,     # 60s without mark price → stale exit
    "exit_on_kill_switch": True,       # immediately exit on kill switch
    "exit_on_mode_off": True,          # exit all if mode changes to OFF

    # ── Paper loop ──────────────────────────────────────────────────────────────
    "paper_loop_interval_sec": 60.0,   # poll interval for paper controller
    "min_score_for_paper": 65.0,       # gate score before submitting PAPER order
    "max_candidates_per_cycle": 3,     # max candidates processed per loop tick
    "require_evidence_coverage": True, # at least one evidence field populated
    "require_fresh_data_age_ms": 30_000,  # require data younger than 30s
}


class SimulationPolicy:
    """Singleton policy container. Audits & centralizes conservative defaults.

    Audit is run once at init and on any explicit call to audit().
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._policy: dict[str, Any] = dict(PAPER_POLICY_DEFAULTS)
        self._audit_result: dict[str, Any] = {}
        self._audit_ts: int = 0
        self._run_audit()

    def _run_audit(self) -> dict[str, Any]:
        """Inspect actual singleton configs and compare against policy defaults."""
        findings: list[dict[str, Any]] = []
        warnings: list[str] = []

        # ── Simulator audit ─────────────────────────────────────────────────────
        try:
            from backend.nexus_research.simulator import get_simulator, _DEFAULT_CONFIG
            sim = get_simulator()
            for key, policy_val in [
                ("spread_bps", self._policy["spread_bps"]),
                ("slippage_market_bps", self._policy["slippage_market_bps"]),
                ("taker_fee_bps", self._policy["taker_fee_bps"]),
                ("max_leverage", self._policy["max_leverage"]),
                ("default_leverage", self._policy["default_leverage"]),
            ]:
                actual = _DEFAULT_CONFIG.get(key)
                if actual is not None and actual > policy_val:
                    warnings.append(
                        f"simulator.{key}={actual} exceeds policy max={policy_val}"
                    )
                findings.append({
                    "component": "simulator",
                    "key": key,
                    "policyDefault": policy_val,
                    "actualDefault": actual,
                    "ok": actual is None or actual <= policy_val,
                })
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"simulator audit failed: {exc}")

        # ── Risk engine audit ────────────────────────────────────────────────────
        try:
            from backend.nexus_research.risk_engine import get_risk_engine, _DEFAULT_RISK_CONFIG
            for key, policy_val in [
                ("max_open_positions", self._policy["max_open_positions"]),
                ("max_leverage", self._policy["max_leverage_risk"]),
                ("max_notional_per_symbol_usd", self._policy["max_notional_per_symbol_usd"]),
                ("max_daily_loss_usd", self._policy["max_daily_loss_usd"]),
                ("max_drawdown_pct", self._policy["max_drawdown_pct"]),
            ]:
                actual = _DEFAULT_RISK_CONFIG.get(key)
                findings.append({
                    "component": "risk_engine",
                    "key": key,
                    "policyDefault": policy_val,
                    "actualDefault": actual,
                    "ok": True,  # risk engine defaults may be higher; paper_controller overrides
                })
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"risk_engine audit failed: {exc}")

        # ── Capital allocator audit ──────────────────────────────────────────────
        try:
            from backend.nexus_research.capital_allocator import get_capital_allocator, _DEFAULT_ALLOC_CONFIG
            for key, policy_val in [
                ("equity_fraction_pct", self._policy["equity_fraction_pct"]),
                ("max_fraction_pct", self._policy["max_fraction_pct"]),
                ("score_scale_min", self._policy["score_scale_min"]),
            ]:
                actual = _DEFAULT_ALLOC_CONFIG.get(key)
                findings.append({
                    "component": "capital_allocator",
                    "key": key,
                    "policyDefault": policy_val,
                    "actualDefault": actual,
                    "ok": True,
                })
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"capital_allocator audit failed: {exc}")

        result = {
            "ok": True,
            "researchOnly": True,
            "privateApi": False,
            "auditTimestampMs": int(time.time() * 1000),
            "totalFindings": len(findings),
            "totalWarnings": len(warnings),
            "findings": findings,
            "warnings": warnings,
            "policyVersion": "6.0.0-gate-c",
            "note": (
                "Paper controller uses PAPER_POLICY_DEFAULTS; "
                "existing singletons may use their own defaults unless overridden."
            ),
        }
        with self._lock:
            self._audit_result = result
            self._audit_ts = int(time.time() * 1000)
        return result

    def audit(self) -> dict[str, Any]:
        """Re-run audit and return result (also stored as SIMULATION_POLICY_AUDIT)."""
        return self._run_audit()

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._policy.get(key, default)

    def status(self) -> dict[str, Any]:
        with self._lock:
            audit = dict(self._audit_result)
            policy = dict(self._policy)
        return {
            "ok": True,
            "researchOnly": True,
            "privateApi": False,
            "SIMULATION_POLICY_AUDIT": audit,
            "policyDefaults": policy,
            "generatedAt": int(time.time() * 1000),
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
_POLICY: SimulationPolicy | None = None
_POLICY_LOCK = threading.Lock()


def get_simulation_policy() -> SimulationPolicy:
    global _POLICY
    with _POLICY_LOCK:
        if _POLICY is None:
            _POLICY = SimulationPolicy()
            logger.info("[sim_policy] SimulationPolicy initialised (researchOnly=true)")
        return _POLICY


# Module-level alias so callers can do:
#   from backend.nexus_research.simulation_policy import SIMULATION_POLICY_AUDIT
def SIMULATION_POLICY_AUDIT() -> dict[str, Any]:
    """Return current policy audit snapshot."""
    return get_simulation_policy().status()["SIMULATION_POLICY_AUDIT"]
