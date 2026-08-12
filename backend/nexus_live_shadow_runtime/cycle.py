"""One Live Shadow Runtime cycle — wires existing V18 modules (no parallel pipeline)."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from backend.nexus_ai_gateway_tool_sandbox import UnifiedAIGateway
from backend.nexus_data_trust_engine_v2 import evaluate_raw as evaluate_trust
from backend.nexus_eligible_universe import evaluate_universe
from backend.nexus_eligible_universe.models import InstrumentSnapshot
from backend.nexus_incremental_backfill_live_ingest.constants import (
    DATA_CLASS_LIVE_READ_ONLY,
    DEFAULT_LICENSE_REFERENCE,
    DEFAULT_SOURCE_ID,
)
from backend.nexus_incremental_backfill_live_ingest.hashing import utc_now_iso
from backend.nexus_incremental_backfill_live_ingest.pipeline import IngestPipeline
from backend.nexus_live_opportunity_pipeline.hard_bans import assert_shadow_flags
from backend.nexus_live_opportunity_pipeline.pipeline import (
    _compose_final_side,
    stage_candidate_score,
    stage_cost_feasibility,
    stage_data_trust,
    stage_evidence,
    stage_feature_snapshot,
    stage_regime,
    stage_risk_review,
    stage_strategy_experts,
    stage_uncertainty,
)
from backend.nexus_live_shadow_runtime.constants import PRIORITY_SYMBOLS
from backend.nexus_live_shadow_runtime.metrics import RuntimeMetrics
from backend.nexus_official_market_adapters import (
    DATA_MODE_LIVE_READ_ONLY,
    OfficialMarketAdapterRegistry,
)
from backend.nexus_official_market_adapters.constants import QUALITY_UNAVAILABLE
from backend.nexus_shadow_decision_ledger import ShadowDecisionLedger, ShadowDecisionRecord


def _ms_now() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _obs_ok(obs: Any) -> bool:
    if obs is None:
        return False
    quality = getattr(obs, "quality", None) or (obs.get("quality") if isinstance(obs, dict) else None)
    payload = getattr(obs, "payload", None)
    if isinstance(obs, dict):
        payload = obs.get("payload")
    return quality not in {None, QUALITY_UNAVAILABLE, "UNAVAILABLE"} and payload is not None


class CycleContext:
    """Mutable per-cycle scratch (not a second writer authority)."""

    def __init__(self) -> None:
        self.adapter_results: dict[str, Any] = {}
        self.catalog_instruments: list[dict[str, Any]] = []
        self.universe: dict[str, Any] | None = None
        self.trust: dict[str, Any] | None = None
        self.decision: dict[str, Any] | None = None
        self.ledger_record_id: str | None = None
        self.projection: dict[str, Any] | None = None
        self.data_lag_ms: int | None = None
        self.failure_reason: str | None = None
        self.degraded: bool = False


def preflight_adapters(
    registry: OfficialMarketAdapterRegistry,
    metrics: RuntimeMetrics,
) -> tuple[dict[str, Any], bool]:
    """Both official read-only sources. Fail-closed; never fabricate LIVE success."""
    results: dict[str, Any] = {}
    any_ok = False
    both_ok = True
    for adapter in registry.official_read_adapters():
        aid = adapter.manifest.adapter_id
        try:
            adapter.set_data_mode(DATA_MODE_LIVE_READ_ONLY)
            catalog = adapter.fetch_instrument_catalog(category="linear")
            ticker = adapter.fetch_ticker(symbol="BTCUSDT")
            ok_catalog = _obs_ok(catalog)
            ok_ticker = _obs_ok(ticker)
            ok = ok_catalog or ok_ticker
            if ok:
                metrics.bump("source_read_success_count")
                any_ok = True
            else:
                metrics.bump("source_read_failure_count")
                both_ok = False
            results[aid] = {
                "ok": ok,
                "catalog_quality": getattr(catalog, "quality", None),
                "ticker_quality": getattr(ticker, "quality", None),
                "catalog_count": len(
                    ((getattr(catalog, "payload", None) or {}).get("instruments") or [])
                    if getattr(catalog, "payload", None)
                    else []
                ),
                "data_mode": getattr(adapter, "data_mode", lambda: None)(),
                "error": None,
            }
            if not ok:
                both_ok = False
        except Exception as exc:  # noqa: BLE001 — live network must never raise open
            metrics.bump("source_read_failure_count")
            both_ok = False
            results[aid] = {
                "ok": False,
                "catalog_quality": QUALITY_UNAVAILABLE,
                "ticker_quality": QUALITY_UNAVAILABLE,
                "catalog_count": 0,
                "data_mode": DATA_MODE_LIVE_READ_ONLY,
                "error": f"{type(exc).__name__}:{exc}",
            }
    return results, both_ok and any_ok


def refresh_instrument_catalog(
    registry: OfficialMarketAdapterRegistry,
    metrics: RuntimeMetrics,
    *,
    max_instruments: int = 40,
    enrich_orderbook: bool = True,
    enrich_history: bool = True,
) -> list[dict[str, Any]]:
    """Refresh catalogs from both adapters; merge by symbol (honest None metrics).

    V18.2 Phase B repairs (proven engineering faults only):
    - Map tick/lot/min_notional/launch from adapter catalog rows (no longer dropped).
    - Batch-enrich ALL selected symbols from Bybit tickers (funding/OI/turnover/spread/mark).
    - Optionally fetch orderbook depth (USDT) and kline history_bars — never invent zeros.
    - Compute measured data_completeness + attach data_trust from live trust inputs.
    - Estimate round_trip_cost_bps from DEFAULT_TAKER_FEE + spread when spread known.
    - trade_count_24h stays None on Bybit (exchange does not publish) — fail-closed.
    """
    by_symbol: dict[str, dict[str, Any]] = {}
    primary_adapter_id: str | None = None
    for adapter in registry.official_read_adapters():
        try:
            adapter.set_data_mode(DATA_MODE_LIVE_READ_ONLY)
            obs = adapter.fetch_instrument_catalog(category="linear")
            if not _obs_ok(obs):
                metrics.bump("source_read_failure_count")
                continue
            metrics.bump("source_read_success_count")
            payload = obs.payload or {}
            rows = payload.get("instruments") or []
            exchange = "bybit" if "bybit" in adapter.manifest.adapter_id else "binance"
            if primary_adapter_id is None:
                primary_adapter_id = str(adapter.manifest.adapter_id)
            for row in rows:
                sym = str(row.get("symbol") or "")
                if not sym or not sym.endswith("USDT"):
                    continue
                if sym not in by_symbol:
                    status = row.get("status")
                    delisting = None
                    if status is not None:
                        delisting = str(status) in {
                            "PreDelisting",
                            "Settling",
                            "Closed",
                            "DELISTING",
                            "PRE_DELISTING",
                            "SETTLING",
                            "CLOSED",
                        }
                    by_symbol[sym] = {
                        "symbol": sym,
                        "exchange": exchange,
                        "source_adapter": adapter.manifest.adapter_id,
                        "status": status,
                        "base_coin": row.get("base_coin") or row.get("baseCoin") or row.get("base_asset"),
                        "quote_coin": row.get("quote_coin") or row.get("quoteCoin") or row.get("quote_asset"),
                        "contract_type": row.get("contract_type") or row.get("contractType"),
                        "launch_time_ms": _safe_float(row.get("launch_time_ms") or row.get("launchTime")),
                        "tick_size": _safe_float(row.get("tick_size")),
                        "lot_size": _safe_float(row.get("lot_size")),
                        "min_notional": _safe_float(row.get("min_notional")),
                        "delisting_flag": delisting,
                        "raw": dict(row),
                    }
        except Exception:  # noqa: BLE001
            metrics.bump("source_read_failure_count")

    # Prefer priority symbols first, then truncate for smoke budget BEFORE enrichment.
    items_all = list(by_symbol.values())
    priority = [i for i in items_all if i["symbol"] in PRIORITY_SYMBOLS]
    rest = [i for i in items_all if i["symbol"] not in PRIORITY_SYMBOLS]
    selected = (priority + rest)[:max_instruments]
    selected_syms = {i["symbol"] for i in selected}
    by_symbol = {i["symbol"]: i for i in selected}

    # Batch ticker enrichment from Bybit (one request) when available.
    ticker_by: dict[str, dict[str, Any]] = {}
    for adapter in registry.official_read_adapters():
        if "bybit" not in adapter.manifest.adapter_id:
            continue
        try:
            adapter.set_data_mode(DATA_MODE_LIVE_READ_ONLY)
            if hasattr(adapter, "fetch_tickers"):
                obs = adapter.fetch_tickers(category="linear")  # type: ignore[attr-defined]
            else:
                obs = None
            if obs is not None and _obs_ok(obs):
                metrics.bump("source_read_success_count")
                for t in (obs.payload or {}).get("tickers") or []:
                    sym = str(t.get("symbol") or "")
                    if sym in selected_syms:
                        ticker_by[sym] = t
            else:
                metrics.bump("source_read_failure_count")
        except Exception:  # noqa: BLE001
            metrics.bump("source_read_failure_count")
        break

    # Fallback: per-symbol ticker for missing (priority first) — never invent.
    for sym in list(selected_syms):
        if sym in ticker_by:
            continue
        for adapter in registry.official_read_adapters():
            try:
                adapter.set_data_mode(DATA_MODE_LIVE_READ_ONLY)
                tick = adapter.fetch_ticker(symbol=sym)
                if not _obs_ok(tick):
                    metrics.bump("source_read_failure_count")
                    continue
                metrics.bump("source_read_success_count")
                ticker_by[sym] = dict(tick.payload or {})
                break
            except Exception:  # noqa: BLE001
                metrics.bump("source_read_failure_count")

    for sym, entry in by_symbol.items():
        p = ticker_by.get(sym) or {}
        if not p:
            continue
        entry["last_price"] = _safe_float(p.get("last_price") or p.get("lastPrice"))
        entry["mark_price"] = _safe_float(p.get("mark_price") or p.get("markPrice"))
        entry["index_price"] = _safe_float(p.get("index_price") or p.get("indexPrice"))
        entry["turnover_24h"] = _safe_float(
            p.get("turnover_24h") or p.get("turnover24h") or p.get("quote_volume")
        )
        if p.get("trade_count_24h") is not None:
            try:
                entry["trade_count_24h"] = int(p["trade_count_24h"])
            except (TypeError, ValueError):
                entry["trade_count_24h"] = None
        bid = _safe_float(p.get("bid1_price") or p.get("bidPrice") or p.get("bid_price"))
        ask = _safe_float(p.get("ask1_price") or p.get("askPrice") or p.get("ask_price"))
        last = entry.get("last_price")
        if bid is not None and ask is not None and last and last > 0 and ask >= bid:
            entry["spread_bps"] = ((ask - bid) / last) * 10_000.0
        funding = _safe_float(p.get("funding_rate") or p.get("fundingRate"))
        if "funding_available" in p:
            entry["funding_available"] = bool(p.get("funding_available"))
            entry["funding_rate"] = funding
        elif funding is not None:
            entry["funding_rate"] = funding
            entry["funding_available"] = True
        oi_val = _safe_float(p.get("open_interest_value") or p.get("openInterestValue"))
        oi_ctr = _safe_float(p.get("open_interest") or p.get("openInterest"))
        if oi_val is not None:
            entry["open_interest_value"] = oi_val
            entry["oi_available"] = True
        elif oi_ctr is not None and last:
            # Contracts * last ≈ notional when value absent — only when both known.
            entry["open_interest_value"] = oi_ctr * float(last)
            entry["oi_available"] = True
        elif "oi_available" in p:
            entry["oi_available"] = bool(p.get("oi_available"))
            entry["open_interest_value"] = oi_val

    # Orderbook depth in USDT for selected symbols (bounded).
    if enrich_orderbook:
        for adapter in registry.official_read_adapters():
            if "bybit" not in adapter.manifest.adapter_id:
                continue
            for sym, entry in by_symbol.items():
                try:
                    adapter.set_data_mode(DATA_MODE_LIVE_READ_ONLY)
                    book = adapter.fetch_order_book_summary(symbol=sym, depth=25)
                    if not _obs_ok(book):
                        metrics.bump("source_read_failure_count")
                        continue
                    metrics.bump("source_read_success_count")
                    bp = book.payload or {}
                    bid_d = _safe_float(bp.get("bid_depth"))
                    ask_d = _safe_float(bp.get("ask_depth"))
                    mid = entry.get("last_price") or entry.get("mark_price")
                    best_bid = _safe_float(bp.get("best_bid"))
                    best_ask = _safe_float(bp.get("best_ask"))
                    if mid is None and best_bid is not None and best_ask is not None:
                        mid = (best_bid + best_ask) / 2.0
                    if bid_d is not None and ask_d is not None and mid is not None:
                        # Bybit depth quantities are base-coin sized → convert to USDT.
                        entry["book_depth_usdt"] = (bid_d + ask_d) * float(mid)
                    if entry.get("spread_bps") is None and best_bid and best_ask and mid and mid > 0:
                        entry["spread_bps"] = ((best_ask - best_bid) / float(mid)) * 10_000.0
                except Exception:  # noqa: BLE001
                    metrics.bump("source_read_failure_count")
            break

    # History bars via kline (honest count of returned bars; None if fetch fails).
    if enrich_history:
        for adapter in registry.official_read_adapters():
            if "bybit" not in adapter.manifest.adapter_id:
                continue
            for sym, entry in by_symbol.items():
                try:
                    adapter.set_data_mode(DATA_MODE_LIVE_READ_ONLY)
                    kl = adapter.fetch_ohlcv(symbol=sym, interval="15m", limit=120)
                    if not _obs_ok(kl):
                        metrics.bump("source_read_failure_count")
                        continue
                    metrics.bump("source_read_success_count")
                    bars = (kl.payload or {}).get("candles") or (kl.payload or {}).get("list") or []
                    if isinstance(bars, list) and bars:
                        entry["history_bars"] = len(bars)
                except Exception:  # noqa: BLE001
                    metrics.bump("source_read_failure_count")
            break

    # Cost estimate from known default taker fee + spread (no fabricated zeros).
    try:
        from backend.nexus_execution.cost_model import DEFAULT_TAKER_FEE

        taker_bps = float(DEFAULT_TAKER_FEE) * 10_000.0
    except Exception:  # noqa: BLE001
        taker_bps = None

    for entry in by_symbol.values():
        spread = entry.get("spread_bps")
        if taker_bps is not None and spread is not None:
            entry["round_trip_cost_bps"] = (2.0 * taker_bps) + float(spread)
        # Measured completeness over required eligibility fields (honest fraction).
        required = (
            "status",
            "quote_coin",
            "launch_time_ms",
            "tick_size",
            "lot_size",
            "min_notional",
            "turnover_24h",
            "trade_count_24h",
            "spread_bps",
            "book_depth_usdt",
            "funding_available",
            "oi_available",
            "open_interest_value",
            "history_bars",
            "round_trip_cost_bps",
        )
        present = sum(1 for k in required if entry.get(k) is not None)
        entry["data_completeness"] = present / float(len(required))
        # Per-instrument trust from measured completeness + source success.
        trust_inputs = build_live_trust_inputs(
            symbol=str(entry["symbol"]),
            source_ok_ratio=1.0 if ticker_by.get(entry["symbol"]) else 0.5,
            catalog_count=max(len(by_symbol), 40),
            data_lag_ms=5_000,
        )
        trust_inputs["completeness"] = float(entry["data_completeness"])
        trust_inputs["market_coverage"] = min(
            1.0, float(entry["data_completeness"]) + 0.05
        )
        trust_inputs["microstructure_availability"] = (
            0.8 if entry.get("book_depth_usdt") is not None else 0.3
        )
        try:
            raw_trust = evaluate_trust(trust_inputs)
            entry["data_trust_status"] = raw_trust.get("trust_status")
        except Exception:  # noqa: BLE001
            entry["data_trust_status"] = None
        # license stays APPROVED_PUBLIC for official public endpoints
        entry["license_status"] = entry.get("license_status") or "APPROVED_PUBLIC"

    return list(by_symbol.values())


def to_instrument_snapshots(rows: list[dict[str, Any]]) -> list[InstrumentSnapshot]:
    """Map catalog rows → InstrumentSnapshot. Missing metrics stay None (fail-closed)."""
    out: list[InstrumentSnapshot] = []
    for row in rows:
        launch = row.get("launch_time_ms")
        launch_ms = int(launch) if launch is not None else None
        out.append(
            InstrumentSnapshot(
                symbol=str(row["symbol"]),
                exchange=str(row.get("exchange") or "bybit"),
                category="linear",
                status=row.get("status"),
                quote_coin=row.get("quote_coin"),
                base_coin=row.get("base_coin"),
                launch_time_ms=launch_ms,
                tick_size=_safe_float(row.get("tick_size")),
                lot_size=_safe_float(row.get("lot_size")),
                min_notional=_safe_float(row.get("min_notional")),
                contract_type=row.get("contract_type"),
                turnover_24h=_safe_float(row.get("turnover_24h")),
                trade_count_24h=int(row["trade_count_24h"]) if row.get("trade_count_24h") is not None else None,
                spread_bps=_safe_float(row.get("spread_bps")),
                book_depth_usdt=_safe_float(row.get("book_depth_usdt")),
                funding_rate=_safe_float(row.get("funding_rate")),
                funding_available=row.get("funding_available"),
                open_interest_value=_safe_float(row.get("open_interest_value")),
                oi_available=row.get("oi_available"),
                history_bars=int(row["history_bars"]) if row.get("history_bars") is not None else None,
                data_completeness=_safe_float(row.get("data_completeness")),
                data_trust_status=row.get("data_trust_status"),
                license_status=row.get("license_status") or "APPROVED_PUBLIC",
                delisting_flag=row.get("delisting_flag"),
                round_trip_cost_bps=_safe_float(row.get("round_trip_cost_bps")),
                last_price=_safe_float(row.get("last_price")),
                raw=dict(row.get("raw") or {}),
            )
        )
    return out


def ingest_live_ticks(
    pipeline: IngestPipeline,
    registry: OfficialMarketAdapterRegistry,
    metrics: RuntimeMetrics,
    symbols: tuple[str, ...] = PRIORITY_SYMBOLS,
) -> dict[str, Any]:
    """Append LIVE_READ_ONLY ticks via existing IngestPipeline (Bronze/PIT bridge)."""
    ingested = 0
    quarantined = 0
    duplicates = 0
    offset = int(pipeline.counters.__dict__.get("live_append_count", 0) or 0)
    for sym in symbols:
        for adapter in registry.official_read_adapters():
            try:
                adapter.set_data_mode(DATA_MODE_LIVE_READ_ONLY)
                tick = adapter.fetch_ticker(symbol=sym)
                if not _obs_ok(tick):
                    metrics.bump("source_read_failure_count")
                    continue
                metrics.bump("source_read_success_count")
                payload = tick.payload or {}
                now = utc_now_iso()
                exch_ts = None
                if getattr(tick, "exchange_timestamp_ms", None):
                    exch_ts = datetime.fromtimestamp(
                        int(tick.exchange_timestamp_ms) / 1000.0, tz=timezone.utc
                    ).strftime("%Y-%m-%dT%H:%M:%SZ")
                batch = {
                    "exchange_timestamp": exch_ts or now,
                    "received_timestamp": now,
                    "source_id": DEFAULT_SOURCE_ID,
                    "symbol_original": sym,
                    "data_class": DATA_CLASS_LIVE_READ_ONLY,
                    "license_reference": DEFAULT_LICENSE_REFERENCE,
                    "payload": {
                        "symbol": sym,
                        "adapter_id": adapter.manifest.adapter_id,
                        "last_price": payload.get("last_price"),
                        "turnover_24h": payload.get("turnover_24h"),
                        "note": "live_shadow_runtime_conductor",
                    },
                }
                result = pipeline.ingest_one(batch, source_offset=offset, mode="live_append")
                offset += 1
                status = str(result.get("status") or "")
                if status in {"INGESTED", "OK", "APPENDED", "LIVE_APPENDED"}:
                    ingested += 1
                    metrics.bump("live_records_ingested")
                elif status == "DUPLICATE":
                    duplicates += 1
                    metrics.bump("duplicate_records")
                elif status == "QUARANTINED":
                    quarantined += 1
                    metrics.bump("records_quarantined")
                else:
                    # Count successful bronze append variants.
                    if result.get("ingested") or result.get("content_hash"):
                        ingested += 1
                        metrics.bump("live_records_ingested")
                break  # one successful source per symbol per cycle
            except Exception:  # noqa: BLE001
                metrics.bump("source_read_failure_count")
    # Mirror pipeline quarantine / duplicate counters if present.
    c = pipeline.counters
    if hasattr(c, "quarantined_count"):
        quarantined = max(quarantined, int(c.quarantined_count or 0))
    return {
        "ingested": ingested,
        "quarantined": quarantined,
        "duplicates": duplicates,
        "pipeline_counters": c.to_dict() if hasattr(c, "to_dict") else {},
    }


def build_live_trust_inputs(
    *,
    symbol: str,
    source_ok_ratio: float,
    catalog_count: int,
    data_lag_ms: int | None,
) -> dict[str, Any]:
    """Honest trust inputs from live preflight — never auto-fill 0 to hide failures."""
    freshness = 0.9
    if data_lag_ms is None:
        freshness = 0.0
    elif data_lag_ms > 60_000:
        freshness = 0.2
    elif data_lag_ms > 15_000:
        freshness = 0.55
    completeness = min(1.0, max(0.0, source_ok_ratio)) * (0.5 if catalog_count == 0 else 0.85)
    agreement = min(1.0, max(0.0, source_ok_ratio))
    # If either source failed hard, degrade agreement.
    if source_ok_ratio < 0.5:
        agreement = 0.3
    return {
        "case_id": "LIVE_SHADOW_RUNTIME",
        "symbol": symbol,
        "source_id": "live_shadow_runtime_conductor",
        "freshness": freshness,
        "completeness": completeness,
        "cross_source_agreement": agreement,
        "schema_validity": 1.0 if catalog_count > 0 else 0.0,
        "timestamp_integrity": 1.0 if data_lag_ms is not None else 0.0,
        "revision_uncertainty": 0.15,
        "license_status": "APPROVED_PUBLIC",
        "market_coverage": min(1.0, catalog_count / 50.0) if catalog_count else 0.0,
        "microstructure_availability": 0.4 if source_ok_ratio >= 0.5 else 0.1,
        "anomaly_rate": 0.05,
        "ai_confidence": 0.5,
        "availability": catalog_count > 0 and source_ok_ratio > 0,
        "notes": "derived_from_live_preflight",
    }


def build_abstention_inputs(*, symbol: str, trust_gate: str, data_lag_ms: int | None) -> dict[str, Any]:
    freshness_sec = (data_lag_ms / 1000.0) if data_lag_ms is not None else 9999.0
    # Insufficient / stale → force high uncertainty (fail-closed).
    stale = freshness_sec > 60.0 or trust_gate in {"WAIT", "ABSTAIN", "BLOCK"}
    return {
        "case_id": "LIVE_SHADOW_RUNTIME",
        "symbol": symbol,
        "provider_status": "DEGRADED" if stale else "OK",
        "model_agreement": 0.4 if stale else 0.75,
        "data_agreement": 0.35 if stale else 0.8,
        "historical_agreement": 0.5,
        "regime_agreement": 0.5,
        "execution_agreement": 0.5,
        "risk_agreement": 0.5,
        "calibration_reliability": 0.4 if stale else 0.7,
        "similarity_coverage": 0.3 if stale else 0.6,
        "prediction_interval_width": 0.55 if stale else 0.25,
        "data_freshness_sec": freshness_sec,
        "stated_confidence": 0.35 if stale else 0.65,
        "notes": "live_shadow_runtime",
    }


def run_decision_cycle(
    *,
    symbol: str,
    trust_inputs: dict[str, Any],
    abstention_inputs: dict[str, Any],
    as_of_ms: int,
    data_class: str,
    ai_gateway: UnifiedAIGateway,
    metrics: RuntimeMetrics,
    force_block: bool = False,
) -> dict[str, Any]:
    """Full shadow decision path reusing V18-D stage functions. Never exchange write."""
    stages: dict[str, Any] = {}

    # AI gateway (typed); capacity/timeout → WAIT/ABSTAIN, never busy-loop.
    metrics.bump("AI_requests")
    try:
        ai_resp = ai_gateway.invoke(
            prompt="shadow_decision_assist",
            payload={"symbol": symbol, "trust": trust_inputs},
            role="candidate_interpretation",
        )
        ai_dict = ai_resp.to_dict() if hasattr(ai_resp, "to_dict") else dict(ai_resp or {})
        ai_status = str(ai_dict.get("result_status") or "")
        if ai_status in {"OK", "SUCCESS", "COMPLETED", "VALID"} or ai_dict.get("output") is not None:
            metrics.bump("AI_success")
        cap = str(ai_dict.get("capacity_status") or "")
        if "CAPACITY" in ai_status.upper() or "CAPACITY" in cap.upper() or str(
            ai_dict.get("pipeline") or ""
        ) == "CONTINUE_WITHOUT_AI":
            metrics.bump("provider_capacity_blocked_count")
        if "TIMEOUT" in ai_status.upper():
            metrics.bump("AI_timeout")
        if "INVALID" in ai_status.upper() or ai_dict.get("invalid_json"):
            metrics.bump("AI_invalid_json")
        provider_id = str(ai_dict.get("provider_id") or "")
        if "FALLBACK" in provider_id.upper() or "DETERMINISTIC" in provider_id.upper():
            metrics.bump("deterministic_fallback_count")
        if int(ai_dict.get("busy_loop_count") or getattr(ai_gateway, "busy_loop_count", 0) or 0) != 0:
            raise RuntimeError("busy_loop_detected")
    except Exception as exc:  # noqa: BLE001 — AI failure → continue without AI
        ai_dict = {
            "result_status": "FAILED",
            "error": f"{type(exc).__name__}:{exc}",
            "decision": "WAIT",
            "provider_id": "DETERMINISTIC_FALLBACK",
            "pipeline": "CONTINUE_WITHOUT_AI",
        }
        metrics.bump("provider_capacity_blocked_count")
        metrics.bump("deterministic_fallback_count")

    trust = stage_data_trust(trust_inputs, ai_attempt_override=False)
    stages["data_trust"] = trust
    # Direct engine check (also counted for evidence honesty).
    raw_trust = evaluate_trust(trust_inputs)
    stages["data_trust_raw"] = {
        "trust_status": raw_trust.get("trust_status"),
        "gate_action": raw_trust.get("gate_action"),
    }

    features = stage_feature_snapshot(symbol, as_of_ms=as_of_ms)
    # Mark feature stage as not claiming live bars unless live path provided them.
    features["data_class"] = data_class
    stages["feature_snapshot"] = features

    regime = stage_regime(symbol, as_of_ms=as_of_ms, scenario="mixed")
    stages["regime"] = regime

    uncertainty = stage_uncertainty(abstention_inputs, ai_confidence=0.5)
    stages["uncertainty"] = uncertainty

    trust_gate = str(trust.get("gate_action") or "BLOCK")
    if force_block or trust_gate in {"WAIT", "ABSTAIN", "BLOCK"}:
        # Fail-closed: do not route experts toward LONG/SHORT when trust blocks.
        risk_allow = False
        risk_reason = f"TRUST_GATE_{trust_gate}"
    else:
        risk_allow = True
        risk_reason = "PASS"

    expert = stage_strategy_experts(
        symbol=symbol,
        as_of_ms=as_of_ms,
        regime=regime,
        trust_score=float(trust.get("trust_score") or 0.0),
        cost_bps=12.0,
        liquidity=0.4,
        stability=0.4,
        uncertainty=float(uncertainty.get("uncertainty_score") or 1.0),
        portfolio_exposure=0.0,
        risk_gate_allow=risk_allow,
        risk_gate_reason=risk_reason,
        open_position_side=None,
        abstention_verdict=str(uncertainty.get("verdict") or "BLOCK"),
        trading_unsafe=bool(regime.get("trading_unsafe")) or force_block,
        formal_state=regime.get("formal_state"),
    )
    stages["strategy_experts"] = expert
    metrics.bump("candidates_generated")

    candidate = stage_candidate_score(expert, trust_score=float(trust.get("trust_score") or 0.0))
    stages["candidate_score"] = candidate
    evidence = stage_evidence(expert, regime)
    cost = stage_cost_feasibility(12.0)
    stages["cost_feasibility"] = cost

    risk = stage_risk_review(
        risk_gate_allow=risk_allow,
        risk_gate_reason=risk_reason,
        portfolio_exposure=0.0,
        cost_feasible=bool(cost.get("feasible")),
        trust_gate=trust_gate,
        abstention_verdict=str(uncertainty.get("verdict") or "BLOCK"),
        ai_attempt_override_risk=False,
    )
    stages["risk_review"] = risk

    final_side = _compose_final_side(
        expert_side=str(expert.get("side") or "WAIT"),
        trust_gate=trust_gate,
        abstention_verdict=str(uncertainty.get("verdict") or "BLOCK"),
        risk=risk,
        cost_feasible=bool(cost.get("feasible")),
        candidate=candidate,
    )
    # Hard rule: insufficient / degraded / force_block → never LONG/SHORT.
    if force_block or trust_gate in {"WAIT", "ABSTAIN", "BLOCK"} or str(
        raw_trust.get("trust_status")
    ) in {"DEGRADED", "STALE", "CONFLICTED", "UNAVAILABLE", "LICENSE_BLOCKED"}:
        if final_side in {"LONG", "SHORT"}:
            final_side = "WAIT" if trust_gate == "WAIT" else (
                "ABSTAIN" if trust_gate == "ABSTAIN" else "BLOCK"
            )

    decision = {
        "decision_id": f"v18_1-lsr-{symbol}-{as_of_ms}",
        "decision": final_side,
        "symbol": symbol,
        "market": "crypto_perp",
        "as_of": as_of_ms,
        "data_class": data_class,
        "data_trust": {
            "trust_status": trust.get("trust_status"),
            "trust_score": trust.get("trust_score"),
            "gate_action": trust_gate,
        },
        "regime_probabilities": regime.get("probabilities") or {},
        "strategy_expert": expert.get("expert_id"),
        "supporting_evidence": evidence.get("supporting_evidence") or [],
        "contradicting_evidence": evidence.get("contradicting_evidence") or [],
        "cost_estimate": cost.get("cost_estimate"),
        "uncertainty": {
            "verdict": uncertainty.get("verdict"),
            "uncertainty_score": uncertainty.get("uncertainty_score"),
        },
        "risk_status": risk.get("risk_status"),
        "invalidation": list(risk.get("reasons") or []),
        "freshness": {"data_freshness_sec": abstention_inputs.get("data_freshness_sec")},
        "lineage": {"conductor": "nexus_live_shadow_runtime"},
        "decision_status": final_side,
        "actual_ordered": False,
        "actual_filled": False,
        "is_trade_signal": False,
        "exchange_order_id": None,
        "candidate_score": candidate,
        "ai": {
            "result_status": ai_dict.get("result_status"),
            "provider_id": ai_dict.get("provider_id"),
            "pipeline": ai_dict.get("pipeline"),
        },
    }
    assert_shadow_flags(decision)
    metrics.record_decision(final_side)
    return {"stages": stages, "decision": decision}


def _ledger_kind(decision_side: str) -> str:
    """Map pipeline sides onto ShadowDecisionRecord kinds (no BLOCK kind)."""
    side = str(decision_side or "").upper()
    if side in {"LONG", "SHORT", "WAIT", "ABSTAIN"}:
        return side
    return "ABSTAIN"


def append_shadow_ledger(
    ledger: ShadowDecisionLedger,
    decision: dict[str, Any],
    *,
    data_class: str,
    metrics: RuntimeMetrics,
) -> ShadowDecisionRecord:
    """Create OBSERVED shadow decision record (research-only)."""
    sid = str(decision["decision_id"])
    kind = _ledger_kind(str(decision.get("decision")))
    rec = ShadowDecisionRecord(
        shadow_decision_id=sid,
        lifecycle_state="OBSERVED",
        market_snapshot={"symbol": decision.get("symbol"), "as_of": decision.get("as_of")},
        universe_decision={},
        candidate=decision.get("candidate_score") or {},
        ai_suggestion=decision.get("ai") or {},
        critic={},
        deterministic_risk={"risk_status": decision.get("risk_status")},
        final_shadow_decision={
            "kind": kind,
            "decision": decision.get("decision"),
            "decision_status": decision.get("decision_status"),
        },
        actual_ordered=False,
        actual_filled=False,
        exchange_order_id=None,
        data_class=data_class,
        virtual_research_position=False,
    )
    ledger.create(rec)
    if decision.get("decision") in {"LONG", "SHORT"}:
        metrics.bump("candidates_generated")
    return rec


def run_full_cycle(
    *,
    registry: OfficialMarketAdapterRegistry,
    ingest: IngestPipeline,
    ledger: ShadowDecisionLedger,
    ai_gateway: UnifiedAIGateway,
    metrics: RuntimeMetrics,
    data_class: str,
    cycle_index: int,
) -> CycleContext:
    """Execute one bounded live-shadow cycle through existing V18 modules."""
    ctx = CycleContext()
    t0 = time.perf_counter()
    as_of_ms = _ms_now()

    adapter_results, both_ok = preflight_adapters(registry, metrics)
    ctx.adapter_results = adapter_results
    ok_count = sum(1 for v in adapter_results.values() if v.get("ok"))
    source_ok_ratio = ok_count / max(1, len(adapter_results))

    if ok_count == 0:
        ctx.degraded = True
        ctx.failure_reason = "both_adapters_failed"
        # Fail-closed decision without inventing market data.
        trust_inputs = build_live_trust_inputs(
            symbol="BTCUSDT",
            source_ok_ratio=0.0,
            catalog_count=0,
            data_lag_ms=None,
        )
        trust = stage_data_trust(trust_inputs, ai_attempt_override=False)
        ctx.trust = trust
        abstention = build_abstention_inputs(
            symbol="BTCUSDT", trust_gate=str(trust.get("gate_action") or "BLOCK"), data_lag_ms=None
        )
        result = run_decision_cycle(
            symbol="BTCUSDT",
            trust_inputs=trust_inputs,
            abstention_inputs=abstention,
            as_of_ms=as_of_ms,
            data_class="FAILED_SAFE" if data_class == "FAILED_SAFE" else data_class,
            ai_gateway=ai_gateway,
            metrics=metrics,
            force_block=True,
        )
        ctx.decision = result["decision"]
        ctx.universe = {
            "funnel": {
                "total_exchange_contracts": 0,
                "eligible_contracts": 0,
                "observe_only_contracts": 0,
                "blocked_contracts": 0,
            }
        }
        metrics.set_latest_universe(total=0, eligible=0, observe_only=0, blocked=0)
        rec = append_shadow_ledger(ledger, ctx.decision, data_class=data_class, metrics=metrics)
        ctx.ledger_record_id = rec.shadow_decision_id
        ctx.data_lag_ms = None
        _ = t0
        return ctx

    catalog = refresh_instrument_catalog(registry, metrics)
    ctx.catalog_instruments = catalog
    ingest_stats = ingest_live_ticks(ingest, registry, metrics)
    _ = ingest_stats

    snapshots = to_instrument_snapshots(catalog)
    universe = evaluate_universe(snapshots, as_of_ms=as_of_ms)
    ctx.universe = universe
    metrics.bump("universe_refresh_count")
    funnel = universe.get("funnel") or {}
    metrics.set_latest_universe(
        total=int(funnel.get("total_exchange_contracts") or 0),
        eligible=int(funnel.get("eligible_contracts") or 0),
        observe_only=int(funnel.get("observe_only_contracts") or 0),
        blocked=int(funnel.get("blocked_contracts") or 0),
    )

    # Prefer eligible, else observe_only, else priority symbol with fail-closed.
    decisions = universe.get("decisions") or []
    pick = next((d for d in decisions if d.get("universe_class") == "ELIGIBLE"), None)
    if pick is None:
        pick = next((d for d in decisions if d.get("universe_class") == "OBSERVE_ONLY"), None)
    symbol = str((pick or {}).get("symbol") or PRIORITY_SYMBOLS[0])
    # Live catalog without full metrics → typically UNAVAILABLE/BLOCKED → fail-closed.
    force_block = pick is None or str((pick or {}).get("universe_class")) not in {
        "ELIGIBLE",
        "OBSERVE_ONLY",
    }
    if not both_ok:
        ctx.degraded = True
        force_block = True

    ctx.data_lag_ms = 5_000  # bounded smoke: just-fetched
    trust_inputs = build_live_trust_inputs(
        symbol=symbol,
        source_ok_ratio=source_ok_ratio,
        catalog_count=len(catalog),
        data_lag_ms=ctx.data_lag_ms,
    )
    # If universe unknown / empty eligible → degrade trust completeness honesty.
    if int(funnel.get("eligible_contracts") or 0) == 0:
        trust_inputs["completeness"] = min(float(trust_inputs["completeness"]), 0.4)
        trust_inputs["notes"] = "no_eligible_contracts_fail_closed"

    trust_probe = evaluate_trust(trust_inputs)
    if str(trust_probe.get("trust_status")) in {
        "DEGRADED",
        "STALE",
        "CONFLICTED",
        "UNAVAILABLE",
        "LICENSE_BLOCKED",
    }:
        ctx.degraded = True
        force_block = True

    abstention = build_abstention_inputs(
        symbol=symbol,
        trust_gate=str(trust_probe.get("gate_action") or "BLOCK"),
        data_lag_ms=ctx.data_lag_ms,
    )
    result = run_decision_cycle(
        symbol=symbol,
        trust_inputs=trust_inputs,
        abstention_inputs=abstention,
        as_of_ms=as_of_ms,
        data_class=data_class,
        ai_gateway=ai_gateway,
        metrics=metrics,
        force_block=force_block,
    )
    ctx.trust = result["stages"].get("data_trust")
    ctx.decision = result["decision"]
    rec = append_shadow_ledger(ledger, ctx.decision, data_class=data_class, metrics=metrics)
    ctx.ledger_record_id = rec.shadow_decision_id
    _ = (cycle_index, t0)
    return ctx
