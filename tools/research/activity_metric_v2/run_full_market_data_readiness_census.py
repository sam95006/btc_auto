#!/usr/bin/env python3
"""FULL-MARKET DATA READINESS CENSUS — Bybit linear public (dynamic discovery).

Classifies each discovered market. No four-fleet language.
Writes: D:\\NEXUS_RUNTIME\\evidence_coordinator\\v18_2_9_full_market_data_readiness.json
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_PATH = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_9_full_market_data_readiness.json")
BASELINE_V18_2_8 = Path(
    r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_8_full_market_data_readiness.json"
)
BASE = "https://api.bybit.com"
TIMEOUT = 20.0

# Classification vocabulary (exact).
CLASSES = (
    "DISCOVERED",
    "SUPPORTED",
    "HISTORY_AVAILABLE",
    "LIVE_AVAILABLE",
    "DATA_VALID",
    "RESEARCH_READY",
    "SHADOW_READY",
    "BLOCKED",
)

# V18.2.8 baseline counts (for delta even if baseline file missing).
V18_2_8_BASELINE_COUNTS = {
    "DISCOVERED": 797,
    "SUPPORTED": 729,
    "HISTORY_AVAILABLE": 794,
    "LIVE_AVAILABLE": 797,
    "DATA_VALID": 797,
    "RESEARCH_READY": 754,
    "SHADOW_READY": 246,
    "BLOCKED": 68,
}


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    qs = urllib.parse.urlencode(params)
    url = f"{BASE}{path}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": "NEXUS-census-v18.2.9/readonly"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def discover_instruments() -> list[dict[str, Any]]:
    instruments: list[dict[str, Any]] = []
    cursor = ""
    while True:
        params: dict[str, Any] = {"category": "linear", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        payload = _get("/v5/market/instruments-info", params)
        if payload.get("retCode") != 0:
            raise RuntimeError(f"instruments-info failed: {payload.get('retMsg')}")
        result = payload.get("result") or {}
        batch = result.get("list") or []
        instruments.extend([r for r in batch if isinstance(r, dict)])
        cursor = str(result.get("nextPageCursor") or "")
        if not cursor or not batch:
            break
        time.sleep(0.05)
    return instruments


def fetch_tickers() -> dict[str, dict[str, Any]]:
    payload = _get("/v5/market/tickers", {"category": "linear"})
    if payload.get("retCode") != 0:
        raise RuntimeError(f"tickers failed: {payload.get('retMsg')}")
    rows = (payload.get("result") or {}).get("list") or []
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict) and row.get("symbol"):
            out[str(row["symbol"])] = row
    return out


def classify_row(
    inst: dict[str, Any],
    ticker: dict[str, Any] | None,
    *,
    as_of_ms: int,
) -> dict[str, Any]:
    symbol = str(inst.get("symbol") or "")
    status = str(inst.get("status") or "")
    quote = str(inst.get("quoteCoin") or "")
    flags: list[str] = ["DISCOVERED"]

    # SUPPORTED: linear USDT perpetual/trading contract with known status
    supported = (
        quote == "USDT"
        and status in {"Trading", "Settling", "Closed", "PreLaunch"}
        and bool(symbol)
    )
    if supported:
        flags.append("SUPPORTED")

    launch_ms = None
    if str(inst.get("launchTime") or "").isdigit():
        launch_ms = int(inst["launchTime"])

    # HISTORY_AVAILABLE: launch age >= 1 day (proxy; true bar history not pulled for all)
    history_available = False
    if launch_ms is not None and (as_of_ms - launch_ms) >= 86_400_000:
        history_available = True
        flags.append("HISTORY_AVAILABLE")

    # LIVE_AVAILABLE: ticker present with last price
    live_available = False
    last_price = _f((ticker or {}).get("lastPrice")) if ticker else None
    if ticker is not None and last_price is not None and last_price > 0 and status == "Trading":
        live_available = True
        flags.append("LIVE_AVAILABLE")

    turnover = _f((ticker or {}).get("turnover24h")) if ticker else None
    volume = _f((ticker or {}).get("volume24h")) if ticker else None
    bid = _f((ticker or {}).get("bid1Price")) if ticker else None
    ask = _f((ticker or {}).get("ask1Price")) if ticker else None
    funding = _f((ticker or {}).get("fundingRate")) if ticker else None
    oi = _f((ticker or {}).get("openInterestValue")) if ticker else None
    # trade_count_24h absent on Bybit public ticker — never invent from volume.
    trade_count_24h = None

    data_valid = False
    if live_available and turnover is not None and bid is not None and ask is not None:
        if ask >= bid > 0:
            data_valid = True
            flags.append("DATA_VALID")

    # RESEARCH_READY: data valid + history + funding/OI present (research-usable)
    research_ready = False
    if data_valid and history_available and funding is not None and oi is not None:
        research_ready = True
        flags.append("RESEARCH_READY")

    # SHADOW_READY: research ready + Trading + turnover floor (not eligibility Gate)
    # Note: trade_count_24h still missing → cannot claim Gate ELIGIBLE; SHADOW_READY
    # here means "shadow observation feed ready", not qualification pass.
    shadow_ready = False
    if research_ready and status == "Trading" and (turnover or 0) >= 1_000_000:
        shadow_ready = True
        flags.append("SHADOW_READY")

    blocked = False
    block_reasons: list[str] = []
    if status != "Trading":
        blocked = True
        block_reasons.append(f"status:{status or 'UNKNOWN'}")
    if quote != "USDT":
        blocked = True
        block_reasons.append("quote_not_usdt")
    if trade_count_24h is None:
        # Known exchange gap — activity Gate blocked until Activity Metric V2 wired.
        block_reasons.append("trade_count_24h_unavailable_bybit_public_ticker")
    if not live_available:
        blocked = True
        block_reasons.append("live_ticker_unavailable")
    if blocked:
        flags.append("BLOCKED")

    return {
        "symbol": symbol,
        "status": status,
        "quote_coin": quote,
        "contract_type": inst.get("contractType"),
        "launch_time_ms": launch_ms,
        "turnover_24h": turnover,
        "volume_24h": volume,
        "trade_count_24h": trade_count_24h,
        "funding_rate": funding,
        "open_interest_value": oi,
        "classes": flags,
        "supported": supported,
        "history_available": history_available,
        "live_available": live_available,
        "data_valid": data_valid,
        "research_ready": research_ready,
        "shadow_ready": shadow_ready,
        "blocked": blocked,
        "block_reasons": block_reasons,
    }


def main() -> int:
    as_of_ms = int(time.time() * 1000)
    instruments = discover_instruments()
    tickers = fetch_tickers()

    rows = [classify_row(inst, tickers.get(str(inst.get("symbol"))), as_of_ms=as_of_ms) for inst in instruments]

    counts = {c: 0 for c in CLASSES}
    for row in rows:
        for c in row["classes"]:
            if c in counts:
                counts[c] += 1

    block_reason_hist = Counter()
    for row in rows:
        for br in row["block_reasons"]:
            block_reason_hist[br] += 1

    # Sample of SHADOW_READY / BLOCKED for evidence compactness
    shadow_samples = [r["symbol"] for r in rows if r["shadow_ready"]][:25]
    blocked_samples = [r["symbol"] for r in rows if r["blocked"]][:25]

    # Every blocked asset needs machine-readable blocker(s).
    blocked_assets = [
        {
            "symbol": r["symbol"],
            "status": r["status"],
            "quote_coin": r["quote_coin"],
            "blockers": list(r["block_reasons"]),
            "classes": list(r["classes"]),
        }
        for r in rows
        if r["blocked"]
    ]

    baseline_counts = dict(V18_2_8_BASELINE_COUNTS)
    if BASELINE_V18_2_8.exists():
        try:
            prev = json.loads(BASELINE_V18_2_8.read_text(encoding="utf-8"))
            if isinstance(prev.get("counts"), dict):
                baseline_counts = {k: int(prev["counts"].get(k, 0)) for k in CLASSES}
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    deltas = {
        k: int(counts[k]) - int(baseline_counts.get(k, 0)) for k in CLASSES
    }

    report = {
        "schema": "v18_2_9_full_market_data_readiness_v1",
        "generated_at": _utc(),
        "as_of_ms": as_of_ms,
        "venue": "bybit",
        "category": "linear",
        "discovery": {
            "endpoint": "/v5/market/instruments-info",
            "ticker_endpoint": "/v5/market/tickers",
            "dynamic": True,
            "instrument_count": len(instruments),
            "ticker_count": len(tickers),
        },
        "counts": counts,
        "totals": {
            "discovered": counts["DISCOVERED"],
            "supported": counts["SUPPORTED"],
            "history_available": counts["HISTORY_AVAILABLE"],
            "live_available": counts["LIVE_AVAILABLE"],
            "data_valid": counts["DATA_VALID"],
            "research_ready": counts["RESEARCH_READY"],
            "shadow_ready": counts["SHADOW_READY"],
            "blocked": counts["BLOCKED"],
        },
        "baseline_v18_2_8_counts": baseline_counts,
        "deltas_vs_v18_2_8": deltas,
        "block_reason_histogram": dict(block_reason_hist.most_common()),
        "blocked_assets": blocked_assets,
        "activity_metric_note": {
            "trade_count_24h_on_public_ticker": False,
            "volume24h_not_substituted": True,
            "turnover24h_not_substituted": True,
            "official_activity_metric_v2_package": "backend/nexus_activity_metric_v2",
            "proxy_field": "trade_count_window",
            "proxy_version": "activity_metric_v2",
            "real_validation_evidence": (
                r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_9_activity_metric_real_validation.json"
            ),
            "wired_into_live_shadow": False,
        },
        "samples": {
            "shadow_ready": shadow_samples,
            "blocked": blocked_samples,
        },
        "four_fleet_language": False,
        "safety": {
            "exchange_write_attempt": 0,
            "demo_order": 0,
            "mainnet_order": 0,
        },
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUT_PATH), "counts": counts}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
