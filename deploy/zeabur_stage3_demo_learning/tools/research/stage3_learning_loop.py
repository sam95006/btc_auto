"""Reflection / patch learning loop for Stage 3 demo learning runner."""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from tools.research.bybit_demo_learning_common import (
    ROOT,
    STOP_CONDITION_KEYS,
    TRADE_RECORD_FIELDS,
    utc_now_iso,
    write_json,
)

OUTPUT_FILES = (
    "decisions.jsonl",
    "orders.jsonl",
    "trade_results.jsonl",
    "reflection_records.jsonl",
    "applied_learning_patches.jsonl",
    "account_snapshots.jsonl",
    "runner_audit.json",
    "stop_conditions.json",
    "demo_order_session_report.json",
)


RECONCILIATION_FIELDS = (
    "account_balance_before",
    "account_balance_after",
    "account_balance_delta",
    "close_pnl",
    "pnl_balance_delta_gap",
    "fee_or_slippage_estimate",
    "reconciliation_status",
    "fee_fields_available",
    "execution_fee",
    "funding_fee",
    "slippage_estimate",
    "possible_orphan_close_impact",
    "requires_manual_review",
)

MANUAL_REVIEW_GAP_THRESHOLD = 0.05

PATCH_ACTIONS = (
    "risk_reduce",
    "block_reentry",
    "cooldown",
    "manual_review_required",
)


def _to_float(raw: Any) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def build_balance_reconciliation(
    *,
    account_balance_before: float | None,
    account_balance_after: float | None,
    close_pnl: float,
    closed_pnl_row: Dict[str, Any] | None = None,
    match_tolerance: float = 0.001,
) -> Dict[str, Any]:
    before = _to_float(account_balance_before)
    after = _to_float(account_balance_after)
    delta = round(after - before, 6) if account_balance_before is not None and account_balance_after is not None else 0.0
    pnl = round(_to_float(close_pnl), 6)
    gap = round(delta - pnl, 6)

    row = closed_pnl_row or {}
    fee_keys = ("openFee", "closeFee", "execFee", "cumExecFee", "fee")
    funding_keys = ("cumFundingFee", "fundingFee")
    fee_fields_available = any(k in row and str(row.get(k) or "").strip() != "" for k in fee_keys + funding_keys)

    execution_fee = 0.0
    if fee_fields_available:
        execution_fee = sum(_to_float(row.get(k)) for k in fee_keys if k in row)
    funding_fee = _to_float(row.get("cumFundingFee") or row.get("fundingFee")) if fee_fields_available else 0.0

    if account_balance_before is None or account_balance_after is None:
        reconciliation_status = "unknown"
    elif abs(gap) <= match_tolerance:
        reconciliation_status = "matched"
    else:
        reconciliation_status = "gap_detected"

    if not fee_fields_available and reconciliation_status != "matched":
        reconciliation_status = "gap_detected"

    fee_or_slippage_estimate = gap
    slippage_estimate = round(gap - execution_fee - funding_fee, 6) if fee_fields_available else gap

    requires_manual_review = abs(gap) > MANUAL_REVIEW_GAP_THRESHOLD
    explained_fees = abs(execution_fee) + abs(funding_fee)
    possible_orphan_close_impact = False
    if requires_manual_review and abs(gap) > explained_fees + match_tolerance:
        possible_orphan_close_impact = True
        if reconciliation_status == "gap_detected":
            reconciliation_status = "orphan_impact_suspected"

    return {
        "account_balance_before": before,
        "account_balance_after": after,
        "account_balance_delta": delta,
        "close_pnl": pnl,
        "pnl_balance_delta_gap": gap,
        "fee_or_slippage_estimate": fee_or_slippage_estimate,
        "reconciliation_status": reconciliation_status,
        "fee_fields_available": fee_fields_available,
        "execution_fee": round(execution_fee, 6),
        "funding_fee": round(funding_fee, 6),
        "slippage_estimate": round(slippage_estimate, 6),
        "possible_orphan_close_impact": possible_orphan_close_impact,
        "requires_manual_review": requires_manual_review,
    }


