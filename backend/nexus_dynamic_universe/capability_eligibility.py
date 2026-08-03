"""Capability-based historical eligibility — one universe, no fleets."""
from __future__ import annotations

import gzip
import hashlib
import json
import time
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.closed_historical_registry import (
    SEPTEMBER_OOS_END_MS,
    SEPTEMBER_OOS_START_MS,
)
from backend.nexus_dynamic_universe.symbol_profile import MEME_BASE_COINS, classify_meme

PUBLIC_BASE = "https://api.bybit.com"

# Consumed / reserved intervals — exclude from development acquisition windows
HOLDOUT_START = 1_720_863_000_000
HOLDOUT_END = 1_736_415_000_000
DEV_START = 1_739_007_000_000
DEV_END = 1_785_663_000_000

EXCLUSION_REASONS = (
    "INSUFFICIENT_LISTING_AGE",
    "INSUFFICIENT_15M_HISTORY",
    "INSUFFICIENT_60M_HISTORY",
    "INSUFFICIENT_240M_HISTORY",
    "MARK_PRICE_HISTORY_MISSING",
    "INDEX_PRICE_HISTORY_MISSING",
    "FUNDING_HISTORY_MISSING",
    "OI_HISTORY_MISSING",
    "INSTRUMENT_METADATA_INVALID",
    "TURNOVER_TOO_LOW",
    "OPEN_INTEREST_TOO_LOW",
    "SPREAD_TOO_HIGH",
    "SLIPPAGE_TOO_HIGH",
    "DATA_GAPS",
    "ABNORMAL_PRICE_DISCONTINUITY",
    "RESERVED_INTERVAL_OVERLAP",
    "PROVIDER_UNAVAILABLE",
    "OTHER_EXPLICIT_REASON",
    # Diagnostic (not a data-quality relaxation): prior H5 runner hard-cap
    "PRIOR_RESEARCH_SYMBOL_CAP_NOT_DATA_GATE",
)

