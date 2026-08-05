"""Deterministic development-only mechanism executors (never live orders)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.nexus_mechanism_execution_compiler.contracts import ExecutorContract
from backend.nexus_mechanism_lab_v4.catalog import SPECS, MechanismSpec
from backend.nexus_mechanism_lab_v4.signals import signal_for
from backend.nexus_mechanism_lab_v4.synthetic import SynthBar


@dataclass(frozen=True, slots=True)
class ExecutorEvent:
    bar_index: int
    entry_ts_ms: int
    exit_ts_ms: int
    signal: int
    exit_reason: str
    failure_triggered: bool
    cost_gated: bool
    gross_proxy: float
    cost_proxy: float


def _spec_by_id() -> dict[str, MechanismSpec]:
    return {s.mechanism_id: s for s in SPECS}


def _invalidate(contract: ExecutorContract, bar: SynthBar) -> bool:
    """Map invalidating conditions to synthetic bar probes (development only)."""
    conds = set(contract.risk_compatibility.invalidating_conditions)
    if "data_quality_gap" in conds and not bar.data_quality_ok:
        return True
    if "spread_shock_active" in conds and bar.spread_shock >= 2.5:
        return True
    if "liquidation_cascade_active" in conds and bar.liquidation_intensity >= 0.85:
        return True
    if "regime_stress" in conds and bar.regime_label == "STRESS":
        return True
    if "book_snapshot_stale" in conds and not bar.data_quality_ok:
        return True
    return False


def _cost_gate(contract: ExecutorContract, bar: SynthBar) -> bool:
    """True when cost gate blocks entry (development research accounting only)."""
    if not contract.cost_dependency.spread_impact_gate:
        return False
    return (bar.spread_bps + bar.impact_bps) >= 25.0


class MechanismExecutor:
    """Deterministic executor bound to one semantic mechanism contract."""

    def __init__(self, contract: ExecutorContract) -> None:
        self.contract = contract
        specs = _spec_by_id()
        if contract.mechanism_id not in specs:
            raise KeyError(f"unknown_mechanism:{contract.mechanism_id}")
        self.spec = specs[contract.mechanism_id]

    def evaluate_entry(self, bar: SynthBar, prev: SynthBar) -> int | None:
        if self.contract.risk_compatibility.control_overlay_only:
            return None
        if not bar.data_quality_ok:
            return None
        if _invalidate(self.contract, bar):
            return None
        if _cost_gate(self.contract, bar):
            return None
        # PIT: only bar/prev — never future bars.
        return signal_for(self.spec, bar, prev)

    def evaluate_exit(self, *, bars_held: int, bar: SynthBar, entry_signal: int) -> tuple[bool, str]:
        hold = self.contract.feature_contract.hold_bars
        if bars_held >= hold:
            return True, "hold_bars_elapsed"
        # Sign-flip exit proxy using contemporaneous primary feature when available.
        primary = self.contract.feature_contract.primary_feature
        if primary == "ofi_top" and hasattr(bar, "ofi_top"):
            cur = 1 if bar.ofi_top > 0 else (-1 if bar.ofi_top < 0 else 0)
            if cur != 0 and cur != entry_signal and self.contract.signal_contract.direction_mode == "continuation":
                return True, "primary_sign_flip"
        return False, "hold"

    def evaluate_failure(self, bar: SynthBar) -> bool:
        return _invalidate(self.contract, bar)

    def run(
        self,
        bars: list[SynthBar],
        *,
        cooldown: int | None = None,
    ) -> dict[str, Any]:
        hold = self.contract.feature_contract.hold_bars
        cd = cooldown if cooldown is not None else max(2, self.contract.feature_contract.horizon_bars)
        events: list[ExecutorEvent] = []
        last_i = -10_000
        cost_gated = 0
        failures = 0
        control_events = 0

        if self.contract.risk_compatibility.control_overlay_only:
            for i in range(1, len(bars)):
                bar = bars[i]
                prev = bars[i - 1]
                if prev.regime_label == "RANGE" and bar.regime_label == "TREND":
                    control_events += 1
            return self._result(
                events=[],
                control_events=control_events,
                cost_gated=0,
                failures=0,
            )

        for i in range(40, len(bars) - hold - 1):
            if i - last_i < cd:
                continue
            bar = bars[i]
            prev = bars[i - 1]
            if self.evaluate_failure(bar):
                failures += 1
                continue
            if _cost_gate(self.contract, bar):
                cost_gated += 1
                continue
            sig = self.evaluate_entry(bar, prev)
            if sig is None:
                continue
            exit_i = i + hold
            exit_bar = bars[exit_i]
            should_exit, reason = self.evaluate_exit(
                bars_held=hold, bar=exit_bar, entry_signal=sig
            )
            if not should_exit:
                reason = "hold_bars_elapsed"
            gross = float(sig) * (exit_bar.mid - bar.mid)
            cost = (bar.spread_bps + bar.impact_bps) * bar.mid / 10_000.0
            events.append(
                ExecutorEvent(
                    bar_index=i,
                    entry_ts_ms=bar.exchange_ts_ms,
                    exit_ts_ms=exit_bar.exchange_ts_ms,
                    signal=sig,
                    exit_reason=reason,
                    failure_triggered=False,
                    cost_gated=False,
                    gross_proxy=gross,
                    cost_proxy=cost,
                )
            )
            last_i = i

        return self._result(
            events=events,
            control_events=0,
            cost_gated=cost_gated,
            failures=failures,
        )

    def _result(
        self,
        *,
        events: list[ExecutorEvent],
        control_events: int,
        cost_gated: int,
        failures: int,
    ) -> dict[str, Any]:
        c = self.contract
        return {
            "executor_id": c.executor_id,
            "mechanism_id": c.mechanism_id,
            "family": c.family,
            "economic_rationale": c.economic_rationale,
            "input_contract": c.to_public_dict()["input_contract"],
            "feature_contract": c.to_public_dict()["feature_contract"],
            "signal_contract": c.to_public_dict()["signal_contract"],
            "entry_hypothesis": c.entry_hypothesis,
            "exit_hypothesis": c.exit_hypothesis,
            "failure_condition": c.failure_condition,
            "cost_dependency": c.to_public_dict()["cost_dependency"],
            "risk_compatibility": c.to_public_dict()["risk_compatibility"],
            "deterministic_replay": c.to_public_dict()["deterministic_replay"],
            "negative_test": c.to_public_dict()["negative_test"],
            "economic_rationale_linkage": c.to_public_dict()["economic_rationale_linkage"],
            "event_count": control_events if c.risk_compatibility.control_overlay_only else len(events),
            "control_overlay_only": c.risk_compatibility.control_overlay_only,
            "cost_gated_count": cost_gated,
            "failure_probe_count": failures,
            "gross_proxy_sum": float(sum(e.gross_proxy for e in events)),
            "cost_proxy_sum": float(sum(e.cost_proxy for e in events)),
            "events_sample": [
                {
                    "bar_index": e.bar_index,
                    "entry_ts_ms": e.entry_ts_ms,
                    "exit_ts_ms": e.exit_ts_ms,
                    "signal": e.signal,
                    "exit_reason": e.exit_reason,
                    "gross_proxy": e.gross_proxy,
                    "cost_proxy": e.cost_proxy,
                }
                for e in events[:3]
            ],
            "qualified": False,
            "qualification_ready": False,
            "edge_claimed": False,
            "profitability_claimed": False,
            "data_lineage": "SYNTHETIC_DEVELOPMENT_FIXTURE",
            "formal_walk_forward_executed": False,
            "oos_executed": False,
        }
