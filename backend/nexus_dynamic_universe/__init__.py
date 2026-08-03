"""NEXUS Dynamic Linear USDT Universe — single universe, no fleets."""
from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PUBLIC_BASE = "https://api.bybit.com"
UNIVERSE_ID = "NEXUS_DYNAMIC_LINEAR_USDT_UNIVERSE"
EXCLUDED_STATUS = frozenset({"PreLaunch", "Settling", "Delivering", "Closed"})


def _sha_obj(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _get(path: str, params: dict[str, Any], *, timeout: float = 20.0) -> dict[str, Any]:
    qs = urllib.parse.urlencode(params)
    url = f"{PUBLIC_BASE}{path}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": "nexus-dynamic-universe/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    ret = payload.get("retCode")
    if ret is None or int(ret) != 0:
        raise RuntimeError(f"bybit_error:{payload.get('retCode')}:{payload.get('retMsg')}")
    return payload


def fetch_all_linear_instruments(*, max_pages: int = 50) -> list[dict[str, Any]]:
    """Complete cursor pagination for linear instruments."""
    rows: list[dict[str, Any]] = []
    cursor = ""
    pages = 0
    for _ in range(max_pages):
        params: dict[str, Any] = {"category": "linear", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        payload = _get("/v5/market/instruments-info", params)
        result = payload.get("result") or {}
        batch = list(result.get("list") or [])
        rows.extend(batch)
        pages += 1
        cursor = str(result.get("nextPageCursor") or "")
        if not cursor or not batch:
            break
        time.sleep(0.05)
    return rows


def fetch_all_linear_tickers() -> list[dict[str, Any]]:
    payload = _get("/v5/market/tickers", {"category": "linear"})
    return list(((payload.get("result") or {}).get("list")) or [])


@dataclass
class InstrumentSnapshot:
    symbol: str
    base_coin: str
    quote_coin: str
    settle_coin: str
    status: str
    contract_type: str
    launch_time: int | None
    delivery_time: int | None
    tick_size: float | None
    qty_step: float | None
    minimum_order_qty: float | None
    minimum_notional: float | None
    maximum_leverage: float | None
    snapshot_timestamp: str
    source_checksum: str
    eligible: bool
    exclusion_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _f(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def normalize_instrument(row: dict[str, Any], *, snapshot_timestamp: str) -> InstrumentSnapshot:
    symbol = str(row.get("symbol") or "")
    status = str(row.get("status") or "")
    contract_type = str(row.get("contractType") or "")
    quote = str(row.get("quoteCoin") or "")
    settle = str(row.get("settleCoin") or "")
    lot = row.get("lotSizeFilter") or {}
    price = row.get("priceFilter") or {}
    lev = row.get("leverageFilter") or {}
    tick = _f(price.get("tickSize"))
    qty_step = _f(lot.get("qtyStep"))
    min_qty = _f(lot.get("minOrderQty"))
    min_notional = _f(lot.get("minNotionalValue") or lot.get("minNotional"))
    max_lev = _f(lev.get("maxLeverage"))
    launch = int(row["launchTime"]) if str(row.get("launchTime") or "").isdigit() else None
    delivery = int(row["deliveryTime"]) if str(row.get("deliveryTime") or "").isdigit() else None

    eligible = True
    reason = None
    if contract_type != "LinearPerpetual":
        eligible, reason = False, "not_LinearPerpetual"
    elif quote != "USDT" or settle != "USDT":
        eligible, reason = False, "quote_or_settle_not_USDT"
    elif status != "Trading":
        eligible, reason = False, f"status_{status}"
    elif status in EXCLUDED_STATUS:
        eligible, reason = False, f"excluded_{status}"
    elif not symbol or tick is None or qty_step is None or min_qty is None:
        eligible, reason = False, "invalid_instrument_metadata"
    elif qty_step <= 0 or tick <= 0:
        eligible, reason = False, "insufficient_quantity_precision"

    body = {
        "symbol": symbol,
        "baseCoin": row.get("baseCoin"),
        "quoteCoin": quote,
        "settleCoin": settle,
        "status": status,
        "contractType": contract_type,
        "launchTime": launch,
        "deliveryTime": delivery,
        "tickSize": tick,
        "qtyStep": qty_step,
        "minOrderQty": min_qty,
        "minNotional": min_notional,
        "maxLeverage": max_lev,
    }
    return InstrumentSnapshot(
        symbol=symbol,
        base_coin=str(row.get("baseCoin") or ""),
        quote_coin=quote,
        settle_coin=settle,
        status=status,
        contract_type=contract_type,
        launch_time=launch,
        delivery_time=delivery,
        tick_size=tick,
        qty_step=qty_step,
        minimum_order_qty=min_qty,
        minimum_notional=min_notional,
        maximum_leverage=max_lev,
        snapshot_timestamp=snapshot_timestamp,
        source_checksum=_sha_obj(body),
        eligible=eligible,
        exclusion_reason=reason,
    )


def build_universe_snapshot(*, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    instruments = fetch_all_linear_instruments()
    tickers = {str(t.get("symbol")): t for t in fetch_all_linear_tickers()}
    snaps = [normalize_instrument(r, snapshot_timestamp=ts) for r in instruments]
    eligible = [s for s in snaps if s.eligible]
    payload = {
        "universe_id": UNIVERSE_ID,
        "fleet_architecture": False,
        "single_universe": True,
        "snapshot_timestamp": ts,
        "instrument_count_raw": len(snaps),
        "eligible_count": len(eligible),
        "pagination_complete": True,
        "instruments": [s.to_dict() for s in snaps],
        "ticker_symbols_present": len(tickers),
        "source": "bybit_public_mainnet_readonly",
        "trading_write": False,
        "mainnet_trading": False,
        "real_money": False,
    }
    payload["snapshot_checksum"] = _sha_obj(
        {"ts": ts, "symbols": sorted(s.symbol for s in eligible), "n": len(eligible)}
    )
    return payload


def point_in_time_membership(
    snapshot: dict[str, Any],
    *,
    as_of_ms: int,
) -> list[str]:
    """Reconstruct eligible symbols at as_of_ms using launch_time (survivorship-aware)."""
    out: list[str] = []
    for row in snapshot.get("instruments") or []:
        if not row.get("eligible"):
            continue
        launch = row.get("launch_time")
        if launch is not None and int(launch) > as_of_ms:
            continue
        delivery = row.get("delivery_time")
        if delivery is not None and int(delivery) > 0 and int(delivery) <= as_of_ms:
            continue
        out.append(str(row["symbol"]))
    return sorted(out)


def save_universe_snapshot(snapshot: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
