"""Real Bybit Demo private GET reader — api-demo.bybit.com only."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.nexus_demo_execution.account_reader import (
    AccountReaderError,
    BybitDemoAccountReader,
    DemoAccountSnapshot,
)
from backend.nexus_demo_execution.capital_constitution import BalanceSource
from backend.nexus_demo_execution.demo_domain import DEMO_REST_BASE_URL, DemoDomainPolicy

logger = logging.getLogger(__name__)

WALLET_BALANCE_PATH = "/v5/account/wallet-balance"
POSITION_LIST_PATH = "/v5/position/list"
OPEN_ORDERS_PATH = "/v5/order/realtime"

ALLOWED_GET_PATHS = frozenset({WALLET_BALANCE_PATH, POSITION_LIST_PATH, OPEN_ORDERS_PATH})

SECRET_MARKERS = frozenset({"api_key", "api_secret", "secret", "password", "token"})


def redact_secrets(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Remove or mask secret-bearing keys from payloads."""
    if not payload:
        return {}
    redacted: dict[str, Any] = {}
    for key, value in payload.items():
        if any(marker in key.lower() for marker in SECRET_MARKERS):
            redacted[key] = "[REDACTED]"
        elif isinstance(value, dict):
            redacted[key] = redact_secrets(value)
        else:
            redacted[key] = value
    return redacted


@dataclass
class HttpDemoTransport:
    """Injectable GET transport — domain-guarded to api-demo.bybit.com."""

    policy: DemoDomainPolicy = field(default_factory=DemoDomainPolicy)
    timeout_sec: float = 10.0
    _http_get: Callable[[str, dict[str, str], dict[str, str]], dict[str, Any]] | None = None
    call_count: int = 0

    def get(
        self,
        path: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if path not in ALLOWED_GET_PATHS:
            raise AccountReaderError("path_not_allowed", path)
        base = self.policy.base_url
        if base != DEMO_REST_BASE_URL:
            raise AccountReaderError("domain_guard_failed", base)

        params = params or {}
        headers = headers or {}
        query = urlencode(sorted((str(k), str(v)) for k, v in params.items()))
        url = f"{base}{path}"
        if query:
            url = f"{url}?{query}"

        self.call_count += 1
        if self._http_get is not None:
            return self._http_get(url, params, headers)

        req = Request(url, headers=headers, method="GET")
        with urlopen(req, timeout=self.timeout_sec) as resp:
            body = resp.read().decode("utf-8")
        return json.loads(body)


def _sign_get(
    api_key: str,
    api_secret: str,
    params: dict[str, str],
    recv_window: str = "5000",
) -> dict[str, str]:
    timestamp = str(int(time.time() * 1000))
    param_str = urlencode(sorted((str(k), str(v)) for k, v in params.items()))
    sign_payload = f"{timestamp}{api_key}{recv_window}{param_str}"
    signature = hmac.new(
        api_secret.encode("utf-8"),
        sign_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-SIGN": signature,
        "X-BAPI-SIGN-TYPE": "2",
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-RECV-WINDOW": recv_window,
    }


@dataclass
class HttpDemoAccountReader(BybitDemoAccountReader):
    """Live Bybit Demo private GET reader with injectable transport."""

    transport: HttpDemoTransport = field(default_factory=HttpDemoTransport)
    api_key: str = ""
    api_secret: str = ""
    account_type: str = "UNIFIED"

    def __post_init__(self) -> None:
        if not self.api_key:
            self.api_key = os.environ.get("BYBIT_DEMO_API_KEY", "")
        if not self.api_secret:
            self.api_secret = os.environ.get("BYBIT_DEMO_API_SECRET", "")

    def read_snapshot(self) -> DemoAccountSnapshot:
        if not self.api_key or not self.api_secret:
            raise AccountReaderError("credentials_missing")

        params = {"accountType": self.account_type}
        headers = _sign_get(self.api_key, self.api_secret, params)
        wallet_resp = self.transport.get(WALLET_BALANCE_PATH, params, headers)
        if wallet_resp.get("retCode") != 0:
            raise AccountReaderError(
                "wallet_read_failed",
                str(wallet_resp.get("retMsg", "unknown")),
            )

        wallet_list = (wallet_resp.get("result") or {}).get("list") or []
        if not wallet_list:
            raise AccountReaderError("empty_wallet_response")

        account = wallet_list[0]
        coin_list = account.get("coin") or []
        usdt = next((c for c in coin_list if c.get("coin") == "USDT"), {})

        positions = self._read_positions()
        orders = self._read_open_orders()

        return DemoAccountSnapshot(
            wallet_balance=_float(account.get("totalWalletBalance")),
            equity=_float(account.get("totalEquity")),
            available_balance=_float(usdt.get("availableToWithdraw") or usdt.get("walletBalance")),
            margin_balance=_float(account.get("totalMarginBalance")),
            used_margin=_float(account.get("totalInitialMargin")),
            unrealized_pnl=_float(account.get("totalPerpUPL")),
            realized_pnl=_float(usdt.get("cumRealisedPnl")),
            open_positions=positions,
            open_orders=orders,
            source=BalanceSource.BYBIT_DEMO_PRIVATE_API.value,
        )

    def _read_positions(self) -> list[dict[str, Any]]:
        params = {"category": "linear", "settleCoin": "USDT"}
        headers = _sign_get(self.api_key, self.api_secret, params)
        try:
            resp = self.transport.get(POSITION_LIST_PATH, params, headers)
            if resp.get("retCode") != 0:
                return []
            return list((resp.get("result") or {}).get("list") or [])
        except Exception:
            logger.warning("position_read_failed", exc_info=False)
            return []

    def _read_open_orders(self) -> list[dict[str, Any]]:
        params = {"category": "linear", "settleCoin": "USDT"}
        headers = _sign_get(self.api_key, self.api_secret, params)
        try:
            resp = self.transport.get(OPEN_ORDERS_PATH, params, headers)
            if resp.get("retCode") != 0:
                return []
            return list((resp.get("result") or {}).get("list") or [])
        except Exception:
            logger.warning("open_orders_read_failed", exc_info=False)
            return []

    def evidence_summary(self) -> dict[str, Any]:
        return redact_secrets(
            {
                "reader": "HttpDemoAccountReader",
                "domain": self.transport.policy.base_url,
                "network_calls": self.transport.call_count,
                "credential_present": bool(self.api_key and self.api_secret),
            }
        )


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
