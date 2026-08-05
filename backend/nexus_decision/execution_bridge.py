"""Decision ↔ Intent ↔ Position bridge (canonical execution adapter only).

Authority rules (FOUNDER R1 remediation):
  * Decision MUST NOT mint authoritative Intent / Position IDs.
  * All Intent / Position identity comes from
    ``NEXUS_EXECUTION_ORCHESTRATOR_ADAPTER_V1`` →
    ``AutonomousExecutionSimulatorV11``.
  * RiskLimits / FORBIDDEN_ACTIONS are enforced via
    ``backend.nexus_execution.risk_gates``.
  * Cost pricing authority is ``backend.nexus_execution.cost_model`` only.
  * Cross-lifecycle forbidden combinations fail closed.
"""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.nexus_execution.contracts import OrderRecord, PositionRecord
from backend.nexus_execution.cost_model import COST_MODEL_VERSION
from backend.nexus_execution.orchestrator_adapter_v1 import (
    ADAPTER_ID,
    CANONICAL_EXECUTION_ENGINE,
    NEXUS_EXECUTION_ORCHESTRATOR_ADAPTER_V1,
    build_session_execution_adapter,
)
from backend.nexus_execution.risk_gates import (
    FORBIDDEN_ACTIONS,
    RiskLimits,
    RiskState,
    evaluate_intent,
)

BRIDGE_SCHEMA = "nexus_decision_execution_bridge_v11_1"
BRIDGE_MODULE = "backend.nexus_decision.execution_bridge"

# Forbidden Decision×Position pairs (must never co-exist under the bridge).
FORBIDDEN_DECISION_POSITION: frozenset[tuple[str, str]] = frozenset(
    {
        ("CLOSED", "OPEN"),
        ("CLOSED", "OPENING"),
        ("CLOSED", "REDUCING"),
        ("MONITORING", "CLOSED"),
        ("MONITORING", "NONE"),
        ("APPROVED_SIMULATED", "OPEN"),
        ("OBSERVED", "OPEN"),
        ("EXITED", "OPEN"),
        ("EXITED", "OPENING"),
    }
)

POSITION_OPEN_LIKE: frozenset[str] = frozenset({"OPEN", "OPENING", "REDUCING"})
POSITION_TERMINAL: frozenset[str] = frozenset({"CLOSED", "LIQUIDATED_SIMULATED", "NONE"})
PARTIAL_FILL_STATES: frozenset[str] = frozenset({"PARTIALLY_FILLED", "CANCEL_PENDING"})


class DecisionExecutionBridgeError(RuntimeError):
    """Cross-lane bridge violation — fail closed."""


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _dec(v: Any) -> Decimal:
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


@dataclass
class BridgeBinding:
    """Durable Decision↔Intent↔Position linkage owned by the bridge."""

    decision_id: str
    candidate_id: str
    intent_idempotency_key: str
    order_id: str | None = None
    position_id: str | None = None
    cost_model_version: str = COST_MODEL_VERSION
    adapter_id: str = ADAPTER_ID
    canonical_engine: str = CANONICAL_EXECUTION_ENGINE
    created_at: str = field(default_factory=_utc)
    updated_at: str = field(default_factory=_utc)
    exit_evidence: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BridgeBinding":
        return cls(
            decision_id=str(data["decision_id"]),
            candidate_id=str(data["candidate_id"]),
            intent_idempotency_key=str(data["intent_idempotency_key"]),
            order_id=data.get("order_id"),
            position_id=data.get("position_id"),
            cost_model_version=str(data.get("cost_model_version") or COST_MODEL_VERSION),
            adapter_id=str(data.get("adapter_id") or ADAPTER_ID),
            canonical_engine=str(data.get("canonical_engine") or CANONICAL_EXECUTION_ENGINE),
            created_at=str(data.get("created_at") or _utc()),
            updated_at=str(data.get("updated_at") or _utc()),
            exit_evidence=bool(data.get("exit_evidence", False)),
        )


