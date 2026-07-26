"""One-shot Autonomous Demo Session Authorization.

Authorizes Demo writes within explicit bounds for a bounded session.
Never authorizes mainnet / real money / withdraw / transfer.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

SESSION_AUTH_ENV = "NEXUS_AUTONOMOUS_DEMO_SESSION_TOKEN"
SESSION_ENABLED_ENV = "NEXUS_AUTONOMOUS_DEMO_ENABLED"

DEFAULT_TTL_MS = 6 * 60 * 60 * 1000  # 6 hours
DEFAULT_MAX_RISK_PCT = 0.5
DEFAULT_MAX_DAILY_LOSS_PCT = 1.5
DEFAULT_MAX_WEEKLY_DD_PCT = 4.0
LEVERAGE_POLICY_VERSION = "v1_tiered_2026_07"
CAPITAL_POLICY_VERSION = "validation_v1"


@dataclass
class AutonomousDemoSessionAuthorization:
    """Bounded session grant for Bybit Demo autonomous trading."""

    authorization_hash: str
    environment: str = "BYBIT_DEMO"
    account_identity: str = "BYBIT_DEMO_ACCOUNT"
    created_at_ms: int = 0
    expires_at_ms: int = 0
    allowed_sides: tuple[str, ...] = ("Buy", "Sell")
    allowed_strategies: tuple[str, ...] = (
        "TREND_FOLLOWING",
        "BREAKOUT",
        "PULLBACK",
        "MOMENTUM",
        "MEAN_REVERSION",
        "VOL_EXPANSION",
        "FUNDING_OI_DIVERGENCE",
        "ORDER_FLOW",
    )
    # Empty allowlist means dynamic universe (still gated by tradability).
    allowed_symbols: tuple[str, ...] = ()
    max_open_positions: int = 1
    max_pending_orders: int = 1
    max_risk_per_trade_pct: float = DEFAULT_MAX_RISK_PCT
    max_daily_loss_pct: float = DEFAULT_MAX_DAILY_LOSS_PCT
    max_weekly_drawdown_pct: float = DEFAULT_MAX_WEEKLY_DD_PCT
    leverage_policy_version: str = LEVERAGE_POLICY_VERSION
    capital_policy_version: str = CAPITAL_POLICY_VERSION
    emergency_stopped: bool = False
    consumed_writes: int = 0
    raw_token_present: bool = False

    def is_expired(self, now_ms: int | None = None) -> bool:
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        return now > self.expires_at_ms

    def is_active(self, now_ms: int | None = None) -> bool:
        return (
            not self.emergency_stopped
            and not self.is_expired(now_ms)
            and self.environment == "BYBIT_DEMO"
            and self.account_identity == "BYBIT_DEMO_ACCOUNT"
        )

    def allows_symbol(self, symbol: str) -> bool:
        if not self.allowed_symbols:
            return True
        return symbol.upper() in {s.upper() for s in self.allowed_symbols}

    def allows_side(self, side: str) -> bool:
        return side in self.allowed_sides

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "authorizationHashPrefix": self.authorization_hash[:12],
            "environment": self.environment,
            "accountIdentity": self.account_identity,
            "createdAtMs": self.created_at_ms,
            "expiresAtMs": self.expires_at_ms,
            "expired": self.is_expired(),
            "active": self.is_active(),
            "emergencyStopped": self.emergency_stopped,
            "allowedSides": list(self.allowed_sides),
            "allowedStrategies": list(self.allowed_strategies),
            "allowedSymbols": list(self.allowed_symbols) if self.allowed_symbols else ["*DYNAMIC*"],
            "maxOpenPositions": self.max_open_positions,
            "maxPendingOrders": self.max_pending_orders,
            "maxRiskPerTradePct": self.max_risk_per_trade_pct,
            "maxDailyLossPct": self.max_daily_loss_pct,
            "maxWeeklyDrawdownPct": self.max_weekly_drawdown_pct,
            "leveragePolicyVersion": self.leverage_policy_version,
            "capitalPolicyVersion": self.capital_policy_version,
            "consumedWrites": self.consumed_writes,
            "mainnetAllowed": False,
            "realMoneyAllowed": False,
            "secretSafe": True,
        }


class AuthorizationError(RuntimeError):
    pass


class AuthorizationValidator:
    """Validate and gate session authorization."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._session: AutonomousDemoSessionAuthorization | None = None

    @property
    def session(self) -> AutonomousDemoSessionAuthorization | None:
        return self._session

    def issue(
        self,
        *,
        ttl_ms: int = DEFAULT_TTL_MS,
        allowed_symbols: tuple[str, ...] | list[str] | None = None,
        max_risk_per_trade_pct: float = DEFAULT_MAX_RISK_PCT,
        raw_token: str | None = None,
    ) -> AutonomousDemoSessionAuthorization:
        now = int(time.time() * 1000)
        token = raw_token or secrets.token_hex(32)
        payload = {
            "environment": "BYBIT_DEMO",
            "account": "BYBIT_DEMO_ACCOUNT",
            "created": now,
            "expires": now + ttl_ms,
            "risk": max_risk_per_trade_pct,
            "lev_pol": LEVERAGE_POLICY_VERSION,
            "cap_pol": CAPITAL_POLICY_VERSION,
            "nonce": token,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        auth = AutonomousDemoSessionAuthorization(
            authorization_hash=digest,
            created_at_ms=now,
            expires_at_ms=now + ttl_ms,
            allowed_symbols=tuple(allowed_symbols or ()),
            max_risk_per_trade_pct=float(max_risk_per_trade_pct),
            raw_token_present=True,
        )
        with self._lock:
            self._session = auth
        return auth

    def emergency_stop(self, reason: str = "") -> None:
        with self._lock:
            if self._session is not None:
                self._session.emergency_stopped = True

    def require_active(self) -> AutonomousDemoSessionAuthorization:
        with self._lock:
            if self._session is None:
                raise AuthorizationError("session_authorization_missing")
            if not self._session.is_active():
                raise AuthorizationError("session_authorization_inactive_or_expired")
            return self._session

    def record_write(self) -> None:
        with self._lock:
            if self._session is not None:
                self._session.consumed_writes += 1

    def validate_order_bounds(
        self,
        *,
        symbol: str,
        side: str,
        risk_pct: float,
        open_positions: int,
        pending_orders: int,
    ) -> list[str]:
        auth = self.require_active()
        blocks: list[str] = []
        if not auth.allows_symbol(symbol):
            blocks.append(f"symbol_not_allowed:{symbol}")
        if not auth.allows_side(side):
            blocks.append(f"side_not_allowed:{side}")
        if risk_pct > auth.max_risk_per_trade_pct + 1e-9:
            blocks.append(
                f"risk_pct:{risk_pct}>max:{auth.max_risk_per_trade_pct}"
            )
        if open_positions >= auth.max_open_positions:
            blocks.append("max_open_positions")
        if pending_orders >= auth.max_pending_orders:
            blocks.append("max_pending_orders")
        return blocks


_GLOBAL_VALIDATOR = AuthorizationValidator()


def get_authorization_validator() -> AuthorizationValidator:
    return _GLOBAL_VALIDATOR


def autonomous_enabled_from_env() -> bool:
    raw = os.environ.get(SESSION_ENABLED_ENV, "").strip().lower()
    return raw in ("1", "true", "yes")