CAPABILITIES = (
    "PRICE_HISTORY_ELIGIBLE",
    "DERIVATIVES_HISTORY_ELIGIBLE",
    "LIVE_MONITOR_ONLY",
    "INELIGIBLE",
)


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_obj(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _get(path: str, params: dict[str, Any], *, timeout: float = 20.0) -> dict[str, Any]:
    qs = urllib.parse.urlencode(params)
    url = f"{PUBLIC_BASE}{path}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": "nexus-goal-align/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    ret = payload.get("retCode")
    if ret is None or int(ret) != 0:
        raise RuntimeError(f"bybit_error:{ret}:{payload.get('retMsg')}")
    return payload


def overlaps_reserved(start_ms: int, end_ms: int) -> bool:
    ranges = [
        (HOLDOUT_START, HOLDOUT_END),
        (SEPTEMBER_OOS_START_MS, SEPTEMBER_OOS_END_MS),
    ]
    for a, b in ranges:
        if start_ms <= b and end_ms >= a:
            return True
    return False


@dataclass
class SymbolCapabilityAssessment:
    symbol: str
    base_coin: str
    market_size_class: str
    meme_classification: str
    capability: str
    exclusion_reasons: list[str] = field(default_factory=list)
    listing_age_days: float | None = None
    turnover_24h: float | None = None
    oi_value: float | None = None
    spread_bps: float | None = None
    history_probe: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _size_class(liq_p: float) -> str:
    if liq_p >= 0.70:
        return "MAINSTREAM"
    if liq_p >= 0.35:
        return "MID_SIZE"
    return "SMALL"


def _pct_rank(values: list[float], x: float) -> float:
    if not values:
        return 0.5
    return sum(1 for v in values if v <= x) / len(values)


def assess_metadata_exclusions(
    *,
    instruments: list[dict[str, Any]],
    tickers: dict[str, dict[str, Any]],
    as_of_ms: int,
    min_listing_age_days: float = 30.0,
    min_turnover: float = 500_000.0,
    min_oi_for_derivatives: float = 100_000.0,
    max_spread_bps: float = 25.0,
) -> list[SymbolCapabilityAssessment]:
    eligible_meta = [i for i in instruments if i.get("eligible")]
    turnovers: list[float] = []
    ois: list[float] = []
    for i in eligible_meta:
        t = tickers.get(i["symbol"]) or {}
        try:
            turnovers.append(float(t.get("turnover24h") or 0))
        except (TypeError, ValueError):
            turnovers.append(0.0)
        try:
            ois.append(float(t.get("openInterestValue") or t.get("openInterest") or 0))
        except (TypeError, ValueError):
            ois.append(0.0)

    out: list[SymbolCapabilityAssessment] = []
    for idx, i in enumerate(eligible_meta):
        sym = i["symbol"]
        t = tickers.get(sym) or {}
        to = turnovers[idx]
        oi = ois[idx]
        liq_p = 0.5 * _pct_rank(turnovers, to) + 0.5 * _pct_rank(ois, oi)
        size = _size_class(liq_p)
        base = str(i.get("base_coin") or "")
        meme = classify_meme(base, taxonomy_available=True)
        reasons: list[str] = []
        launch = i.get("launch_time")
        age = None
        if launch:
            age = max(0.0, (as_of_ms - int(launch)) / 86_400_000)
        if age is None or age < min_listing_age_days:
            reasons.append("INSUFFICIENT_LISTING_AGE")
        if not i.get("eligible") or i.get("tick_size") is None:
            reasons.append("INSTRUMENT_METADATA_INVALID")
        if to < min_turnover:
            reasons.append("TURNOVER_TOO_LOW")
        spread = None
        try:
            b, a, last = float(t.get("bid1Price") or 0), float(t.get("ask1Price") or 0), float(t.get("lastPrice") or 0)
            mid = (b + a) / 2 if b and a else last
            if mid > 0 and a >= b:
                spread = (a - b) / mid * 10_000
        except (TypeError, ValueError):
            spread = None
        slip = spread * 0.5 if spread is not None else None
        if spread is not None and spread > max_spread_bps:
            reasons.append("SPREAD_TOO_HIGH")
        if slip is not None and slip > 15:
            reasons.append("SLIPPAGE_TOO_HIGH")

        # Capability assignment from metadata only (history probed later)
        if reasons:
            # young / incomplete → live monitor if not unsafe execution
            unsafe = any(
                r in reasons
                for r in (
                    "INSTRUMENT_METADATA_INVALID",
                    "SPREAD_TOO_HIGH",
                    "SLIPPAGE_TOO_HIGH",
                )
            )
            if unsafe and "TURNOVER_TOO_LOW" in reasons:
                cap = "INELIGIBLE"
            elif "INSUFFICIENT_LISTING_AGE" in reasons or "TURNOVER_TOO_LOW" in reasons:
                cap = "LIVE_MONITOR_ONLY" if not unsafe else "INELIGIBLE"
            else:
                cap = "INELIGIBLE"
        else:
            # price-eligible pending history confirmation; derivatives needs OI floor
            if oi < min_oi_for_derivatives:
                # still can be price-eligible; OI missing/low is NOT a price blocker
                cap = "PRICE_HISTORY_ELIGIBLE"
                # note OI for derivatives track separately after probe
            else:
                cap = "PRICE_HISTORY_ELIGIBLE"

        out.append(
            SymbolCapabilityAssessment(
                symbol=sym,
                base_coin=base,
                market_size_class=size,
                meme_classification=meme,
                capability=cap,
                exclusion_reasons=reasons,
                listing_age_days=age,
                turnover_24h=to,
                oi_value=oi,
                spread_bps=spread,
            )
        )
    return out


def probe_kline_availability(symbol: str, interval: str, *, end_ms: int) -> dict[str, Any]:
    """Lightweight probe: one page only — does not download full history."""
    try:
        payload = _get(
            "/v5/market/kline",
            {
                "category": "linear",
                "symbol": symbol,
                "interval": interval,
                "end": str(end_ms),
                "limit": "5",
            },
        )
        rows = list((payload.get("result") or {}).get("list") or [])
        if not rows:
            return {"status": "MISSING", "count": 0}
        stamps = [int(r[0]) for r in rows]
        return {
            "status": "AVAILABLE",
            "count": len(rows),
            "newest_ts": max(stamps),
            "oldest_in_page": min(stamps),
        }
    except Exception as exc:
        return {"status": "PROVIDER_UNAVAILABLE", "error": str(exc)[:80]}


def apply_history_probes(
    assessments: list[SymbolCapabilityAssessment],
    *,
    end_ms: int = DEV_END,
    max_probe: int = 120,
    rate_limit_s: float = 0.05,
) -> list[SymbolCapabilityAssessment]:
    """Probe a liquidity-ranked subset; update capabilities with history reasons."""
    # Rank candidates that are not already INELIGIBLE for probing
    candidates = [a for a in assessments if a.capability != "INELIGIBLE"]
    candidates.sort(key=lambda a: (a.turnover_24h or 0), reverse=True)
    probe_set = {a.symbol for a in candidates[:max_probe]}

    for a in assessments:
        if a.symbol not in probe_set:
            a.history_probe["probed"] = False
            # Unprobed symbols are not yet research-eligible — monitor only
            if a.capability in {"PRICE_HISTORY_ELIGIBLE", "DERIVATIVES_HISTORY_ELIGIBLE"}:
                a.capability = "LIVE_MONITOR_ONLY"
                if "OTHER_EXPLICIT_REASON" not in a.exclusion_reasons:
                    a.exclusion_reasons.append("OTHER_EXPLICIT_REASON")
                a.history_probe["unprobed_pending_download"] = True
            continue
        a.history_probe["probed"] = True
        for iv, reason in (("15", "INSUFFICIENT_15M_HISTORY"), ("60", "INSUFFICIENT_60M_HISTORY"), ("240", "INSUFFICIENT_240M_HISTORY")):
            time.sleep(rate_limit_s)
            probe = probe_kline_availability(a.symbol, iv, end_ms=end_ms)
            a.history_probe[f"kline_{iv}"] = probe
            if probe.get("status") != "AVAILABLE":
                if reason not in a.exclusion_reasons:
                    a.exclusion_reasons.append(reason)
                if probe.get("status") == "PROVIDER_UNAVAILABLE" and "PROVIDER_UNAVAILABLE" not in a.exclusion_reasons:
                    a.exclusion_reasons.append("PROVIDER_UNAVAILABLE")
        # Mark/index probe (optional light)
        time.sleep(rate_limit_s)
        try:
            mark = _get(
                "/v5/market/mark-price-kline",
                {"category": "linear", "symbol": a.symbol, "interval": "60", "end": str(end_ms), "limit": "3"},
            )
            if not list((mark.get("result") or {}).get("list") or []):
                a.exclusion_reasons.append("MARK_PRICE_HISTORY_MISSING")
                a.history_probe["mark"] = "MISSING"
            else:
                a.history_probe["mark"] = "AVAILABLE"
        except Exception:
            a.exclusion_reasons.append("MARK_PRICE_HISTORY_MISSING")
            a.history_probe["mark"] = "PROVIDER_UNAVAILABLE"

        # Recompute capability
        hist_blockers = [
            r
            for r in a.exclusion_reasons
            if r
            in {
                "INSUFFICIENT_15M_HISTORY",
                "INSUFFICIENT_60M_HISTORY",
                "INSUFFICIENT_240M_HISTORY",
                "MARK_PRICE_HISTORY_MISSING",
                "INSTRUMENT_METADATA_INVALID",
                "SPREAD_TOO_HIGH",
                "SLIPPAGE_TOO_HIGH",
            }
        ]
        meta_live = [
            r
            for r in a.exclusion_reasons
            if r in {"INSUFFICIENT_LISTING_AGE", "TURNOVER_TOO_LOW"}
        ]
        if hist_blockers and any(
            r in hist_blockers
            for r in ("INSTRUMENT_METADATA_INVALID", "SPREAD_TOO_HIGH", "SLIPPAGE_TOO_HIGH")
        ):
            a.capability = "INELIGIBLE"
        elif hist_blockers or meta_live:
            if a.capability != "INELIGIBLE":
                a.capability = "LIVE_MONITOR_ONLY"
        else:
            a.capability = "PRICE_HISTORY_ELIGIBLE"
            # Derivatives: require OI value present (not invented)
            if a.oi_value is not None and a.oi_value > 0:
                # funding/OI history still UNKNOWN until downloaded — mark tentative
                a.capability = "DERIVATIVES_HISTORY_ELIGIBLE"
                a.history_probe["derivatives_tentative"] = True
            else:
                a.exclusion_reasons.append("OI_HISTORY_MISSING")
                # price still eligible; OI missing must not invent zero
                a.history_probe["oi_status"] = "MISSING"
    return assessments


def exclusion_counts(assessments: list[SymbolCapabilityAssessment]) -> dict[str, int]:
    c: Counter[str] = Counter()
    for a in assessments:
        for r in a.exclusion_reasons:
            c[r] += 1
        # Diagnostic: prior H5 research only used 10 symbols by hard cap
    c["PRIOR_RESEARCH_SYMBOL_CAP_NOT_DATA_GATE"] = max(0, len(assessments) - 10)
    return {k: int(c.get(k, 0)) for k in EXCLUSION_REASONS}


def coverage_by_capability(assessments: list[SymbolCapabilityAssessment]) -> dict[str, Any]:
    def filt(cap: str) -> list[SymbolCapabilityAssessment]:
        return [a for a in assessments if a.capability == cap]

    price = filt("PRICE_HISTORY_ELIGIBLE") + filt("DERIVATIVES_HISTORY_ELIGIBLE")
    # derivatives are also price-capable
    deriv = filt("DERIVATIVES_HISTORY_ELIGIBLE")

    def by_class(rows: list[SymbolCapabilityAssessment], cls: str) -> int:
        return sum(1 for a in rows if a.market_size_class == cls)

    def by_meme(rows: list[SymbolCapabilityAssessment], m: str) -> int:
        return sum(1 for a in rows if a.meme_classification == m)

    return {
        "price_history_eligible_count": len(set(a.symbol for a in price)),
        "derivatives_history_eligible_count": len(deriv),
        "live_monitor_only_count": len(filt("LIVE_MONITOR_ONLY")),
        "ineligible_count": len(filt("INELIGIBLE")),
        "mainstream_price_eligible_count": by_class(price, "MAINSTREAM"),
        "mid_size_price_eligible_count": by_class(price, "MID_SIZE"),
        "small_price_eligible_count": by_class(price, "SMALL"),
        "meme_price_eligible_count": by_meme(price, "MEME"),
        "targets": {
            "PRICE_HISTORY_ELIGIBLE": 60,
            "DERIVATIVES_HISTORY_ELIGIBLE": 20,
            "mainstream": 15,
            "mid_size": 20,
            "small": 15,
            "meme": 8,
        },
        "note": "Price-structure strategies must not require OI; OI/Funding strategies require DERIVATIVES_HISTORY_ELIGIBLE",
    }


@dataclass
class DownloadPartition:
    symbol: str
    series_type: str
    interval: str
    start_ms: int
    end_ms: int
    content_checksum: str
    record_count: int
    path: str


class HistoricalDownloadQueue:
    """Resumable checksummed compressed acquisition queue under .nexus_runtime."""

    def __init__(self, root: Path):
        self.root = root
        self.queue_path = root / "download_queue.json"
        self.partitions_dir = root / "partitions"
        self.partitions_dir.mkdir(parents=True, exist_ok=True)
        self.state = self._load()

    def _load(self) -> dict[str, Any]:
        if self.queue_path.exists():
            return json.loads(self.queue_path.read_text(encoding="utf-8"))
        return {"items": [], "completed": {}, "schema": "hist_download_queue_v1"}

    def save(self) -> None:
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        self.queue_path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def enqueue_symbol(self, symbol: str, *, start_ms: int = DEV_START, end_ms: int = DEV_END) -> None:
        if overlaps_reserved(start_ms, end_ms):
            raise ValueError("RESERVED_INTERVAL_OVERLAP")
        # clip away from reserved
        if end_ms > SEPTEMBER_OOS_START_MS:
            end_ms = SEPTEMBER_OOS_START_MS
        for series in ("trade", "mark", "index"):
            for interval in ("15", "60", "240"):
                key = f"{symbol}|{series}|{interval}|{start_ms}|{end_ms}"
                if key in self.state["completed"]:
                    continue
                if any(i.get("key") == key for i in self.state["items"]):
                    continue
                self.state["items"].append(
                    {
                        "key": key,
                        "symbol": symbol,
                        "series_type": series,
                        "interval": interval,
                        "start_ms": start_ms,
                        "end_ms": end_ms,
                        "status": "PENDING",
                    }
                )

    def partition_path(self, key: str) -> Path:
        safe = key.replace("|", "_")
        return self.partitions_dir / f"{safe}.json.gz"

    def process_one(self, item: dict[str, Any], *, rate_limit_s: float = 0.08) -> DownloadPartition | None:
        key = item["key"]
        path = self.partition_path(key)
        if path.exists():
            raw = gzip.decompress(path.read_bytes())
            checksum = _sha_bytes(raw)
            payload = json.loads(raw.decode("utf-8"))
            self.state["completed"][key] = {
                "checksum": checksum,
                "record_count": len(payload.get("rows") or []),
                "path": str(path),
            }
            item["status"] = "SKIPPED_IDENTICAL"
            return DownloadPartition(
                symbol=item["symbol"],
                series_type=item["series_type"],
                interval=item["interval"],
                start_ms=item["start_ms"],
                end_ms=item["end_ms"],
                content_checksum=checksum,
                record_count=len(payload.get("rows") or []),
                path=str(path),
            )

        # Fetch one page (bounded) for coverage expansion — full pagination can resume later
        path_map = {
            "trade": "/v5/market/kline",
            "mark": "/v5/market/mark-price-kline",
            "index": "/v5/market/index-price-kline",
        }
        api_path = path_map[item["series_type"]]
        all_rows: list[Any] = []
        cursor_end = int(item["end_ms"])
        start_ms = int(item["start_ms"])
        try:
            for _ in range(8):  # bounded pages; resume continues later
                time.sleep(rate_limit_s)
                payload = _get(
                    api_path,
                    {
                        "category": "linear",
                        "symbol": item["symbol"],
                        "interval": item["interval"],
                        "start": str(start_ms),
                        "end": str(cursor_end),
                        "limit": "1000",
                    },
                )
                page = list((payload.get("result") or {}).get("list") or [])
                if not page:
                    break
                all_rows.extend(page)
                oldest = min(int(r[0]) for r in page)
                if oldest <= start_ms:
                    break
                cursor_end = oldest - 1
        except Exception as exc:
            item["status"] = "PENDING"
            item["last_error"] = str(exc)[:120]
            return None
        by_ts = {int(r[0]): r for r in all_rows}
        rows = [by_ts[k] for k in sorted(by_ts)]
        if not rows:
            item["status"] = "EMPTY"
            return None
        blob = {
            "symbol": item["symbol"],
            "series_type": item["series_type"],
            "interval": item["interval"],
            "start_ms": start_ms,
            "end_ms": item["end_ms"],
            "rows": rows,
            "download_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        raw = json.dumps(blob, separators=(",", ":")).encode("utf-8")
        checksum = _sha_bytes(raw)
        path.write_bytes(gzip.compress(raw))
        self.state["completed"][key] = {
            "checksum": checksum,
            "record_count": len(rows),
            "path": str(path),
        }
        item["status"] = "DONE"
        return DownloadPartition(
            symbol=item["symbol"],
            series_type=item["series_type"],
            interval=item["interval"],
            start_ms=start_ms,
            end_ms=item["end_ms"],
            content_checksum=checksum,
            record_count=len(rows),
            path=str(path),
        )

    def process_pending(self, *, max_items: int = 30) -> dict[str, Any]:
        done = 0
        records = 0
        checksums = []
        # Prefer finishing one symbol's required series before jumping around
        pending = [i for i in self.state["items"] if i.get("status") in (None, "PENDING")]
        pending.sort(key=lambda i: (i["symbol"], i["series_type"], i["interval"]))
        for item in pending:
            if done >= max_items:
                break
            part = self.process_one(item)
            if part:
                done += 1
                records += part.record_count
                checksums.append(part.content_checksum)
        self.save()
        return {
            "partitions_written": done,
            "historical_record_count": records,
            "historical_dataset_checksum": _sha_obj(sorted(checksums)) if checksums else _sha_obj([]),
            "pending_remaining": sum(1 for i in self.state["items"] if i.get("status") == "PENDING"),
            "completed_count": len(self.state["completed"]),
        }

    def storage_size(self) -> int:
        return sum(p.stat().st_size for p in self.partitions_dir.glob("*.json.gz"))


def strategy_requires_derivatives(strategy_features: set[str]) -> bool:
    return bool(strategy_features & {"open_interest", "funding", "oi", "OI", "FUNDING"})


def assert_price_strategy_not_blocked_by_missing_oi(
    capability: str, *, requires_derivatives: bool
) -> bool:
    """Price-only strategies may use PRICE_HISTORY_ELIGIBLE even if OI missing."""
    if requires_derivatives:
        return capability == "DERIVATIVES_HISTORY_ELIGIBLE"
    return capability in {"PRICE_HISTORY_ELIGIBLE", "DERIVATIVES_HISTORY_ELIGIBLE"}