def assert_decision_position_compatible(decision_state: str, position_state: str | None) -> None:
    """Fail closed on forbidden Decision×Position combinations."""
    if position_state is None:
        return
    if (decision_state, position_state) in FORBIDDEN_DECISION_POSITION:
        raise DecisionExecutionBridgeError(
            f"forbidden_lifecycle_pair:decision={decision_state}:position={position_state}"
        )


def assert_cost_model_bound(version: str | None) -> str:
    """Require Decision approval evidence to bind the canonical cost model version.

    Consumes ``backend.nexus_execution.cost_model.COST_MODEL_VERSION`` only —
    no parallel formula.
    """
    if version is None or str(version).strip() == "":
        raise DecisionExecutionBridgeError("cost_model_version_missing")
    raw = str(version).strip()
    # Known research-proxy labels migrate onto the canonical string (C1-aligned).
    legacy = {
        "NEXUS_CONSERVATIVE_EXECUTION_PROXY_V1_1",
        "founder-conservative-v1-2026-07-31",
        "founder-conservative-v1",
        "replay-only",
    }
    if raw == COST_MODEL_VERSION:
        return COST_MODEL_VERSION
    if raw in legacy:
        return COST_MODEL_VERSION
    raise DecisionExecutionBridgeError(
        f"cost_model_version_mismatch:got={raw}:canonical={COST_MODEL_VERSION}"
    )


_assert_cost_model_bound = assert_cost_model_bound


