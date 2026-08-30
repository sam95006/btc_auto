"""Bybit Demo signed READ-ONLY preflight for the certifier.

Uses the service's own env-held BYBIT_DEMO_API_KEY/SECRET. Every call is a GET
against api-demo.bybit.com only. No order submit/cancel/amend/close and no
position/leverage mutation is reachable from here. Returns booleans/readiness
only — never keys, secrets, or account-identifying values.
"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.nexus_demo_execution.demo_domain import DEMO_REST_BASE_URL
from backend.nexus_demo_execution.http_demo_reader import HttpDemoAccountReader, _sign_get

MARKET_TIME_PATH = "/v5/market/time"
INSTRUMENTS_PATH = "/v5/market/instruments-info"
USER_QUERY_PATH = "/v5/user/query-api"  # read-only: returns this key's user info
CLOCK_SKEW_LIMIT_MS = 5000
_TIMEOUT = 10.0

# Explicit READ-ONLY allow-list for this module. It contains no order/position
# mutating path; a mismatch is a guarded failure, never a silent write.
_ALLOWED_PATHS = frozenset({MARKET_TIME_PATH, INSTRUMENTS_PATH, USER_QUERY_PATH})


def _public_get(path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    if path not in _ALLOWED_PATHS:
        raise ValueError("path_not_allowed")
    url = f"{DEMO_REST_BASE_URL}{path}"
    if params:
        url = f"{url}?{urlencode(sorted(params.items()))}"
    req = Request(url, method="GET")
    with urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _signed_get(path: str, api_key: str, api_secret: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    if path not in _ALLOWED_PATHS:
        raise ValueError("path_not_allowed")
    params = params or {}
    headers = _sign_get(api_key, api_secret, params)
    url = f"{DEMO_REST_BASE_URL}{path}"
    if params:
        url = f"{url}?{urlencode(sorted(params.items()))}"
    req = Request(url, headers=headers, method="GET")
    with urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def bybit_readonly_preflight(*, expected_uid: str | None = None, reader: HttpDemoAccountReader | None = None) -> dict[str, Any]:
    """Signed read-only Bybit Demo certification. All mutation counters stay 0."""
    result: dict[str, Any] = {
        "auth": "FAIL",
        "uid_binding": "SKIPPED",
        "balance_read": "FAIL",
        "positions_read": "FAIL",
        "instrument_read": "FAIL",
        "clock_skew_ok": "FAIL",
        "account_flat": None,
        "domain": DEMO_REST_BASE_URL,
        # Proof that this path performs no writes.
        "orders_submitted": 0,
        "cancels": 0,
        "position_mutations": 0,
    }

    rd = reader or HttpDemoAccountReader()
    api_key = getattr(rd, "api_key", "")
    api_secret = getattr(rd, "api_secret", "")

    # 1) Signed auth + balance + positions via the domain-guarded read-only reader.
    try:
        snapshot = rd.read_snapshot()
        result["auth"] = "PASS"
        result["balance_read"] = "PASS" if isinstance(snapshot.wallet_balance, (int, float)) else "FAIL"
        positions = list(snapshot.open_positions or [])
        result["positions_read"] = "PASS"
        result["account_flat"] = len(positions) == 0
    except Exception:  # noqa: BLE001 - any read failure is a truthful FAIL, no detail leaked
        return result

    # 2) Public instrument metadata (read-only, unsigned).
    try:
        instr = _public_get(INSTRUMENTS_PATH, {"category": "linear", "limit": "1"})
        result["instrument_read"] = "PASS" if instr.get("retCode") == 0 else "FAIL"
    except Exception:  # noqa: BLE001
        result["instrument_read"] = "FAIL"

    # 3) Server clock skew (read-only, unsigned).
    try:
        t = _public_get(MARKET_TIME_PATH)
        server_ms = int((t.get("result") or {}).get("timeNano", 0)) // 1_000_000 or int((t.get("result") or {}).get("timeSecond", 0)) * 1000
        skew = abs(server_ms - int(time.time() * 1000))
        result["clock_skew_ok"] = "PASS" if server_ms and skew <= CLOCK_SKEW_LIMIT_MS else "FAIL"
    except Exception:  # noqa: BLE001
        result["clock_skew_ok"] = "FAIL"

    # 4) UID binding (signed read-only) — only when an expected UID is configured.
    if expected_uid:
        try:
            info = _signed_get(USER_QUERY_PATH, api_key, api_secret)
            uid = str((info.get("result") or {}).get("userID") or "")
            result["uid_binding"] = "PASS" if uid and uid == str(expected_uid) else "FAIL"
        except Exception:  # noqa: BLE001
            result["uid_binding"] = "FAIL"

    return result
