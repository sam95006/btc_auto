"""Stage 4 Stage-3 context summaries for LLM prompts (no secrets)."""
from __future__ import annotations

from typing import Any, Dict, List


def summarize_trade_result(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "symbol": str(row.get("symbol") or "").upper(),
        "side": str(row.get("side") or "").upper(),
        "close_pnl": row.get("close_pnl"),
        "failure_reason": str(row.get("exit_reason") or row.get("failure_reason") or "")[:120],
        "setup_key": str(row.get("setup_key") or "")[:120],
        "created_at_utc": str(row.get("created_at_utc") or row.get("closed_at_utc") or "")[:32],
    }


def summarize_reflection(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "symbol": str(row.get("symbol") or "").upper(),
        "side": str(row.get("side") or "").upper(),
        "failure_reason": str(row.get("failure_reason") or row.get("root_cause") or "")[:120],
        "patch_action": str(row.get("recommended_action") or row.get("patch_action") or "")[:64],
        "setup_key": str(row.get("setup_key") or "")[:120],
        "created_at_utc": str(row.get("created_at_utc") or "")[:32],
    }


def summarize_patch(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "symbol": str(row.get("symbol") or "").upper(),
        "side": str(row.get("side") or "").upper(),
        "patch_action": str(row.get("action") or "")[:64],
        "setup_key": str(row.get("setup_key") or "")[:120],
        "failure_reason": str(row.get("failure_reason") or row.get("reason") or "")[:120],
        "created_at_utc": str(row.get("created_at_utc") or row.get("applied_at_utc") or "")[:32],
    }


def summarize_trades(rows: List[Dict[str, Any]], *, limit: int = 5) -> List[Dict[str, Any]]:
    return [summarize_trade_result(r) for r in rows[:limit]]


def summarize_reflections(rows: List[Dict[str, Any]], *, limit: int = 5) -> List[Dict[str, Any]]:
    return [summarize_reflection(r) for r in rows[:limit]]


def summarize_patches(rows: List[Dict[str, Any]], *, limit: int = 5) -> List[Dict[str, Any]]:
    return [summarize_patch(r) for r in rows[:limit]]
