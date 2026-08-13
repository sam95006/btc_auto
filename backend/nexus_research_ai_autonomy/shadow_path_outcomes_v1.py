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
from backend.nexus_research_ai_autonomy.shadow_signal_v1 import (
    REQUIRED_HORIZONS_SEC,
    ensure_signal_state_entry,
    load_active_shadow_signals,
    load_signal_state,
    mark_horizon_complete,
    save_signal_state,
    shadow_dir,
)

SHADOW_HORIZONS_SEC = REQUIRED_HORIZONS_SEC

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
    """Fetch 1m OHLC path for [entry, entry+horizon] via bounded start/end (not latest-200-only)."""
    end_ms = int(entry_ts_ms) + int(horizon_sec) * 1000
    entry_candle_start = (int(entry_ts_ms) // CANDLE_MS) * CANDLE_MS
    bars: list[dict[str, Any]] = []
    path_source = "bybit_public_1m_ohlc_start_end"
    resolution_label = "1m_ohlc"
    resolution_ms = CANDLE_MS
    warnings: list[str] = ["REDUCED_TEMPORAL_RESOLUTION", "OHLC_1M_LIMITED"]

    # Need enough 1m bars to cover horizon (30m=30); pad for entry candle + clock skew.
    need = max(5, int(horizon_sec) // 60 + 5)
    limit = str(min(1000, max(need, 50)))
    params = {
        "category": "linear",
        "symbol": symbol,
        "interval": "1",
        "start": str(entry_candle_start),
        "end": str(end_ms + CANDLE_MS),
        "limit": limit,
    }
    try:
        raw = client.public_get("/v5/market/kline", params)
        rows = (raw.get("result") or {}).get("list") or []
    except Exception:  # noqa: BLE001
        rows = []

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
        warnings = ["NO_PATH_DATA", "HISTORICAL_PATH_UNAVAILABLE"]
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
        "data_quality_warnings": sorted(set(warnings)),
        "bars": bars,
        "query_start_ms": entry_candle_start,
        "query_end_ms": end_ms + CANDLE_MS,
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
    # Incremental compact index update (strip bars for ingest)
    try:
        from backend.nexus_research_ai_autonomy.shadow_path_index_v1 import append_scan_path_index

        append_scan_path_index(campaign_root)
    except Exception:  # noqa: BLE001
        pass


def load_path_records(campaign_root: Path) -> list[dict[str, Any]]:
    """Full materialization — OFF hot path. Prefer streaming index / iter_jsonl_dicts."""
    path = path_records_path(campaign_root)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
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


def existing_path_keys(campaign_root: Path) -> set[tuple[str, int]]:
    return set(existing_path_key_status(campaign_root).keys())


def existing_path_key_status(campaign_root: Path) -> dict[tuple[str, int], str]:
    """Prefer compact index; never load OHLC bars for key status."""
    from backend.nexus_research_ai_autonomy.shadow_path_index_v1 import (
        ensure_path_index,
        index_key_status,
    )

    index = ensure_path_index(campaign_root)
    return index_key_status(index)


def path_outcome_audit(campaign_root: Path) -> dict[str, Any]:
    from backend.nexus_research_ai_autonomy.shadow_path_index_v1 import ensure_path_index

    index = ensure_path_index(campaign_root)
    return {
        "path_record_rows": int(index.get("path_record_rows") or 0),
        "unique_path_keys": int(index.get("unique_path_keys") or 0),
        "duplicate_path_record_rows": int(index.get("duplicate_path_record_rows") or 0),
        "outcome_rows": int(index.get("outcome_rows") or 0),
        "unique_outcome_keys": int(index.get("unique_outcome_keys") or 0),
        "duplicate_outcome_rows": int(index.get("duplicate_outcome_rows") or 0),
    }


V2_PRIORITY_FRACTION = 0.75
V2_PRIORITY_PROGRESS_FILE = "shadow_v2_priority_progress.json"


def _backfill_budgets() -> tuple[float, int]:
    import os

    try:
        max_sec = float(os.environ.get("NEXUS_SHADOW_BACKFILL_MAX_SEC") or 20)
    except (TypeError, ValueError):
        max_sec = 20.0
    try:
        max_horizons = int(os.environ.get("NEXUS_SHADOW_BACKFILL_MAX_HORIZONS_PER_CYCLE") or 40)
    except (TypeError, ValueError):
        max_horizons = 40
    return max(1.0, max_sec), max(1, max_horizons)


def v2_priority_horizon_budget(max_horizons: int, *, v2_pending: int) -> tuple[int, int]:
    """Return (v2_cap, legacy_floor). Unused V2 cap rolls to legacy during the cycle."""
    mh = max(1, int(max_horizons))
    if v2_pending <= 0:
        return 0, mh
    v2_cap = max(1, int(mh * V2_PRIORITY_FRACTION))
    if mh > 1:
        v2_cap = min(v2_cap, mh - 1)
    else:
        v2_cap = mh
    return v2_cap, mh - v2_cap


def v2_priority_progress_path(campaign_root: Path) -> Path:
    return shadow_dir(campaign_root) / V2_PRIORITY_PROGRESS_FILE


def load_v2_priority_progress(campaign_root: Path) -> dict[str, Any]:
    path = v2_priority_progress_path(campaign_root)
    if not path.exists():
        return {"schema": "v30_shadow_v2_priority_progress_v1", "cursor_index": 0}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {"cursor_index": 0}
    except Exception:  # noqa: BLE001
        return {"cursor_index": 0}


def save_v2_priority_progress(campaign_root: Path, progress: dict[str, Any]) -> None:
    d = shadow_dir(campaign_root)
    d.mkdir(parents=True, exist_ok=True)
    path = v2_priority_progress_path(campaign_root)
    payload = {
        "schema": "v30_shadow_v2_priority_progress_v1",
        "updated_at_ms": int(time.time() * 1000),
        "cursor_index": int(progress.get("cursor_index") or 0),
        "last_processed_signal_id": progress.get("last_processed_signal_id"),
        "v2_priority_pending_before": progress.get("v2_priority_pending_before"),
        "v2_priority_processed_this_cycle": progress.get("v2_priority_processed_this_cycle"),
        "v2_priority_valid_written": progress.get("v2_priority_valid_written"),
        "v2_priority_unavailable_written": progress.get("v2_priority_unavailable_written"),
        "v2_priority_pending_after": progress.get("v2_priority_pending_after"),
        "legacy_processed_this_cycle": progress.get("legacy_processed_this_cycle"),
        "priority_starvation_prevented": progress.get("priority_starvation_prevented"),
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def _mature_pending_horizons(
    signal: dict[str, Any],
    entry: dict[str, Any],
    *,
    now_ms: int,
    keys: set[tuple[str, int]],
) -> list[int]:
    from backend.nexus_research_ai_autonomy.shadow_signal_v1 import HORIZON_LABELS

    sid = str(signal.get("signal_id") or "")
    if not sid:
        return []
    if entry.get("lifecycle_state") in {"INVALIDATED", "EXPIRED"}:
        return []
    if entry.get("fully_resolved_all_horizons"):
        return []
    entry_ts = int(signal.get("detected_at_ms") or 0)
    want: list[int] = []
    for h in SHADOW_HORIZONS_SEC:
        label = HORIZON_LABELS.get(h, str(h))
        if (
            entry_ts > 0
            and now_ms >= entry_ts + h * 1000
            and (sid, h) not in keys
            and str((entry.get("horizon_status") or {}).get(label) or "PENDING") == "PENDING"
        ):
            want.append(int(h))
    return want


def _count_pending_horizons(
    signals: list[dict[str, Any]],
    state: dict[str, Any],
    *,
    now_ms: int,
    keys: set[tuple[str, int]],
) -> int:
    n = 0
    st_map = state.get("signals") or {}
    for sig in signals:
        sid = str(sig.get("signal_id") or "")
        entry = st_map.get(sid) or {}
        n += len(_mature_pending_horizons(sig, entry, now_ms=now_ms, keys=keys))
    return n


def evaluate_signal_horizons(
    client: DemoWriteClient,
    *,
    signal: dict[str, Any],
    campaign_root: Path,
    stop_pct: float = 0.40,
    target_pct: float = 0.55,
    notional: float = 350.0,
    horizons: tuple[int, ...] | list[int] | None = None,
    existing_keys: set[tuple[str, int]] | None = None,
    state_entry: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Evaluate mature pending horizons once each; persist path/outcome; update state (no early OUTCOME)."""
    symbol = str(signal.get("symbol") or "")
    entry = float(signal.get("entry_price") or 0)
    direction = str(signal.get("direction") or "LONG")
    entry_ts = int(signal.get("detected_at_ms") or signal.get("entry_timestamp") or 0)
    signal_id = str(signal.get("signal_id") or "")
    decision_id = signal.get("snapshot_decision_id") or signal.get("decision_id")
    if not symbol or entry <= 0 or entry_ts <= 0 or not signal_id:
        return []

    now_ms = int(time.time() * 1000)
    keys = existing_keys if existing_keys is not None else existing_path_keys(campaign_root)
    want = list(horizons) if horizons is not None else list(SHADOW_HORIZONS_SEC)
    results: list[dict[str, Any]] = []

    for h in want:
        h = int(h)
        if now_ms < entry_ts + h * 1000:
            continue
        if (signal_id, h) in keys:
            # Already persisted — sync state only
            if state_entry is not None:
                mark_horizon_complete(state_entry, horizon_sec=h, now_ms=now_ms)
            continue

        path_meta = fetch_ohlc_path(client, symbol=symbol, entry_ts_ms=entry_ts, horizon_sec=h)
        bars = list(path_meta.get("bars") or [])
        if not bars:
            # Persist explicit unavailable reason; do not invent outcome metrics
            unavail = {
                "schema": PATH_SCHEMA,
                "signal_id": signal_id,
                "decision_id": decision_id,
                "symbol": symbol,
                "direction": direction,
                "entry_timestamp": entry_ts,
                "entry_price": entry,
                "horizon_sec": h,
                "path_source": path_meta.get("path_source"),
                "measurement_quality": "HISTORICAL_PATH_UNAVAILABLE",
                "data_quality_warnings": path_meta.get("data_quality_warnings")
                or ["HISTORICAL_PATH_UNAVAILABLE"],
                "bars": [],
                "MFE": None,
                "MAE": None,
                "post_cost_hypothetical": None,
                "ambiguous_first_touch": False,
                "recorded_at_ms": now_ms,
                "unavailable_reason": "HISTORICAL_PATH_UNAVAILABLE",
            }
            persist_path_record(campaign_root, unavail)
            keys.add((signal_id, h))
            _record_outcome_row(
                campaign_root,
                {
                    "signal_id": signal_id,
                    "decision_id": decision_id,
                    "horizon_sec": h,
                    "recorded_at_ms": now_ms,
                    "unavailable_reason": "HISTORICAL_PATH_UNAVAILABLE",
                    "measurement_quality": "HISTORICAL_PATH_UNAVAILABLE",
                },
            )
            if state_entry is not None:
                mark_horizon_complete(
                    state_entry,
                    horizon_sec=h,
                    now_ms=now_ms,
                    unavailable_reason="HISTORICAL_PATH_UNAVAILABLE",
                )
            results.append(unavail)
            continue

        metrics = evaluate_ohlc_path(
            entry_price=entry,
            direction=direction,
            bars=bars,
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
            "query_start_ms": path_meta.get("query_start_ms"),
            "query_end_ms": path_meta.get("query_end_ms"),
            "bars": path_meta.get("bars"),
            **metrics,
            "recorded_at_ms": now_ms,
        }
        persist_path_record(campaign_root, record)
        keys.add((signal_id, h))
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
        if state_entry is not None:
            mark_horizon_complete(state_entry, horizon_sec=h, now_ms=now_ms)
        results.append(record)
    return results


def path_records_for_counterfactual(
    campaign_root: Path,
    *,
    max_records: int | None = None,
    only_new_since_offset: bool = True,
) -> list[dict[str, Any]]:
    """Bounded path records WITH bars for counterfactual — not full history each cycle."""
    import os

    from backend.nexus_research_ai_autonomy.shadow_path_index_v1 import path_records_path

    try:
        default_max = int(os.environ.get("NEXUS_SHADOW_CF_MAX_RECORDS_PER_CYCLE") or 25)
    except (TypeError, ValueError):
        default_max = 25
    limit = max_records if max_records is not None else default_max
    limit = max(1, limit)

    progress_path = shadow_dir(campaign_root) / "counterfactual_progress.json"
    offset = 0
    if only_new_since_offset and progress_path.exists():
        try:
            offset = int(json.loads(progress_path.read_text(encoding="utf-8")).get("byte_offset") or 0)
        except Exception:  # noqa: BLE001
            offset = 0

    path = path_records_path(campaign_root)
    out: list[dict[str, Any]] = []
    if not path.exists():
        return out
    size = path.stat().st_size
    if offset > size:
        offset = 0
    new_offset = offset
    with path.open("r", encoding="utf-8") as fh:
        fh.seek(offset)
        while len(out) < limit:
            line = fh.readline()
            if not line:
                break
            new_offset = fh.tell()
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
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
        # If we didn't fill limit but EOF, keep offset at EOF
        if not out and offset == size:
            new_offset = size
        elif fh.tell():
            new_offset = fh.tell()
    # Persist progress only when caller asks via side file write after successful CF
    campaign_root_ref = campaign_root
    meta = {"byte_offset": new_offset, "last_batch": len(out), "updated_at_ms": int(time.time() * 1000)}
    # stash for run_counterfactual to commit
    path_records_for_counterfactual._last_progress = (campaign_root_ref, meta)  # type: ignore[attr-defined]
    return out


def commit_counterfactual_progress(campaign_root: Path) -> None:
    meta_pair = getattr(path_records_for_counterfactual, "_last_progress", None)
    if not meta_pair:
        return
    root, meta = meta_pair
    if root != campaign_root:
        return
    d = shadow_dir(campaign_root)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "counterfactual_progress.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def refresh_mature_shadow_outcomes(
    client: DemoWriteClient,
    *,
    campaign_root: Path,
) -> dict[str, Any]:
    """Bounded, resumable backfill. Checkpoints state; never unbounded 8k-pass in one cycle."""
    from backend.nexus_research_ai_autonomy.shadow_signal_v1 import (
        HORIZON_LABELS,
        ledger_stats as _ledger_stats,
        load_backfill_progress,
        save_backfill_progress,
    )

    t0 = time.time()
    max_sec, max_horizons = _backfill_budgets()
    led = _ledger_stats(campaign_root)
    from backend.nexus_research_ai_autonomy.shadow_v2_challenger_v1 import (
        evidence_to_shadow_signal,
        load_selected_top1_long,
        load_v2_c1_shadow_signals,
    )

    v1_signals = load_active_shadow_signals(campaign_root)
    v2_all = [evidence_to_shadow_signal(e) for e in load_v2_c1_shadow_signals(campaign_root)]
    v2_selected = [evidence_to_shadow_signal(e) for e in load_selected_top1_long(campaign_root)]
    v2_priority_ids = {str(s.get("signal_id") or "") for s in v2_selected if s.get("signal_id")}
    v1_sorted = sorted(
        v1_signals,
        key=lambda s: (int(s.get("detected_at_ms") or 0), str(s.get("signal_id") or "")),
    )
    v2_priority_sorted = sorted(
        v2_selected,
        key=lambda s: (int(s.get("detected_at_ms") or 0), str(s.get("signal_id") or "")),
    )
    # Combined for state sync / pending totals only — legacy cursor walks V1-only.
    signals_sorted = sorted(
        v1_signals + v2_all,
        key=lambda s: (int(s.get("detected_at_ms") or 0), str(s.get("signal_id") or "")),
    )
    state = load_signal_state(campaign_root)
    key_status = existing_path_key_status(campaign_root)
    keys = set(key_status.keys())
    progress = load_backfill_progress(campaign_root)
    cursor = int(progress.get("cursor_index") or 0)
    n = len(v1_sorted)
    if n and (cursor < 0 or cursor >= n):
        cursor = 0
    v2_prog = load_v2_priority_progress(campaign_root)
    v2_cursor = int(v2_prog.get("cursor_index") or 0)
    n_v2 = len(v2_priority_sorted)
    if n_v2 and (v2_cursor < 0 or v2_cursor >= n_v2):
        v2_cursor = 0

    horizons_processed = 0
    state_synced = 0
    new_paths = 0
    unavailable_writes = 0
    evaluated = 0
    outcomes: list[dict[str, Any]] = []
    checkpoint_every = 10
    dirty = False
    status = "IDLE"

    def _budget_hit() -> bool:
        return (time.time() - t0) >= max_sec or horizons_processed >= max_horizons

    def _checkpoint(cur_status: str) -> None:
        nonlocal dirty
        if not dirty:
            return
        save_signal_state(campaign_root, state)
        save_backfill_progress(
            campaign_root,
            {
                "cursor_index": cursor,
                "last_processed_signal_id": progress.get("last_processed_signal_id"),
                "backfill_status": cur_status,
            },
        )
        dirty = False

    try:
        # Phase A: sync state from already-persisted path keys (no API)
        sync_budget = max(200, max_horizons * 5)
        synced_this = 0
        for sig in signals_sorted:
            if synced_this >= sync_budget or (time.time() - t0) >= max_sec:
                status = "PARTIAL"
                break
            sid = str(sig.get("signal_id") or "")
            if not sid:
                continue
            entry = ensure_signal_state_entry(state, sig)
            now_ms = int(time.time() * 1000)
            for h in SHADOW_HORIZONS_SEC:
                st = key_status.get((sid, h))
                if not st:
                    continue
                label = HORIZON_LABELS.get(h, str(h))
                cur = str((entry.get("horizon_status") or {}).get(label) or "PENDING")
                if cur == st:
                    continue
                mark_horizon_complete(
                    entry,
                    horizon_sec=h,
                    now_ms=now_ms,
                    unavailable_reason="HISTORICAL_PATH_UNAVAILABLE" if st == "UNAVAILABLE" else None,
                    status=st,
                )
                state_synced += 1
                synced_this += 1
                dirty = True
            if dirty and state_synced % 50 == 0:
                _checkpoint("PARTIAL")
        _checkpoint(status if status == "PARTIAL" else "IDLE")

        # Count pending fetch work
        now_ms = int(time.time() * 1000)
        pending_before = _count_pending_horizons(signals_sorted, state, now_ms=now_ms, keys=keys)
        v2_priority_pending_before = _count_pending_horizons(
            v2_priority_sorted, state, now_ms=now_ms, keys=keys
        )
        v2_cap, _legacy_floor = v2_priority_horizon_budget(
            max_horizons, v2_pending=v2_priority_pending_before
        )
        v2_priority_processed = 0
        v2_priority_valid = 0
        v2_priority_unavailable = 0
        legacy_processed = 0

        def _ingest_rows(sid: str, rows: list[dict[str, Any]], *, v2_priority: bool) -> None:
            nonlocal horizons_processed, evaluated, dirty, new_paths, unavailable_writes
            nonlocal v2_priority_processed, v2_priority_valid, v2_priority_unavailable, legacy_processed
            if not rows:
                return
            evaluated += 1
            outcomes.extend(rows)
            for r in rows:
                horizons_processed += 1
                dirty = True
                h = int(r.get("horizon_sec") or 0)
                keys.add((sid, h))
                if r.get("unavailable_reason") == "HISTORICAL_PATH_UNAVAILABLE":
                    unavailable_writes += 1
                    key_status[(sid, h)] = "UNAVAILABLE"
                    if v2_priority:
                        v2_priority_unavailable += 1
                else:
                    new_paths += 1
                    key_status[(sid, h)] = "VALID"
                    if v2_priority:
                        v2_priority_valid += 1
                if v2_priority:
                    v2_priority_processed += 1
                else:
                    legacy_processed += 1

        def _process_one(sig: dict[str, Any], *, v2_priority: bool, cap: int) -> bool:
            """Process pending horizons for one signal. Return True if any work done."""
            sid = str(sig.get("signal_id") or "")
            if not sid or _budget_hit() or horizons_processed >= cap:
                return False
            entry = ensure_signal_state_entry(state, sig)
            now_local = int(time.time() * 1000)
            want = _mature_pending_horizons(sig, entry, now_ms=now_local, keys=keys)
            remaining = cap - horizons_processed
            want = want[: max(0, remaining)]
            if not want:
                return False
            rows = evaluate_signal_horizons(
                client,
                signal=sig,
                campaign_root=campaign_root,
                horizons=want,
                existing_keys=keys,
                state_entry=entry,
            )
            _ingest_rows(sid, rows, v2_priority=v2_priority)
            return bool(rows)

        if n == 0 and n_v2 == 0:
            status = "CAUGHT_UP"
        else:
            status = "PARTIAL"
            # Phase B: V2 selected Top1 priority (bounded). Never consumes the full budget
            # when legacy work remains — unused V2 cap rolls to the V1 cursor walk.
            if v2_priority_pending_before > 0 and n_v2 > 0 and not _budget_hit():
                v2_visited = 0
                idx = v2_cursor % n_v2
                while v2_visited < n_v2 and not _budget_hit() and horizons_processed < v2_cap:
                    sig = v2_priority_sorted[idx]
                    sid = str(sig.get("signal_id") or "")
                    v2_prog["last_processed_signal_id"] = sid
                    v2_cursor = (idx + 1) % n_v2
                    v2_visited += 1
                    idx = v2_cursor
                    if not sid or sid not in v2_priority_ids:
                        continue
                    _process_one(sig, v2_priority=True, cap=v2_cap)
                    if horizons_processed % checkpoint_every == 0:
                        _checkpoint("PARTIAL")

            # Phase C: remaining budget → legacy V1 cursor (V1-only list; cursor preserved).
            if n > 0 and not _budget_hit() and horizons_processed < max_horizons:
                visited = 0
                idx = cursor % n
                while visited < n and not _budget_hit() and horizons_processed < max_horizons:
                    sig = v1_sorted[idx]
                    sid = str(sig.get("signal_id") or "")
                    progress["last_processed_signal_id"] = sid
                    cursor = (idx + 1) % n
                    visited += 1
                    idx = cursor
                    if not sid:
                        continue
                    if sid in v2_priority_ids:
                        continue
                    _process_one(sig, v2_priority=False, cap=max_horizons)
                    if horizons_processed % checkpoint_every == 0:
                        _checkpoint("PARTIAL")

            # Leftover only: non-selected V2 (SHORT research) — never V2 priority, never V1 cursor.
            if not _budget_hit() and horizons_processed < max_horizons:
                for sig in v2_all:
                    if _budget_hit() or horizons_processed >= max_horizons:
                        break
                    sid = str(sig.get("signal_id") or "")
                    if not sid or sid in v2_priority_ids:
                        continue
                    _process_one(sig, v2_priority=False, cap=max_horizons)

            still_pending = False
            now_ms = int(time.time() * 1000)
            for sig in signals_sorted:
                sid = str(sig.get("signal_id") or "")
                entry = (state.get("signals") or {}).get(sid) or {}
                if _mature_pending_horizons(sig, entry, now_ms=now_ms, keys=keys):
                    still_pending = True
                    break
            if _budget_hit() or still_pending:
                status = "PARTIAL"
            else:
                status = "CAUGHT_UP"

        progress["cursor_index"] = cursor
        progress["backfill_status"] = status
        dirty = True
        _checkpoint(status)
        save_signal_state(campaign_root, state)
        save_backfill_progress(campaign_root, progress)

        now_ms = int(time.time() * 1000)
        pending_after = _count_pending_horizons(signals_sorted, state, now_ms=now_ms, keys=keys)
        v2_priority_pending_after = _count_pending_horizons(
            v2_priority_sorted, state, now_ms=now_ms, keys=keys
        )
        priority_starvation_prevented = bool(
            v2_priority_pending_before <= 0 or v2_priority_processed > 0
        )
        v2_prog["cursor_index"] = v2_cursor
        v2_prog["v2_priority_pending_before"] = v2_priority_pending_before
        v2_prog["v2_priority_processed_this_cycle"] = v2_priority_processed
        v2_prog["v2_priority_valid_written"] = v2_priority_valid
        v2_prog["v2_priority_unavailable_written"] = v2_priority_unavailable
        v2_prog["v2_priority_pending_after"] = v2_priority_pending_after
        v2_prog["legacy_processed_this_cycle"] = legacy_processed
        v2_prog["priority_starvation_prevented"] = priority_starvation_prevented
        save_v2_priority_progress(campaign_root, v2_prog)

        fully_resolved = sum(
            1 for e in (state.get("signals") or {}).values() if e.get("fully_resolved_all_horizons")
        )
        fully_valid = sum(
            1 for e in (state.get("signals") or {}).values() if e.get("fully_matured_valid_all_horizons")
        )
        with_unavail = sum(
            1 for e in (state.get("signals") or {}).values() if e.get("has_unavailable_horizon")
        )
        audit = path_outcome_audit(campaign_root)
        return {
            "signals_checked": len(signals_sorted),
            "signals_evaluated": evaluated,
            "outcomes_written": len(outcomes),
            "path_records_persisted": len(outcomes),
            "horizons": list(SHADOW_HORIZONS_SEC),
            "close_only_MFE_removed": True,
            "ledger_rows": led["ledger_rows"],
            "ledger_unique": led["unique_signal_ids"],
            "duplicate_signal_rows": led["duplicate_signal_rows"],
            "pending_signals_before": pending_before,
            "pending_signals_after": pending_after,
            "horizons_processed_this_cycle": horizons_processed,
            "state_synced_from_existing_paths": state_synced,
            "new_paths_written": new_paths,
            "unavailable_paths_written": unavailable_writes,
            "wall_time_sec": round(time.time() - t0, 3),
            "backfill_status": status,
            "backfill_work_budget": max_horizons,
            "backfill_time_budget": max_sec,
            "cursor_index": cursor,
            "v2_priority_pending_before": v2_priority_pending_before,
            "v2_priority_processed_this_cycle": v2_priority_processed,
            "v2_priority_valid_written": v2_priority_valid,
            "v2_priority_unavailable_written": v2_priority_unavailable,
            "v2_priority_pending_after": v2_priority_pending_after,
            "legacy_processed_this_cycle": legacy_processed,
            "priority_starvation_prevented": priority_starvation_prevented,
            "v2_priority_horizon_budget": v2_cap,
            "fully_resolved_all_horizons": fully_resolved,
            "fully_matured_valid_all_horizons": fully_valid,
            "fully_matured_all_horizons": fully_valid,
            "signals_with_unavailable_horizon": with_unavail,
            "lifecycle_source": "active_shadow_signals.jsonl",
            "premature_outcome_blocked": True,
            "per_horizon_exactly_once": True,
            "historical_kline_start_end": True,
            "bounded_backfill": True,
            "periodic_state_checkpoint": True,
            "restart_resume_safe": True,
            "existing_path_state_sync": True,
            **audit,
        }
    except Exception as exc:  # noqa: BLE001
        try:
            save_signal_state(campaign_root, state)
            progress["cursor_index"] = cursor
            progress["backfill_status"] = "ERROR"
            save_backfill_progress(campaign_root, progress)
        except Exception:  # noqa: BLE001
            pass
        return {
            "backfill_status": "ERROR",
            "error": f"{type(exc).__name__}:{exc}"[:300],
            "horizons_processed_this_cycle": horizons_processed,
            "state_synced_from_existing_paths": state_synced,
            "wall_time_sec": round(time.time() - t0, 3),
            "bounded_backfill": True,
            "backfill_work_budget": max_horizons,
            "backfill_time_budget": max_sec,
            "periodic_state_checkpoint": True,
        }