def resolve_output_dir() -> Path:
    nexus = os.environ.get("NEXUS_DATA_DIR", "").strip()
    if nexus:
        candidate = Path(nexus) / "stage3_demo_learning"
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            test = candidate / ".write_probe"
            test.write_text("ok", encoding="utf-8")
            test.unlink(missing_ok=True)
            return candidate
        except OSError:
            pass
    out = ROOT / "data" / "external_alpha" / "stage3_demo_learning"
    out.mkdir(parents=True, exist_ok=True)
    return out


def append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def setup_key(
    symbol: str,
    side: str,
    regime: str,
    failure_reason: str,
    decision_source: str = "controlled_demo_order",
) -> str:
    return f"{symbol.upper()}|{side.upper()}|{regime}|{decision_source}|{failure_reason}"


def _read_jsonl_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _cooldown_active(patch: Dict[str, Any]) -> bool:
    until = patch.get("cooldown_until_utc")
    if not until:
        return False
    try:
        text = str(until).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        from datetime import datetime, timezone

        end = datetime.fromisoformat(text)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) < end.astimezone(timezone.utc)
    except ValueError:
        return False


@dataclass
class LearningState:
    confidence: float = 0.72
    position_size: float = 18.0
    patches: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    loss_setups: Dict[str, int] = field(default_factory=dict)
    stats: Dict[str, int] = field(default_factory=lambda: {
        "loss_trade_count": 0,
        "loss_without_reflection_count": 0,
        "repeated_mistake_detected_count": 0,
        "repeated_mistake_blocked_count": 0,
        "balance_read_failed_count": 0,
    })

    def reduce_after_loss(self) -> Tuple[float, float]:
        self.confidence = max(0.1, round(self.confidence * 0.85, 4))
        self.position_size = max(1.0, round(self.position_size * 0.75, 4))
        return self.confidence, self.position_size


@dataclass
class StopConditionMonitor:
    triggered: List[str] = field(default_factory=list)
    flags: Dict[str, bool] = field(default_factory=lambda: {k: False for k in STOP_CONDITION_KEYS})

    def trigger(self, key: str, detail: str = "") -> None:
        self.flags[key] = True
        if key not in self.triggered:
            self.triggered.append(key)
        if detail and detail not in self.triggered:
            self.triggered.append(detail)

    @property
    def should_stop(self) -> bool:
        return bool(self.triggered)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generated_at_utc": utc_now_iso(),
            "triggered": self.triggered,
            "flags": self.flags,
        }


