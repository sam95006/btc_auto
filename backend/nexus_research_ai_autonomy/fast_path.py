"""Fast execution path — WS update → features → trigger → Risk → Demo REST.

AI/Reasoner/Critic/Reflection MUST NOT run here.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from backend.nexus_research_ai_autonomy.ai_roles import HOT_PATH_GUARD
from backend.nexus_research_ai_autonomy.constants import BYBIT_DEMO_HOST, EXECUTION_PURPOSE_RESEARCH
from backend.nexus_research_ai_autonomy.latency import LatencyTrace
from backend.nexus_research_ai_autonomy.prepared_decision import PreparedDecision
from backend.nexus_research_ai_autonomy.research_risk import ResearchRiskEngine


def _now_ms() -> int:
    return int(time.time() * 1000)


class OrderTransport(Protocol):
    def send_research_order(self, intent: dict[str, Any]) -> dict[str, Any]:
        ...


@dataclass
class SimulatedDemoTransport:
    """Deterministic local simulation transport for tests / research harness.

    Latency from this transport is LOCAL_SIMULATION_LATENCY — never claim
    BYBIT_EXCHANGE_LATENCY. Millisecond wall-clock rounding can produce 0/1/2ms
    figures that are NOT exchange RTT.
    """

    host: str = BYBIT_DEMO_HOST
    orders: list[dict[str, Any]] = field(default_factory=list)
    auto_fill: bool = True
    send_delay_ms: int = 2
    ack_delay_ms: int = 3
    fill_delay_ms: int = 4

    def send_research_order(self, intent: dict[str, Any]) -> dict[str, Any]:
        mono_req = time.perf_counter()
        send_ts = _now_ms()
        send_mono = time.perf_counter()
        time.sleep(self.send_delay_ms / 1000.0)
        ack_ts = _now_ms()
        ack_mono = time.perf_counter()
        time.sleep(max(self.ack_delay_ms - self.send_delay_ms, 0) / 1000.0)
        fill_ts = _now_ms() if self.auto_fill else 0
        fill_mono = ack_mono
        if self.auto_fill:
            time.sleep(max(self.fill_delay_ms - self.ack_delay_ms, 0) / 1000.0)
            fill_ts = _now_ms()
            fill_mono = time.perf_counter()
        order_id = f"sim_demo_{len(self.orders)+1:04d}"
        result = {
            "accepted": True,
            "order_id": order_id,
            "execution_id": f"sim_exec_{len(self.orders)+1:04d}",
            "host": self.host,
            "demo_only": True,
            "execution_purpose": EXECUTION_PURPOSE_RESEARCH,
            "transport_mode": "LOCAL_SIMULATION",
            "exchange_domain": self.host,
            "real_http_request": False,
            "latency_class": "LOCAL_SIMULATION_LATENCY",
            "not_bybit_exchange_latency": True,
            "http_send_ts": send_ts,
            "exchange_ack_ts": ack_ts,
            "fill_ts": fill_ts,
            "monotonic": {
                "request_perf": mono_req,
                "send_perf": send_mono,
                "ack_perf": ack_mono,
                "fill_perf": fill_mono,
                "network_roundtrip_ms": None,
                "internal_trigger_to_send_ms": None,
                "exchange_ack_ms": (ack_mono - send_mono) * 1000.0,
                "fill_ms": (fill_mono - ack_mono) * 1000.0 if self.auto_fill else None,
            },
            "bybit_orderId": None,
            "bybit_executionId": None,
            "ws_timestamp": None,
            "local_timestamp": send_ts,
            "intent": dict(intent),
        }
        self.orders.append(result)
        return result


@dataclass
class ProvenanceRecordingTransport:
    """Wraps any OrderTransport and records required latency provenance fields."""

    inner: OrderTransport
    records: list[dict[str, Any]] = field(default_factory=list)

    def send_research_order(self, intent: dict[str, Any]) -> dict[str, Any]:
        t0 = time.perf_counter()
        out = self.inner.send_research_order(intent)
        t1 = time.perf_counter()
        real_http = bool(out.get("real_http_request"))
        raw_mode = str(out.get("transport_mode") or "")
        # BYBIT_DEMO_REAL_TRANSPORT only when real HTTP evidence exists.
        if real_http and raw_mode == "BYBIT_DEMO_REAL_TRANSPORT":
            transport_mode = "BYBIT_DEMO_REAL_TRANSPORT"
            latency_class = "BYBIT_EXCHANGE_LATENCY"
        elif real_http:
            transport_mode = raw_mode or "BYBIT_DEMO_REST"
            latency_class = str(out.get("latency_class") or "BYBIT_EXCHANGE_LATENCY")
        else:
            transport_mode = raw_mode or "LOCAL_SIMULATION"
            latency_class = str(out.get("latency_class") or "LOCAL_SIMULATION_LATENCY")
        mono = dict(out.get("monotonic") or {})
        mono.setdefault("wrapper_e2e_ms", (t1 - t0) * 1000.0)
        provenance = {
            "transport_mode": transport_mode,
            "exchange_domain": out.get("exchange_domain") or out.get("host") or BYBIT_DEMO_HOST,
            "real_http_request": real_http,
            "latency_class": latency_class,
            "monotonic": mono,
            "bybit_orderId": out.get("bybit_orderId") or (out.get("order_id") if real_http else None),
            "bybit_executionId": out.get("bybit_executionId") or out.get("execution_id"),
            "ws_timestamp": out.get("ws_timestamp"),
            "local_timestamp": out.get("local_timestamp") or out.get("http_send_ts"),
            "split": {
                "internal_market_to_trigger": out.get("split", {}).get("internal_market_to_trigger")
                if isinstance(out.get("split"), dict)
                else None,
                "internal_trigger_to_send": out.get("split", {}).get("internal_trigger_to_send")
                if isinstance(out.get("split"), dict)
                else mono.get("internal_trigger_to_send_ms"),
                "network_roundtrip": mono.get("network_roundtrip_ms"),
                "exchange_ack": mono.get("exchange_ack_ms"),
                "fill": mono.get("fill_ms"),
                "e2e": mono.get("wrapper_e2e_ms"),
            },
        }
        out["latency_provenance"] = provenance
        out["latency_class"] = latency_class
        self.records.append({"intent": dict(intent), "result": out, "provenance": provenance})
        return out


def evaluate_trigger(decision: PreparedDecision, market_update: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """Deterministic trigger — no AI."""
    trig = dict(decision.entry_trigger or {})
    px = float(market_update.get("last_price") or market_update.get("price") or 0.0)
    side = str(decision.side or "").upper()
    trigger_px = trig.get("price")
    evidence = {"price": px, "trigger_price": trigger_px, "side": side}
    if trigger_px is None or px <= 0:
        # Zone fallback: mid crossed with small epsilon
        zone = dict(decision.entry_zone or {})
        mid = float(zone.get("mid") or 0.0)
        width = float(zone.get("width_pct") or 0.001)
        if mid <= 0:
            return False, {**evidence, "reason": "no_trigger_price"}
        if side == "LONG" and px >= mid:
            return True, {**evidence, "reason": "zone_long"}
        if side == "SHORT" and px <= mid:
            return True, {**evidence, "reason": "zone_short"}
        return False, {**evidence, "reason": "zone_not_reached"}
    tp = float(trigger_px)
    if side == "LONG" and px >= tp:
        return True, {**evidence, "reason": "long_cross"}
    if side == "SHORT" and px <= tp:
        return True, {**evidence, "reason": "short_cross"}
    return False, {**evidence, "reason": "trigger_not_reached"}


@dataclass
class FastPathExecutor:
    risk: ResearchRiskEngine = field(default_factory=ResearchRiskEngine)
    transport: OrderTransport = field(default_factory=SimulatedDemoTransport)
    on_ai_forbidden: Callable[[str], None] | None = None

    def execute_if_triggered(
        self,
        decision: PreparedDecision,
        *,
        market_update: dict[str, Any],
        feature_update: dict[str, Any] | None = None,
        risk_packet_extra: dict[str, Any] | None = None,
        ai_callable_probe: Callable[[], Any] | None = None,
    ) -> dict[str, Any]:
        """Hot path. Returns execution result dict."""
        trace = LatencyTrace(decision_id=decision.decision_id)
        trace.mark("market_event_ts", int(market_update.get("event_ts") or _now_ms()))
        _ = feature_update  # incremental features already applied by caller
        trace.mark("feature_ready_ts")

        if decision.status != "READY":
            return {
                "executed": False,
                "reason": f"not_ready:{decision.status}",
                "latency": trace.to_dict(),
                "slow_path_leak": False,
            }

        HOT_PATH_GUARD.begin_hot_path()
        leak = False
        try:
            # Probe: any AI call here must flag SLOW_PATH_LEAK.
            if ai_callable_probe is not None:
                try:
                    ai_callable_probe()
                except Exception:
                    pass
                if HOT_PATH_GUARD.slow_path_leak_count > 0:
                    leak = True

            hit, trig_ev = evaluate_trigger(decision, market_update)
            trace.mark("trigger_ts")
            if not hit:
                return {
                    "executed": False,
                    "reason": "trigger_not_reached",
                    "trigger_evidence": trig_ev,
                    "latency": trace.to_dict(),
                    "slow_path_leak": leak or bool(HOT_PATH_GUARD.leaks),
                }

            decision.transition("TRIGGERED", reason=str(trig_ev.get("reason") or "trigger"))
            trace.mark("risk_start_ts")
            packet = {
                "execution_purpose": EXECUTION_PURPOSE_RESEARCH,
                "demo_only": True,
                "mainnet": False,
                "real_money": False,
                "leverage": 1,
                "open_positions": int((risk_packet_extra or {}).get("open_positions") or 0),
                "stop_logic": decision.stop_logic,
                "max_hold": decision.max_hold,
                "requested_size": decision.requested_size,
                "member_execution": 0,
                **dict(risk_packet_extra or {}),
            }
            risk_res = self.risk.evaluate(packet)
            decision.risk_result = risk_res.to_dict()
            if not risk_res.passed:
                decision.transition("REJECTED", reason="research_risk_block")
                return {
                    "executed": False,
                    "reason": "research_risk_block",
                    "risk": risk_res.to_dict(),
                    "trigger_evidence": trig_ev,
                    "latency": trace.to_dict(),
                    "slow_path_leak": leak,
                }
            trace.mark("risk_pass_ts")

            intent = {
                "symbol": decision.symbol,
                "side": "Buy" if decision.side == "LONG" else "Sell",
                "qty": risk_res.size,
                "leverage": 1,
                "orderType": "Market",
                "reduceOnly": False,
                "stop_logic": decision.stop_logic,
                "execution_purpose": EXECUTION_PURPOSE_RESEARCH,
                "decision_id": decision.decision_id,
                "strategy_family": decision.strategy_family,
                "strategy_id": decision.strategy_id,
                "regime": decision.regime,
            }
            trace.mark("order_intent_ts")
            # Final AI check before send
            if HOT_PATH_GUARD.leaks:
                leak = True
                trace.slow_path_leak = True

            send_result = self.transport.send_research_order(intent)
            trace.mark("http_send_ts", int(send_result.get("http_send_ts") or _now_ms()))
            if send_result.get("exchange_ack_ts"):
                trace.mark("exchange_ack_ts", int(send_result["exchange_ack_ts"]))
            if send_result.get("fill_ts"):
                trace.mark("fill_ts", int(send_result["fill_ts"]))

            if send_result.get("accepted"):
                decision.transition("EXECUTED", reason="demo_order_accepted")
            else:
                decision.transition("REJECTED", reason=str(send_result.get("reason") or "send_rejected"))

            trace.slow_path_leak = leak or bool(HOT_PATH_GUARD.leaks)
            return {
                "executed": bool(send_result.get("accepted")),
                "reason": "executed" if send_result.get("accepted") else "send_rejected",
                "order": send_result,
                "intent": intent,
                "trigger_evidence": trig_ev,
                "risk": risk_res.to_dict(),
                "latency": trace.to_dict(),
                "slow_path_leak": trace.slow_path_leak,
                "execution_purpose": EXECUTION_PURPOSE_RESEARCH,
            }
        finally:
            HOT_PATH_GUARD.end_hot_path()
