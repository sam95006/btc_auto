"""In-memory dynamic symbol/feature blocks from post-trade post-mortem."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional, Set


class DynamicBlocklist:
    def __init__(self):
        self._lock = threading.RLock()
        self._symbol_until: Dict[str, float] = {}
        self._feature_penalties: Dict[str, float] = {}

    def block_symbol(self, symbol: str, minutes: int, reason: str = "") -> None:
        symbol = str(symbol or "").upper()
        if not symbol:
            return
        until = time.time() + max(1, int(minutes)) * 60
        with self._lock:
            self._symbol_until[symbol] = max(self._symbol_until.get(symbol, 0.0), until)

    def is_symbol_blocked(self, symbol: str) -> bool:
        symbol = str(symbol or "").upper()
        now = time.time()
        with self._lock:
            until = self._symbol_until.get(symbol, 0.0)
            if until and until > now:
                return True
            if until:
                self._symbol_until.pop(symbol, None)
        return False

    def add_feature_penalty(self, features: List[str], penalty_points: float, hours: float = 24.0) -> None:
        expiry = time.time() + max(1.0, float(hours)) * 3600.0
        with self._lock:
            for feat in features or []:
                key = str(feat or "").strip().lower()
                if not key:
                    continue
                self._feature_penalties[key] = expiry
        self._macro_penalty_until = expiry
        self._macro_penalty_points = float(penalty_points)

    def macro_penalty(self) -> float:
        if not getattr(self, "_macro_penalty_until", 0) or time.time() > self._macro_penalty_until:
            return 0.0
        return float(getattr(self, "_macro_penalty_points", 0.0) or 0.0)

    def matching_toxic_penalty(self, context: Optional[Dict[str, Any]]) -> float:
        ctx = dict(context or {})
        penalty = self.macro_penalty()
        if penalty <= 0:
            return 0.0
        tags = set()
        if ctx.get("external_oi_stress"):
            tags.add("oi_stress")
        if ctx.get("external_whale_dump_alert"):
            tags.add("high_inflow")
        if str(ctx.get("market_regime_ai") or "").upper() == "HIGH_RISK_MACRO":
            tags.add("macro_bearish")
        with self._lock:
            active = [k for k, exp in self._feature_penalties.items() if exp > time.time()]
        if active and tags.intersection(active):
            return penalty
        return penalty if active else 0.0

    def blocked_symbols(self) -> List[str]:
        now = time.time()
        with self._lock:
            live = [sym for sym, until in self._symbol_until.items() if until > now]
            for sym, until in list(self._symbol_until.items()):
                if until <= now:
                    self._symbol_until.pop(sym, None)
        return sorted(live)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "blocked_symbols": self.blocked_symbols(),
            "macro_penalty": self.macro_penalty(),
        }
