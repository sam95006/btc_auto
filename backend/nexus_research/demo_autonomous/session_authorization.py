"""One-shot Autonomous Demo Session Authorization.

Authorizes Demo writes within explicit bounds for a bounded session.
Never authorizes mainnet / real money / withdraw / transfer.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
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
    session_id: str = ""
    auto_send: bool = False
    max_consecutive_losses: int = 3
    risk_tier: str = "VALIDATION"

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
            "sessionId": self.session_id or self.authorization_hash[:16],
            "authorizationHashPrefix": self.authorization_hash[:12],
            "environment": self.environment,
            "accountIdentity": self.account_identity,
            "createdAtMs": self.created_at_ms,
            "expiresAtMs": self.expires_at_ms,
            "expired": self.is_expired(),
            "active": self.is_active(),
            "emergencyStopped": self.emergency_stopped,
            "autoSend": self.auto_send,
            "riskTier": self.risk_tier,
            "allowedSides": list(self.allowed_sides),
            "allowedStrategies": list(self.allowed_strategies),
            "allowedSymbols": list(self.allowed_symbols) if self.allowed_symbols else ["*DYNAMIC*"],
            "maxOpenPositions": self.max_open_positions,
            "maxPendingOrders": self.max_pending_orders,
            "maxRiskPerTradePct": self.max_risk_per_trade_pct,
            "maxDailyLossPct": self.max_daily_loss_pct,
            "maxWeeklyDrawdownPct": self.max_weekly_drawdown_pct,
            "maxConsecutiveLosses": self.max_consecutive_losses,
            "leveragePolicyVersion": self.leverage_policy_version,
            "capitalPolicyVersion": self.capital_policy_version,
            "consumedWrites": self.consumed_writes,
            "mainnetAllowed": False,
            "realMoneyAllowed": False,
            "withdrawAllowed": False,
            "transferAllowed": False,
            "secretSafe": True,
        }


class AuthorizationError(RuntimeError):
    pass


def _session_store_path() -> Path | None:
    try:
        from backend.nexus_research.boot_identity import research_data_dir

        root = research_data_dir()
        if root is None:
            return None
        return root / "autonomous_session.json"
    except Exception:
        return None


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
        auto_send: bool = False,
        max_consecutive_losses: int = 3,
        risk_tier: str = "VALIDATION",
    ) -> AutonomousDemoSessionAuthorization:
        now = int(time.time() * 1000)
        # Never raise risk above default ceiling.
        max_risk_per_trade_pct = min(float(max_risk_per_trade_pct), DEFAULT_MAX_RISK_PCT)
        token = raw_token or secrets.token_hex(32)
        session_id = secrets.token_hex(8)
        payload = {
            "environment": "BYBIT_DEMO",
            "account": "BYBIT_DEMO_ACCOUNT",
            "created": now,
            "expires": now + ttl_ms,
            "risk": max_risk_per_trade_pct,
            "lev_pol": LEVERAGE_POLICY_VERSION,
            "cap_pol": CAPITAL_POLICY_VERSION,
            "nonce": token,
            "session_id": session_id,
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
            session_id=session_id,
            auto_send=bool(auto_send),
            max_consecutive_losses=max(1, min(int(max_consecutive_losses), 3)),
            risk_tier=str(risk_tier or "VALIDATION"),
        )
        with self._lock:
            self._session = auth
        self.persist_to_disk()
        return auth

    def renew(
        self,
        *,
        ttl_ms: int = DEFAULT_TTL_MS,
        max_risk_per_trade_pct: float | None = None,
    ) -> AutonomousDemoSessionAuthorization:
        """Renew Demo session without raising risk limits. Mainnet forever blocked."""
        with self._lock:
            parent = self._session
            if parent is None:
                raise AuthorizationError("session_authorization_missing_for_renew")
            if parent.emergency_stopped:
                raise AuthorizationError("session_emergency_stopped")
            if parent.environment != "BYBIT_DEMO" or parent.account_identity != "BYBIT_DEMO_ACCOUNT":
                raise AuthorizationError("session_environment_not_demo")
            if parent.leverage_policy_version != LEVERAGE_POLICY_VERSION:
                raise AuthorizationError("leverage_policy_version_mismatch")
            if parent.capital_policy_version != CAPITAL_POLICY_VERSION:
                raise AuthorizationError("capital_policy_version_mismatch")
            risk = parent.max_risk_per_trade_pct
            if max_risk_per_trade_pct is not None:
                risk = min(float(max_risk_per_trade_pct), parent.max_risk_per_trade_pct)
            symbols = parent.allowed_symbols
            auto_send = parent.auto_send
            max_cl = parent.max_consecutive_losses
            risk_tier = parent.risk_tier
        return self.issue(
            ttl_ms=ttl_ms,
            allowed_symbols=symbols,
            max_risk_per_trade_pct=risk,
            auto_send=auto_send,
            max_consecutive_losses=max_cl,
            risk_tier=risk_tier,
        )

    def persist_to_disk(self) -> bool:
        path = _session_store_path()
        if path is None:
            return False
        with self._lock:
            sess = self._session
            if sess is None:
                return False
            payload = {
                "authorizationHash": sess.authorization_hash,
                "environment": sess.environment,
                "accountIdentity": sess.account_identity,
                "createdAtMs": sess.created_at_ms,
                "expiresAtMs": sess.expires_at_ms,
                "allowedSides": list(sess.allowed_sides),
                "allowedStrategies": list(sess.allowed_strategies),
                "allowedSymbols": list(sess.allowed_symbols),
                "maxOpenPositions": sess.max_open_positions,
                "maxPendingOrders": sess.max_pending_orders,
                "maxRiskPerTradePct": sess.max_risk_per_trade_pct,
                "maxDailyLossPct": sess.max_daily_loss_pct,
                "maxWeeklyDrawdownPct": sess.max_weekly_drawdown_pct,
                "leveragePolicyVersion": sess.leverage_policy_version,
                "capitalPolicyVersion": sess.capital_policy_version,
                "emergencyStopped": sess.emergency_stopped,
                "consumedWrites": sess.consumed_writes,
                "sessionId": sess.session_id,
                "autoSend": sess.auto_send,
                "maxConsecutiveLosses": sess.max_consecutive_losses,
                "riskTier": sess.risk_tier,
            }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        except Exception:
            return False

    def restore_from_disk(self) -> bool:
        path = _session_store_path()
        if path is None:
            return False
        try:
            if not path.is_file():
                return False
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("environment") != "BYBIT_DEMO":
                return False
            if data.get("accountIdentity") != "BYBIT_DEMO_ACCOUNT":
                return False
            if data.get("leveragePolicyVersion") != LEVERAGE_POLICY_VERSION:
                return False
            if data.get("capitalPolicyVersion") != CAPITAL_POLICY_VERSION:
                return False
            auth = AutonomousDemoSessionAuthorization(
                authorization_hash=str(data.get("authorizationHash") or ""),
                created_at_ms=int(data.get("createdAtMs") or 0),
                expires_at_ms=int(data.get("expiresAtMs") or 0),
                allowed_sides=tuple(data.get("allowedSides") or ("Buy", "Sell")),
                allowed_strategies=tuple(data.get("allowedStrategies") or ()),
                allowed_symbols=tuple(data.get("allowedSymbols") or ()),
                max_open_positions=int(data.get("maxOpenPositions") or 1),
                max_pending_orders=int(data.get("maxPendingOrders") or 1),
                max_risk_per_trade_pct=min(
                    float(data.get("maxRiskPerTradePct") or DEFAULT_MAX_RISK_PCT),
                    DEFAULT_MAX_RISK_PCT,
                ),
                max_daily_loss_pct=float(data.get("maxDailyLossPct") or DEFAULT_MAX_DAILY_LOSS_PCT),
                max_weekly_drawdown_pct=float(
                    data.get("maxWeeklyDrawdownPct") or DEFAULT_MAX_WEEKLY_DD_PCT
                ),
                leverage_policy_version=LEVERAGE_POLICY_VERSION,
                capital_policy_version=CAPITAL_POLICY_VERSION,
                emergency_stopped=bool(data.get("emergencyStopped")),
                consumed_writes=int(data.get("consumedWrites") or 0),
                raw_token_present=False,
                session_id=str(data.get("sessionId") or ""),
                auto_send=bool(data.get("autoSend")),
                max_consecutive_losses=int(data.get("maxConsecutiveLosses") or 3),
                risk_tier=str(data.get("riskTier") or "VALIDATION"),
            )
            # Expired sessions are restored as expired (no silent write grant).
            with self._lock:
                self._session = auth
            return True
        except Exception:
            return False

    def emergency_stop(self, reason: str = "") -> None:
        with self._lock:
            if self._session is not None:
                self._session.emergency_stopped = True
        self.persist_to_disk()

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
        self.persist_to_disk()

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
