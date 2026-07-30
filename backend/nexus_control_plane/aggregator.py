"""Control Plane aggregators — ownership-enforced overview fields."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from backend.nexus_control_plane import (
    DATA_STATUS_LIVE,
    DATA_STATUS_MISSING,
    DATA_STATUS_SERVICE_UNAVAILABLE,
    DATA_STATUS_UNKNOWN,
    EXECUTION_OWNER_DEMO_VALIDATION,
    ROLE_CONTROL_PLANE,
    ROLE_DEMO_EXECUTION,
    ROLE_LEARNING_ENGINE,
    ROLE_MARKET_INTELLIGENCE,
)
from backend.nexus_control_plane.federation_client import FederationClient
from backend.nexus_control_plane.field_envelope import envelope, missing
from backend.nexus_control_plane.service_registry import ServiceRegistry


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

        return {
            "system_mode": {
                "bybit_demo": True,
                "mainnet": False,
                "real_money": False,
                "fixed_leverage": 25,
                "margin_mode": "ISOLATED",
                "execution_owner": EXECUTION_OWNER_DEMO_VALIDATION,
                "stage3_execution_disabled": True,
            },
            "service_health": self._service_health(market, demo_status),
            "demo_session": self._demo_session(demo_6h, demo_status, now),
            "demo_account": self._demo_account(demo_account, now),
            "market_funnel": self._market_funnel(market, demo_6h, now),
            "current_execution": self._current_execution(demo_6h, demo_status, now),
            "performance": self._performance(demo_6h, now),
            "learning": self._learning(demo_6h, now),
            "runtime_identity": self._runtime_identity(demo_6h, demo_status, now),
            "ownership": {
                "market_scan": ROLE_MARKET_INTELLIGENCE,
                "demo_wallet": ROLE_DEMO_EXECUTION,
                "demo_session": ROLE_DEMO_EXECUTION,
                "positions_orders": ROLE_DEMO_EXECUTION,
                "outcome_reflection": ROLE_DEMO_EXECUTION,
                "note": "Stage3 legacy autonomous state must not masquerade as Demo Validation state",
            },
        }

    def services(self) -> dict[str, Any]:
        return self.registry.summary()

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

    def _service_health(self, market: dict[str, Any], demo: dict[str, Any]) -> dict[str, Any]:
        def one(role: str, probe: dict[str, Any]) -> dict[str, Any]:
            if probe.get("ok"):
                status = DATA_STATUS_LIVE
                health = "UP"
            else:
                status = probe.get("data_status") or DATA_STATUS_SERVICE_UNAVAILABLE
                health = "DOWN"
            return envelope(
                health,
                source_service=role,
                source_timestamp=probe.get("fetched_at"),
                data_status=status,
                evidence_ref=probe.get("error") or "health_probe",
            )

        return {
            "market_intelligence": one(ROLE_MARKET_INTELLIGENCE, market),
            "demo_execution": one(ROLE_DEMO_EXECUTION, demo),
            "learning_engine": one(ROLE_LEARNING_ENGINE, demo),
            "control_plane": envelope(
                "UP",
                source_service=ROLE_CONTROL_PLANE,
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
                    data_status=DATA_STATUS_SERVICE_UNAVAILABLE,
                    evidence_ref="EXECUTION_SERVICE_UNAVAILABLE",
                ),
                "note": "EXECUTION_SERVICE_UNAVAILABLE",
            }
        payload = demo_6h.get("payload") or {}
        bounded = payload.get("bounded_6h") or payload
        return {
            "session_id": envelope(
                bounded.get("session_id"),
                source_service=ROLE_DEMO_EXECUTION,
                source_timestamp=demo_6h.get("fetched_at"),
                data_status=DATA_STATUS_LIVE if bounded.get("session_id") else DATA_STATUS_MISSING,
                evidence_ref="/api/nexus/demo-execution/bounded-6h/status",
            ),
            "status": envelope(
                bounded.get("status"),
                source_service=ROLE_DEMO_EXECUTION,
                source_timestamp=demo_6h.get("fetched_at"),
                data_status=DATA_STATUS_LIVE if bounded.get("status") else DATA_STATUS_MISSING,
                evidence_ref="bounded_6h.status",
            ),
            "started_at": envelope(
                bounded.get("started_at"),
                source_service=ROLE_DEMO_EXECUTION,
                source_timestamp=demo_6h.get("fetched_at"),
                data_status=DATA_STATUS_LIVE if bounded.get("started_at") else DATA_STATUS_MISSING,
                evidence_ref="bounded_6h.started_at",
            ),
            "entries_total": envelope(
                bounded.get("entries_total"),
                source_service=ROLE_DEMO_EXECUTION,
                source_timestamp=demo_6h.get("fetched_at"),
                data_status=DATA_STATUS_LIVE if "entries_total" in bounded else DATA_STATUS_MISSING,
                evidence_ref="bounded_6h.entries_total",
            ),
            "trades_completed": envelope(
                bounded.get("trades_completed"),
                source_service=ROLE_DEMO_EXECUTION,
                source_timestamp=demo_6h.get("fetched_at"),
                data_status=DATA_STATUS_LIVE if "trades_completed" in bounded else DATA_STATUS_MISSING,
                evidence_ref="bounded_6h.trades_completed",
            ),
            "session_write_enabled": envelope(
                bounded.get("session_write_enabled"),
                source_service=ROLE_DEMO_EXECUTION,
                source_timestamp=demo_6h.get("fetched_at"),
                data_status=DATA_STATUS_LIVE if "session_write_enabled" in bounded else DATA_STATUS_MISSING,
                evidence_ref="bounded_6h.session_write_enabled",
            ),
        }

    def _demo_account(self, demo_account: dict[str, Any], now: float) -> dict[str, Any]:
        if not demo_account.get("ok"):
            return {
                "wallet_balance": missing(ROLE_DEMO_EXECUTION, evidence_ref="EXECUTION_SERVICE_UNAVAILABLE"),
                "equity": missing(ROLE_DEMO_EXECUTION, evidence_ref="EXECUTION_SERVICE_UNAVAILABLE"),
                "available_balance": missing(ROLE_DEMO_EXECUTION, evidence_ref="EXECUTION_SERVICE_UNAVAILABLE"),
                "note": "EXECUTION_SERVICE_UNAVAILABLE — do not fall back to Stage3 account",
            }
        p = demo_account.get("payload") or {}
        # Reject synthetic zeros when unavailable reason present
        if p.get("available") is False or p.get("reason"):
            return {
                "wallet_balance": missing(ROLE_DEMO_EXECUTION, evidence_ref=str(p.get("reason") or "unavailable")),
                "equity": missing(ROLE_DEMO_EXECUTION, evidence_ref=str(p.get("reason") or "unavailable")),
                "available_balance": missing(ROLE_DEMO_EXECUTION, evidence_ref=str(p.get("reason") or "unavailable")),
                "used_margin": missing(ROLE_DEMO_EXECUTION, evidence_ref=str(p.get("reason") or "unavailable")),
                "unrealized_pnl": missing(ROLE_DEMO_EXECUTION, evidence_ref=str(p.get("reason") or "unavailable")),
                "source": envelope(p.get("source"), source_service=ROLE_DEMO_EXECUTION, data_status=DATA_STATUS_UNKNOWN),
            }
        ts = demo_account.get("fetched_at")
        return {
            "wallet_balance": envelope(p.get("wallet_balance"), source_service=ROLE_DEMO_EXECUTION, source_timestamp=ts, data_status=DATA_STATUS_LIVE if "wallet_balance" in p else DATA_STATUS_MISSING, evidence_ref="demo-execution/account"),
            "equity": envelope(p.get("equity"), source_service=ROLE_DEMO_EXECUTION, source_timestamp=ts, data_status=DATA_STATUS_LIVE if "equity" in p else DATA_STATUS_MISSING, evidence_ref="demo-execution/account"),
            "available_balance": envelope(p.get("available_balance"), source_service=ROLE_DEMO_EXECUTION, source_timestamp=ts, data_status=DATA_STATUS_LIVE if "available_balance" in p else DATA_STATUS_MISSING, evidence_ref="demo-execution/account"),
            "used_margin": envelope(p.get("used_margin"), source_service=ROLE_DEMO_EXECUTION, source_timestamp=ts, data_status=DATA_STATUS_LIVE if "used_margin" in p else DATA_STATUS_MISSING, evidence_ref="demo-execution/account"),
            "unrealized_pnl": envelope(p.get("unrealized_pnl"), source_service=ROLE_DEMO_EXECUTION, source_timestamp=ts, data_status=DATA_STATUS_LIVE if "unrealized_pnl" in p else DATA_STATUS_MISSING, evidence_ref="demo-execution/account"),
            "open_positions": envelope(p.get("open_positions"), source_service=ROLE_DEMO_EXECUTION, source_timestamp=ts, data_status=DATA_STATUS_LIVE if "open_positions" in p else DATA_STATUS_MISSING, evidence_ref="demo-execution/account"),
            "open_orders": envelope(p.get("open_orders"), source_service=ROLE_DEMO_EXECUTION, source_timestamp=ts, data_status=DATA_STATUS_LIVE if "open_orders" in p else DATA_STATUS_MISSING, evidence_ref="demo-execution/account"),
            "source": envelope(p.get("source"), source_service=ROLE_DEMO_EXECUTION, source_timestamp=ts, data_status=DATA_STATUS_LIVE if p.get("source") else DATA_STATUS_MISSING, evidence_ref="demo-execution/account"),
        }

    def _market_funnel(self, market: dict[str, Any], demo_6h: dict[str, Any], now: float) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if market.get("ok"):
            p = market.get("payload") or {}
            ts = market.get("fetched_at")
            out["stage3_status"] = envelope(
                p.get("status") or p.get("mode") or "OK",
                source_service=ROLE_MARKET_INTELLIGENCE,
                source_timestamp=ts,
                data_status=DATA_STATUS_LIVE,
                evidence_ref="/api/nexus/stage3/status",
            )
        else:
            out["stage3_status"] = envelope(
                None,
                source_service=ROLE_MARKET_INTELLIGENCE,
                data_status=DATA_STATUS_SERVICE_UNAVAILABLE,
                evidence_ref="SERVICE_UNAVAILABLE",
            )
        # Candidate funnel counters owned by demo session when available
        if demo_6h.get("ok"):
            b = (demo_6h.get("payload") or {}).get("bounded_6h") or (demo_6h.get("payload") or {})
            ts = demo_6h.get("fetched_at")
            for key in ("candidates_total", "cost_gate_blocks", "mistake_guard_blocks", "risk_critic_blocks"):
                out[key] = envelope(
                    b.get(key),
                    source_service=ROLE_DEMO_EXECUTION,
                    source_timestamp=ts,
                    data_status=DATA_STATUS_LIVE if key in b else DATA_STATUS_MISSING,
                    evidence_ref=f"bounded_6h.{key}",
                )
        else:
            for key in ("candidates_total", "cost_gate_blocks", "mistake_guard_blocks", "risk_critic_blocks"):
                out[key] = missing(ROLE_DEMO_EXECUTION, evidence_ref="bounded_6h_unavailable")
        return out

    def _current_execution(self, demo_6h: dict[str, Any], demo_status: dict[str, Any], now: float) -> dict[str, Any]:
        if not demo_6h.get("ok"):
            return {
                "note": "EXECUTION_SERVICE_UNAVAILABLE",
                "open_position": missing(ROLE_DEMO_EXECUTION, evidence_ref="EXECUTION_SERVICE_UNAVAILABLE"),
            }
        b = (demo_6h.get("payload") or {}).get("bounded_6h") or (demo_6h.get("payload") or {})
        ts = demo_6h.get("fetched_at")
        return {
            "open_position": envelope(b.get("open_position"), source_service=ROLE_DEMO_EXECUTION, source_timestamp=ts, data_status=DATA_STATUS_LIVE if "open_position" in b else DATA_STATUS_MISSING, evidence_ref="bounded_6h.open_position"),
            "entries_total": envelope(b.get("entries_total"), source_service=ROLE_DEMO_EXECUTION, source_timestamp=ts, data_status=DATA_STATUS_LIVE if "entries_total" in b else DATA_STATUS_MISSING, evidence_ref="bounded_6h.entries_total"),
            "kill_switch_events": envelope(b.get("kill_switch_events"), source_service=ROLE_DEMO_EXECUTION, source_timestamp=ts, data_status=DATA_STATUS_LIVE if "kill_switch_events" in b else DATA_STATUS_MISSING, evidence_ref="bounded_6h.kill_switch_events"),
        }

    def _performance(self, demo_6h: dict[str, Any], now: float) -> dict[str, Any]:
        if not demo_6h.get("ok"):
            return {"note": "EXECUTION_SERVICE_UNAVAILABLE"}
        b = (demo_6h.get("payload") or {}).get("bounded_6h") or (demo_6h.get("payload") or {})
        ts = demo_6h.get("fetched_at")
        keys = ("gross_pnl", "total_fees", "funding", "net_pnl", "wins", "losses")
        return {
            k: envelope(b.get(k), source_service=ROLE_DEMO_EXECUTION, source_timestamp=ts, data_status=DATA_STATUS_LIVE if k in b else DATA_STATUS_MISSING, evidence_ref=f"bounded_6h.{k}")
            for k in keys
        }

    def _learning(self, demo_6h: dict[str, Any], now: float) -> dict[str, Any]:
        if not demo_6h.get("ok"):
            return {"note": "LEARNING_EVIDENCE_UNAVAILABLE"}
        b = (demo_6h.get("payload") or {}).get("bounded_6h") or (demo_6h.get("payload") or {})
        ts = demo_6h.get("fetched_at")
        return {
            "decision_delta_count": envelope(b.get("decision_delta_count"), source_service=ROLE_DEMO_EXECUTION, source_timestamp=ts, data_status=DATA_STATUS_LIVE if "decision_delta_count" in b else DATA_STATUS_MISSING, evidence_ref="bounded_6h.decision_delta_count"),
            "good_process_wins": envelope(b.get("good_process_wins"), source_service=ROLE_DEMO_EXECUTION, source_timestamp=ts, data_status=DATA_STATUS_LIVE if "good_process_wins" in b else DATA_STATUS_MISSING, evidence_ref="bounded_6h.good_process_wins"),
            "good_process_losses": envelope(b.get("good_process_losses"), source_service=ROLE_DEMO_EXECUTION, source_timestamp=ts, data_status=DATA_STATUS_LIVE if "good_process_losses" in b else DATA_STATUS_MISSING, evidence_ref="bounded_6h.good_process_losses"),
            "bad_process_wins": envelope(b.get("bad_process_wins"), source_service=ROLE_DEMO_EXECUTION, source_timestamp=ts, data_status=DATA_STATUS_LIVE if "bad_process_wins" in b else DATA_STATUS_MISSING, evidence_ref="bounded_6h.bad_process_wins"),
            "bad_process_losses": envelope(b.get("bad_process_losses"), source_service=ROLE_DEMO_EXECUTION, source_timestamp=ts, data_status=DATA_STATUS_LIVE if "bad_process_losses" in b else DATA_STATUS_MISSING, evidence_ref="bounded_6h.bad_process_losses"),
        }

    def _runtime_identity(self, demo_6h: dict[str, Any], demo_status: dict[str, Any], now: float) -> dict[str, Any]:
        if demo_6h.get("ok"):
            b = (demo_6h.get("payload") or {}).get("bounded_6h") or (demo_6h.get("payload") or {})
            ident = b.get("runtime_identity") or {}
            ts = demo_6h.get("fetched_at")
            return {
                "deployment_commit": envelope(ident.get("deployment_commit"), source_service=ROLE_DEMO_EXECUTION, source_timestamp=ts, data_status=DATA_STATUS_LIVE if ident.get("deployment_commit") else DATA_STATUS_MISSING, evidence_ref="runtime_identity"),
                "policy_version": envelope(ident.get("policy_version"), source_service=ROLE_DEMO_EXECUTION, source_timestamp=ts, data_status=DATA_STATUS_LIVE if ident.get("policy_version") else DATA_STATUS_MISSING, evidence_ref="runtime_identity"),
                "schema_version": envelope(ident.get("schema_version"), source_service=ROLE_DEMO_EXECUTION, source_timestamp=ts, data_status=DATA_STATUS_LIVE if ident.get("schema_version") else DATA_STATUS_MISSING, evidence_ref="runtime_identity"),
                "account_epoch": envelope(b.get("account_epoch") or ident.get("account_epoch"), source_service=ROLE_DEMO_EXECUTION, source_timestamp=ts, data_status=DATA_STATUS_LIVE if (b.get("account_epoch") or ident.get("account_epoch")) else DATA_STATUS_MISSING, evidence_ref="runtime_identity"),
                "observation_code_sha_note": envelope(
                    "PR head and deployed observation SHA must be labeled separately",
                    source_service=ROLE_CONTROL_PLANE,
                    source_timestamp=now,
                    data_status=DATA_STATUS_LIVE,
                    evidence_ref="founder_instruction",
                ),
            }
        return {"note": "EXECUTION_SERVICE_UNAVAILABLE"}