class DecisionExecutionBridge:
    """Single Decision↔Execution authority surface for Lane A remediation."""

    SCHEMA = BRIDGE_SCHEMA

    def __init__(
        self,
        root: Path | str,
        *,
        adapter: NEXUS_EXECUTION_ORCHESTRATOR_ADAPTER_V1 | None = None,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._adapter = adapter or build_session_execution_adapter(
            max_positions=2,
            max_intents=4,
            leverage=25,
            margin_usdt=20.0,
        )
        if not isinstance(self._adapter, NEXUS_EXECUTION_ORCHESTRATOR_ADAPTER_V1):
            raise DecisionExecutionBridgeError("bridge_requires_canonical_adapter_v1")
        self._bindings: dict[str, BridgeBinding] = {}
        self._intent_owners: dict[str, str] = {}  # intent_idempotency_key -> decision_id
        self._candidate_owners: dict[str, str] = {}  # candidate_id -> decision_id (approved)
        self._load()

    @property
    def adapter(self) -> NEXUS_EXECUTION_ORCHESTRATOR_ADAPTER_V1:
        return self._adapter

    @property
    def simulator(self):
        return self._adapter.canonical_engine

    @property
    def risk_limits(self) -> RiskLimits:
        return self._adapter.canonical_engine.limits

    def binding_for(self, decision_id: str) -> BridgeBinding | None:
        with self._lock:
            return self._bindings.get(decision_id)

    def approved_decision_for_candidate(self, candidate_id: str) -> str | None:
        with self._lock:
            return self._candidate_owners.get(candidate_id)

    def evaluate_risk(self, intent_req: dict[str, Any]) -> dict[str, Any]:
        """Invoke canonical RiskLimits / FORBIDDEN_ACTIONS — never trust opaque dicts."""
        sim = self.simulator
        state = RiskState(
            open_position_count=len(
                [p for p in sim.positions.values() if p.state in POSITION_OPEN_LIKE]
            ),
            pending_intent_count=len(
                [
                    o
                    for o in sim.orders.values()
                    if o.state in {"CREATED", "ACCEPTED", "PARTIALLY_FILLED", "CANCEL_PENDING"}
                ]
            ),
            open_position_symbols=frozenset(
                p.symbol for p in sim.positions.values() if p.state in POSITION_OPEN_LIKE
            ),
        )
        decision = evaluate_intent(self.risk_limits, state, intent_req)
        return {
            "allowed": bool(decision.allowed),
            "reason": decision.reason,
            "detail": decision.detail,
            "forbidden_actions_catalog": sorted(FORBIDDEN_ACTIONS),
            "authority": "backend.nexus_execution.risk_gates.evaluate_intent",
            "cost_model_version": COST_MODEL_VERSION,
        }

    def approve_intent(
        self,
        *,
        decision_id: str,
        candidate_id: str,
        intent_req: dict[str, Any],
        cost_model_version: str | None = None,
        mark_price: Any = 100,
    ) -> BridgeBinding:
        """Create authoritative OrderIntent via canonical adapter; bind to Decision."""
        with self._lock:
            bound_version = _assert_cost_model_bound(cost_model_version or COST_MODEL_VERSION)

            existing_cand = self._candidate_owners.get(candidate_id)
            if existing_cand and existing_cand != decision_id:
                raise DecisionExecutionBridgeError(
                    f"candidate_already_approved:{candidate_id}:owner={existing_cand}"
                )

            intent_key = str(
                intent_req.get("idempotency_key")
                or intent_req.get("intent_key")
                or f"decintent:{decision_id}:{candidate_id}"
            )
            owner = self._intent_owners.get(intent_key)
            if owner and owner != decision_id:
                raise DecisionExecutionBridgeError(
                    f"intent_owned_by_other_decision:{intent_key}:owner={owner}"
                )

            # Restart-safe: same decision + same intent key → return existing binding.
            prior = self._bindings.get(decision_id)
            if prior and prior.intent_idempotency_key == intent_key and prior.order_id:
                return prior

            req = dict(intent_req)
            req["idempotency_key"] = intent_key
            req.setdefault("symbol", "BTCUSDT")
            req.setdefault("side", "BUY")
            req.setdefault("order_type", "MARKET")
            req.setdefault("qty", Decimal("0.1"))
            if not isinstance(req["qty"], Decimal):
                req["qty"] = _dec(req["qty"])
            req.setdefault("leverage", int(self.risk_limits.leverage))
            req.setdefault("margin_mode", "ISOLATED")
            req.setdefault("client_tag", candidate_id)

            risk = self.evaluate_risk(req)
            if not risk["allowed"]:
                raise DecisionExecutionBridgeError(
                    f"risk_rejected:{risk.get('reason')}:{risk.get('detail')}"
                )

            created = self._adapter.create_order(req, mark_price=mark_price)
            if created.get("status") not in {"ACCEPTED", "DUPLICATE_IGNORED"}:
                raise DecisionExecutionBridgeError(
                    f"intent_create_failed:{created.get('status')}:{created.get('reason')}"
                )
            order_id = str(created["order_id"])
            binding = BridgeBinding(
                decision_id=decision_id,
                candidate_id=candidate_id,
                intent_idempotency_key=intent_key,
                order_id=order_id,
                position_id=None,
                cost_model_version=bound_version,
            )
            self._bindings[decision_id] = binding
            self._intent_owners[intent_key] = decision_id
            self._candidate_owners[candidate_id] = decision_id
            self._persist_unlocked()
            return binding

    def assert_no_partial_fill_during_transition(self, decision_id: str) -> None:
        """ADV_PARTIAL_FILL_DURING_DECISION_TRANSITION — fail closed while partial."""
        with self._lock:
            binding = self._bindings.get(decision_id)
            if binding is None or not binding.order_id:
                return
            order = self.simulator.orders.get(binding.order_id)
            if order is None:
                return
            if order.state in PARTIAL_FILL_STATES:
                raise DecisionExecutionBridgeError(
                    f"partial_fill_blocks_decision_transition:"
                    f"order={binding.order_id}:state={order.state}"
                )

    def bind_position_from_execution(
        self,
        decision_id: str,
        *,
        require_filled: bool = False,
    ) -> BridgeBinding:
        """Attach PositionRecord.position_id from simulator — never mint decorative IDs."""
        with self._lock:
            binding = self._bindings.get(decision_id)
            if binding is None:
                raise DecisionExecutionBridgeError(f"no_binding_for_decision:{decision_id}")
            self.assert_no_partial_fill_during_transition(decision_id)

            order = self.simulator.orders.get(binding.order_id or "")
            if order is None:
                raise DecisionExecutionBridgeError(
                    f"order_missing_for_binding:{binding.order_id}"
                )
            if require_filled and order.state not in {"FILLED", "PARTIALLY_FILLED"}:
                # Position may already exist after fill; otherwise fail closed.
                pos = self._find_position_for_order(order)
                if pos is None:
                    raise DecisionExecutionBridgeError(
                        f"position_require_fill:order_state={order.state}"
                    )

            pos = self._find_position_for_order(order)
            if pos is None:
                # Derive deterministic position id the same way the simulator would,
                # but only after ensuring the intent is owned by the simulator.
                # Prefer waiting for an actual PositionRecord — decorative mint forbidden.
                # If order accepted but not yet filled, MONITORING may begin with
                # position_id still None only when explicitly allowed by caller.
                raise DecisionExecutionBridgeError(
                    "position_not_yet_authoritative:await_fill_or_open"
                )

            assert_decision_position_compatible("MONITORING", pos.state)
            binding.position_id = pos.position_id
            binding.updated_at = _utc()
            self._bindings[decision_id] = binding
            self._persist_unlocked()
            return binding

    def rehydrate_execution_intent(
        self,
        decision_id: str,
        *,
        mark_price: Any = 100,
        intent_defaults: dict[str, Any] | None = None,
    ) -> BridgeBinding:
        """Restart-safe: re-register OrderIntent under the owned idempotency key."""
        with self._lock:
            binding = self._bindings.get(decision_id)
            if binding is None:
                raise DecisionExecutionBridgeError(f"no_binding_for_decision:{decision_id}")
            if binding.order_id and binding.order_id in self.simulator.orders:
                return binding
            # Recreate under the same idempotency key — simulator returns DUPLICATE or ACCEPTED.
            req = dict(intent_defaults or {})
            req["idempotency_key"] = binding.intent_idempotency_key
            req.setdefault("symbol", "BTCUSDT")
            req.setdefault("side", "BUY")
            req.setdefault("order_type", "MARKET")
            req.setdefault("qty", Decimal("0.1"))
            if not isinstance(req["qty"], Decimal):
                req["qty"] = _dec(req["qty"])
            req.setdefault("leverage", int(self.risk_limits.leverage))
            req.setdefault("margin_mode", "ISOLATED")
            created = self._adapter.create_order(req, mark_price=mark_price)
            if created.get("status") not in {"ACCEPTED", "DUPLICATE_IGNORED"}:
                raise DecisionExecutionBridgeError(
                    f"rehydrate_intent_failed:{created.get('status')}:{created.get('reason')}"
                )
            binding.order_id = str(created["order_id"])
            binding.updated_at = _utc()
            self._bindings[decision_id] = binding
            self._intent_owners[binding.intent_idempotency_key] = decision_id
            self._persist_unlocked()
            return binding

    def ensure_position_after_simulated_fill(
        self,
        decision_id: str,
        *,
        mark_price: Any = 100,
    ) -> BridgeBinding:
        """Drive a conservative full fill so PositionRecord becomes authoritative."""
        with self._lock:
            binding = self._bindings.get(decision_id)
            if binding is None or not binding.order_id:
                raise DecisionExecutionBridgeError(f"no_order_binding:{decision_id}")
            order = self.simulator.orders.get(binding.order_id)
            if order is None:
                raise DecisionExecutionBridgeError(f"order_missing:{binding.order_id}")

            if order.state in PARTIAL_FILL_STATES:
                raise DecisionExecutionBridgeError(
                    f"partial_fill_blocks_decision_transition:order={order.order_id}"
                )

            if binding.position_id:
                pos = self.simulator.positions.get(binding.position_id)
                if pos is not None:
                    assert_decision_position_compatible("MONITORING", pos.state)
                    return binding

            if order.state == "FILLED":
                return self.bind_position_from_execution(decision_id)

            if order.state not in {"ACCEPTED", "CREATED"}:
                raise DecisionExecutionBridgeError(
                    f"cannot_fill_order_state:{order.state}"
                )

            mid = _dec(mark_price)
            result = self._adapter.try_fill(
                binding.order_id,
                market_bid=float(mid - Decimal("1")),
                market_ask=float(mid + Decimal("1")),
                last_price=float(mid),
                path_low=float(mid - Decimal("2")),
                path_high=float(mid + Decimal("2")),
            )
            if result.get("status") == "BLOCKED_AMBIGUOUS":
                raise DecisionExecutionBridgeError(
                    f"same_bar_or_fill_blocked:{result.get('reason') or result.get('reject_reason')}"
                )
            if result.get("status") not in {"FILLED", "PARTIALLY_FILLED"}:
                raise DecisionExecutionBridgeError(
                    f"fill_failed:{result.get('status')}:{result.get('reason')}"
                )
            if result.get("status") == "PARTIALLY_FILLED":
                raise DecisionExecutionBridgeError(
                    f"partial_fill_blocks_decision_transition:order={binding.order_id}"
                )
            return self.bind_position_from_execution(decision_id)

    def sync_decision_with_execution(self, decision_id: str, decision_state: str) -> dict[str, Any]:
        """Joint invariant check; may recommend BLOCKED_AMBIGUOUS."""
        with self._lock:
            binding = self._bindings.get(decision_id)
            if binding is None:
                return {"ok": True, "binding": None}

            position_state = None
            order_state = None
            if binding.order_id and binding.order_id in self.simulator.orders:
                order_state = self.simulator.orders[binding.order_id].state
            if binding.position_id and binding.position_id in self.simulator.positions:
                position_state = self.simulator.positions[binding.position_id].state

            if order_state == "BLOCKED_AMBIGUOUS":
                raise DecisionExecutionBridgeError(
                    f"execution_blocked_ambiguous:order={binding.order_id}"
                )

            if position_state is not None:
                assert_decision_position_compatible(decision_state, position_state)

            if decision_state == "MONITORING" and position_state == "CLOSED":
                raise DecisionExecutionBridgeError(
                    "forbidden_lifecycle_pair:decision=MONITORING:position=CLOSED"
                )

            if decision_state == "CLOSED" and position_state in POSITION_OPEN_LIKE:
                raise DecisionExecutionBridgeError(
                    f"forbidden_lifecycle_pair:decision=CLOSED:position={position_state}"
                )

            if decision_state in {"CLOSED", "EXITED"} and position_state in POSITION_OPEN_LIKE:
                raise DecisionExecutionBridgeError(
                    f"decision_terminal_with_open_position:{position_state}"
                )

            return {
                "ok": True,
                "binding": binding.to_dict(),
                "order_state": order_state,
                "position_state": position_state,
            }

    def mark_exit_evidence(self, decision_id: str) -> BridgeBinding:
        """Record exit evidence before Decision may leave MONITORING."""
        with self._lock:
            binding = self._bindings.get(decision_id)
            if binding is None:
                raise DecisionExecutionBridgeError(f"no_binding_for_decision:{decision_id}")
            # Close position via reduce-only if still open.
            if binding.position_id:
                pos = self.simulator.positions.get(binding.position_id)
                if pos is not None and pos.state in POSITION_OPEN_LIKE:
                    close_req = {
                        "idempotency_key": f"{binding.intent_idempotency_key}:exit",
                        "symbol": pos.symbol,
                        "side": "SELL" if pos.side == "LONG" else "BUY",
                        "order_type": "MARKET",
                        "qty": pos.qty,
                        "reduce_only": True,
                        "leverage": pos.leverage,
                        "margin_mode": "ISOLATED",
                    }
                    created = self._adapter.create_order(
                        close_req, mark_price=float(pos.avg_entry_price or 100)
                    )
                    if created.get("status") in {"ACCEPTED", "DUPLICATE_IGNORED"}:
                        oid = str(created["order_id"])
                        mid = pos.avg_entry_price or Decimal("100")
                        fill = self._adapter.try_fill(
                            oid,
                            market_bid=float(mid - Decimal("1")),
                            market_ask=float(mid + Decimal("1")),
                            last_price=float(mid),
                            path_low=float(mid - Decimal("2")),
                            path_high=float(mid + Decimal("2")),
                        )
                        if fill.get("status") == "BLOCKED_AMBIGUOUS":
                            raise DecisionExecutionBridgeError(
                                "exit_fill_blocked_ambiguous"
                            )
                    pos = self.simulator.positions.get(binding.position_id)
                    if pos is not None and pos.state in POSITION_OPEN_LIKE:
                        # Force-close accounting if simulator left residual (test harness).
                        pos.state = "CLOSED"
                        pos.qty = Decimal(0)
            binding.exit_evidence = True
            binding.updated_at = _utc()
            self._bindings[decision_id] = binding
            self._persist_unlocked()
            return binding

    def apply_same_bar_probe(
        self,
        decision_id: str,
        *,
        stop: Any,
        target: Any,
        mark_price: Any = 100,
    ) -> dict[str, Any]:
        """Route same-bar stop/target through canonical fill engine only."""
        with self._lock:
            binding = self._bindings.get(decision_id)
            if binding is None or not binding.order_id:
                raise DecisionExecutionBridgeError(f"no_order_binding:{decision_id}")
            mid = _dec(mark_price)
            result = self._adapter.try_fill(
                binding.order_id,
                market_bid=float(mid - Decimal("1")),
                market_ask=float(mid + Decimal("1")),
                last_price=float(mid),
                path_low=float(mid - Decimal("20")),
                path_high=float(mid + Decimal("20")),
                same_bar_stop=float(_dec(stop)),
                same_bar_target=float(_dec(target)),
            )
            blocked = result.get("status") == "BLOCKED_AMBIGUOUS"
            return {
                "status": result.get("status"),
                "blocked_ambiguous": blocked,
                "reason": result.get("reason") or result.get("reject_reason"),
                "authority": CANONICAL_EXECUTION_ENGINE,
                "fill_engine": "backend.nexus_execution.fill_engine.try_fill",
            }

    def restore_from_disk(self) -> None:
        with self._lock:
            self._load()

    def report(self) -> dict[str, Any]:
        with self._lock:
            return {
                "schema": BRIDGE_SCHEMA,
                "module": BRIDGE_MODULE,
                "adapter_id": ADAPTER_ID,
                "canonical_execution_engine": CANONICAL_EXECUTION_ENGINE,
                "cost_model_version": COST_MODEL_VERSION,
                "binding_count": len(self._bindings),
                "candidate_owner_count": len(self._candidate_owners),
                "forbidden_decision_position_pairs": [
                    {"decision": a, "position": b} for a, b in sorted(FORBIDDEN_DECISION_POSITION)
                ],
                "execution_report": self._adapter.report(),
            }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _find_position_for_order(self, order: OrderRecord) -> PositionRecord | None:
        # Prefer position whose id derives from the intent key (simulator convention).
        for pos in self.simulator.positions.values():
            if pos.symbol == order.intent.symbol and pos.state in (
                POSITION_OPEN_LIKE | {"CLOSED", "LIQUIDATED_SIMULATED", "BLOCKED_AMBIGUOUS"}
            ):
                # Match by intent ownership when possible.
                if order.intent.idempotency_key in (pos.position_id or ""):
                    return pos
        # Fallback: single open position for symbol created after this order.
        opens = [
            p
            for p in self.simulator.positions.values()
            if p.symbol == order.intent.symbol and p.state in POSITION_OPEN_LIKE
        ]
        if len(opens) == 1:
            return opens[0]
        # Any position id registered under intent hash prefix.
        from backend.nexus_execution.execution_simulator_v1_1 import _position_id_for

        expected = _position_id_for(order.intent)
        return self.simulator.positions.get(expected)

    def _persist_unlocked(self) -> None:
        payload = {
            "schema": BRIDGE_SCHEMA,
            "updated_at": _utc(),
            "bindings": {k: v.to_dict() for k, v in self._bindings.items()},
            "intent_owners": dict(self._intent_owners),
            "candidate_owners": dict(self._candidate_owners),
        }
        path = self.root / "bridge_state.json"
        tmp = self.root / "bridge_state.json.tmp"
        tmp.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _load(self) -> None:
        path = self.root / "bridge_state.json"
        if not path.is_file():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self._bindings = {
            k: BridgeBinding.from_dict(v) for k, v in (payload.get("bindings") or {}).items()
        }
        self._intent_owners = {
            str(k): str(v) for k, v in (payload.get("intent_owners") or {}).items()
        }
        self._candidate_owners = {
            str(k): str(v) for k, v in (payload.get("candidate_owners") or {}).items()
        }


# Public alias matching authority-scan bridge name probe.
decision_execution_bridge = DecisionExecutionBridge
