#!/usr/bin/env python3
"""Stage 4.17-A paper event logger — append-only hypothetical JSONL, no orders."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402
from tools.research.stage4_paper_guard_inputs import (  # noqa: E402
    MAE_SOURCE_LEGACY,
    MAE_SOURCE_LLM,
    MAE_SOURCE_MISSING,
    get_paper_mae_pct,
    legacy_market_mae_proxy_pct,
    llm_mae_risk_estimate_pct,
)

RECORD_TYPE = "stage4_hypothetical_paper_event"
DESIGN_GATE_VERSION = "4.16"
CREATED_BY = "stage4_17a_paper_event_logger"

FLEET_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "PEPEUSDT"]

CONFIDENCE_FLOORS = {
    "BTCUSDT": 0.40,
    "ETHUSDT": 0.38,
    "SOLUSDT": 0.50,
    "PEPEUSDT": 0.52,
}

MAE_CAPS_PCT = {
    "BTCUSDT": 0.35,
    "ETHUSDT": 0.35,
    "SOLUSDT": 0.25,
    "PEPEUSDT": 0.20,
}

SHADOW_PRIOR_BAD_WATCH_RATE = {
    "BTCUSDT": 0.1124,
    "ETHUSDT": 0.0556,
    "SOLUSDT": 0.2590,
    "PEPEUSDT": 0.2515,
}

SYMBOL_SL_TP_HOLD = {
    "BTCUSDT": (0.35, 0.60, 60),
    "ETHUSDT": (0.35, 0.60, 60),
    "SOLUSDT": (0.25, 0.45, 45),
    "PEPEUSDT": (0.20, 0.40, 30),
}

DEFAULT_INPUT_DIRS = [
    "/data/stage4_ai_decisions_413d_fixed_fleet_180m",
    "/data/stage4_ai_decisions_414b_fixed_fleet_6h",
    "/data/stage4_ai_decisions_414d_fixed_fleet_6h_clean",
    "/data/stage4_ai_decisions_414f_schema_repair_30m_regression",
]

SECRET_PATTERNS = (
    re.compile(r"gsk_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"csk-[A-Za-z0-9]{20,}"),
)

ALT_SYMBOLS = frozenset({"SOLUSDT", "PEPEUSDT"})
WATCHLIST_EXPIRE_TICKS = 6


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_side(raw: Any) -> str:
    side = str(raw or "NONE").upper()
    if side in {"BUY", "LONG"}:
        return "LONG"
    if side in {"SELL", "SHORT"}:
        return "SHORT"
    return "NONE"


def _normalize_regime(decision: Dict[str, Any]) -> str:
    mc = decision.get("market_context") or {}
    raw = str(decision.get("regime") or mc.get("regime") or "unknown").lower()
    if "volatile" in raw:
        return "volatile"
    if "trend" in raw:
        return "trend"
    if "range" in raw:
        return "range"
    return "unknown"


def _volatility_level(decision: Dict[str, Any]) -> str:
    mc = decision.get("market_context") or {}
    level = str(mc.get("volatility_level") or "unknown").lower()
    if level in {"low", "medium", "high"}:
        return level
    return "unknown"


def _mae_proxy_pct(decision: Dict[str, Any]) -> float:
    """Backward-compatible alias — prefer get_paper_mae_pct() for paper guards."""
    return legacy_market_mae_proxy_pct(decision)


def _reference_price(decision: Dict[str, Any]) -> float:
    mc = decision.get("market_context") or {}
    return _safe_float(mc.get("last_price"))


def _paper_event_id(decision: Dict[str, Any], symbol: str) -> str:
    did = str(decision.get("decision_id") or "unknown")
    digest = hashlib.sha256(did.encode()).hexdigest()[:6]
    ts = str(decision.get("created_at_utc") or "unknown").replace(":", "").replace("-", "")
    return f"pevt_{ts}_{symbol}_{digest}"


def _watchlist_id(symbol: str, first_decision_id: str) -> str:
    digest = hashlib.sha256(first_decision_id.encode()).hexdigest()[:6]
    return f"wl_{symbol}_{digest}"


def _side_aligns_with_trend(decision: Dict[str, Any], side: str) -> bool:
    mc = decision.get("market_context") or {}
    trend15 = str(mc.get("trend_15m") or "").lower()
    if not trend15 or side == "NONE":
        return False
    if trend15 in {"up", "bull", "long"}:
        return side == "LONG"
    if trend15 in {"down", "bear", "short"}:
        return side == "SHORT"
    return True


def _provider_chain_failed(decision: Dict[str, Any]) -> bool:
    if decision.get("provider_chain_failed"):
        return True
    pet = str(decision.get("parse_error_type") or "")
    return pet in {"provider_chain_failed", "provider_exhaustion", "all_providers_failed"}


def _hard_block_enter(decision: Dict[str, Any]) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    if decision.get("parse_error"):
        reasons.append("parse_error")
    if decision.get("is_mock_ai"):
        reasons.append("mock_ai")
    if decision.get("order_sent"):
        reasons.append("order_sent")
    if str(decision.get("schema_repair_mode") or "") == "safe_skip_defaults":
        reasons.append("schema_safe_skip_repair")
    if _provider_chain_failed(decision):
        reasons.append("provider_chain_failed")
    if not str(decision.get("provider") or "").strip():
        reasons.append("missing_provider")
    from tools.research.stage4_paper_readiness import infer_decision_quality_incomplete

    if infer_decision_quality_incomplete(decision):
        reasons.append("decision_quality_incomplete")
    from tools.research.stage4_paper_readiness import infer_paper_readiness_mae_block

    if infer_paper_readiness_mae_block(decision):
        reasons.append("paper_readiness_mae_block")
    return bool(reasons), reasons


@dataclass
class GuardStats:
    sol: int = 0
    pepe: int = 0
    mae: int = 0
    trend: int = 0


@dataclass
class WatchlistState:
    watchlist_id: str
    symbol: str
    source_dataset: str
    first_decision_id: str
    first_tick_index: int
    last_tick_index: int
    confirmation_count: int = 1
    confirmation_threshold: int = 2
    side_bias: str = "NONE"
    first_confidence: float = 0.0
    last_confidence: float = 0.0
    regimes: List[str] = field(default_factory=list)

    def touch(self, decision: Dict[str, Any], *, threshold: int) -> None:
        self.last_tick_index = _safe_int(decision.get("tick_index"))
        self.last_confidence = _safe_float(decision.get("confidence"))
        self.confirmation_threshold = threshold
        side = _normalize_side(decision.get("candidate_side"))
        if side != "NONE":
            self.side_bias = side
        regime = _normalize_regime(decision)
        self.regimes.append(regime)
        intent = str(decision.get("decision_intent") or "").lower()
        if intent in {"watch", "enter_candidate"}:
            self.confirmation_count += 1

    def expired(self, tick_index: int) -> bool:
        return tick_index - self.last_tick_index > WATCHLIST_EXPIRE_TICKS

    def confirmed(self) -> bool:
        return self.confirmation_count >= self.confirmation_threshold

    def confidence_non_decreasing(self) -> bool:
        return self.last_confidence >= self.first_confidence - 0.05


@dataclass
class MaeSourceStats:
    llm: int = 0
    legacy: int = 0
    missing: int = 0

    def record(self, source: str) -> None:
        if source == MAE_SOURCE_LLM:
            self.llm += 1
        elif source == MAE_SOURCE_LEGACY:
            self.legacy += 1
        else:
            self.missing += 1

    def to_summary(self) -> Dict[str, Any]:
        return {
            "mae_source_distribution": {
                MAE_SOURCE_LLM: self.llm,
                MAE_SOURCE_LEGACY: self.legacy,
                MAE_SOURCE_MISSING: self.missing,
            },
            "llm_mae_used_count": self.llm,
            "legacy_mae_proxy_used_count": self.legacy,
            "missing_mae_source_count": self.missing,
        }


@dataclass
class GuardResult:
    verdict: str
    reasons: List[str] = field(default_factory=list)
    sol_fired: bool = False
    pepe_fired: bool = False
    mae_fired: bool = False
    trend_fired: bool = False
    confirmation_threshold: int = 2
    paper_mae_pct: float = 0.0
    paper_mae_source: str = MAE_SOURCE_LEGACY


def apply_paper_guards(
    decision: Dict[str, Any],
    *,
    intent: str,
    side: str,
    watchlist: Optional[WatchlistState] = None,
    mae_source_mode: str = "llm_mae_primary",
) -> GuardResult:
    """Stage 4.16 watch-quality guards (design-only, no order path)."""
    symbol = str(decision.get("symbol") or "").upper()
    regime = _normalize_regime(decision)
    vol_level = _volatility_level(decision)
    confidence = _safe_float(decision.get("confidence"))
    mae_proxy, mae_source = get_paper_mae_pct(decision, mae_source_mode=mae_source_mode)
    mae_cap = MAE_CAPS_PCT.get(symbol, 0.35)
    intent_l = intent.lower()
    reasons: List[str] = []
    result = GuardResult(
        verdict="allow",
        confirmation_threshold=2,
        paper_mae_pct=mae_proxy,
        paper_mae_source=mae_source,
    )

    # 1. SOL guard
    if symbol == "SOLUSDT":
        fired = False
        if regime == "volatile" and vol_level == "high":
            if intent_l in {"watch", "enter_candidate"}:
                result.verdict = "downgrade_to_skip"
                reasons.append("sol_vol_block")
                fired = True
        elif regime == "trend" and mae_proxy > 0.25:
            result.verdict = "downgrade_to_skip"
            reasons.append("sol_trend_mae")
            fired = True
        elif confidence < 0.45 and regime == "volatile":
            result.verdict = "downgrade_to_skip"
            reasons.append("sol_low_conf_vol")
            fired = True
        if fired:
            result.sol_fired = True

    # 2. PEPE guard
    if symbol == "PEPEUSDT":
        fired = False
        if intent_l == "enter_candidate" and (watchlist is None or not watchlist.confirmed()):
            result.verdict = "downgrade_to_watchlist"
            reasons.append("pepe_watchlist_required")
            fired = True
        elif regime == "volatile" or vol_level == "high":
            if intent_l == "enter_candidate":
                result.verdict = "downgrade_to_skip"
                reasons.append("pepe_vol_cap")
            else:
                result.verdict = "allow"
                reasons.append("pepe_watchlist_only")
            fired = True
        elif mae_proxy > 0.20:
            result.verdict = "downgrade_to_skip"
            reasons.append("pepe_mae_cap")
            fired = True
        if fired:
            result.pepe_fired = True

    # 3. MAE guard
    if intent_l == "watch" and mae_proxy > mae_cap * 0.80:
        result.verdict = "downgrade_to_skip"
        reasons.append("mae_watch_downgrade")
        result.mae_fired = True
    elif intent_l == "enter_candidate" and mae_proxy > mae_cap * 0.60:
        if result.verdict == "allow":
            result.verdict = "downgrade_to_watchlist"
        reasons.append("mae_enter_downgrade")
        result.mae_fired = True

    # 4. Trend guard
    if regime == "trend" and symbol in ALT_SYMBOLS and intent_l == "watch":
        result.confirmation_threshold = 3
        result.trend_fired = True
        reasons.append("trend_watchlist_threshold_3")
    elif regime == "trend" and intent_l == "enter_candidate" and side == "NONE":
        result.verdict = "downgrade_to_watchlist"
        reasons.append("trend_side_unclear")
        result.trend_fired = True
    elif regime == "trend" and symbol in ALT_SYMBOLS and confidence < 0.55 and intent_l == "enter_candidate":
        result.verdict = "downgrade_to_skip"
        reasons.append("trend_alt_low_conf")
        result.trend_fired = True

    result.reasons = reasons
    return result


def _hypothetical_prices(symbol: str, side: str, entry: float) -> Tuple[float, float, float, int]:
    sl_pct, tp_pct, hold = SYMBOL_SL_TP_HOLD.get(symbol, (0.35, 0.60, 60))
    if entry <= 0 or side == "NONE":
        return 0.0, 0.0, 0.0, hold
    if side == "LONG":
        return entry, entry * (1 - sl_pct / 100), entry * (1 + tp_pct / 100), hold
    return entry, entry * (1 + sl_pct / 100), entry * (1 - tp_pct / 100), hold


def _quality_blocked_skip_reason(decision: Dict[str, Any]) -> Optional[str]:
    from tools.research.stage4_paper_readiness import (
        infer_decision_quality_incomplete,
        infer_paper_readiness_mae_block,
    )

    if infer_paper_readiness_mae_block(decision):
        return "paper_readiness_mae_block"
    if infer_decision_quality_incomplete(decision):
        return "decision_quality_incomplete"
    return None


def build_quality_blocked_skip_event(
    decision: Dict[str, Any],
    *,
    source_dataset: str,
    reason: str,
) -> Dict[str, Any]:
    symbol = str(decision.get("symbol") or "").upper()
    ref_price = _reference_price(decision)
    mae_pct, mae_src = get_paper_mae_pct(decision)
    return _build_event(
        decision,
        source_dataset=source_dataset,
        paper_action="hypothetical_skip",
        side="NONE",
        ref_price=ref_price,
        verdict="block",
        reasons=[reason],
        watchlist_meta={
            "required": False,
            "watchlist_id": None,
            "confirmation_count": 0,
            "confirmation_threshold": 2,
        },
        paper_mae_pct=mae_pct,
        paper_mae_source=mae_src,
    )


def is_eligible_decision(decision: Dict[str, Any]) -> bool:
    if decision.get("parse_error"):
        return False
    if decision.get("is_mock_ai"):
        return False
    if decision.get("order_sent"):
        return False
    if _quality_blocked_skip_reason(decision):
        return False
    return True


def classify_paper_event(
    decision: Dict[str, Any],
    *,
    source_dataset: str,
    watchlists: Dict[str, WatchlistState],
    guard_stats: Optional[GuardStats] = None,
    mae_source_stats: Optional[MaeSourceStats] = None,
) -> Optional[Dict[str, Any]]:
    """Map one eligible decision to a hypothetical paper event."""
    if not is_eligible_decision(decision):
        return None

    symbol = str(decision.get("symbol") or "").upper()
    intent = str(decision.get("decision_intent") or "unknown").lower()
    side = _normalize_side(decision.get("candidate_side"))
    confidence = _safe_float(decision.get("confidence"))
    ref_price = _reference_price(decision)
    tick_index = _safe_int(decision.get("tick_index"))
    wl_key = f"{source_dataset}:{symbol}"

    existing = watchlists.get(wl_key)
    if existing and existing.expired(tick_index):
        watchlists.pop(wl_key, None)
        existing = None

    guard_stats = guard_stats or GuardStats()
    mae_source_stats = mae_source_stats or MaeSourceStats()
    enter_downgraded = False
    enter_allowed = False

    def _mae_event_kwargs(guard: Optional[GuardResult] = None) -> Dict[str, Any]:
        if guard is not None:
            return {
                "paper_mae_pct": guard.paper_mae_pct,
                "paper_mae_source": guard.paper_mae_source,
            }
        mae_pct, mae_src = get_paper_mae_pct(decision)
        mae_source_stats.record(mae_src)
        return {"paper_mae_pct": mae_pct, "paper_mae_source": mae_src}

    # --- skip intents ---
    if intent in {"hard_skip", "soft_skip"}:
        verdict = "downgrade_to_skip" if intent == "soft_skip" else "block"
        return _build_event(
            decision,
            source_dataset=source_dataset,
            paper_action="hypothetical_skip",
            side="NONE",
            ref_price=ref_price,
            verdict=verdict,
            reasons=[f"{intent}_intent"],
            watchlist_meta={"required": False, "watchlist_id": None, "confirmation_count": 0, "confirmation_threshold": 2},
            **_mae_event_kwargs(),
        )

    guard = apply_paper_guards(decision, intent=intent, side=side, watchlist=existing)
    if guard.sol_fired:
        guard_stats.sol += 1
    if guard.pepe_fired:
        guard_stats.pepe += 1
    if guard.mae_fired:
        guard_stats.mae += 1
    if guard.trend_fired:
        guard_stats.trend += 1
    mae_source_stats.record(guard.paper_mae_source)
    mae_kwargs = _mae_event_kwargs(guard)

    # --- watch intent ---
    if intent == "watch":
        if guard.verdict == "downgrade_to_skip":
            return _build_event(
                decision,
                source_dataset=source_dataset,
                paper_action="hypothetical_skip",
                side="NONE",
                ref_price=ref_price,
                verdict="downgrade_to_skip",
                reasons=guard.reasons,
                watchlist_meta={"required": False, "watchlist_id": None, "confirmation_count": 0, "confirmation_threshold": guard.confirmation_threshold},
                **mae_kwargs,
            )

        if existing is None:
            did = str(decision.get("decision_id") or "")
            existing = WatchlistState(
                watchlist_id=_watchlist_id(symbol, did),
                symbol=symbol,
                source_dataset=source_dataset,
                first_decision_id=did,
                first_tick_index=tick_index,
                last_tick_index=tick_index,
                confirmation_count=1,
                confirmation_threshold=guard.confirmation_threshold,
                side_bias=side if side != "NONE" else "NONE",
                first_confidence=confidence,
                last_confidence=confidence,
                regimes=[_normalize_regime(decision)],
            )
            watchlists[wl_key] = existing
        else:
            existing.touch(decision, threshold=guard.confirmation_threshold)

        return _build_event(
            decision,
            source_dataset=source_dataset,
            paper_action="watchlist",
            side=side if side != "NONE" else existing.side_bias,
            ref_price=ref_price,
            verdict="allow",
            reasons=guard.reasons,
            watchlist_meta={
                "required": True,
                "watchlist_id": existing.watchlist_id,
                "confirmation_count": existing.confirmation_count,
                "confirmation_threshold": existing.confirmation_threshold,
            },
            **mae_kwargs,
        )

    # --- enter_candidate ---
    if intent == "enter_candidate":
        blocked, block_reasons = _hard_block_enter(decision)
        if blocked:
            return _build_event(
                decision,
                source_dataset=source_dataset,
                paper_action="hypothetical_skip",
                side="NONE",
                ref_price=ref_price,
                verdict="block",
                reasons=block_reasons,
                watchlist_meta={"required": False, "watchlist_id": None, "confirmation_count": 0, "confirmation_threshold": 2},
                enter_downgraded=True,
                **mae_kwargs,
            )

        floor = CONFIDENCE_FLOORS.get(symbol, 0.35)
        if side == "NONE":
            return _build_event(
                decision,
                source_dataset=source_dataset,
                paper_action="watchlist",
                side="NONE",
                ref_price=ref_price,
                verdict="downgrade_to_watchlist",
                reasons=["candidate_side_none"],
                watchlist_meta={"required": True, "watchlist_id": existing.watchlist_id if existing else None, "confirmation_count": existing.confirmation_count if existing else 0, "confirmation_threshold": guard.confirmation_threshold},
                enter_downgraded=True,
                **mae_kwargs,
            )

        if confidence < floor:
            enter_downgraded = True
            return _build_event(
                decision,
                source_dataset=source_dataset,
                paper_action="hypothetical_skip",
                side=side,
                ref_price=ref_price,
                verdict="downgrade_to_skip",
                reasons=[f"confidence_below_floor_{floor}"],
                watchlist_meta={"required": False, "watchlist_id": None, "confirmation_count": 0, "confirmation_threshold": 2},
                enter_downgraded=True,
                **mae_kwargs,
            )

        if guard.verdict in {"downgrade_to_skip", "block"}:
            enter_downgraded = True
            return _build_event(
                decision,
                source_dataset=source_dataset,
                paper_action="hypothetical_skip",
                side=side,
                ref_price=ref_price,
                verdict=guard.verdict if guard.verdict != "allow" else "downgrade_to_skip",
                reasons=guard.reasons,
                watchlist_meta={"required": False, "watchlist_id": None, "confirmation_count": 0, "confirmation_threshold": guard.confirmation_threshold},
                enter_downgraded=True,
                **mae_kwargs,
            )

        if guard.verdict == "downgrade_to_watchlist":
            enter_downgraded = True
            if existing is None:
                did = str(decision.get("decision_id") or "")
                existing = WatchlistState(
                    watchlist_id=_watchlist_id(symbol, did),
                    symbol=symbol,
                    source_dataset=source_dataset,
                    first_decision_id=did,
                    first_tick_index=tick_index,
                    last_tick_index=tick_index,
                    confirmation_count=1,
                    confirmation_threshold=guard.confirmation_threshold,
                    side_bias=side,
                    first_confidence=confidence,
                    last_confidence=confidence,
                )
                watchlists[wl_key] = existing
            return _build_event(
                decision,
                source_dataset=source_dataset,
                paper_action="watchlist",
                side=side,
                ref_price=ref_price,
                verdict="downgrade_to_watchlist",
                reasons=guard.reasons,
                watchlist_meta={
                    "required": True,
                    "watchlist_id": existing.watchlist_id,
                    "confirmation_count": existing.confirmation_count,
                    "confirmation_threshold": existing.confirmation_threshold,
                },
                enter_downgraded=True,
                **mae_kwargs,
            )

        # SOL/PEPE require watchlist confirmation
        if symbol in ALT_SYMBOLS:
            if existing is None or not existing.confirmed() or not existing.confidence_non_decreasing():
                enter_downgraded = True
                if existing is None:
                    did = str(decision.get("decision_id") or "")
                    existing = WatchlistState(
                        watchlist_id=_watchlist_id(symbol, did),
                        symbol=symbol,
                        source_dataset=source_dataset,
                        first_decision_id=did,
                        first_tick_index=tick_index,
                        last_tick_index=tick_index,
                        confirmation_count=1,
                        confirmation_threshold=max(2, guard.confirmation_threshold),
                        side_bias=side,
                        first_confidence=confidence,
                        last_confidence=confidence,
                    )
                    watchlists[wl_key] = existing
                else:
                    existing.touch(decision, threshold=max(2, guard.confirmation_threshold))
                return _build_event(
                    decision,
                    source_dataset=source_dataset,
                    paper_action="watchlist",
                    side=side,
                    ref_price=ref_price,
                    verdict="downgrade_to_watchlist",
                    reasons=["alt_watchlist_confirmation_required"],
                    watchlist_meta={
                        "required": True,
                        "watchlist_id": existing.watchlist_id,
                        "confirmation_count": existing.confirmation_count,
                        "confirmation_threshold": existing.confirmation_threshold,
                    },
                    enter_downgraded=True,
                    **mae_kwargs,
                )

        # BTC/ETH may skip watchlist if elevated confidence in trend
        if symbol in {"BTCUSDT", "ETHUSDT"}:
            regime = _normalize_regime(decision)
            major_direct_ok = confidence >= floor + 0.05 and (
                regime in {"range", "unknown"} or (regime == "trend" and _side_aligns_with_trend(decision, side))
            )
            if not major_direct_ok and (existing is None or not existing.confirmed()):
                enter_downgraded = True
                return _build_event(
                    decision,
                    source_dataset=source_dataset,
                    paper_action="watchlist",
                    side=side,
                    ref_price=ref_price,
                    verdict="downgrade_to_watchlist",
                    reasons=["major_watchlist_or_trend_required"],
                    watchlist_meta={
                        "required": True,
                        "watchlist_id": existing.watchlist_id if existing else None,
                        "confirmation_count": existing.confirmation_count if existing else 0,
                        "confirmation_threshold": 2,
                    },
                    enter_downgraded=True,
                    **mae_kwargs,
                )

        enter_allowed = True
        entry, sl, tp, hold = _hypothetical_prices(symbol, side, ref_price)
        return _build_event(
            decision,
            source_dataset=source_dataset,
            paper_action="hypothetical_entry",
            side=side,
            ref_price=ref_price,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            max_hold=hold,
            verdict="allow",
            reasons=guard.reasons,
            watchlist_meta={
                "required": bool(existing),
                "watchlist_id": existing.watchlist_id if existing else None,
                "confirmation_count": existing.confirmation_count if existing else 0,
                "confirmation_threshold": existing.confirmation_threshold if existing else 2,
            },
            enter_allowed=enter_allowed,
            enter_downgraded=enter_downgraded,
            **mae_kwargs,
        )

    # unknown intent → skip
    return _build_event(
        decision,
        source_dataset=source_dataset,
        paper_action="hypothetical_skip",
        side="NONE",
        ref_price=ref_price,
        verdict="block",
        reasons=[f"unknown_intent_{intent}"],
        watchlist_meta={"required": False, "watchlist_id": None, "confirmation_count": 0, "confirmation_threshold": 2},
        **_mae_event_kwargs(),
    )


def _build_event(
    decision: Dict[str, Any],
    *,
    source_dataset: str,
    paper_action: str,
    side: str,
    ref_price: float,
    verdict: str,
    reasons: List[str],
    watchlist_meta: Dict[str, Any],
    entry_price: float = 0.0,
    stop_loss: float = 0.0,
    take_profit: float = 0.0,
    max_hold: int = 0,
    enter_allowed: bool = False,
    enter_downgraded: bool = False,
    paper_mae_pct: Optional[float] = None,
    paper_mae_source: Optional[str] = None,
) -> Dict[str, Any]:
    symbol = str(decision.get("symbol") or "").upper()
    mae_pct, mae_src = (
        (paper_mae_pct, paper_mae_source)
        if paper_mae_pct is not None and paper_mae_source is not None
        else get_paper_mae_pct(decision)
    )
    event = {
        "record_type": RECORD_TYPE,
        "paper_event_id": _paper_event_id(decision, symbol),
        "source_decision_id": decision.get("decision_id"),
        "source_dataset": source_dataset,
        "source_tick_index": _safe_int(decision.get("tick_index")),
        "timestamp_utc": decision.get("created_at_utc"),
        "symbol": symbol,
        "decision_intent": decision.get("decision_intent"),
        "final_action": decision.get("final_action"),
        "paper_action": paper_action,
        "candidate_side": side,
        "reference_price": round(ref_price, 8) if ref_price else 0.0,
        "hypothetical_entry_price": round(entry_price, 8) if entry_price else 0.0,
        "hypothetical_stop_loss": round(stop_loss, 8) if stop_loss else 0.0,
        "hypothetical_take_profit": round(take_profit, 8) if take_profit else 0.0,
        "hypothetical_max_hold_minutes": max_hold,
        "risk_governor_verdict": verdict,
        "risk_governor_reasons": reasons,
        "watchlist_follow_up": watchlist_meta,
        "provider": decision.get("provider"),
        "confidence": _safe_float(decision.get("confidence")),
        "market_regime": _normalize_regime(decision),
        "volatility_level": _volatility_level(decision),
        "shadow_prior_bad_watch_rate": SHADOW_PRIOR_BAD_WATCH_RATE.get(symbol, 0.0),
        "parse_error": bool(decision.get("parse_error")),
        "schema_repaired": bool(decision.get("schema_repaired")),
        "schema_repair_mode": decision.get("schema_repair_mode"),
        "order_sent": False,
        "is_mock_ai": bool(decision.get("is_mock_ai")),
        "created_by": CREATED_BY,
        "design_gate_version": DESIGN_GATE_VERSION,
        "paper_mae_pct": round(mae_pct, 6),
        "paper_mae_source": mae_src,
        "llm_mae_risk_estimate_pct": round(llm_mae_risk_estimate_pct(decision), 6),
    }
    if enter_allowed:
        event["_enter_allowed"] = True
    if enter_downgraded:
        event["_enter_downgraded"] = True
    return event


def _sort_key(row: Dict[str, Any], dataset: str) -> Tuple[str, int, str]:
    return (
        dataset,
        _safe_int(row.get("tick_index")),
        str(row.get("created_at_utc") or ""),
    )


def load_existing_event_keys(path: Path) -> Set[Tuple[str, str]]:
    keys: Set[Tuple[str, str]] = set()
    for row in _read_jsonl(path):
        keys.add((str(row.get("source_dataset") or ""), str(row.get("source_decision_id") or "")))
    return keys


def build_summary(
    *,
    datasets_analyzed: Sequence[str],
    missing_datasets: Sequence[str],
    total_decisions_read: int,
    events: Sequence[Dict[str, Any]],
    guard_stats: GuardStats,
    excluded_parse: int,
    excluded_mock: int,
    excluded_order: int,
    excluded_quality_incomplete: int = 0,
    paper_readiness_metrics: Optional[Dict[str, int]] = None,
    mae_source_stats: Optional[MaeSourceStats] = None,
) -> Dict[str, Any]:
    paper_actions = Counter(str(e.get("paper_action") or "unknown") for e in events)
    verdicts = Counter(str(e.get("risk_governor_verdict") or "unknown") for e in events)
    reason_counts: Counter[str] = Counter()
    per_symbol: Counter[str] = Counter()
    per_symbol_actions: Dict[str, Counter[str]] = defaultdict(Counter)

    watchlist_count = 0
    hypothetical_entry_count = 0
    hypothetical_skip_count = 0
    enter_allowed = 0
    enter_downgraded = 0

    for e in events:
        sym = str(e.get("symbol") or "unknown")
        action = str(e.get("paper_action") or "")
        per_symbol[sym] += 1
        per_symbol_actions[sym][action] += 1
        if action == "watchlist":
            watchlist_count += 1
        elif action == "hypothetical_entry":
            hypothetical_entry_count += 1
        elif action == "hypothetical_skip":
            hypothetical_skip_count += 1
        if e.get("_enter_allowed"):
            enter_allowed += 1
        if e.get("_enter_downgraded"):
            enter_downgraded += 1
        for r in e.get("risk_governor_reasons") or []:
            reason_counts[str(r)] += 1

    clean_events = []
    for e in events:
        row = dict(e)
        row.pop("_enter_allowed", None)
        row.pop("_enter_downgraded", None)
        clean_events.append(row)

    summary = {
        "record_type": "stage4_17_paper_event_summary",
        "generated_at_utc": utc_now_iso(),
        "datasets_analyzed": list(datasets_analyzed),
        "missing_datasets": list(missing_datasets),
        "total_decisions_read": total_decisions_read,
        "total_events_written": len(clean_events),
        "excluded_parse_error_count": excluded_parse,
        "excluded_mock_ai_count": excluded_mock,
        "excluded_order_sent_count": excluded_order,
        "excluded_decision_quality_incomplete_count": excluded_quality_incomplete,
        "paper_action_distribution": dict(paper_actions),
        "per_symbol_event_counts": dict(per_symbol),
        "per_symbol_paper_action_distribution": {k: dict(v) for k, v in per_symbol_actions.items()},
        "risk_governor_verdict_distribution": dict(verdicts),
        "risk_governor_reason_counts": dict(reason_counts),
        "watchlist_count": watchlist_count,
        "hypothetical_entry_count": hypothetical_entry_count,
        "hypothetical_skip_count": hypothetical_skip_count,
        "enter_candidate_allowed_count": enter_allowed,
        "enter_candidate_downgraded_count": enter_downgraded,
        "sol_guard_fired_count": guard_stats.sol,
        "pepe_guard_fired_count": guard_stats.pepe,
        "mae_guard_fired_count": guard_stats.mae,
        "trend_guard_fired_count": guard_stats.trend,
        "mock_ai_used_count": 0,
        "order_sent_count": 0,
        "any_exchange_call_made": False,
        "production_touched": False,
        "btc_auto_touched": False,
        **(paper_readiness_metrics or {}),
        "events": clean_events,
    }
    if mae_source_stats is not None:
        summary.update(mae_source_stats.to_summary())
    return summary


def strip_events_for_output(summary: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(summary)
    out.pop("events", None)
    return out


def run_paper_event_logger(
    input_dirs: Sequence[str | Path],
    *,
    output_dir: str | Path,
    mode: str = "append-only",
) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "hypothetical_entry_log.jsonl"

    existing_keys: Set[Tuple[str, str]] = set()
    if mode == "append-only" and log_path.is_file():
        existing_keys = load_existing_event_keys(log_path)
    elif mode != "append-only":
        if log_path.is_file():
            log_path.unlink()

    datasets_analyzed: List[str] = []
    missing_datasets: List[str] = []
    all_rows: List[Tuple[str, Dict[str, Any]]] = []
    total_read = 0
    excluded_parse = excluded_mock = excluded_order = excluded_quality = 0
    from tools.research.stage4_paper_readiness import (
        build_mae_calibration_metrics,
        build_paper_readiness_metrics,
        infer_decision_quality_incomplete,
    )

    for raw_dir in input_dirs:
        dpath = Path(raw_dir)
        canonical = str(raw_dir)
        jsonl = dpath / "ai_decisions.jsonl"
        if not jsonl.is_file():
            missing_datasets.append(canonical)
            continue
        datasets_analyzed.append(canonical)
        rows = _read_jsonl(jsonl)
        total_read += len(rows)
        for row in rows:
            if row.get("parse_error"):
                excluded_parse += 1
            if row.get("is_mock_ai"):
                excluded_mock += 1
            if row.get("order_sent"):
                excluded_order += 1
            if infer_decision_quality_incomplete(row):
                excluded_quality += 1
            all_rows.append((canonical, row))

    all_rows.sort(key=lambda item: _sort_key(item[1], item[0]))

    watchlists: Dict[str, WatchlistState] = {}
    guard_stats = GuardStats()
    mae_source_stats = MaeSourceStats()
    events: List[Dict[str, Any]] = []
    written = 0

    with log_path.open("a", encoding="utf-8") as fh:
        for dataset, decision in all_rows:
            if decision.get("parse_error") or decision.get("is_mock_ai") or decision.get("order_sent"):
                continue
            did = str(decision.get("decision_id") or "")
            key = (dataset, did)
            if key in existing_keys:
                continue

            quality_reason = _quality_blocked_skip_reason(decision)
            if quality_reason:
                event = build_quality_blocked_skip_event(
                    decision,
                    source_dataset=dataset,
                    reason=quality_reason,
                )
                mae_source_stats.record(str(event.get("paper_mae_source") or MAE_SOURCE_MISSING))
            elif not is_eligible_decision(decision):
                continue
            else:
                event = classify_paper_event(
                    decision,
                    source_dataset=dataset,
                    watchlists=watchlists,
                    guard_stats=guard_stats,
                    mae_source_stats=mae_source_stats,
                )
            if not event:
                continue
            events.append(event)
            row = dict(event)
            row.pop("_enter_allowed", None)
            row.pop("_enter_downgraded", None)
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            existing_keys.add(key)
            written += 1

    summary = build_summary(
        datasets_analyzed=datasets_analyzed,
        missing_datasets=missing_datasets,
        total_decisions_read=total_read,
        events=events,
        guard_stats=guard_stats,
        excluded_parse=excluded_parse,
        excluded_mock=excluded_mock,
        excluded_order=excluded_order,
        excluded_quality_incomplete=excluded_quality,
        paper_readiness_metrics=build_paper_readiness_metrics([r for _, r in all_rows]),
        mae_source_stats=mae_source_stats,
    )
    summary.update(build_mae_calibration_metrics([r for _, r in all_rows]))
    write_json(output_dir / "stage4_17_paper_event_summary.json", strip_events_for_output(summary))
    return summary


def render_report(summary: Dict[str, Any]) -> str:
    lines = [
        "# Stage 4.17-A — Paper Event Logger Report",
        "",
        f"**Generated:** {summary.get('generated_at_utc', 'unknown')}  ",
        f"**Mode:** append-only hypothetical JSONL — **no execution**",
        "",
        "## 1. Executive summary",
        "",
        f"- Decisions read: **{summary.get('total_decisions_read', 0)}**",
        f"- Paper events written: **{summary.get('total_events_written', 0)}**",
        f"- Hypothetical entries: **{summary.get('hypothetical_entry_count', 0)}**",
        f"- Watchlist events: **{summary.get('watchlist_count', 0)}**",
        f"- Hypothetical skips: **{summary.get('hypothetical_skip_count', 0)}**",
        f"- Enter candidate allowed: **{summary.get('enter_candidate_allowed_count', 0)}**",
        f"- Enter candidate downgraded: **{summary.get('enter_candidate_downgraded_count', 0)}**",
        "",
        "## 2. Inputs analyzed",
        "",
    ]
    for ds in summary.get("datasets_analyzed") or []:
        lines.append(f"- `{ds}`")
    for ds in summary.get("missing_datasets") or []:
        lines.append(f"- **MISSING:** `{ds}`")
    lines.extend(
        [
            "",
            "## 3. Paper event schema implemented",
            "",
            "See `tools/research/stage4_paper_event_logger.py` — `record_type=stage4_hypothetical_paper_event`.",
            "",
            "## 4. Paper action distribution",
            "",
            "```json",
            json.dumps(summary.get("paper_action_distribution") or {}, indent=2),
            "```",
            "",
            "## 5. Per-symbol paper event distribution",
            "",
            "```json",
            json.dumps(summary.get("per_symbol_paper_action_distribution") or {}, indent=2),
            "```",
            "",
            "## 6. Risk Governor guard results",
            "",
            f"- SOL guard fired: **{summary.get('sol_guard_fired_count', 0)}**",
            f"- PEPE guard fired: **{summary.get('pepe_guard_fired_count', 0)}**",
            f"- MAE guard fired: **{summary.get('mae_guard_fired_count', 0)}**",
            f"- Trend guard fired: **{summary.get('trend_guard_fired_count', 0)}**",
            "",
            "```json",
            json.dumps(summary.get("risk_governor_reason_counts") or {}, indent=2),
            "```",
            "",
            "## 7. Watchlist vs hypothetical entry",
            "",
            f"| Metric | Count |",
            f"|--------|-------|",
            f"| watchlist | {summary.get('watchlist_count', 0)} |",
            f"| hypothetical_entry | {summary.get('hypothetical_entry_count', 0)} |",
            f"| hypothetical_skip | {summary.get('hypothetical_skip_count', 0)} |",
            "",
            "## 8. Safety confirmation",
            "",
            f"- mock_ai_used_count: **{summary.get('mock_ai_used_count', 0)}**",
            f"- order_sent_count: **{summary.get('order_sent_count', 0)}**",
            f"- any_exchange_call_made: **{summary.get('any_exchange_call_made', False)}**",
            f"- production_touched: **{summary.get('production_touched', False)}**",
            f"- btc_auto_touched: **{summary.get('btc_auto_touched', False)}**",
            "",
            "## 9. Why this is still not execution",
            "",
            "This logger only appends hypothetical paper events derived from existing AI decisions. "
            "It does not call exchange APIs, does not submit demo orders, and sets `order_sent=false` on every record.",
            "",
            "## 10. Recommended Stage 4.18 next gate",
            "",
            "**Option B — Watchlist follow-up simulator** on historical decisions + paper logs; "
            "evaluate graduation rate and hypothetical exit outcomes offline. Still no orders.",
            "",
            "**final_verdict:** `STAGE_4_17A_PAPER_EVENT_LOGGER_COMPLETE`",
            "",
            "**Stopped at gate — Stage 4.18 requires explicit operator approval.**",
            "",
        ]
    )
    return "\n".join(lines)


def contains_secret(text: str) -> bool:
    return any(p.search(text) for p in SECRET_PATTERNS)


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4.17-A paper event logger (no orders)")
    parser.add_argument("--input-dir", action="append", dest="input_dirs", default=[])
    parser.add_argument("--output-dir", default="/data/stage4_paper_events")
    parser.add_argument("--mode", default="append-only", choices=["append-only", "overwrite"])
    parser.add_argument("--report-path", default=str(ROOT / "docs/reports/STAGE_4_17A_PAPER_EVENT_LOGGER_REPORT.md"))
    args = parser.parse_args()

    input_dirs = args.input_dirs or DEFAULT_INPUT_DIRS
    summary = run_paper_event_logger(input_dirs, output_dir=args.output_dir, mode=args.mode)

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_text = render_report(strip_events_for_output(summary))
    if contains_secret(report_text):
        raise SystemExit("Report contains suspected secret pattern — aborting")
    report_path.write_text(report_text, encoding="utf-8")

    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir),
                "total_events_written": summary.get("total_events_written"),
                "hypothetical_entry_count": summary.get("hypothetical_entry_count"),
                "watchlist_count": summary.get("watchlist_count"),
                "report_path": str(report_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
