from __future__ import annotations

import os

from config.radar_dispatch_config import CORE_FLEET_SYMBOLS, RADAR_MIN_CANDIDATE_SCORE


def _env_bool(name, default=True):
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _safe_float(value, default=0.0):
    try:
        return float(value or default)
    except Exception:
        return default


class RadarLlmProposalBridge:
    """
    RADAR-only coin selection via LLM proposals.
    Core fleets BTC/ETH/SOL/PEPE are never opened here (fixed fleet engines).
    """

    def __init__(self, radar_dispatch, llm_gateway=None):
        self.radar_dispatch = radar_dispatch
        self.llm_gateway = llm_gateway
        self.enabled = _env_bool("NEXUS_RADAR_LLM_PROPOSALS", True)
        self.min_confidence = _safe_float(os.getenv("NEXUS_RADAR_LLM_MIN_CONFIDENCE", "0.55"), 0.55)

    def build_llm_payload(self, radar_scan, market_board=None, truth_status=None):
        board = {str(item.get("symbol") or "").upper(): item for item in (market_board or (radar_scan or {}).get("market_board") or [])}
        candidates = list((radar_scan or {}).get("candidates") or [])[:8]
        return {
            "core_fleet_symbols": sorted(CORE_FLEET_SYMBOLS),
            "candidates": candidates,
            "market_board": list(board.values())[:12],
            "truth_layer_status": {
                "futures_ready_for_ai": bool((truth_status or {}).get("futures_ready_for_ai")),
                "fresh_for_ai": bool((truth_status or {}).get("fresh_for_ai")),
            },
        }

    def parse_llm_output(self, llm_result, radar_scan):
        llm_result = llm_result or {}
        output = llm_result.get("output") if isinstance(llm_result.get("output"), dict) else llm_result
        if not isinstance(output, dict):
            output = {}
        orders = list(output.get("radar_orders") or output.get("trade_proposals") or [])
        board = {str(item.get("symbol") or "").upper(): item for item in (radar_scan or {}).get("market_board") or []}
        proposals = []
        for item in orders:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "").upper().replace("/", "")
            if not symbol or symbol in CORE_FLEET_SYMBOLS:
                continue
            confidence = _safe_float(item.get("confidence", 0.0))
            if confidence < self.min_confidence:
                continue
            board_row = board.get(symbol, {})
            score = float(board_row.get("candidate_score", 0.0) or 0.0)
            if score > 0 and score < RADAR_MIN_CANDIDATE_SCORE:
                continue
            side = str(item.get("side", "BUY")).upper()
            proposals.append(
                {
                    "symbol": symbol,
                    "candidate_side": "LONG" if side in {"BUY", "LONG"} else "SHORT",
                    "candidate_score": max(score, confidence * 100.0),
                    "reason": "llm_radar_proposal",
                    "llm_rationale": str(item.get("rationale") or item.get("reason") or "")[:240],
                    "llm_confidence": confidence,
                    "source": "radar_llm",
                }
            )
        return proposals

    def fetch_proposals(self, radar_scan, truth_status=None):
        if not self.enabled or not self.llm_gateway:
            return []
        payload = self.build_llm_payload(radar_scan, truth_status=truth_status)
        llm_result = self.llm_gateway.run_task("radar_proposal", payload, fallback_output={"radar_orders": []})
        return self.parse_llm_output(llm_result, radar_scan)

    def merge_with_scan_candidates(self, radar_scan, llm_proposals):
        merged = []
        seen = set()
        for item in list(llm_proposals or []) + list(self.radar_dispatch.eligible_candidates(radar_scan) or []):
            symbol = str(item.get("symbol") or "").upper()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            merged.append(item)
        return merged
