"""Fetch Bybit Demo / public linear instruments for DynamicContractUniverse."""
from __future__ import annotations

import json
import logging
from typing import Any
from urllib.request import Request, urlopen

from backend.nexus_research.demo_exchange.constants import DEMO_REST_BASE_URL, HTTP_TIMEOUT_SEC

logger = logging.getLogger(__name__)

# Public instruments are readable without credentials; still Demo host only.
INSTRUMENTS_PATH = "/v5/market/instruments-info"


def fetch_linear_perpetual_instruments(
    *,
    base_url: str = DEMO_REST_BASE_URL,
    timeout_sec: float = HTTP_TIMEOUT_SEC,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """GET linear instruments from api-demo.bybit.com (or overridden Demo base)."""
    if "api-demo.bybit.com" not in base_url and "bybit.com" in base_url:
        # Refuse mainnet/testnet hosts for autonomous path.
        raise ValueError(f"instruments_host_not_demo:{base_url}")
    url = f"{base_url.rstrip('/')}{INSTRUMENTS_PATH}?category=linear&limit={int(limit)}"
    req = Request(url, method="GET")
    with urlopen(req, timeout=timeout_sec) as resp:
        raw = resp.read().decode("utf-8", "replace")
    data = json.loads(raw)
    if not isinstance(data, dict) or int(data.get("retCode", -1)) != 0:
        raise RuntimeError(f"instruments_fetch_failed:{data.get('retMsg') if isinstance(data, dict) else 'bad'}")
    result = data.get("result") or {}
    rows = result.get("list") or []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        # Prefer perpetual USDT symbols
        symbol = str(row.get("symbol") or "")
        if not symbol.endswith("USDT"):
            continue
        ctype = str(row.get("contractType") or "")
        if ctype and "Perpetual" not in ctype and "PERPETUAL" not in ctype.upper():
            continue
        status = str(row.get("status") or "")
        if status and status not in ("Trading", "trading", "TRADING"):
            continue
        out.append(row)
    logger.info("fetched_linear_instruments count=%s", len(out))
    return out
