"""Shadow path outcome evaluation — OHLC integrity, no close-only MFE/MAE.

Measurement rules (authoritative):
- Prefer finer trade/mark path if available; otherwise 1m OHLC with limitations labeled.
- LONG MFE = max favorable HIGH; MAE = max adverse LOW.
- SHORT MFE = max favorable LOW; MAE = max adverse HIGH.
- Entry candle mid-bar HIGH/LOW excluded (ENTRY_CANDLE_PARTIAL).
- Same candle target+stop → first_touch=AMBIGUOUS (never arbitrary order).
- Decision snapshots never rewritten with future data.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.demo_write_client import DemoWriteClient, _float
from backend.nexus_research_ai_autonomy.shadow_signal_v1 import shadow_dir

SHADOW_HORIZONS_SEC = (60, 180, 300, 900, 1800)

RESEARCH_CONFIGS = (
    {"name": "champion_v30", "stop_pct": 0.40, "target_pct": 0.55, "trail_pct": 0.30},
    {"name": "wider_stop", "stop_pct": 0.60, "target_pct": 0.55, "trail_pct": 0.30},
    {"name": "tighter_target", "stop_pct": 0.40, "target_pct": 0.35, "trail_pct": 0.25},
    {"name": "wider_both", "stop_pct": 0.70, "target_pct": 0.80, "trail_pct": 0.40},
    {"name": "narrow_scalp", "stop_pct": 0.25, "target_pct": 0.30, "trail_pct": 0.20},
)

# Conservative documented fallback — do NOT lower to improve expectancy.
FALLBACK_FEE_RATE_RT = 0.0011
FALLBACK_FEE_MODEL_SOURCE = "conservative_fallback_roundtrip_0.0011"
PATH_SCHEMA = "v30_shadow_path_record_v1"
CANDLE_MS = 60_000


def path_records_path(campaign_root: Path) -> Path:
    return shadow_dir(campaign_root) / "path_records.jsonl"


def _parse_kline_row(r: Any) -> dict[str, float | int] | None:
    """Bybit linear kline: [start, open, high, low, close, volume, turnover]."""
    if isinstance(r, (list, tuple)) and len(r) >= 5:
        return {
            "ts_ms": int(float(r[0])),
            "open": float(r[1]),
            "high": float(r[2]),
            "low": float(r[3]),
            "close": float(r[4]),
        }
    if isinstance(r, dict):
        ts = int(_float(r.get("startTime") or r.get("start") or 0))
        o = _float(r.get("open") or r.get("o"))
        h = _float(r.get("high") or r.get("h"))
        low = _float(r.get("low") or r.get("l"))
        c = _float(r.get("close") or r.get("c"))
        if ts and o > 0 and h > 0 and low > 0 and c > 0:
            return {"ts_ms": ts, "open": o, "high": h, "low": low, "close": c}
    return None


def fetch_ohlc_path(
    client: DemoWriteClient,
    *,
    symbol: str,
    entry_ts_ms: int,
    horizon_sec: int,
) -> dict[str, Any]:
    """Fetch 1m OHLC path after entry with measurement quality metadata."""
    end_ms = int(entry_ts_ms) + int(horizon_sec) * 1000
    bars: list[dict[str, Any]] = []
    path_source = "bybit_public_1m_ohlc"
    resolution_label = "1m_ohlc"
    resolution_ms = CANDLE_MS
    warnings: list[str] = ["REDUCED_TEMPORAL_RESOLUTION"]

    try:
        raw = client.public_get(
            "/v5/market/kline",
            {"category": "linear", "symbol": symbol, "interval": "1", "limit": "200"},
        )
        rows = (raw.get("result") or {}).get("list") or []
    except Exception:  # noqa: BLE001
        rows = []

    entry_candle_start = (int(entry_ts_ms) // CANDLE_MS) * CANDLE_MS
    for r in rows:
        parsed = _parse_kline_row(r)
        if not parsed:
            continue
        ts = int(parsed["ts_ms"])
        candle_end = ts + CANDLE_MS
        # Keep candles that overlap [entry_ts, end_ms]
        if candle_end <= entry_ts_ms:
            continue
        if ts > end_ms:
            continue
        partial = False
        # Mid-candle entry: HIGH/LOW may include pre-signal movement
        if ts == entry_candle_start and entry_ts_ms > ts:
            partial = True
            warnings.append("ENTRY_CANDLE_PARTIAL")
        bars.append(
            {
                "ts_ms": ts,
                "open": float(parsed["open"]),
                "high": float(parsed["high"]),
                "low": float(parsed["low"]),
                "close": float(parsed["close"]),
                "entry_candle_partial": partial,
            }
        )
    bars.sort(key=lambda b: int(b["ts_ms"]))

    coverage_start = bars[0]["ts_ms"] if bars else None
    coverage_end = (bars[-1]["ts_ms"] + CANDLE_MS) if bars else None
    data_complete = bool(bars) and coverage_end is not None and int(coverage_end) >= end_ms - CANDLE_MS
    quality = "OHLC_1M_LIMITED"
    if not bars:
        quality = "NO_PATH_DATA"
    elif "ENTRY_CANDLE_PARTIAL" in warnings:
        quality = "OHLC_1M_ENTRY_PARTIAL"

    return {
        "path_source": path_source,
        "resolution_ms": resolution_ms,
        "resolution_label": resolution_label,
        "coverage_start": coverage_start,
        "coverage_end": coverage_end,
        "point_count": len(bars),
        "data_complete": data_complete,
        "measurement_quality": quality,
        "data_quality_warnings": sorted(set(warnings)) if bars else ["NO_PATH_DATA"],
        "bars": bars,
    }


def _move_pct(entry_price: float, price: float, side: str) -> float:
    if entry_price <= 0:
        return 0.0
    if side == "LONG":
        return (price - entry_price) / entry_price * 100.0
    return (entry_price - price) / entry_price * 100.0


def evaluate_ohlc_path(
    *,
    entry_price: float,
    direction: str,
    bars: list[dict[str, Any]],
    stop_pct: float,
    target_pct: float,
    notional: float = 350.0,
    fee_rate_rt: float = FALLBACK_FEE_RATE_RT,
    fee_model_source: str = FALLBACK_FEE_MODEL_SOURCE,
    observed_fee_rate: float | None = None,
    spread_cost: float = 0.0,
    slippage_cost: float = 0.0,
    funding_cost: float = 0.0,
) -> dict[str, Any]:
    """Authoritative MFE/MAE from OHLC highs/lows + ambiguous first-touch."""
    empty = {
        "MFE": None,
        "MAE": None,
        "mfe_pct": None,
        "mae_pct": None,
        "target_before_stop": None,
        "stop_before_target": None,
        "first_touch": None,
        "ambiguous_first_touch": False,
        "post_cost_hypothetical": None,
        "path_points": 0,
        "close_only_MFE": False,
    }
    if entry_price <= 0 or not bars:
        return empty

    side = str(direction or "LONG").upper()
    mfe_pct = 0.0
    mae_pct = 0.0
    first_touch: str | None = None  # TARGET | STOP | AMBIGUOUS | None
    exit_pct = 0.0
    used_bars = 0

    for bar in bars:
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        partial = bool(bar.get("entry_candle_partial"))

        if partial:
            # Exclude pre-entry-ambiguous HIGH/LOW excursions from entry candle.
            # Close is at candle end (after entry) — usable for mark-to-market only,
            # not for expanding MFE/MAE via intrabar extremes.
            used_bars += 1
            continue

        used_bars += 1
        if side == "LONG":
            fav = _move_pct(entry_price, high, side)
            adv = _move_pct(entry_price, low, side)
            hit_target = fav >= target_pct
            hit_stop = adv <= -stop_pct
        else:
            fav = _move_pct(entry_price, low, side)
            adv = _move_pct(entry_price, high, side)
            hit_target = fav >= target_pct
            hit_stop = adv <= -stop_pct

        mfe_pct = max(mfe_pct, fav)
        mae_pct = min(mae_pct, adv)

        if first_touch is None:
            if hit_target and hit_stop:
                first_touch = "AMBIGUOUS"
                exit_pct = 0.0  # do not pick either side
            elif hit_target:
                first_touch = "TARGET"
                exit_pct = target_pct
            elif hit_stop:
                first_touch = "STOP"
                exit_pct = -stop_pct

    if first_touch is None:
        last_close = float(bars[-1]["close"])
        exit_pct = _move_pct(entry_price, last_close, side)
    elif first_touch == "AMBIGUOUS":
        # Conservative: neither claim; mark-to-market at last close for PnL research
        last_close = float(bars[-1]["close"])
        exit_pct = _move_pct(entry_price, last_close, side)

    rate = float(observed_fee_rate) if observed_fee_rate is not None else float(fee_rate_rt)
    fee_cost = notional * rate
    total_cost = fee_cost + float(spread_cost) + float(slippage_cost) + float(funding_cost)
    gross = notional * (exit_pct / 100.0)
    net = gross - total_cost

    return {
        "MFE": round(notional * (mfe_pct / 100.0), 6),
        "MAE": round(notional * (mae_pct / 100.0), 6),
        "mfe_pct": round(mfe_pct, 6),
        "mae_pct": round(mae_pct, 6),
        "target_before_stop": True if first_touch == "TARGET" else (False if first_touch == "STOP" else None),
        "stop_before_target": True if first_touch == "STOP" else (False if first_touch == "TARGET" else None),
        "first_touch": first_touch,
        "ambiguous_first_touch": first_touch == "AMBIGUOUS",
        "exit_pct": round(exit_pct, 6),
        "gross_hypothetical": round(gross, 6),
        "estimated_cost": round(total_cost, 6),
        "post_cost_hypothetical": round(net, 6),
        "path_points": used_bars,
        "stop_pct": stop_pct,
        "target_pct": target_pct,
        "close_only_MFE": False,
        "fee_model_source": fee_model_source if observed_fee_rate is None else "observed_exchange_fee_rate",
        "observed_fee_rate": observed_fee_rate,
        "fallback_fee_rate": fee_rate_rt if observed_fee_rate is None else None,
        "spread_cost": round(float(spread_cost), 6),
        "slippage_cost": round(float(slippage_cost), 6),
        "funding_cost": round(float(funding_cost), 6),
        "total_estimated_cost": round(total_cost, 6),
    }


# Backward-compatible alias used by older tests / callers
def evaluate_path_mfe_mae(
    *,
    entry_price: float,
    direction: str,
    path: list[Any] | None = None,
    bars: list[dict[str, Any]] | None = None,
    stop_pct: float,
    target_pct: float,
    notional: float = 350.0,
    fee_rate_rt: float = FALLBACK_FEE_RATE_RT,
    **kwargs: Any,
) -> dict[str, Any]:
    """Accept OHLC bars or legacy close tuples (legacy converted with quality warning)."""
    if bars is None and path:
        # Legacy close-only tuples → synthesize degenerate bars (NOT authoritative).
        # Prefer callers migrate to bars=. Kept only for transition.
        synth: list[dict[str, Any]] = []
        for item in path:
            if isinstance(item, dict) and "high" in item and "low" in item:
                synth.append(item)
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                ts, px = int(item[0]), float(item[1])
                synth.append(
                    {
                        "ts_ms": ts,
                        "open": px,
                        "high": px,
                        "low": px,
                        "close": px,
                        "entry_candle_partial": False,
                        "_legacy_close_only": True,
                    }
                )
        bars = synth
    out = evaluate_ohlc_path(
        entry_price=entry_price,
        direction=direction,
        bars=list(bars or []),
        stop_pct=stop_pct,
        target_pct=target_pct,
        notional=notional,
        fee_rate_rt=fee_rate_rt,
        **{k: v for k, v in kwargs.items() if k in {
            "fee_model_source", "observed_fee_rate", "spread_cost", "slippage_cost", "funding_cost"
        }},
    )
    if path and any(isinstance(p, (list, tuple)) for p in path):
        out["data_quality_warnings"] = ["LEGACY_CLOSE_ONLY_INPUT_SYNTHETIC_OHLC"]
        out["measurement_quality"] = "LEGACY_CLOSE_ONLY_NOT_AUTHORITATIVE"
    return out


def persist_path_record(campaign_root: Path, record: dict[str, Any]) -> None:
    path = path_records_path(campaign_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


def load_path_records(campaign_root: Path) -> list[dict[str, Any]]:
    path = path_records_path(campaign_root)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _record_outcome_row(campaign_root: Path, row: dict[str, Any]) -> None:
    d = shadow_dir(campaign_root)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "shadow_outcomes.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def evaluate_signal_horizons(
    client: DemoWriteClient,
    *,
    signal: dict[str, Any],
    campaign_root: Path,
    stop_pct: float = 0.40,
    target_pct: float = 0.55,
    notional: float = 350.0,
    horizons: tuple[int, ...] = SHADOW_HORIZONS_SEC,
) -> list[dict[str, Any]]:
    """Evaluate mature horizons; persist path records + outcomes (separate from snapshot)."""
    symbol = str(signal.get("symbol") or "")
    entry = float(signal.get("entry_price") or 0)
    direction = str(signal.get("direction") or "LONG")
    entry_ts = int(signal.get("detected_at_ms") or 0)
    signal_id = str(signal.get("signal_id") or "")
    decision_id = signal.get("snapshot_decision_id")
    if not symbol or entry <= 0 or entry_ts <= 0 or not signal_id:
        return []

    now_ms = int(time.time() * 1000)
    results: list[dict[str, Any]] = []
    for h in horizons:
        if now_ms < entry_ts + h * 1000:
            continue
        path_meta = fetch_ohlc_path(client, symbol=symbol, entry_ts_ms=entry_ts, horizon_sec=h)
        metrics = evaluate_ohlc_path(
            entry_price=entry,
            direction=direction,
            bars=list(path_meta.get("bars") or []),
            stop_pct=stop_pct,
            target_pct=target_pct,
            notional=notional,
            fee_rate_rt=FALLBACK_FEE_RATE_RT,
            fee_model_source=FALLBACK_FEE_MODEL_SOURCE,
        )
        record = {
            "schema": PATH_SCHEMA,
            "signal_id": signal_id,
            "decision_id": decision_id,
            "symbol": symbol,
            "direction": direction,
            "entry_timestamp": entry_ts,
            "entry_price": entry,
            "horizon_sec": h,
            "path_source": path_meta.get("path_source"),
            "path_resolution": path_meta.get("resolution_label"),
            "resolution_ms": path_meta.get("resolution_ms"),
            "coverage_start": path_meta.get("coverage_start"),
            "coverage_end": path_meta.get("coverage_end"),
            "point_count": path_meta.get("point_count"),
            "data_complete": path_meta.get("data_complete"),
            "measurement_quality": path_meta.get("measurement_quality"),
            "data_quality_warnings": path_meta.get("data_quality_warnings"),
            "bars": path_meta.get("bars"),
            **metrics,
            "recorded_at_ms": now_ms,
        }
        persist_path_record(campaign_root, record)
        _record_outcome_row(
            campaign_root,
            {
                "signal_id": signal_id,
                "decision_id": decision_id,
                "horizon_sec": h,
                "recorded_at_ms": now_ms,
                "MFE": metrics.get("MFE"),
                "MAE": metrics.get("MAE"),
                "target_before_stop": metrics.get("target_before_stop"),
                "stop_before_target": metrics.get("stop_before_target"),
                "ambiguous_first_touch": metrics.get("ambiguous_first_touch"),
                "first_touch": metrics.get("first_touch"),
                "estimated_cost": metrics.get("estimated_cost"),
                "post_cost_hypothetical": metrics.get("post_cost_hypothetical"),
                "fee_model_source": metrics.get("fee_model_source"),
                "path_source": path_meta.get("path_source"),
                "measurement_quality": path_meta.get("measurement_quality"),
            },
        )
        results.append(record)
    return results


def load_active_shadow_signals(campaign_root: Path) -> list[dict[str, Any]]:
    path = shadow_dir(campaign_root) / "active_shadow_signals_latest.json"
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return list(raw.get("signals") or [])
    except Exception:  # noqa: BLE001
        return []


def path_records_for_counterfactual(campaign_root: Path) -> list[dict[str, Any]]:
    """Mature path records with OHLC bars for config comparison."""
    out: list[dict[str, Any]] = []
    for rec in load_path_records(campaign_root):
        bars = rec.get("bars")
        if not bars:
            continue
        out.append(
            {
                "signal_id": rec.get("signal_id"),
                "decision_id": rec.get("decision_id"),
                "symbol": rec.get("symbol"),
                "entry_price": rec.get("entry_price"),
                "direction": rec.get("direction"),
                "horizon_sec": rec.get("horizon_sec"),
                "bars": bars,
                "notional": 350.0,
                "path_source": rec.get("path_source"),
                "measurement_quality": rec.get("measurement_quality"),
            }
        )
    return out


def refresh_mature_shadow_outcomes(
    client: DemoWriteClient,
    *,
    campaign_root: Path,
) -> dict[str, Any]:
    signals = load_active_shadow_signals(campaign_root)
    evaluated = 0
    outcomes: list[dict[str, Any]] = []
    for sig in signals:
        if sig.get("lifecycle_state") not in {"READY", "WATCH", "DETECTED"}:
            continue
        rows = evaluate_signal_horizons(client, signal=sig, campaign_root=campaign_root)
        if rows:
            evaluated += 1
            outcomes.extend(rows)
            sig["lifecycle_state"] = "OUTCOME"
            sig["outcome"] = {
                k: rows[-1].get(k)
                for k in (
                    "horizon_sec",
                    "MFE",
                    "MAE",
                    "first_touch",
                    "ambiguous_first_touch",
                    "post_cost_hypothetical",
                    "measurement_quality",
                )
            }
    if signals:
        from backend.nexus_research_ai_autonomy.shadow_signal_v1 import persist_shadow_signals

        persist_shadow_signals(campaign_root, signals)
    return {
        "signals_checked": len(signals),
        "signals_evaluated": evaluated,
        "outcomes_written": len(outcomes),
        "path_records_persisted": len(outcomes),
        "horizons": list(SHADOW_HORIZONS_SEC),
        "close_only_MFE_removed": True,
    }
