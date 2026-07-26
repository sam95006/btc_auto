"""Phase 6.6 — Fixture / mock payloads when credentials absent."""
from __future__ import annotations

import time
from typing import Any


def _now_ms() -> int:
    return int(time.time() * 1000)


def fixture_wallet(*, stale: bool = False) -> dict[str, Any]:
    ts = _now_ms() - (300_000 if stale else 1_000)
    return {
        "retCode": 0,
        "retMsg": "OK",
        "time": ts,
        "result": {
            "list": [
                {
                    "accountType": "UNIFIED",
                    "totalEquity": "10000",
                    "totalWalletBalance": "10000",
                    "totalAvailableBalance": "9500",
                    "coin": [
                        {
                            "coin": "USDT",
                            "walletBalance": "10000",
                            "availableToWithdraw": "9500",
                            "equity": "10000",
                        }
                    ],
                }
            ]
        },
    }


def fixture_positions(*, stale: bool = False) -> dict[str, Any]:
    ts = _now_ms() - (300_000 if stale else 1_000)
    return {
        "retCode": 0,
        "retMsg": "OK",
        "time": ts,
        "result": {
            "list": [
                {
                    "symbol": "BTCUSDT",
                    "side": "Buy",
                    "size": "0.01",
                    "avgPrice": "60000",
                    "unrealisedPnl": "10",
                    "cumRealisedPnl": "5",
                    "updatedTime": str(ts),
                }
            ],
            "nextPageCursor": "",
        },
    }


def fixture_open_orders(*, page: int = 1) -> dict[str, Any]:
    ts = _now_ms()
    rows = [
        {
            "orderId": f"ord-{page}-1",
            "orderLinkId": f"nexus-demo-{page}-1",
            "symbol": "ETHUSDT",
            "side": "Buy",
            "qty": "0.1",
            "avgPrice": "0",
            "orderStatus": "New",
            "createdTime": str(ts),
            "updatedTime": str(ts),
        }
    ]
    return {
        "retCode": 0,
        "retMsg": "OK",
        "time": ts,
        "result": {
            "list": rows,
            "nextPageCursor": "page2" if page == 1 else "",
        },
    }


def fixture_order_history() -> dict[str, Any]:
    ts = _now_ms()
    return {
        "retCode": 0,
        "retMsg": "OK",
        "time": ts,
        "result": {
            "list": [
                {
                    "orderId": "hist-1",
                    "orderLinkId": "nexus-demo-hist-1",
                    "symbol": "BTCUSDT",
                    "side": "Sell",
                    "qty": "0.01",
                    "avgPrice": "61000",
                    "orderStatus": "Filled",
                    "createdTime": str(ts - 60_000),
                    "updatedTime": str(ts - 50_000),
                }
            ],
            "nextPageCursor": "",
        },
    }


def fixture_executions(*, duplicate: bool = False) -> dict[str, Any]:
    ts = _now_ms()
    row = {
        "execId": "exec-1",
        "orderId": "ord-1",
        "orderLinkId": "nexus-demo-1",
        "symbol": "BTCUSDT",
        "side": "Buy",
        "execQty": "0.01",
        "execPrice": "60000",
        "execTime": str(ts - 10_000),
        "closedPnl": "0",
    }
    rows = [row, dict(row)] if duplicate else [row]
    return {
        "retCode": 0,
        "retMsg": "OK",
        "time": ts,
        "result": {"list": rows, "nextPageCursor": ""},
    }


def fixture_server_time() -> dict[str, Any]:
    ts = _now_ms()
    return {
        "retCode": 0,
        "retMsg": "OK",
        "time": ts,
        "result": {"timeSecond": str(ts // 1000), "timeNano": str(ts * 1_000_000)},
    }


def fixture_query_api(*, trade: bool = False, withdraw: bool = False) -> dict[str, Any]:
    """Permission fixture. Default: read-capable without hard-fail perms."""
    permissions: dict[str, list[str]] = {"ContractTrade": []}
    if trade:
        permissions["ContractTrade"] = ["Order", "Position"]
    if withdraw:
        permissions["Wallet"] = ["Withdraw"]
    # Bybit-style nested permission bags; probe flattens values.
    if not trade and not withdraw:
        permissions = {"ReadOnly": ["ReadOnly"]}
    return {
        "retCode": 0,
        "retMsg": "OK",
        "time": _now_ms(),
        "result": {
            "id": "fixture-key",
            "note": "fixture",
            "apiKey": "REDACTED",
            "readOnly": 0 if trade else 1,
            "permissions": permissions,
        },
    }


FIXTURE_BY_PATH = {
    "/v5/market/time": lambda **_: fixture_server_time(),
    "/v5/user/query-api": lambda **kw: fixture_query_api(
        trade=bool(kw.get("trade", False)),
        withdraw=bool(kw.get("withdraw", False)),
    ),
    "/v5/account/wallet-balance": lambda **_: fixture_wallet(),
    "/v5/position/list": lambda **_: fixture_positions(),
    "/v5/order/realtime": lambda **kw: fixture_open_orders(page=int(kw.get("page", 1))),
    "/v5/order/history": lambda **_: fixture_order_history(),
    "/v5/execution/list": lambda **_: fixture_executions(),
    "/v5/position/closed-pnl": lambda **_: {
        "retCode": 0,
        "retMsg": "OK",
        "time": _now_ms(),
        "result": {"list": [], "nextPageCursor": ""},
    },
}
