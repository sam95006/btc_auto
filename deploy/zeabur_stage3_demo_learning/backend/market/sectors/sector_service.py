"""Server-side sector aggregation (Phase 3) — read-only.

Breadth layer: Bybit public tickers (~742).
Deep layer: MarketScannerService (~80).
No browser aggregation · not a trading trigger.
"""
from __future__ import annotations

import statistics
import threading
import time
from typing import Any

from backend.market.scanner.scanner_service import get_market_scanner
from backend.market.scanner.universe import fetch_all_linear_tickers
from backend.market.sectors import taxonomy as tax

_SNAPSHOT_INTERVAL_SEC = 30.0
_BAR_LIMIT_NOTE = 500


def _f(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _median(vals: list[float]) -> float | None:
    if not vals:
        return None
    return float(statistics.median(vals))


def _weighted_return(rows: list[dict[str, Any]]) -> float | None:
    num = 0.0
    den = 0.0
    for r in rows:
        ch = _f(r.get("change24hPct"))
        to = _f(r.get("turnover24h")) or 0.0
        if ch is None or to <= 0:
            continue
        num += ch * to
        den += to
    if den <= 0:
        return None
    return num / den


def _sector_state(m: dict[str, Any]) -> tuple[str, str, list[str]]:
    """Return (state, labelZh, reasons). Transparent thresholds — not Buy/Sell."""
    reasons: list[str] = []
    conflicts: list[str] = []
    valid = int(m.get("validMarketCount") or 0)
    if valid < 3:
        return "INSUFFICIENT_DATA", "資料不足", ["有效樣本過少"]
    collecting = int(m.get("collectingCount") or 0)
    if collecting >= max(1, int(valid * 0.7)):
        return "COLLECTING", "資料累積中", ["多數成員仍在累積窗口"]

    ret = m.get("turnoverWeightedReturn24h")
    breadth = m.get("breadthRatio")
    risk = int(m.get("overextendedCount") or 0) + int(m.get("highSeverityAnomalyCount") or 0)
    longs = int(m.get("longCandidateCount") or 0)
    shorts = int(m.get("shortCandidateCount") or 0)

    if risk >= 3:
        conflicts.append("高風險／過熱標的偏多")
        return "RISKY", "風險升高", conflicts
    if ret is not None and breadth is not None:
        if ret >= 3 and breadth >= 0.55:
            reasons.append("加權漲幅與上漲廣度同步偏強")
            return "HOT", "熱度上升", reasons
        if ret <= -3 and breadth <= 0.45:
            reasons.append("加權回撤且上漲廣度偏弱")
            return "WEAK", "動能偏弱", reasons
    if longs and shorts and abs(longs - shorts) <= 1:
        reasons.append("做多與做空候選接近")
        return "MIXED", "多空分歧", reasons
    if (m.get("averageTurnoverPace") or 0) > 0 or (ret is not None and abs(ret) >= 1):
        reasons.append("資金或價格仍有活躍度")
        return "ACTIVE", "資金活躍", reasons
    return "MIXED", "多空分歧", ["方向不明顯"]


class SectorService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cache: dict[str, Any] | None = None
        self._cache_at = 0.0

    def _build(self) -> dict[str, Any]:
        now = int(time.time() * 1000)
        tickers = fetch_all_linear_tickers()
        breadth_rows: list[dict[str, Any]] = []
        for t in tickers:
            sym = str(t.get("symbol") or "")
            if not sym.endswith("USDT"):
                continue
            ch = _f(t.get("price24hPcnt"))
            if ch is not None:
                ch = ch * 100.0
            breadth_rows.append(
                {
                    "symbol": sym,
                    "lastPrice": _f(t.get("lastPrice")),
                    "change24hPct": ch,
                    "turnover24h": _f(t.get("turnover24h")),
                    "fundingRate": _f(t.get("fundingRate")),
                    "openInterestValue": _f(t.get("openInterestValue")),
                    "openInterest": _f(t.get("openInterest")),
                }
            )

        scanner = get_market_scanner()
        deep = scanner.sector_deep_snapshot()
        deep_map = {r["symbol"]: r for r in deep.get("rows") or []}
        candidates = deep.get("candidates") or []
        cand_by_sym = {c["symbol"]: c for c in candidates}

        by_sector: dict[str, list[dict[str, Any]]] = {s["id"]: [] for s in tax.list_sectors()}
        classified = 0
        for row in breadth_rows:
            mem = tax.membership_for_symbol(row["symbol"])
            deep_row = deep_map.get(row["symbol"])
            cand = cand_by_sym.get(row["symbol"])
            enriched = {
                **row,
                "classified": mem["classified"],
                "sectorIds": mem["sectorIds"],
                "confidence": mem["confidence"],
                "inDeepScan": deep_row is not None,
                "priceChange5mPct": (deep_row or {}).get("priceChange5mPct") if deep_row else (cand or {}).get("priceChange5mPct"),
                "oiChange5mPct": (deep_row or {}).get("oiChange5mPct") if deep_row else (cand or {}).get("oiChange5mPct"),
                "turnoverPace": (cand or {}).get("turnoverPace"),
                "side": (cand or {}).get("side"),
                "stage": (cand or {}).get("stage"),
                "opportunityScore": (cand or {}).get("opportunityScore"),
                "riskScore": (cand or {}).get("riskScore"),
                "rank": (cand or {}).get("rank"),
                "freshness": (cand or {}).get("freshness") or deep.get("freshness"),
                "collecting": bool((cand or {}).get("collecting") or (deep_row or {}).get("collecting")),
            }
            if mem["classified"]:
                classified += 1
                for sid in mem["sectorIds"]:
                    by_sector.setdefault(sid, []).append(enriched)
            # do NOT force into Other for coverage inflation

        unclassified = len(breadth_rows) - classified
        sectors_out: list[dict[str, Any]] = []
        for meta in tax.list_sectors():
            if meta["id"] == "other":
                continue
            members = by_sector.get(meta["id"]) or []
            valid = [m for m in members if m.get("change24hPct") is not None]
            deep_members = [m for m in members if m.get("inDeepScan")]
            rets = [float(m["change24hPct"]) for m in valid]
            funds = [float(m["fundingRate"]) for m in members if m.get("fundingRate") is not None]
            oi5 = [float(m["oiChange5mPct"]) for m in members if m.get("oiChange5mPct") is not None]
            rising = sum(1 for m in valid if float(m["change24hPct"]) > 0.5)
            falling = sum(1 for m in valid if float(m["change24hPct"]) < -0.5)
            neutral = max(0, len(valid) - rising - falling)
            collecting = sum(1 for m in members if m.get("collecting"))
            longs = sum(1 for m in members if m.get("side") == "LONG" and m.get("rank"))
            shorts = sum(1 for m in members if m.get("side") == "SHORT" and m.get("rank"))
            confirmed = sum(1 for m in members if m.get("stage") == "CONFIRMED")
            overext = sum(1 for m in members if m.get("stage") == "OVEREXTENDED")
            paces = [float(m["turnoverPace"]) for m in members if m.get("turnoverPace") is not None]
            breadth_ratio = (rising / len(valid)) if valid else None
            metrics = {
                "id": meta["id"],
                "slug": meta["slug"],
                "nameZhTW": meta["nameZhTW"],
                "nameEn": meta["nameEn"],
                "iconKey": meta.get("iconKey"),
                "descriptionZhTW": meta.get("descriptionZhTW"),
                "source": meta.get("source"),
                "memberCount": len(members),
                "validMarketCount": len(valid),
                "deepScanMemberCount": len(deep_members),
                "classifiedCoverage": True,
                "risingCount": rising,
                "fallingCount": falling,
                "neutralCount": neutral,
                "collectingCount": collecting,
                "breadthRatio": breadth_ratio,
                "medianReturn24h": _median(rets),
                "turnoverWeightedReturn24h": _weighted_return(valid),
                "medianFundingRate": _median(funds),
                "medianOiChange5m": _median(oi5) if oi5 else None,
                "oiSampleCount": len(oi5),
                "fundingSampleCount": len(funds),
                "turnoverContribution": sum(float(m.get("turnover24h") or 0) for m in members),
                "averageTurnoverPace": (sum(paces) / len(paces)) if paces else None,
                "longCandidateCount": longs,
                "shortCandidateCount": shorts,
                "confirmedCandidateCount": confirmed,
                "overextendedCount": overext,
                "highSeverityAnomalyCount": 0,
                "freshness": deep.get("freshness") or "LIVE",
                "generatedAt": now,
                "researchOnly": True,
                "notTradingSignal": True,
            }
            state, label, reasons = _sector_state(metrics)
            metrics["sectorState"] = state
            metrics["sectorStateLabelZh"] = label
            metrics["reasons"] = reasons
            metrics["sampleNote"] = (
                f"有效市場 {len(valid)} / {len(members)} · 深度掃描 {len(deep_members)} / {len(members)}"
            )
            sectors_out.append(metrics)

        return {
            "ok": True,
            "read_only": True,
            "private_api": False,
            "researchOnly": True,
            "trading_integration": False,
            "source": "BYBIT_MAINNET_LINEAR+NEXUS_CURATED_TAXONOMY",
            "generatedAt": now,
            "snapshotIntervalSec": _SNAPSHOT_INTERVAL_SEC,
            "breadthMarketCount": len(breadth_rows),
            "deepScanCount": deep.get("symbolCount") or 0,
            "classifiedSymbolCount": classified,
            "unclassifiedSymbolCount": unclassified,
            "classificationCoverage": (classified / len(breadth_rows)) if breadth_rows else 0.0,
            "taxonomy": tax.taxonomy_stats(),
            "sectors": sectors_out,
            "cache": "no-store",
        }

    def snapshot(self, *, force: bool = False) -> dict[str, Any]:
        with self._lock:
            age = time.time() - self._cache_at
            if not force and self._cache and age < _SNAPSHOT_INTERVAL_SEC:
                return self._cache
            body = self._build()
            self._cache = body
            self._cache_at = time.time()
            return body

    def status(self) -> dict[str, Any]:
        snap = self.snapshot()
        return {
            "ok": True,
            "read_only": True,
            "private_api": False,
            "researchOnly": True,
            "breadthMarketCount": snap.get("breadthMarketCount"),
            "deepScanCount": snap.get("deepScanCount"),
            "sectorCount": len(snap.get("sectors") or []),
            "classifiedSymbolCount": snap.get("classifiedSymbolCount"),
            "unclassifiedSymbolCount": snap.get("unclassifiedSymbolCount"),
            "classificationCoverage": snap.get("classificationCoverage"),
            "generatedAt": snap.get("generatedAt"),
            "freshness": (snap.get("sectors") or [{}])[0].get("freshness") if snap.get("sectors") else "COLLECTING",
            "snapshotIntervalSec": _SNAPSHOT_INTERVAL_SEC,
            "marketCoverageWording": "市場涵蓋（廣度層）與深度掃描（約 80）分層顯示",
            "cache": "no-store",
        }

    def list_sectors(self, *, sort: str = "performance", state: str | None = None) -> dict[str, Any]:
        snap = self.snapshot()
        rows = list(snap.get("sectors") or [])
        if state:
            st = state.upper()
            rows = [r for r in rows if r.get("sectorState") == st]
        key = sort.lower()
        sorters = {
            "performance": lambda r: (r.get("turnoverWeightedReturn24h") is None, -(r.get("turnoverWeightedReturn24h") or 0)),
            "breadth": lambda r: (r.get("breadthRatio") is None, -(r.get("breadthRatio") or 0)),
            "turnover": lambda r: -(r.get("turnoverContribution") or 0),
            "oi": lambda r: (r.get("medianOiChange5m") is None, -(abs(r.get("medianOiChange5m") or 0))),
            "candidates": lambda r: -(int(r.get("longCandidateCount") or 0) + int(r.get("shortCandidateCount") or 0)),
            "risk": lambda r: -int(r.get("overextendedCount") or 0),
            "anomaly": lambda r: -int(r.get("highSeverityAnomalyCount") or 0),
            "alphabetical": lambda r: str(r.get("nameEn") or ""),
            "updated": lambda r: -(r.get("generatedAt") or 0),
        }
        rows.sort(key=sorters.get(key, sorters["performance"]))
        return {
            "ok": True,
            "read_only": True,
            "generatedAt": snap.get("generatedAt"),
            "breadthMarketCount": snap.get("breadthMarketCount"),
            "deepScanCount": snap.get("deepScanCount"),
            "classifiedSymbolCount": snap.get("classifiedSymbolCount"),
            "unclassifiedSymbolCount": snap.get("unclassifiedSymbolCount"),
            "count": len(rows),
            "sectors": rows,
            "cache": "no-store",
        }

    def sector_detail(self, sector_id: str) -> dict[str, Any]:
        meta = tax.get_sector(sector_id)
        if not meta or meta["id"] == "other":
            return {"ok": False, "error": "sector_not_found"}
        snap = self.snapshot()
        row = next((s for s in snap.get("sectors") or [] if s["id"] == meta["id"] or s["slug"] == meta["slug"]), None)
        if not row:
            return {"ok": False, "error": "sector_empty", "sector": meta}
        members = self.sector_symbols(meta["id"]).get("symbols") or []
        insight = _insight_line(row)
        return {
            "ok": True,
            "read_only": True,
            "researchOnly": True,
            "notTradingSignal": True,
            "sector": row,
            "membersPreview": members[:20],
            "insight": insight,
            "generatedAt": snap.get("generatedAt"),
            "cache": "no-store",
        }

    def sector_symbols(self, sector_id: str, *, limit: int = 80) -> dict[str, Any]:
        meta = tax.get_sector(sector_id)
        if not meta:
            return {"ok": False, "error": "sector_not_found"}
        snap = self.snapshot()
        # Prefer live rebuild from deep snapshot + membership
        scanner = get_market_scanner()
        deep = scanner.sector_deep_snapshot()
        deep_map = {r["symbol"]: r for r in deep.get("rows") or []}
        cands = {c["symbol"]: c for c in deep.get("candidates") or []}
        symbols: list[dict[str, Any]] = []
        for base_sym in tax.symbols_for_sector(meta["id"]):
            base = _strip(base_sym)
            variants = [f"{base}USDT", f"1000{base}USDT"]
            hit = None
            for v in variants:
                if v in deep_map or v in cands:
                    hit = v
                    break
            if not hit:
                symbols.append(
                    {
                        "symbol": base_sym,
                        "inDeepScan": False,
                        "classified": True,
                        "collecting": True,
                    }
                )
                continue
            d = deep_map.get(hit) or {}
            c = cands.get(hit) or {}
            symbols.append(
                {
                    "symbol": hit,
                    "lastPrice": d.get("lastPrice") or c.get("currentPrice"),
                    "change24hPct": d.get("change24hPct") or c.get("change24hPct"),
                    "priceChange5mPct": c.get("priceChange5mPct"),
                    "oiChange5mPct": c.get("oiChange5mPct"),
                    "fundingRate": d.get("fundingRate") or c.get("fundingRate"),
                    "turnover24h": d.get("turnover24h"),
                    "turnoverPace": c.get("turnoverPace"),
                    "side": c.get("side"),
                    "stage": c.get("stage"),
                    "opportunityScore": c.get("opportunityScore"),
                    "riskScore": c.get("riskScore"),
                    "rank": c.get("rank"),
                    "freshness": c.get("freshness") or deep.get("freshness"),
                    "inDeepScan": True,
                    "collecting": bool(c.get("collecting")),
                }
            )
        symbols.sort(key=lambda r: (-(r.get("opportunityScore") or 0), str(r.get("symbol"))))
        return {
            "ok": True,
            "sectorId": meta["id"],
            "count": len(symbols),
            "symbols": symbols[: max(1, min(limit, 120))],
            "generatedAt": snap.get("generatedAt"),
            "cache": "no-store",
        }

    def sector_candidates(self, sector_id: str) -> dict[str, Any]:
        body = self.sector_symbols(sector_id, limit=120)
        if not body.get("ok"):
            return body
        rows = [r for r in body.get("symbols") or [] if r.get("side") in ("LONG", "SHORT") and r.get("rank")]
        return {"ok": True, "count": len(rows), "candidates": rows, "cache": "no-store"}

    def rankings(self, *, sort: str = "performance") -> dict[str, Any]:
        return self.list_sectors(sort=sort)


def _strip(sym: str) -> str:
    s = sym.upper()
    if s.endswith("USDT"):
        s = s[:-4]
    if s.startswith("1000"):
        s = s[4:]
    return s


def _insight_line(row: dict[str, Any]) -> str:
    name = row.get("nameZhTW") or row.get("nameEn") or "此版塊"
    label = row.get("sectorStateLabelZh") or "觀察中"
    sample = row.get("sampleNote") or ""
    ret = row.get("turnoverWeightedReturn24h")
    ret_s = f"{ret:+.2f}%" if isinstance(ret, (int, float)) else "—"
    longs = row.get("longCandidateCount") or 0
    shorts = row.get("shortCandidateCount") or 0
    return (
        f"{name}目前「{label}」。加權 24h {ret_s}；"
        f"深度候選 多 {longs}／空 {shorts}。{sample}。"
        f"此為市場情報摘要，不是買賣建議。"
    )


_SERVICE: SectorService | None = None
_SERVICE_LOCK = threading.Lock()


def get_sector_service() -> SectorService:
    global _SERVICE
    with _SERVICE_LOCK:
        if _SERVICE is None:
            _SERVICE = SectorService()
        return _SERVICE
