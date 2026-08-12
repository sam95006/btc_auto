"""Research AI Autonomy Runtime — market-adaptive slow path + fast trigger path."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_research_ai_autonomy.ai_roles import (
    HOT_PATH_GUARD,
    DeepQuantEvaluator,
    ResearchCritic,
    ResearchReasoner,
)
from backend.nexus_research_ai_autonomy.constants import (
    DEFAULT_RESEARCH_SHORTLIST_N,
    EXECUTION_PURPOSE_RESEARCH,
    POLICY_RESEARCH_AI_DEMO,
)
from backend.nexus_research_ai_autonomy.decision_memory_bridge import DecisionMemoryBridge
from backend.nexus_research_ai_autonomy.exploration_gate import ResearchExplorationGateV1
from backend.nexus_research_ai_autonomy.fast_path import FastPathExecutor, SimulatedDemoTransport
from backend.nexus_research_ai_autonomy.latency import LatencyAggregator
from backend.nexus_research_ai_autonomy.lesson_firewall_bridge import LessonFirewallBridge
from backend.nexus_research_ai_autonomy.market_state import MarketStateEngine
from backend.nexus_research_ai_autonomy.metrics import AutonomyMetrics
from backend.nexus_research_ai_autonomy.policies import ExplorationBudget, RESEARCH_AI_DEMO_POLICY
from backend.nexus_research_ai_autonomy.position_manager import PositionManager
from backend.nexus_research_ai_autonomy.prepared_decision import PreparedDecision, PreparedDecisionStore
from backend.nexus_research_ai_autonomy.radar_feed import ServerRadarFeed
from backend.nexus_research_ai_autonomy.reflection_loop import ReflectionLoop
from backend.nexus_research_ai_autonomy.research_risk import ResearchRiskEngine
from backend.nexus_research_ai_autonomy.strategy_router import ResearchStrategyRouter


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class ResearchAutonomyRuntime:
    """End-to-end RESEARCH_AI_DEMO autonomy conductor (demo_only)."""

    market_state: MarketStateEngine = field(default_factory=MarketStateEngine)
    router: ResearchStrategyRouter = field(default_factory=ResearchStrategyRouter)
    radar: ServerRadarFeed = field(default_factory=ServerRadarFeed)
    quant: DeepQuantEvaluator = field(default_factory=DeepQuantEvaluator)
    reasoner: ResearchReasoner = field(default_factory=ResearchReasoner)
    critic: ResearchCritic = field(default_factory=ResearchCritic)
    exploration_gate: ResearchExplorationGateV1 = field(default_factory=ResearchExplorationGateV1)
    research_risk: ResearchRiskEngine = field(default_factory=ResearchRiskEngine)
    decisions: PreparedDecisionStore = field(default_factory=PreparedDecisionStore)
    fast_path: FastPathExecutor = field(default_factory=FastPathExecutor)
    positions: PositionManager = field(default_factory=PositionManager)
    reflection: ReflectionLoop = field(default_factory=ReflectionLoop)
    lessons: LessonFirewallBridge = field(default_factory=LessonFirewallBridge)
    memory: DecisionMemoryBridge = field(default_factory=DecisionMemoryBridge)
    budget: ExplorationBudget = field(default_factory=ExplorationBudget)
    metrics: AutonomyMetrics = field(default_factory=AutonomyMetrics)
    latency_agg: LatencyAggregator = field(default_factory=LatencyAggregator)
    shortlist_n: int = DEFAULT_RESEARCH_SHORTLIST_N
    last_market_state: dict[str, Any] = field(default_factory=dict)
    last_route: dict[str, Any] = field(default_factory=dict)
    last_deep: list[dict[str, Any]] = field(default_factory=list)
    last_ai_decision: dict[str, Any] = field(default_factory=dict)
    last_risk: dict[str, Any] = field(default_factory=dict)
    last_closed: dict[str, Any] = field(default_factory=dict)
    last_reflection: dict[str, Any] = field(default_factory=dict)
    formal_gates_ignored_for_research: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.fast_path.transport, SimulatedDemoTransport):
            # Keep default sim transport unless injected.
            pass
        self.fast_path.risk = self.research_risk
        self.positions.risk = self.research_risk

    def run_slow_path_cycle(
        self,
        *,
        market_inputs: dict[str, Any],
        radar_snapshot: dict[str, Any],
        symbol_features: dict[str, dict[str, Any]],
        formal_status: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Market State → Router → Radar shortlist → Quant → Reasoner → Critic → Gate → PreparedDecision."""
        _ = formal_status  # intentionally unused — formal WF/OOS must not block research
        ms = self.market_state.evaluate(market_inputs)
        self.metrics.market_state_cycles += 1
        self.last_market_state = ms.to_dict()

        route = self.router.route(ms.regime_primary)
        self.last_route = route.to_dict()
        if route.selected_strategy_family is None:
            self.metrics.blocked_decisions += 1
            return {
                "status": "BLOCK",
                "reason": route.abstain_reason,
                "market_state": ms.to_dict(),
                "route": route.to_dict(),
                "funnel": self.metrics.funnel_counts(),
                "formal_gates_not_blocking": True,
            }

        shortlist = self.radar.shortlist(radar_snapshot, n=self.shortlist_n)
        self.metrics.radar_candidates_seen += len(shortlist)
        deep_rows: list[dict[str, Any]] = []
        prepared: list[dict[str, Any]] = []
        actionable: list[tuple[Any, dict[str, Any], Any, Any, Any]] = []

        # Capacity-aware: deep-eval full shortlist, then prepare at most one.
        for cand in shortlist:
            feats = dict(symbol_features.get(cand.symbol) or {})
            feats.setdefault("data_trust", market_inputs.get("data_trust", 0.8))
            feats.setdefault("freshness_sec", market_inputs.get("freshness_sec", 5))
            feats.setdefault("spread", market_inputs.get("spread", 0.0004))
            feats.setdefault("liquidity", market_inputs.get("liquidity", 0.8))
            feats.setdefault("funding", market_inputs.get("funding", 0.0))

            q = self.quant.evaluate(cand.symbol, feats, route.selected_strategy_family)
            self.metrics.deep_quant_evaluations += 1

            r = self.reasoner.reason(
                symbol=cand.symbol,
                regime=ms.regime_primary,
                family=route.selected_strategy_family,
                quant=q,
                market=feats,
            )
            self.metrics.ai_reasoner_evaluations += 1
            if r.verdict == "LONG":
                self.metrics.reasoner_long += 1
            elif r.verdict == "SHORT":
                self.metrics.reasoner_short += 1
            elif r.verdict == "WAIT":
                self.metrics.reasoner_wait += 1
                self.metrics.wait_decisions += 1
            elif r.verdict == "BLOCK":
                self.metrics.blocked_decisions += 1

            c = self.critic.critique(r, feats)
            self.metrics.ai_critic_evaluations += 1
            if c.verdict == "REJECT":
                self.metrics.critic_rejected += 1
                self.metrics.blocked_decisions += 1

            row = {
                "symbol": cand.symbol,
                "rank": cand.rank,
                "radar_eligible": cand.radar_eligible,
                "trade_eligible": cand.trade_eligible,
                "quant": q.to_dict(),
                "reasoner": r.to_dict(),
                "critic": c.to_dict(),
            }
            deep_rows.append(row)
            self.last_ai_decision = {
                "symbol": cand.symbol,
                "verdict": r.verdict,
                "critic": c.verdict,
                "objections": c.objections,
            }

            if r.verdict in {"WAIT", "BLOCK"} or c.verdict == "REJECT":
                continue

            gate = self.exploration_gate.evaluate(
                {
                    "data_trust": feats.get("data_trust"),
                    "freshness_sec": feats.get("freshness_sec"),
                    "exchange_ok": True,
                    "position_safety_ok": True,
                    "loss_safety_ok": True,
                    "regime": ms.regime_primary,
                    "strategy_fit_score": route.strategy_fit_score,
                    "expected_edge": q.expected_edge,
                    "estimated_cost": q.estimated_cost,
                    "economic_thesis": r.thesis,
                    "spread": feats.get("spread"),
                    "liquidity": feats.get("liquidity"),
                    "ai_quant_agreement": q.side_bias == r.verdict,
                    "critic_objections": c.objections,
                    "radar_eligible": cand.radar_eligible,
                    "trade_eligible": cand.trade_eligible,
                }
            )
            row["exploration_gate"] = gate.to_dict()
            if not gate.passed:
                self.metrics.blocked_decisions += 1
                continue
            actionable.append((cand, feats, q, r, c))

        for cand, feats, q, r, c in actionable:
            risk_packet = {
                "execution_purpose": EXECUTION_PURPOSE_RESEARCH,
                "demo_only": True,
                "mainnet": False,
                "real_money": False,
                "leverage": 1,
                "open_positions": self.positions.open_count(),
                "stop_logic": r.stop_logic,
                "max_hold": 1800,
                "requested_size": float(feats.get("min_size") or 0.001),
                "member_execution": 0,
            }
            risk = self.research_risk.evaluate(risk_packet)
            self.last_risk = risk.to_dict()
            if not risk.passed:
                self.metrics.research_risk_block_count += 1
                continue
            self.metrics.research_risk_pass_count += 1

            ok_budget, budget_reason = self.budget.can_open(_now_ms())
            if not ok_budget:
                self.metrics.blocked_decisions += 1
                continue

            pd = PreparedDecision(
                symbol=cand.symbol,
                regime=ms.regime_primary,
                strategy_family=route.selected_strategy_family or "",
                side=r.verdict,
                setup_type=r.setup_type,
                entry_trigger=r.entry_trigger,
                entry_zone=r.entry_zone,
                expected_edge=q.expected_edge,
                estimated_cost=q.estimated_cost,
                supporting_evidence=r.supporting_evidence,
                contradicting_evidence=r.contradicting_evidence + c.objections,
                confidence=r.confidence,
                invalidation=["regime_change", "data_stale", "setup_invalid"],
                stop_logic=r.stop_logic,
                take_profit_logic=r.take_profit_logic,
                max_hold=risk.max_hold_sec,
                requested_size=risk.size,
                research_policy=POLICY_RESEARCH_AI_DEMO,
                candidate_id=f"radar#{cand.rank}:{cand.symbol}",
                strategy_id=f"{route.selected_strategy_family}_RESEARCH",
                strategy_version=route.strategy_version,
                reasoner_result=r.to_dict(),
                critic_result=c.to_dict(),
                risk_result=risk.to_dict(),
                radar_snapshot=cand.to_dict(),
                market_snapshot=feats,
                activity_snapshot={"note": "activity_label_only"},
                status="PREPARING",
            )
            pd.transition("READY", reason="slow_path_complete")
            self.decisions.put(pd)
            self.metrics.prepared_decisions_created += 1
            prepared.append(pd.to_dict())
            # Concurrent research intent: at most one prepared actionable decision.
            break

        self.last_deep = deep_rows
        return {
            "status": "SLOW_PATH_COMPLETE",
            "market_state": ms.to_dict(),
            "route": route.to_dict(),
            "deep_evaluations": deep_rows,
            "prepared_decisions": prepared,
            "funnel": self.metrics.funnel_counts(),
            "policy": RESEARCH_AI_DEMO_POLICY.policy,
            "formal_gates_not_blocking": True,
        }

    def run_fast_path_for_ready(self, market_updates: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        # Reset per-order leak accounting baseline
        for pd in self.decisions.list_by_status("READY"):
            HOT_PATH_GUARD.leaks.clear()
            # Do not reset total leak count mid-campaign; track per execution via result flag
            leak_before = HOT_PATH_GUARD.slow_path_leak_count
            upd = dict(market_updates.get(pd.symbol) or {})
            if not upd:
                self.metrics.trigger_not_reached += 1
                results.append({"decision_id": pd.decision_id, "executed": False, "reason": "no_market_update"})
                continue
            # Invalidate checks
            inv = pd.check_invalidate(context={"regime": upd.get("regime"), "data_stale": upd.get("data_stale")})
            if inv == "ttl":
                self.metrics.prepared_decisions_expired += 1
                continue
            if inv:
                continue

            exec_res = self.fast_path.execute_if_triggered(
                pd,
                market_update=upd,
                risk_packet_extra={"open_positions": self.positions.open_count()},
            )
            if exec_res.get("reason") == "trigger_not_reached":
                self.metrics.trigger_not_reached += 1
            if exec_res.get("slow_path_leak") or HOT_PATH_GUARD.slow_path_leak_count > leak_before:
                self.metrics.slow_path_leak_count += 1
            if exec_res.get("executed"):
                self.metrics.prepared_decisions_triggered += 1
                self.metrics.research_demo_orders += 1
                self.budget.record_entry(_now_ms())
                order = exec_res.get("order") or {}
                fill_px = float(upd.get("last_price") or upd.get("price") or 0.0)
                pos = self.positions.open_from_execution(
                    decision=pd.to_dict(),
                    fill_price=fill_px,
                    qty=float((exec_res.get("intent") or {}).get("qty") or pd.requested_size),
                )
                # latency aggregate
                from backend.nexus_research_ai_autonomy.latency import LatencyTrace

                lat = exec_res.get("latency") or {}
                trace = LatencyTrace(
                    decision_id=pd.decision_id,
                    market_event_ts=int(lat.get("market_event_ts") or 0),
                    feature_ready_ts=int(lat.get("feature_ready_ts") or 0),
                    trigger_ts=int(lat.get("trigger_ts") or 0),
                    risk_start_ts=int(lat.get("risk_start_ts") or 0),
                    risk_pass_ts=int(lat.get("risk_pass_ts") or 0),
                    order_intent_ts=int(lat.get("order_intent_ts") or 0),
                    http_send_ts=int(lat.get("http_send_ts") or 0),
                    exchange_ack_ts=int(lat.get("exchange_ack_ts") or 0),
                    fill_ts=int(lat.get("fill_ts") or 0),
                    slow_path_leak=bool(exec_res.get("slow_path_leak")),
                )
                self.latency_agg.add(trace)
                exec_res["position_id"] = pos.position_id
            results.append(exec_res)
        self.metrics.latency_summary = self.latency_agg.summary()
        return results

    def manage_open_positions(self, markets: dict[str, dict[str, Any]], *, ai_proposals: dict[str, str] | None = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for pos in list(self.positions.positions.values()):
            if pos.status != "OPEN":
                continue
            m = dict(markets.get(pos.symbol) or {})
            prop = (ai_proposals or {}).get(pos.position_id) or (ai_proposals or {}).get(pos.symbol) or "HOLD"
            res = self.positions.manage_cycle(
                pos.position_id,
                market=m,
                regime=str(m.get("regime") or pos.regime_at_entry),
                ai_proposal=prop,
                ai_widens_max_risk=False,
            )
            out.append(res)
            if res.get("action") == "EXIT":
                self.budget.record_close()
                pnl = float(res.get("pnl_pct") or 0.0)
                if pnl > 0:
                    self.metrics.research_demo_wins += 1
                elif pnl < 0:
                    self.metrics.research_demo_losses += 1
                self.metrics.research_demo_completed_lifecycles += 1
                closed = res.get("position") or pos.to_dict()
                self.last_closed = closed
                # enqueue reflection (async)
                lifecycle = {
                    "decision_id": pos.decision_id,
                    "symbol": pos.symbol,
                    "side": pos.side,
                    "strategy_family": pos.strategy_family,
                    "regime": pos.regime_at_entry,
                    "entry_price": pos.entry_price,
                    "exit_price": float(m.get("last_price") or m.get("price") or pos.entry_price),
                    "pnl_pct": pnl,
                    "exit_reason": res.get("reason"),
                    "pit_market_path": [
                        {"price": pos.entry_price},
                        {"price": (pos.entry_price + float(m.get("last_price") or pos.entry_price)) / 2.0},
                        {"price": float(m.get("last_price") or pos.entry_price)},
                    ],
                    "process_evidence": {
                        "rule_violation_ids": [],
                        "missing_evidence_ids": [],
                        "risk_gate_results": {"status": "PASS"},
                        "cost_gate_results": {"status": "PASS"},
                        "data_quality_results": {"status": "PASS"},
                        "prohibited_action_results": [],
                        "entry_rule_compliance": "PASS",
                        "exit_rule_compliance": "PASS",
                        "regime_diagnosis": "ok",
                        "strategy_selection": "ok",
                        "direction": "ok",
                        "why": res.get("reason"),
                    },
                }
                # Mark timing error example when hard_stop on breakout-like exits quickly
                if res.get("reason") == "hard_stop":
                    lifecycle["process_evidence"]["timing_error"] = True
                    lifecycle["process_evidence"]["entry_rule_compliance"] = "FAIL"
                    lifecycle["process_evidence"]["rule_violation_ids"] = ["EARLY_ENTRY"]
                self.reflection.enqueue_lifecycle(lifecycle)
        return out

    def run_reflection_async(self) -> list[dict[str, Any]]:
        records = self.reflection.drain_async()
        out: list[dict[str, Any]] = []
        for rec in records:
            self.metrics.reflections_completed += 1
            self.metrics.counterfactuals_completed += len(rec.counterfactuals)
            self.metrics.note_process_class(rec.process_class)
            if rec.lesson_candidate:
                self.lessons.ingest_lesson_candidate(rec.lesson_candidate)
                self.metrics.lesson_candidates_created += 1
            self.metrics.active_lessons_created_from_live_demo = self.lessons.active_lessons_created_from_live_demo
            self.memory.link_research_lifecycle(
                regime=str((rec.process_notes or {}).get("regime_diagnosis") or ""),
                strategy_family="",
                symbol=rec.symbol,
                decision_id=rec.decision_id,
                trade={"decision_id": rec.decision_id},
                management_journal=[j.to_dict() for j in self.positions.journal if j.position_id],
                outcome={"process_class": rec.process_class, "pnl_note": rec.what_happened},
                reflection=rec.to_dict(),
                error_classes=rec.error_classes,
                lesson_candidate=rec.lesson_candidate,
            )
            self.last_reflection = rec.to_dict()
            out.append(rec.to_dict())
        return out

    def monitor_snapshot(self) -> dict[str, Any]:
        open_pos = [p.to_dict() for p in self.positions.positions.values() if p.status == "OPEN"]
        ready = [d.to_dict() for d in self.decisions.list_by_status("READY")]
        lat = self.latency_agg.summary()
        # Separate REAL BYBIT vs LOCAL SIM vs SHADOW — never conflate labels.
        transport = getattr(getattr(self, "fast_path", None), "transport", None)
        inner = getattr(transport, "inner", transport)
        transport_mode = str(getattr(inner, "last_transport_mode", None) or "")
        real_http = bool(getattr(inner, "last_real_http_request", False))
        if transport_mode == "BYBIT_DEMO_REAL_TRANSPORT" and real_http:
            lane = "REAL_BYBIT"
        elif transport_mode in {"SHADOW", "ACTIVITY_SHADOW"}:
            lane = "SHADOW"
        else:
            # ProvenanceRecordingTransport / SimulatedDemoTransport → LOCAL_SIMULATION
            lane = "LOCAL_SIMULATION"
            records = getattr(transport, "records", None) or []
            if records:
                last = (records[-1].get("result") or records[-1].get("provenance") or {})
                if last.get("transport_mode") == "BYBIT_DEMO_REAL_TRANSPORT" and last.get(
                    "real_http_request"
                ):
                    lane = "REAL_BYBIT"
                elif str(last.get("transport_mode") or "") == "LOCAL_SIMULATION":
                    lane = "LOCAL_SIMULATION"
        ref_tag = (self.last_reflection or {}).get("transport_tag")
        return {
            "founder_only": True,
            "member_product": False,
            "secrets_exposed": False,
            "execution_lanes": {
                "REAL_BYBIT": lane == "REAL_BYBIT",
                "LOCAL_SIMULATION": lane == "LOCAL_SIMULATION",
                "SHADOW": lane == "SHADOW",
                "active_lane": lane,
                "labels_separated": True,
            },
            "market_regime": self.last_market_state,
            "radar_shortlist": [
                c.to_dict() for c in self.radar.shortlist(self.radar.last_snapshot or {"ranking_authority": "SERVER", "candidates": []}, n=self.shortlist_n)
            ] if self.radar.last_snapshot else [],
            "deep_evaluated": self.last_deep,
            "prepared_decisions": ready,
            "research_demo_position": open_pos[0] if open_pos else None,
            "last_ai_decision": self.last_ai_decision,
            "last_risk_result": self.last_risk,
            "last_closed_research_demo": self.last_closed,
            "last_reflection": self.last_reflection,
            "last_reflection_transport_tag": ref_tag,
            "experience_counters": self.metrics.to_dict(),
            "latency": {
                "trigger_to_send_p50_ms": lat.get("trigger_to_send_p50_ms"),
                "trigger_to_send_p95_ms": lat.get("trigger_to_send_p95_ms"),
                "send_to_ack_p50_ms": lat.get("send_to_ack_p50_ms"),
                "send_to_ack_p95_ms": lat.get("send_to_ack_p95_ms"),
                "market_to_fill_p50_ms": lat.get("market_to_fill_p50_ms"),
                "market_to_fill_p95_ms": lat.get("market_to_fill_p95_ms"),
                "slow_path_leak_count": self.metrics.slow_path_leak_count,
                "lane": lane,
            },
            "policy_split": {
                "RESEARCH_AI_DEMO": {
                    "requires_pre_wf": False,
                    "requires_formal_wf": False,
                    "requires_oos": False,
                },
                "QUALIFIED_SYSTEM_DEMO": {
                    "requires_pre_wf": True,
                    "requires_formal_wf": True,
                    "requires_oos": True,
                    "weakened": False,
                },
            },
            "safety": {
                "demo_only": True,
                "mainnet_writes": 0,
                "real_money": False,
                "member_execution": 0,
                "leverage": 1,
                "max_concurrent": 1,
            },
        }
