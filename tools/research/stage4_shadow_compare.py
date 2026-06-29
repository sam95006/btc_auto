#!/usr/bin/env python3
"""Stage 4 shadow compare — read-only decision vs subsequent market data."""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import BYBIT_DEMO_BASE_URL, utc_now_iso, write_json  # noqa: E402

SECRET_PATTERNS = (
    re.compile(r"gsk_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"csk-[A-Za-z0-9]{20,}"),
)

TREND_THRESHOLD_PCT = 0.4
NEUTRAL_THRESHOLD_PCT = 0.15
MFE_MAE_MARGIN_PCT = 0.2
ADVERSITY_WATCH_PCT = 0.35


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def parse_utc_iso(ts: str) -> datetime:
    raw = (ts or "").strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    return datetime.fromisoformat(raw).astimezone(timezone.utc)


def _http_get_json(url: str, timeout: int = 20) -> Dict[str, Any]:
    req = urlopen(url, timeout=timeout)
    return json.loads(req.read().decode("utf-8"))


def fetch_klines_range(
    *,
    symbol: str,
    start_ms: int,
    end_ms: int,
    interval: str = "1",
    base_url: str = BYBIT_DEMO_BASE_URL,
) -> List[Dict[str, Any]]:
    """Read-only Bybit public klines in [start_ms, end_ms]."""
    out: List[Dict[str, Any]] = []
    cursor_start = start_ms
    while cursor_start < end_ms:
        params = {
            "category": "linear",
            "symbol": symbol.upper(),
            "interval": interval,
            "start": str(cursor_start),
            "end": str(end_ms),
            "limit": "200",
        }
        url = f"{base_url.rstrip('/')}/v5/market/kline?{urlencode(params)}"
        payload = _http_get_json(url)
        batch = list((payload.get("result") or {}).get("list") or [])
        if not batch:
            break
        parsed: List[Dict[str, Any]] = []
        for item in batch:
            if isinstance(item, list) and len(item) >= 5:
                parsed.append(
                    {
                        "start_ms": int(item[0]),
                        "open": float(item[1]),
                        "high": float(item[2]),
                        "low": float(item[3]),
                        "close": float(item[4]),
                    }
                )
        if not parsed:
            break
        out.extend(parsed)
        newest = max(r["start_ms"] for r in parsed)
        if newest <= cursor_start:
            break
        cursor_start = newest + 60_000
        time.sleep(0.05)
        if len(batch) < 200:
            break
    out.sort(key=lambda r: r["start_ms"])
    dedup: Dict[int, Dict[str, Any]] = {r["start_ms"]: r for r in out}
    return [dedup[k] for k in sorted(dedup)]


def price_at_offset(
    klines: Sequence[Dict[str, Any]],
    *,
    start_ms: int,
    offset_minutes: int,
) -> Optional[float]:
    target = start_ms + offset_minutes * 60_000
    best: Optional[float] = None
    best_delta = 10**18
    for row in klines:
        delta = abs(row["start_ms"] - target)
        if delta < best_delta:
            best_delta = delta
            best = float(row["close"])
    if best is None or best_delta > 3 * 60_000:
        return None
    return best


def compute_excursions(
    *,
    entry_price: float,
    klines: Sequence[Dict[str, Any]],
    start_ms: int,
    end_ms: int,
    side: str,
) -> Tuple[float, float, float]:
    """Return (mfe_pct, mae_pct, realized_vol_pct) over window."""
    window = [k for k in klines if start_ms <= k["start_ms"] <= end_ms]
    if not entry_price or not window:
        return 0.0, 0.0, 0.0
    highs = [float(k["high"]) for k in window]
    lows = [float(k["low"]) for k in window]
    max_high = max(highs)
    min_low = min(lows)
    side_u = (side or "NONE").upper()
    if side_u == "BUY":
        mfe = (max_high - entry_price) / entry_price * 100.0
        mae = (entry_price - min_low) / entry_price * 100.0
    elif side_u == "SELL":
        mfe = (entry_price - min_low) / entry_price * 100.0
        mae = (max_high - entry_price) / entry_price * 100.0
    else:
        mfe = (max_high - entry_price) / entry_price * 100.0
        mae = (entry_price - min_low) / entry_price * 100.0
    closes = [float(k["close"]) for k in window]
    vol = 0.0
    if len(closes) >= 2:
        rets = [abs((closes[i] - closes[i - 1]) / closes[i - 1]) * 100.0 for i in range(1, len(closes)) if closes[i - 1]]
        vol = sum(rets) / len(rets) if rets else 0.0
    return round(mfe, 4), round(mae, 4), round(vol, 4)


def detect_patch_awareness(decision: Dict[str, Any]) -> bool:
    text = " ".join(
        str(decision.get(k) or "")
        for k in ("patch_awareness", "why_skip", "confidence_reason", "risk_notes")
    ).lower()
    if decision.get("patch_blocked"):
        return True
    if any(w in text for w in ("patch", "blocking", "block_reentry", "manual_review")):
        return True
    return bool(decision.get("matched_patch_count"))


def detect_reflection_awareness(decision: Dict[str, Any]) -> bool:
    text = " ".join(
        str(decision.get(k) or "")
        for k in ("why_skip", "why_enter", "confidence_reason", "risk_notes", "patch_awareness")
    ).lower()
    if any(w in text for w in ("trade result", "recent trade", "reflection", "mixed performance", "pnl", "loss")):
        return True
    return False


def classify_shadow_label(
    *,
    decision_intent: str,
    return_60m_pct: Optional[float],
    mfe_60m_pct: float,
    mae_60m_pct: float,
    realized_volatility_60m: float,
    has_full_horizon: bool,
) -> Tuple[str, str]:
    if not has_full_horizon or return_60m_pct is None:
        return "insufficient_future_data", "Not enough kline data after decision timestamp"

    intent = (decision_intent or "unknown").lower()
    abs_ret = abs(return_60m_pct)

    if abs_ret < NEUTRAL_THRESHOLD_PCT:
        return "neutral", f"60m move {return_60m_pct:.3f}% below neutral threshold"

    directional = abs_ret >= TREND_THRESHOLD_PCT and (mfe_60m_pct - mae_60m_pct) >= MFE_MAE_MARGIN_PCT

    if intent in {"hard_skip", "soft_skip"}:
        if directional:
            return "missed_opportunity", (
                f"Skip intent but 60m move {return_60m_pct:.3f}% with MFE {mfe_60m_pct:.3f}% > MAE {mae_60m_pct:.3f}%"
            )
        return "good_skip", (
            f"Skip intent; 60m move {return_60m_pct:.3f}% not directional (MFE {mfe_60m_pct:.3f}, MAE {mae_60m_pct:.3f})"
        )

    if intent == "watch":
        if mae_60m_pct >= ADVERSITY_WATCH_PCT and mae_60m_pct > mfe_60m_pct + MFE_MAE_MARGIN_PCT:
            return "bad_watch", f"Watch but adverse excursion {mae_60m_pct:.3f}% dominated"
        if directional:
            return "missed_opportunity", f"Watch but clear 60m directional move {return_60m_pct:.3f}%"
        return "reasonable_watch", (
            f"Watch; volatile but not clearly directional (ret={return_60m_pct:.3f}%, vol={realized_volatility_60m:.3f}%)"
        )

    if intent == "enter_candidate":
        if directional:
            return "missed_opportunity", "Enter candidate with directional 60m move (shadow only, no order)"
        return "neutral", "Enter candidate without clear 60m edge in shadow window"

    return "neutral", f"Unhandled intent {intent}"


def compare_decision(
    decision: Dict[str, Any],
    *,
    symbol: str,
    horizons_minutes: Sequence[int],
    now_utc: Optional[datetime] = None,
    kline_fetcher=fetch_klines_range,
) -> Dict[str, Any]:
    tick_index = int(decision.get("tick_index") or 0)
    ts = str(decision.get("created_at_utc") or "")
    dt = parse_utc_iso(ts)
    start_ms = int(dt.timestamp() * 1000)
    max_horizon = max(horizons_minutes) if horizons_minutes else 60
    end_ms = start_ms + (max_horizon + 5) * 60_000
    now = now_utc or datetime.now(timezone.utc)
    has_full_horizon = now.timestamp() * 1000 >= start_ms + max_horizon * 60_000

    mc = decision.get("market_context") or {}
    entry = float(mc.get("last_price") or 0.0)
    side = str(decision.get("candidate_side") or "NONE")

    row: Dict[str, Any] = {
        "decision_id": decision.get("decision_id"),
        "tick_index": tick_index,
        "timestamp_utc": ts,
        "symbol": symbol.upper(),
        "provider": decision.get("provider"),
        "decision_intent": decision.get("decision_intent"),
        "final_action": decision.get("final_action"),
        "confidence": decision.get("confidence"),
        "regime": decision.get("regime") or mc.get("regime"),
        "stage3_context_available": decision.get("stage3_context_available"),
        "price_at_decision": entry,
        "patch_awareness_detected": detect_patch_awareness(decision),
        "reflection_awareness_detected": detect_reflection_awareness(decision),
        "order_sent": False,
        "data_quality": "ok",
    }

    if not entry:
        row.update(
            {
                "shadow_label": "insufficient_future_data",
                "shadow_reason": "Missing price_at_decision",
                "data_quality": "partial",
            }
        )
        return row

    try:
        klines = kline_fetcher(symbol=symbol, start_ms=start_ms, end_ms=end_ms)
    except Exception as exc:
        row.update(
            {
                "shadow_label": "insufficient_future_data",
                "shadow_reason": f"kline_fetch_error:{str(exc)[:80]}",
                "data_quality": "partial",
            }
        )
        return row

    if not klines:
        row.update(
            {
                "shadow_label": "insufficient_future_data",
                "shadow_reason": "No klines returned",
                "data_quality": "partial",
            }
        )
        return row

    for h in horizons_minutes:
        px = price_at_offset(klines, start_ms=start_ms, offset_minutes=h)
        row[f"price_after_{h}m"] = px
        if px is not None and entry:
            ret = (px - entry) / entry * 100.0
            if side.upper() == "SELL":
                ret = -ret
            row[f"return_{h}m_pct"] = round(ret, 4)
        else:
            row[f"return_{h}m_pct"] = None

    window_end = start_ms + max_horizon * 60_000
    mfe, mae, rvol = compute_excursions(
        entry_price=entry,
        klines=klines,
        start_ms=start_ms,
        end_ms=window_end,
        side=side,
    )
    row["mfe_60m_pct"] = mfe if max_horizon >= 60 else mfe
    row["mae_60m_pct"] = mae if max_horizon >= 60 else mae
    row["realized_volatility_60m"] = rvol

    ret_60 = row.get("return_60m_pct") if max_horizon >= 60 else row.get(f"return_{max_horizon}m_pct")
    label, reason = classify_shadow_label(
        decision_intent=str(decision.get("decision_intent") or ""),
        return_60m_pct=ret_60 if isinstance(ret_60, (int, float)) else None,
        mfe_60m_pct=mfe,
        mae_60m_pct=mae,
        realized_volatility_60m=rvol,
        has_full_horizon=has_full_horizon and ret_60 is not None,
    )
    row["shadow_label"] = label
    row["shadow_reason"] = reason
    if label == "insufficient_future_data":
        row["data_quality"] = "partial"
    return row


def build_summary(
    *,
    source_dir: Path,
    rows: List[Dict[str, Any]],
    decisions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    from collections import Counter

    labels = Counter(str(r.get("shadow_label") or "unknown") for r in rows)
    intents = Counter(str(d.get("decision_intent") or "unknown") for d in decisions)
    confidences = [float(d.get("confidence") or 0) for d in decisions if d.get("confidence") is not None]
    ret60 = [float(r["return_60m_pct"]) for r in rows if r.get("return_60m_pct") is not None]
    mfe = [float(r["mfe_60m_pct"]) for r in rows if r.get("mfe_60m_pct") is not None]
    mae = [float(r["mae_60m_pct"]) for r in rows if r.get("mae_60m_pct") is not None]
    compared = sum(1 for r in rows if r.get("shadow_label") != "insufficient_future_data")
    insufficient = labels.get("insufficient_future_data", 0)

    return {
        "record_type": "stage4_shadow_compare_summary",
        "generated_at_utc": utc_now_iso(),
        "source_output_dir": str(source_dir),
        "decision_count": len(decisions),
        "shadow_compared_count": compared,
        "insufficient_future_data_count": insufficient,
        "shadow_label_distribution": dict(labels),
        "decision_intent_distribution": dict(intents),
        "confidence_average": round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
        "return_60m_average_pct": round(sum(ret60) / len(ret60), 4) if ret60 else None,
        "mfe_60m_average_pct": round(sum(mfe) / len(mfe), 4) if mfe else None,
        "mae_60m_average_pct": round(sum(mae) / len(mae), 4) if mae else None,
        "good_skip_count": labels.get("good_skip", 0),
        "missed_opportunity_count": labels.get("missed_opportunity", 0),
        "bad_watch_count": labels.get("bad_watch", 0),
        "reasonable_watch_count": labels.get("reasonable_watch", 0),
        "neutral_count": labels.get("neutral", 0),
        "sample_size_too_small": len(decisions) < 30,
        "minimum_next_sample_size": 30,
        "not_a_backtest": True,
        "order_sent_count": sum(1 for d in decisions if d.get("order_sent")),
        "mock_ai_used_count": sum(1 for d in decisions if d.get("is_mock_ai")),
    }


def render_report_md(summary: Dict[str, Any], rows: List[Dict[str, Any]]) -> str:
    lines = [
        "# Stage 4.10 Shadow Compare Report",
        "",
        f"**Generated:** {summary.get('generated_at_utc')}",
        f"**Source:** `{summary.get('source_output_dir')}`",
        "",
        "> **not_a_backtest=true** — read-only shadow labels only; no orders sent.",
        "",
        "## Dataset summary",
        "",
        f"- decision_count: {summary.get('decision_count')}",
        f"- shadow_compared_count: {summary.get('shadow_compared_count')}",
        f"- insufficient_future_data_count: {summary.get('insufficient_future_data_count')}",
        f"- sample_size_too_small: {summary.get('sample_size_too_small')}",
        f"- order_sent_count: {summary.get('order_sent_count')}",
        "",
        "## Shadow label distribution",
        "",
        "```json",
        json.dumps(summary.get("shadow_label_distribution") or {}, indent=2),
        "```",
        "",
        "## Intent vs outcome",
        "",
        "| decision_id (short) | intent | shadow_label | return_60m_pct | mfe | mae |",
        "|---|---|---|---:|---:|---:|",
    ]
    for r in rows:
        did = str(r.get("decision_id") or "")[:8]
        lines.append(
            f"| {did} | {r.get('decision_intent')} | {r.get('shadow_label')} | "
            f"{r.get('return_60m_pct')} | {r.get('mfe_60m_pct')} | {r.get('mae_60m_pct')} |"
        )
    lines.extend(
        [
            "",
            "## Aggregate metrics",
            "",
            f"- confidence_average: {summary.get('confidence_average')}",
            f"- return_60m_average_pct: {summary.get('return_60m_average_pct')}",
            f"- mfe_60m_average_pct: {summary.get('mfe_60m_average_pct')}",
            f"- mae_60m_average_pct: {summary.get('mae_60m_average_pct')}",
            "",
            "## Limitations",
            "",
            "- Shadow compare is not a backtest; skips were never entered.",
            "- Sample size is below 30; labels are indicative only.",
            "- Uses public Bybit demo klines; no production or mainnet access.",
            "",
            "## Next recommendation",
            "",
            "Collect ≥30 decisions (Stage 4.9 extended soak) before using shadow labels for prompt tuning.",
        ]
    )
    return "\n".join(lines) + "\n"


def run_shadow_compare(
    *,
    decisions_dir: Path,
    output_dir: Path,
    symbol: str = "ETHUSDT",
    horizons_minutes: Sequence[int] = (15, 30, 60),
    kline_fetcher=fetch_klines_range,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    decisions = _read_jsonl(decisions_dir / "ai_decisions.jsonl")
    rows: List[Dict[str, Any]] = []
    for idx, decision in enumerate(decisions, start=1):
        enriched = dict(decision)
        if not enriched.get("tick_index"):
            enriched["tick_index"] = idx
        rows.append(
            compare_decision(
                enriched,
                symbol=symbol,
                horizons_minutes=horizons_minutes,
                kline_fetcher=kline_fetcher,
            )
        )

    summary = build_summary(source_dir=decisions_dir, rows=rows, decisions=decisions)
    jsonl_path = output_dir / "shadow_compare.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    write_json(output_dir / "stage4_shadow_compare_summary.json", summary)
    report = render_report_md(summary, rows)
    (output_dir / "stage4_shadow_compare_report.md").write_text(report, encoding="utf-8")

    text_blob = json.dumps(summary) + report
    summary["debug_log_has_api_key"] = any(p.search(text_blob) for p in SECRET_PATTERNS)
    write_json(output_dir / "stage4_shadow_compare_summary.json", summary)
    return {"summary": summary, "rows": rows, "output_dir": str(output_dir)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4 shadow compare (read-only)")
    parser.add_argument("--decisions-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--symbol", default="ETHUSDT")
    parser.add_argument("--horizons-minutes", default="15,30,60")
    args = parser.parse_args()
    horizons = [int(x.strip()) for x in args.horizons_minutes.split(",") if x.strip()]
    result = run_shadow_compare(
        decisions_dir=Path(args.decisions_dir),
        output_dir=Path(args.output_dir),
        symbol=args.symbol.upper(),
        horizons_minutes=horizons,
    )
    print(json.dumps(result["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