class Stage3LearningLoop:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.state = LearningState()
        self.stop = StopConditionMonitor()
        self._paths = {name: output_dir / name for name in OUTPUT_FILES}
        self._hydrate_from_disk()

    def path(self, name: str) -> Path:
        return self._paths[name]

    def _hydrate_from_disk(self) -> None:
        patch_path = self.path("applied_learning_patches.jsonl")
        for row in _read_jsonl_rows(patch_path):
            key = row.get("setup_key")
            if not key:
                key = setup_key(
                    str(row.get("symbol") or ""),
                    str(row.get("side") or ""),
                    str(row.get("regime") or ""),
                    str(row.get("failure_reason") or ""),
                    str(row.get("decision_source") or "controlled_demo_order"),
                )
            self.state.patches[key] = row
            hits = int(row.get("hit_count") or 0)
            if hits > 0:
                self.state.loss_setups[key] = max(self.state.loss_setups.get(key, 0), hits)

        for trade in _read_jsonl_rows(self.path("trade_results.jsonl")):
            if float(trade.get("close_pnl") or 0) < 0:
                key = trade.get("setup_key")
                if key:
                    self.state.loss_setups[key] = self.state.loss_setups.get(key, 0) + 1
            if trade.get("repeated_mistake_detected"):
                self.state.stats["repeated_mistake_detected_count"] += 1
            if trade.get("repeated_mistake_blocked"):
                self.state.stats["repeated_mistake_blocked_count"] += 1

    def _choose_patch_action(self, loss_count: int, *, severe_gap: bool = False) -> str:
        if severe_gap:
            return "manual_review_required"
        if loss_count <= 1:
            return "risk_reduce"
        if loss_count == 2:
            return "block_reentry"
        return "cooldown"

    def evaluate_same_setup(
        self,
        *,
        symbol: str,
        side: str,
        regime: str,
        failure_reason: str,
        decision_source: str = "controlled_demo_order",
    ) -> Dict[str, Any]:
        key = setup_key(symbol, side, regime, failure_reason, decision_source)
        patch = self.state.patches.get(key)
        loss_count = int(self.state.loss_setups.get(key, 0))
        repeated = loss_count >= 1
        result = {
            "setup_key": key,
            "repeated_mistake_detected": repeated,
            "repeated_mistake_blocked": False,
            "skip_trade": False,
            "confidence": self.state.confidence,
            "position_size": self.state.position_size,
            "patch_applied_to_next_decision": False,
            "patch_action": patch.get("action") if patch else None,
            "loss_count_before": loss_count,
        }
        if not repeated or not patch:
            return result

        result["repeated_mistake_detected"] = True
        self.state.stats["repeated_mistake_detected_count"] += 1
        action = str(patch.get("action") or "risk_reduce")
        if action == "block":
            action = "block_reentry"

        if action == "risk_reduce" and loss_count >= 1:
            result["skip_trade"] = True
            result["repeated_mistake_blocked"] = True
            result["patch_action"] = "block_reentry"
            self.state.stats["repeated_mistake_blocked_count"] += 1
            patch["blocked_count"] = int(patch.get("blocked_count") or 0) + 1
            patch["last_used_at_utc"] = utc_now_iso()
            return result

        if action in {"block_reentry", "manual_review_required"}:
            result["skip_trade"] = True
            result["repeated_mistake_blocked"] = True
            self.state.stats["repeated_mistake_blocked_count"] += 1
            patch["blocked_count"] = int(patch.get("blocked_count") or 0) + 1
            patch["last_used_at_utc"] = utc_now_iso()
            return result

        if action == "cooldown":
            if _cooldown_active(patch):
                result["skip_trade"] = True
                result["repeated_mistake_blocked"] = True
                self.state.stats["repeated_mistake_blocked_count"] += 1
                patch["blocked_count"] = int(patch.get("blocked_count") or 0) + 1
            else:
                result["confidence"] = float(patch.get("confidence_after") or self.state.confidence)
                result["position_size"] = float(patch.get("position_size_after") or self.state.position_size)
                result["patch_applied_to_next_decision"] = True
            patch["last_used_at_utc"] = utc_now_iso()
            return result

        result["confidence"] = float(patch.get("confidence_after") or self.state.confidence)
        result["position_size"] = float(patch.get("position_size_after") or self.state.position_size)
        result["patch_applied_to_next_decision"] = True
        self.state.confidence = result["confidence"]
        self.state.position_size = result["position_size"]
        patch["last_used_at_utc"] = utc_now_iso()
        return result

    def record_loss_reflection_patch(
        self,
        *,
        decision_id: str,
        trade: Dict[str, Any],
        regime: str,
        failure_reason: str,
    ) -> Dict[str, Any]:
        symbol = trade["symbol"]
        side = trade["side"]
        decision_source = str(trade.get("decision_source") or "controlled_demo_order")
        key = setup_key(symbol, side, regime, failure_reason, decision_source)
        conf_before = float(trade.get("confidence_before", self.state.confidence))
        size_before = float(trade.get("position_size_before", self.state.position_size))
        conf_after, size_after = self.state.reduce_after_loss()
        loss_count = self.state.loss_setups.get(key, 0) + 1
        self.state.loss_setups[key] = loss_count
        self.state.stats["loss_trade_count"] += 1
        severe_gap = bool(trade.get("requires_manual_review")) or str(
            trade.get("reconciliation_status") or ""
        ) in {"gap_detected", "orphan_impact_suspected"}
        patch_action = self._choose_patch_action(loss_count, severe_gap=severe_gap)

        reflection = {
            "reflection_id": str(uuid.uuid4()),
            "decision_id": decision_id,
            "signal_id": trade.get("signal_id"),
            "order_id": trade.get("order_id"),
            "symbol": symbol,
            "side": side,
            "regime": regime,
            "failure_reason": failure_reason,
            "close_pnl": trade.get("close_pnl"),
            "exit_reason": trade.get("exit_reason"),
            "confidence_before": conf_before,
            "confidence_after": conf_after,
            "position_size_before": size_before,
            "position_size_after": size_after,
            "created_at_utc": utc_now_iso(),
        }
        append_jsonl(self.path("reflection_records.jsonl"), reflection)

        confidence_penalty = round(max(0.0, conf_before - conf_after), 6)
        size_multiplier = round(conf_after / conf_before, 6) if conf_before else 1.0
        patch = {
            "patch_id": str(uuid.uuid4()),
            "decision_id": decision_id,
            "setup_key": key,
            "symbol": symbol,
            "side": side,
            "regime": regime,
            "failure_reason": failure_reason,
            "decision_source": decision_source,
            "action": patch_action,
            "confidence_after": conf_after,
            "position_size_after": size_after,
            "confidence_penalty": confidence_penalty,
            "size_multiplier": size_multiplier,
            "created_at_utc": utc_now_iso(),
            "last_used_at_utc": utc_now_iso(),
            "hit_count": loss_count,
            "blocked_count": int(self.state.patches.get(key, {}).get("blocked_count") or 0),
            "cooldown_until_utc": None,
            "evidence_session_id": decision_id,
        }
        if patch_action == "cooldown":
            from datetime import datetime, timedelta, timezone

            patch["cooldown_until_utc"] = (
                datetime.now(timezone.utc) + timedelta(minutes=30)
            ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        self.state.patches[key] = patch
        append_jsonl(self.path("applied_learning_patches.jsonl"), patch)

        if trade.get("close_pnl", 0) < 0 and not reflection:
            self.state.stats["loss_without_reflection_count"] += 1
            self.stop.trigger("loss_without_reflection")

        trade.update(
            {
                "confidence_after": conf_after,
                "position_size_after": size_after,
                "reflection_created": True,
                "patch_created": True,
                "patch_applied_to_next_decision": False,
            }
        )
        return trade

    def build_trade_record(
        self,
        *,
        decision_id: str,
        signal_id: str,
        order_id: str,
        symbol: str,
        side: str,
        entry_price: float,
        exit_price: float,
        close_pnl: float,
        exit_reason: str,
        confidence_before: float,
        confidence_after: float,
        position_size_before: float,
        position_size_after: float,
        reflection_created: bool,
        patch_created: bool,
        patch_applied_to_next_decision: bool,
        repeated_mistake_detected: bool,
        repeated_mistake_blocked: bool,
    ) -> Dict[str, Any]:
        row = {
            "decision_id": decision_id,
            "signal_id": signal_id,
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "close_pnl": close_pnl,
            "exit_reason": exit_reason,
            "confidence_before": confidence_before,
            "confidence_after": confidence_after,
            "position_size_before": position_size_before,
            "position_size_after": position_size_after,
            "reflection_created": reflection_created,
            "patch_created": patch_created,
            "patch_applied_to_next_decision": patch_applied_to_next_decision,
            "repeated_mistake_detected": repeated_mistake_detected,
            "repeated_mistake_blocked": repeated_mistake_blocked,
            "recorded_at_utc": utc_now_iso(),
        }
        for fld in TRADE_RECORD_FIELDS:
            row.setdefault(fld, None)
        return row

    def write_audit(self, audit: Dict[str, Any]) -> None:
        write_json(self.path("runner_audit.json"), audit)

    def write_stop_conditions(self) -> None:
        write_json(self.path("stop_conditions.json"), self.stop.to_dict())
