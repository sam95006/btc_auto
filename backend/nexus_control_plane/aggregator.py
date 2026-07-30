"""Control Plane aggregators — ownership-enforced overview fields."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from backend.nexus_control_plane import (
    DATA_STATUS_LIVE,
    DATA_STATUS_MISSING,
    DATA_STATUS_SERVICE_UNAVAILABLE,
    DATA_STATUS_UNKNOWN,
    EXECUTION_OWNER_DEMO_VALIDATION,
    LEGACY_STAGE3_LABELS,
    ROLE_CONTROL_PLANE,
    ROLE_DEMO_EXECUTION,
    ROLE_LEARNING_ENGINE,
    ROLE_MARKET_INTELLIGENCE,
    SCHEMA_VERSION,
)
from backend.nexus_control_plane.cost_gate_diagnosis import why_no_trade_message
from backend.nexus_control_plane.federation_client import FederationClient
from backend.nexus_control_plane.field_envelope import envelope, missing
from backend.nexus_control_plane.ownership_contract import validate_execution_ownership
from backend.nexus_control_plane.service_registry import ServiceRegistry


def _bounded(payload: dict[str, Any]) -> dict[str, Any]:
    return (payload.get("bounded_6h") if isinstance(payload.get("bounded_6h"), dict) else None) or payload


@dataclass
class ControlPlaneAggregator:
    registry: ServiceRegistry
    client: FederationClient

    def overview(self) -> dict[str, Any]:
        now = time.time()
        market = self.client.get_json(ROLE_MARKET_INTELLIGENCE, "/api/nexus/stage3/status")
        demo_status = self.client.get_json(ROLE_DEMO_EXECUTION, "/api/nexus/demo-execution/status")
        demo_account = self.client.get_json(ROLE_DEMO_EXECUTION, "/api/nexus/demo-execution/account?fresh=true")
        demo_6h = self.client.get_json(ROLE_DEMO_EXECUTION, "/api/nexus/demo-execution/bounded-6h/status")
        ownership = validate_execution_ownership(self.registry)

        funnel = self._market_funnel(market, demo_6h, now)
        session = self._demo_session(demo_6h, demo_status, now)
        why = self._why_no_trade(demo_6h)

        return {
            "schema_version": SCHEMA_VERSION,
            "system_mode": {
                "bybit_demo": True,
                "mainnet": False,
                "real_money": False,
                "fixed_leverage": 25,
                "margin_mode": "ISOLATED",
                "execution_owner": EXECUTION_OWNER_DEMO_VALIDATION,
                "stage3_execution_disabled": True,
                "automatic_extension": False,
            },
            "service_health": self._service_health(market, demo_status),
            "demo_session": session,
            "demo_account": self._demo_account(demo_account, now),
            "market": funnel,
            "market_funnel": funnel,
            "execution": self._current_execution(demo_6h, demo_status, now),
            "current_execution": self._current_execution(demo_6h, demo_status, now),
            "portfolio": self._portfolio(demo_account, demo_6h, now),
            "performance": self._performance(demo_6h, now),
            "learning": self._learning(demo_6h, now),
            "safety": self._safety(demo_6h, ownership, now),
            "why_no_trade": why,
            "runtime_identity": self._runtime_identity(demo_6h, demo_status, now),
            "version_labels": self._version_labels(demo_6h, now),
            "ownership": {
                "market_scan": ROLE_MARKET_INTELLIGENCE,
                "demo_wallet": ROLE_DEMO_EXECUTION,
                "demo_session": ROLE_DEMO_EXECUTION,
                "positions_orders": ROLE_DEMO_EXECUTION,
                "outcome_reflection": ROLE_DEMO_EXECUTION,
                "execution_owner_contract": ownership,
                "legacy_stage3_labels": sorted(LEGACY_STAGE3_LABELS),
                "note": "Stage3 legacy autonomous state must not masquerade as Demo Validation state",
            },
            "user_facing": {
                "single_nexus_site": True,
                "hide_dual_demo_cards": True,
                "operator_diagnostics_only_for_service_names": True,
            },
        }

    def services(self) -> dict[str, Any]:
        out = self.registry.summary()
        out["ownership_contract"] = validate_execution_ownership(self.registry)
        return out

    def market(self) -> dict[str, Any]:
        market = self.client.get_json(ROLE_MARKET_INTELLIGENCE, "/api/nexus/stage3/status")
        return {"market": self._market_funnel(market, {"ok": False}, time.time()), "raw_ok": market.get("ok")}

    def demo_session(self) -> dict[str, Any]:
        demo_6h = self.client.get_json(ROLE_DEMO_EXECUTION, "/api/nexus/demo-execution/bounded-6h/status")
        demo_status = self.client.get_json(ROLE_DEMO_EXECUTION, "/api/nexus/demo-execution/status")
        return self._demo_session(demo_6h, demo_status, time.time())

    def positions(self) -> dict[str, Any]:
        demo_6h = self.client.get_json(ROLE_DEMO_EXECUTION, "/api/nexus/demo-execution/bounded-6h/status")
        return self._current_execution(demo_6h, {"ok": False}, time.time())

    def performance(self) -> dict[str, Any]:
        demo_6h = self.client.get_json(ROLE_DEMO_EXECUTION, "/api/nexus/demo-execution/bounded-6h/status")
        return self._performance(demo_6h, time.time())

    def learning(self) -> dict[str, Any]:
        demo_6h = self.client.get_json(ROLE_DEMO_EXECUTION, "/api/nexus/demo-execution/bounded-6h/status")
        return self._learning(demo_6h, time.time())

    def runtime_identity(self) -> dict[str, Any]:
        demo_6h = self.client.get_json(ROLE_DEMO_EXECUTION, "/api/nexus/demo-execution/bounded-6h/status")
        demo_status = self.client.get_json(ROLE_DEMO_EXECUTION, "/api/nexus/demo-execution/status")
        return self._runtime_identity(demo_6h, demo_status, time.time())

    def why_no_trade(self) -> dict[str, Any]:
        demo_6h = self.client.get_json(ROLE_DEMO_EXECUTION, "/api/nexus/demo-execution/bounded-6h/status")
        return self._why_no_trade(demo_6h)

    def _why_no_trade(self, demo_6h: dict[str, Any]) -> dict[str, Any]:
        if not demo_6h.get("ok"):
            return {
                "active": True,
                "headline": "DEMO_EXECUTION_SERVICE_UNAVAILABLE",
                "detail": "無法取得 Demo Session 漏斗；不得回退 Stage3 舊交易狀態。",
                "gate_breakdown": None,
            }
        b = _bounded(demo_6h.get("payload") or {})
        msg = why_no_trade_message(
            candidates_total=int(b.get("candidates_total") or 0),
            cost_gate_blocks=int(b.get("cost_gate_blocks") or 0),
            entries=int(b.get("entries_total") or 0),
        )
        msg["gate_breakdown"] = {
            "candidates_total": b.get("candidates_total"),
            "risk_critic_blocks": b.get("risk_critic_blocks"),
            "mistake_guard_blocks": b.get("mistake_guard_blocks"),
            "cost_gate_blocks": b.get("cost_gate_blocks"),
            "data_missing_blocks": b.get("data_missing_blocks"),
            "fee_unknown_blocks": b.get("fee_unknown_blocks"),
            "funding_buffer_blocks": b.get("funding_buffer_blocks"),
            "spread_blocks": b.get("spread_blocks"),
            "slippage_blocks": b.get("slippage_blocks"),
            "net_reward_blocks": b.get("net_reward_blocks"),
            "entries_total": b.get("entries_total"),
        }
        return msg

    def _service_health(self, market: dict[str, Any], demo: dict[str, Any]) -> dict[str, Any]:
        def one(role: str, probe: dict[str, Any]) -> dict[str, Any]:
            if probe.get("ok"):
                status = DATA_STATUS_LIVE
                health = "HEALTHY"
            else:
                status = probe.get("data_status") or DATA_STATUS_SERVICE_UNAVAILABLE
                health = "DOWN"
            return envelope(
                health,
                source_service=role,
                source_role=role,
                source_timestamp=probe.get("fetched_at"),
                data_status=status,
                evidence_ref=probe.get("error") or "health_probe",
            )

        return {
            "market_intelligence": one(ROLE_MARKET_INTELLIGENCE, market),
            "demo_execution": one(ROLE_DEMO_EXECUTION, demo),
            "learning_engine": one(ROLE_LEARNING_ENGINE, demo),
            "control_plane": envelope(
                "HEALTHY",
                source_service=ROLE_CONTROL_PLANE,
                source_role=ROLE_CONTROL_PLANE,
                source_timestamp=time.time(),
                data_status=DATA_STATUS_LIVE,
                evidence_ref="local",
            ),
        }

    def _demo_session(self, demo_6h: dict[str, Any], demo_status: dict[str, Any], now: float) -> dict[str, Any]:
        if not demo_6h.get("ok"):
            return {
                "session": envelope(
                    None,
                    source_service=ROLE_DEMO_EXECUTION,
                    source_role=ROLE_DEMO_EXECUTION,
                    data_status=DATA_STATUS_SERVICE_UNAVAILABLE,
                    evidence_ref="DEMO_EXECUTION_SERVICE_UNAVAILABLE",
                ),
                "note": "DEMO_EXECUTION_SERVICE_UNAVAILABLE",
            }
        bounded = _bounded(demo_6h.get("payload") or {})
        ts = demo_6h.get("fetched_at")

        def f(key: str) -> dict[str, Any]:
            return envelope(
                bounded.get(key),
                source_service=ROLE_DEMO_EXECUTION,
                source_role=ROLE_DEMO_EXECUTION,
                source_timestamp=ts,
                data_status=DATA_STATUS_LIVE if key in bounded else DATA_STATUS_MISSING,
                evidence_ref=f"bounded_6h.{key}",
                now=now,
            )

        started = bounded.get("started_at")
        ends = bounded.get("ends_at") or bounded.get("deadline_at")
        remaining = None
        if ends is not None:
            try:
                remaining = max(0.0, float(ends) - now)
            except (TypeError, ValueError):
                remaining = None
        elif started is not None:
            try:
                remaining = max(0.0, float(started) + 6 * 3600 - now)
            except (TypeError, ValueError):
                remaining = None

        return {
            "session_id": f("session_id"),
            "status": f("status"),
            "started_at": f("started_at"),
            "ends_at": envelope(
                ends,
                source_service=ROLE_DEMO_EXECUTION,
                source_role=ROLE_DEMO_EXECUTION,
                source_timestamp=ts,
                data_status=DATA_STATUS_LIVE if ends is not None else DATA_STATUS_MISSING,
                evidence_ref="bounded_6h.ends_at",
                now=now,
            ),
            "remaining_seconds": envelope(
                remaining,
                source_service=ROLE_CONTROL_PLANE,
                source_role=ROLE_CONTROL_PLANE,
                source_timestamp=now,
                data_status=DATA_STATUS_LIVE if remaining is not None else DATA_STATUS_MISSING,
                evidence_ref="derived_remaining",
                now=now,
            ),
            "entries_total": f("entries_total"),
            "entry_limit": envelope(
                bounded.get("max_entries") or bounded.get("entry_limit") or 6,
                source_service=ROLE_DEMO_EXECUTION,
                source_role=ROLE_DEMO_EXECUTION,
                source_timestamp=ts,
                data_status=DATA_STATUS_LIVE,
                evidence_ref="bounded_6h.entry_limit",
                now=now,
            ),
            "trades_completed": f("trades_completed"),
            "session_write_enabled": f("session_write_enabled"),
            "automatic_extension": envelope(
                False,
                source_service=ROLE_CONTROL_PLANE,
                source_role=ROLE_CONTROL_PLANE,
                source_timestamp=now,
                data_status=DATA_STATUS_LIVE,
                evidence_ref="policy_fixed",
                now=now,
            ),
        }

    def _demo_account(self, demo_account: dict[str, Any], now: float) -> dict[str, Any]:
        if not demo_account.get("ok"):
            return {
                "wallet_balance": missing(ROLE_DEMO_EXECUTION, evidence_ref="DEMO_EXECUTION_SERVICE_UNAVAILABLE"),
                "equity": missing(ROLE_DEMO_EXECUTION, evidence_ref="DEMO_EXECUTION_SERVICE_UNAVAILABLE"),
                "available_balance": missing(ROLE_DEMO_EXECUTION, evidence_ref="DEMO_EXECUTION_SERVICE_UNAVAILABLE"),
                "note": "DEMO_EXECUTION_SERVICE_UNAVAILABLE — do not fall back to Stage3 account",
            }
        p = demo_account.get("payload") or {}
        if p.get("available") is False or p.get("reason"):
            return {
                "wallet_balance": missing(ROLE_DEMO_EXECUTION, evidence_ref=str(p.get("reason") or "unavailable")),
                "equity": missing(ROLE_DEMO_EXECUTION, evidence_ref=str(p.get("reason") or "unavailable")),
                "available_balance": missing(ROLE_DEMO_EXECUTION, evidence_ref=str(p.get("reason") or "unavailable")),
                "used_margin": missing(ROLE_DEMO_EXECUTION, evidence_ref=str(p.get("reason") or "unavailable")),
                "unrealized_pnl": missing(ROLE_DEMO_EXECUTION, evidence_ref=str(p.get("reason") or "unavailable")),
                "source": envelope(
                    p.get("source"),
                    source_service=ROLE_DEMO_EXECUTION,
                    source_role=ROLE_DEMO_EXECUTION,
                    data_status=DATA_STATUS_UNKNOWN,
                ),
            }
        ts = demo_account.get("fetched_at")

        def f(key: str) -> dict[str, Any]:
            return envelope(
                p.get(key),
                source_service=ROLE_DEMO_EXECUTION,
                source_role=ROLE_DEMO_EXECUTION,
                source_timestamp=ts,
                data_status=DATA_STATUS_LIVE if key in p else DATA_STATUS_MISSING,
                evidence_ref="demo-execution/account",
                now=now,
            )

        return {
            "wallet_balance": f("wallet_balance"),
            "equity": f("equity"),
            "available_balance": f("available_balance"),
            "used_margin": f("used_margin"),
            "unrealized_pnl": f("unrealized_pnl"),
            "open_positions": f("open_positions"),
            "open_orders": f("open_orders"),
            "source": envelope(
                p.get("source"),
                source_service=ROLE_DEMO_EXECUTION,
                source_role=ROLE_DEMO_EXECUTION,
                source_timestamp=ts,
                data_status=DATA_STATUS_LIVE if p.get("source") else DATA_STATUS_MISSING,
                evidence_ref="demo-execution/account",
                now=now,
            ),
        }

    def _market_funnel(self, market: dict[str, Any], demo_6h: dict[str, Any], now: float) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if market.get("ok"):
            p = market.get("payload") or {}
            ts = market.get("fetched_at")
            out["stage3_status"] = envelope(
                p.get("status") or p.get("mode") or "OK",
                source_service=ROLE_MARKET_INTELLIGENCE,
                source_role=ROLE_MARKET_INTELLIGENCE,
                source_timestamp=ts,
                data_status=DATA_STATUS_LIVE,
                evidence_ref="/api/nexus/stage3/status",
                now=now,
            )
        else:
            out["stage3_status"] = envelope(
                None,
                source_service=ROLE_MARKET_INTELLIGENCE,
                source_role=ROLE_MARKET_INTELLIGENCE,
                data_status=DATA_STATUS_SERVICE_UNAVAILABLE,
                evidence_ref="SERVICE_UNAVAILABLE",
                now=now,
            )
        if demo_6h.get("ok"):
            b = _bounded(demo_6h.get("payload") or {})
            ts = demo_6h.get("fetched_at")
            for key in (
                "candidates_total",
                "cost_gate_blocks",
                "mistake_guard_blocks",
                "risk_critic_blocks",
                "universe_count",
                "tradable_count",
            ):
                out[key] = envelope(
                    b.get(key),
                    source_service=ROLE_DEMO_EXECUTION,
                    source_role=ROLE_DEMO_EXECUTION,
                    source_timestamp=ts,
                    data_status=DATA_STATUS_LIVE if key in b else DATA_STATUS_MISSING,
                    evidence_ref=f"bounded_6h.{key}",
                    now=now,
                )
        else:
            for key in (
                "candidates_total",
                "cost_gate_blocks",
                "mistake_guard_blocks",
                "risk_critic_blocks",
                "universe_count",
                "tradable_count",
            ):
                out[key] = missing(ROLE_DEMO_EXECUTION, evidence_ref="bounded_6h_unavailable")
        return out

    def _current_execution(self, demo_6h: dict[str, Any], demo_status: dict[str, Any], now: float) -> dict[str, Any]:
        if not demo_6h.get("ok"):
            return {
                "note": "DEMO_EXECUTION_SERVICE_UNAVAILABLE",
                "open_position": missing(ROLE_DEMO_EXECUTION, evidence_ref="DEMO_EXECUTION_SERVICE_UNAVAILABLE"),
            }
        b = _bounded(demo_6h.get("payload") or {})
        ts = demo_6h.get("fetched_at")

        def f(key: str) -> dict[str, Any]:
            return envelope(
                b.get(key),
                source_service=ROLE_DEMO_EXECUTION,
                source_role=ROLE_DEMO_EXECUTION,
                source_timestamp=ts,
                data_status=DATA_STATUS_LIVE if key in b else DATA_STATUS_MISSING,
                evidence_ref=f"bounded_6h.{key}",
                now=now,
            )

        return {
            "current_candidate": f("current_candidate") if "current_candidate" in b else f("selected_candidate"),
            "open_position": f("open_position"),
            "open_orders": f("open_orders") if "open_orders" in b else f("open_order_count"),
            "stop_loss": f("stop_loss") if "stop_loss" in b else f("sl"),
            "take_profit": f("take_profit") if "take_profit" in b else f("tp"),
            "protection_status": f("protection_status"),
            "reconciliation": f("reconciliation"),
            "entries_total": f("entries_total"),
            "kill_switch_events": f("kill_switch_events"),
        }

    def _portfolio(self, demo_account: dict[str, Any], demo_6h: dict[str, Any], now: float) -> dict[str, Any]:
        account = self._demo_account(demo_account, now)
        execu = self._current_execution(demo_6h, {"ok": False}, now)
        return {
            "equity": account.get("equity"),
            "available_balance": account.get("available_balance"),
            "open_position": execu.get("open_position"),
            "open_orders": execu.get("open_orders"),
            "note": account.get("note") or execu.get("note"),
        }

    def _performance(self, demo_6h: dict[str, Any], now: float) -> dict[str, Any]:
        if not demo_6h.get("ok"):
            return {"note": "DEMO_EXECUTION_SERVICE_UNAVAILABLE"}
        b = _bounded(demo_6h.get("payload") or {})
        ts = demo_6h.get("fetched_at")
        keys = ("gross_pnl", "total_fees", "funding", "net_pnl", "wins", "losses", "max_drawdown")
        return {
            k: envelope(
                b.get(k),
                source_service=ROLE_DEMO_EXECUTION,
                source_role=ROLE_DEMO_EXECUTION,
                source_timestamp=ts,
                data_status=DATA_STATUS_LIVE if k in b else DATA_STATUS_MISSING,
                evidence_ref=f"bounded_6h.{k}",
                now=now,
            )
            for k in keys
        }

    def _learning(self, demo_6h: dict[str, Any], now: float) -> dict[str, Any]:
        if not demo_6h.get("ok"):
            return {"note": "LEARNING_EVIDENCE_UNAVAILABLE", "learning_effectiveness": "NOT_YET_OBSERVABLE"}
        b = _bounded(demo_6h.get("payload") or {})
        ts = demo_6h.get("fetched_at")
        chain = b.get("learning_chain") if isinstance(b.get("learning_chain"), dict) else {}
        delta_count = b.get("decision_delta_count")
        similar = b.get("similar_case_count") or chain.get("similar_candidate_id")
        if not b.get("reflection_count") and not chain:
            effectiveness = "NOT_YET_OBSERVABLE"
        elif not similar:
            effectiveness = "NOT_YET_OBSERVABLE"
        elif not delta_count:
            effectiveness = "NOT_PROVEN"
        else:
            effectiveness = "PRELIMINARY_EVIDENCE"

        def f(key: str, src: dict[str, Any] | None = None) -> dict[str, Any]:
            bag = src if src is not None else b
            return envelope(
                bag.get(key),
                source_service=ROLE_DEMO_EXECUTION,
                source_role=ROLE_LEARNING_ENGINE,
                source_timestamp=ts,
                data_status=DATA_STATUS_LIVE if key in bag else DATA_STATUS_MISSING,
                evidence_ref=f"learning.{key}",
                now=now,
            )

        return {
            "evidence_chain": {
                "source_trade_case_id": f("source_trade_case_id", chain),
                "outcome": f("outcome", chain),
                "process_quality": f("process_quality", chain),
                "reflection_summary": f("reflection_summary", chain),
                "counterfactual": f("counterfactual", chain),
                "learning_proposal_status": f("learning_proposal_status", chain),
                "similar_candidate_id": f("similar_candidate_id", chain),
                "similarity_score": f("similarity_score", chain),
                "before_verdict": f("before_verdict", chain),
                "after_verdict": f("after_verdict", chain),
                "guard_action": f("guard_action", chain),
                "policy_version": f("policy_version", chain),
            },
            "decision_delta_count": f("decision_delta_count"),
            "good_process_wins": f("good_process_wins"),
            "good_process_losses": f("good_process_losses"),
            "bad_process_wins": f("bad_process_wins"),
            "bad_process_losses": f("bad_process_losses"),
            "learning_effectiveness": envelope(
                effectiveness,
                source_service=ROLE_CONTROL_PLANE,
                source_role=ROLE_LEARNING_ENGINE,
                source_timestamp=now,
                data_status=DATA_STATUS_LIVE,
                evidence_ref="derived_effectiveness",
                now=now,
            ),
            "forbidden_labels": {
                "PROVEN": False,
                "SELF_IMPROVING_CONFIRMED": False,
                "PROFITABLE": False,
            },
        }

    def _safety(self, demo_6h: dict[str, Any], ownership: dict[str, Any], now: float) -> dict[str, Any]:
        if not demo_6h.get("ok"):
            return {
                "note": "DEMO_EXECUTION_SERVICE_UNAVAILABLE",
                "ownership_ok": ownership.get("ok"),
            }
        b = _bounded(demo_6h.get("payload") or {})
        ts = demo_6h.get("fetched_at")
        return {
            "reconciliation": envelope(
                b.get("reconciliation"),
                source_service=ROLE_DEMO_EXECUTION,
                source_role=ROLE_DEMO_EXECUTION,
                source_timestamp=ts,
                data_status=DATA_STATUS_LIVE if "reconciliation" in b else DATA_STATUS_MISSING,
                evidence_ref="bounded_6h.reconciliation",
                now=now,
            ),
            "kill_switch_events": envelope(
                b.get("kill_switch_events"),
                source_service=ROLE_DEMO_EXECUTION,
                source_role=ROLE_DEMO_EXECUTION,
                source_timestamp=ts,
                data_status=DATA_STATUS_LIVE if "kill_switch_events" in b else DATA_STATUS_MISSING,
                evidence_ref="bounded_6h.kill_switch_events",
                now=now,
            ),
            "execution_owner_count": envelope(
                ownership.get("execution_owner_count"),
                source_service=ROLE_CONTROL_PLANE,
                source_role=ROLE_CONTROL_PLANE,
                source_timestamp=now,
                data_status=DATA_STATUS_LIVE,
                evidence_ref="ownership_contract",
                now=now,
            ),
            "ownership_deploy_gate": ownership.get("deploy_gate"),
        }

    def _version_labels(self, demo_6h: dict[str, Any], now: float) -> dict[str, Any]:
        """Keep PR head and observation SHA as separate labels — never conflate."""
        b = _bounded(demo_6h.get("payload") or {}) if demo_6h.get("ok") else {}
        ident = b.get("runtime_identity") if isinstance(b.get("runtime_identity"), dict) else {}
        return {
            "pr6_branch_head": envelope(
                os.environ.get("NEXUS_PR6_BRANCH_HEAD") or "2a647695e9cc6f90d54a92ce5c35fd8de3000aea",
                source_service=ROLE_CONTROL_PLANE,
                source_role=ROLE_CONTROL_PLANE,
                source_timestamp=now,
                data_status=DATA_STATUS_LIVE,
                evidence_ref="label:pr6_branch_head",
                now=now,
            ),
            "observation_deployed_code_sha": envelope(
                ident.get("deployment_commit")
                or os.environ.get("NEXUS_OBSERVATION_CODE_SHA")
                or "9b6f57c1bc3afe988f0fc3829f62dad2ee510156",
                source_service=ROLE_DEMO_EXECUTION if ident.get("deployment_commit") else ROLE_CONTROL_PLANE,
                source_role=ROLE_DEMO_EXECUTION,
                source_timestamp=demo_6h.get("fetched_at") or now,
                data_status=DATA_STATUS_LIVE,
                evidence_ref="label:observation_deployed_code_sha",
                now=now,
            ),
            "control_plane_sha": envelope(
                os.environ.get("NEXUS_CONTROL_PLANE_SHA") or os.environ.get("GITHUB_SHA") or "UNAVAILABLE",
                source_service=ROLE_CONTROL_PLANE,
                source_role=ROLE_CONTROL_PLANE,
                source_timestamp=now,
                data_status=DATA_STATUS_LIVE if os.environ.get("NEXUS_CONTROL_PLANE_SHA") or os.environ.get("GITHUB_SHA") else DATA_STATUS_MISSING,
                evidence_ref="label:control_plane_sha",
                now=now,
            ),
            "deploy_run": envelope(
                os.environ.get("NEXUS_OBSERVATION_DEPLOY_RUN") or "30509623012",
                source_service=ROLE_CONTROL_PLANE,
                source_role=ROLE_CONTROL_PLANE,
                source_timestamp=now,
                data_status=DATA_STATUS_LIVE,
                evidence_ref="label:deploy_run",
                now=now,
            ),
            "note": "PR branch head and observation runtime SHA must never be shown as one version",
        }

    def _runtime_identity(self, demo_6h: dict[str, Any], demo_status: dict[str, Any], now: float) -> dict[str, Any]:
        if demo_6h.get("ok"):
            b = _bounded(demo_6h.get("payload") or {})
            ident = b.get("runtime_identity") or {}
            ts = demo_6h.get("fetched_at")
            return {
                "deployment_commit": envelope(
                    ident.get("deployment_commit"),
                    source_service=ROLE_DEMO_EXECUTION,
                    source_role=ROLE_DEMO_EXECUTION,
                    source_timestamp=ts,
                    data_status=DATA_STATUS_LIVE if ident.get("deployment_commit") else DATA_STATUS_MISSING,
                    evidence_ref="runtime_identity",
                    now=now,
                ),
                "policy_version": envelope(
                    ident.get("policy_version"),
                    source_service=ROLE_DEMO_EXECUTION,
                    source_role=ROLE_DEMO_EXECUTION,
                    source_timestamp=ts,
                    data_status=DATA_STATUS_LIVE if ident.get("policy_version") else DATA_STATUS_MISSING,
                    evidence_ref="runtime_identity",
                    now=now,
                ),
                "schema_version": envelope(
                    ident.get("schema_version") or SCHEMA_VERSION,
                    source_service=ROLE_DEMO_EXECUTION,
                    source_role=ROLE_DEMO_EXECUTION,
                    source_timestamp=ts,
                    data_status=DATA_STATUS_LIVE,
                    evidence_ref="runtime_identity",
                    now=now,
                ),
                "account_epoch": envelope(
                    b.get("account_epoch") or ident.get("account_epoch"),
                    source_service=ROLE_DEMO_EXECUTION,
                    source_role=ROLE_DEMO_EXECUTION,
                    source_timestamp=ts,
                    data_status=DATA_STATUS_LIVE if (b.get("account_epoch") or ident.get("account_epoch")) else DATA_STATUS_MISSING,
                    evidence_ref="runtime_identity",
                    now=now,
                ),
                "session_id": envelope(
                    b.get("session_id"),
                    source_service=ROLE_DEMO_EXECUTION,
                    source_role=ROLE_DEMO_EXECUTION,
                    source_timestamp=ts,
                    data_status=DATA_STATUS_LIVE if b.get("session_id") else DATA_STATUS_MISSING,
                    evidence_ref="runtime_identity",
                    now=now,
                ),
                "version_labels": self._version_labels(demo_6h, now),
            }
        return {"note": "DEMO_EXECUTION_SERVICE_UNAVAILABLE"}
