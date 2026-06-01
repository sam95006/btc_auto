"""HQ-level multi-agent debate gate for Pure AI entries.

Goal: before executing Pure AI entry proposals, run a Bull/Bear/Risk discussion and
veto proposals that are likely to be impulsive or structurally misaligned.

This is intentionally HQ-level (總站) logic: it does not belong to any single fleet,
and it never changes fleet strategy engines.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional, Tuple

from config.pure_ai_trading_config import PURE_AI_DEBATE_GATE


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value if value is not None else default)
    except Exception:
        return default


class PureAiDebateGate:
    """Bull/Bear/Risk advisory gate using existing LLM 'agent' task."""

    def __init__(self, llm_gateway=None):
        self.llm_gateway = llm_gateway
        self._last_snapshot: Dict[str, Any] = {}

    @property
    def enabled(self) -> bool:
        return bool(PURE_AI_DEBATE_GATE)

    def last_snapshot(self) -> Dict[str, Any]:
        return dict(self._last_snapshot or {})

    def filter_entries(self, proposals: List[Dict[str, Any]], context: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        proposals = [dict(item) for item in (proposals or []) if isinstance(item, dict)]
        if not proposals:
            self._last_snapshot = {
                "enabled": self.enabled,
                "timestamp": int(time.time() * 1000),
                "kept": 0,
                "rejected": 0,
                "reason": "no_proposals",
            }
            return [], self.last_snapshot()

        if not self.enabled:
            self._last_snapshot = {
                "enabled": False,
                "timestamp": int(time.time() * 1000),
                "kept": len(proposals),
                "rejected": 0,
                "reason": "disabled",
            }
            return proposals, self.last_snapshot()

        advisory = self._run_debate(proposals, context)
        keep, reject = self._apply_veto(proposals, advisory)
        self._last_snapshot = {
            "enabled": True,
            "timestamp": int(time.time() * 1000),
            "kept": len(keep),
            "rejected": len(reject),
            "rejected_symbols": [item.get("symbol") for item in reject if item.get("symbol")][:8],
            "advisory": advisory,
        }
        return keep, self.last_snapshot()

    def _run_debate(self, proposals: List[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, Any]:
        if not self.llm_gateway or not getattr(self.llm_gateway, "enabled", lambda: False)():
            return {"status": "disabled", "reason": "llm_offline", "output": {}}

        compact = []
        for p in proposals[:4]:
            compact.append(
                {
                    "fleet": p.get("fleet"),
                    "symbol": p.get("symbol"),
                    "side": p.get("side"),
                    "confidence": _safe_float(p.get("confidence")),
                    "score": _safe_float(p.get("score")),
                    "leverage": _safe_float(p.get("leverage")),
                    "margin_usd": _safe_float(p.get("margin_usd")),
                    "risk_flags": list(p.get("risk_flags") or [])[:6],
                    "edge_summary": (p.get("edge_summary") or "")[:220],
                }
            )

        regime = dict((context.get("regime_state") or {}) if isinstance(context.get("regime_state"), dict) else {})
        growth = dict((context.get("growth_status") or {}) if isinstance(context.get("growth_status"), dict) else {})
        portfolio = {
            "deployable_pool": _safe_float(context.get("deployable_pool")),
            "active_positions": len(list(context.get("positions") or [])),
            "block_new_entries": bool(growth.get("block_new_entries")),
            "block_reason": growth.get("block_reason"),
        }

        payload = {
            "world_channel": [
                {"topic": "pure_ai_entry_proposals", "items": compact},
            ],
            "internal_channels": {
                "bull_case": {
                    "prompt": "Argue for the best proposal(s). Highlight why NOW and why this side.",
                    "proposals": compact,
                },
                "bear_case": {
                    "prompt": "Argue against the proposals. Identify hidden risks and why the edge may be fake.",
                    "proposals": compact,
                },
                "risk_audit": {
                    "prompt": "Hard risk audit: liquidation, news/macro, regime mismatch, capital concentration.",
                    "regime_state": regime,
                    "portfolio": portfolio,
                    "proposals": compact,
                },
            },
            "truth_layer_status": dict(context.get("truth_layer_status") or {}),
            "market_context": {},  # keep small; main context is already in proposals
        }
        return self.llm_gateway.run_task("agent", payload, fallback_output={"hq_review_required": False})

    def _apply_veto(self, proposals: List[Dict[str, Any]], advisory: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        output = advisory.get("output") if isinstance(advisory.get("output"), dict) else {}
        if not isinstance(output, dict):
            return proposals, []

        conflicts = [str(item) for item in (output.get("conflicts") or []) if item]
        veto_all = bool(output.get("hq_review_required")) and _env_bool("NEXUS_PURE_AI_DEBATE_HARD_VETO", False)
        veto_symbols = {str(s).upper() for s in (output.get("veto_symbols") or []) if s}

        kept, rejected = [], []
        for p in proposals:
            symbol = str(p.get("symbol") or "").upper()
            flagged = bool(symbol and symbol in veto_symbols)
            if veto_all or flagged:
                rejected.append({**p, "debate_veto": True, "debate_conflicts": conflicts[:6]})
            else:
                kept.append({**p, "debate_conflicts": conflicts[:6]})
        return kept, rejected

