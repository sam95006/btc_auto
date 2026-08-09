"""Alert event model + anti-spam (dedup / cooldown / severity / thresholds / prefs)."""
from __future__ import annotations

import hashlib
import threading
import time
from typing import Any, Optional

from backend.nexus_paid_beta_retention.constants import (
    ALERT_EVENT_TYPES,
    DEFAULT_COOLDOWN_SEC,
    DEFAULT_DEDUP_WINDOW_SEC,
    DEFAULT_MAX_PER_SYMBOL_HOUR,
    SEVERITIES,
)


def _utcnow_ms() -> int:
    return int(time.time() * 1000)


def normalize_event_type(raw: str) -> str:
    key = str(raw or "").strip().upper()
    if key in ALERT_EVENT_TYPES:
        return key
    # Map common radar / scanner labels into the retention contract.
    if key in {"NEW", "RADAR_ENTER"}:
        return "RADAR_NEW"
    if key in {"UP", "RANK_UP"}:
        return "RADAR_UP"
    if key in {"DOWN", "RANK_DOWN"}:
        return "RADAR_DOWN"
    if key in {"OUT", "RADAR_EXIT"}:
        return "RADAR_OUT"
    if "FUND" in key:
        return "FUNDING_EXTREME"
    if key.startswith("OI") or "OPEN_INTEREST" in key:
        return "OI_CHANGE"
    if "RISK" in key:
        return "RISK_CHANGE"
    if "DATA" in key or "STALE" in key or "DEGRAD" in key:
        return "DATA_DEGRADED"
    if "WATCH" in key:
        return "WATCHLIST_EVENT"
    if "ACTIV" in key:
        return "ACTIVITY_ACCELERATION"
    if "STATE" in key or "STAGE" in key:
        return "STATE_CHANGE"
    return "WATCHLIST_EVENT"


def default_prefs() -> dict[str, Any]:
    return {
        "enabled_types": list(ALERT_EVENT_TYPES),
        "min_severity": "INFO",
        "cooldown_sec": DEFAULT_COOLDOWN_SEC,
        "dedup_window_sec": DEFAULT_DEDUP_WINDOW_SEC,
        "max_per_symbol_hour": DEFAULT_MAX_PER_SYMBOL_HOUR,
        "delivery": {"in_app": True, "web_push": False, "email": False},
    }


class AlertAntiSpam:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._recent: dict[str, list[int]] = {}
        self._last_key: dict[str, int] = {}
        self._prefs: dict[str, dict[str, Any]] = {}

    def prefs_for(self, account_id: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._prefs.get(account_id) or default_prefs())

    def set_prefs(self, account_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            cur = self._prefs.get(account_id) or default_prefs()
            next_prefs = {**cur, **{k: v for k, v in patch.items() if k in cur or k == "delivery"}}
            if "delivery" in patch and isinstance(patch["delivery"], dict):
                next_prefs["delivery"] = {
                    **cur.get("delivery", {}),
                    **patch["delivery"],
                    "email": False,  # hard ban large email vendor
                }
            self._prefs[account_id] = next_prefs
            return dict(next_prefs)

    def allow(
        self,
        account_id: str,
        *,
        event_type: str,
        symbol: str,
        severity: str,
        dedup_key: str,
    ) -> tuple[bool, str]:
        prefs = self.prefs_for(account_id)
        et = normalize_event_type(event_type)
        if et not in set(prefs.get("enabled_types") or []):
            return False, "type_disabled"
        sev = str(severity or "INFO").upper()
        if sev not in SEVERITIES:
            sev = "INFO"
        min_sev = str(prefs.get("min_severity") or "INFO").upper()
        if SEVERITIES.index(sev) < SEVERITIES.index(min_sev if min_sev in SEVERITIES else "INFO"):
            return False, "below_severity_threshold"

        now = int(time.time())
        cooldown = int(prefs.get("cooldown_sec") or DEFAULT_COOLDOWN_SEC)
        dedup_window = int(prefs.get("dedup_window_sec") or DEFAULT_DEDUP_WINDOW_SEC)
        max_hour = int(prefs.get("max_per_symbol_hour") or DEFAULT_MAX_PER_SYMBOL_HOUR)
        key = f"{account_id}:{et}:{symbol.upper()}:{dedup_key}"
        sym_key = f"{account_id}:{symbol.upper()}"

        with self._lock:
            last = self._last_key.get(key)
            if last is not None and now - last < dedup_window:
                return False, "dedup"
            if last is not None and now - last < cooldown:
                return False, "cooldown"
            bucket = [t for t in self._recent.get(sym_key, []) if now - t < 3600]
            if len(bucket) >= max_hour:
                return False, "symbol_rate_limit"
            bucket.append(now)
            self._recent[sym_key] = bucket
            self._last_key[key] = now
            return True, "ok"


def build_alert_event(
    *,
    event_type: str,
    symbol: str,
    severity: str = "MEDIUM",
    headline: str,
    metric: Optional[dict[str, Any]] = None,
    source: str = "retention",
    link: Optional[str] = None,
) -> dict[str, Any]:
    et = normalize_event_type(event_type)
    sym = str(symbol or "").upper()
    ts = _utcnow_ms()
    raw = f"{et}:{sym}:{ts}:{headline}"
    eid = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]
    return {
        "id": f"evt_{eid}",
        "type": et,
        "symbol": sym,
        "severity": str(severity or "MEDIUM").upper(),
        "headline": headline,
        "metric": metric or {},
        "source": source,
        "ts": ts,
        "link": link or (f"/market/{sym}" if sym else "/alerts"),
        "schema": "retention_alert_event_v1",
    }


_ANTISPAM: Optional[AlertAntiSpam] = None
_LOCK = threading.Lock()


def get_anti_spam() -> AlertAntiSpam:
    global _ANTISPAM
    with _LOCK:
        if _ANTISPAM is None:
            _ANTISPAM = AlertAntiSpam()
        return _ANTISPAM
