"""Read-only API routes for Bybit Demo Execution Validation."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from flask import Flask, jsonify

from backend.nexus_demo_execution import (
    BYBIT_DEMO,
    DEMO_EXECUTION_LABELS,
    FIXED_LEVERAGE,
    MAINNET,
    MAX_MARGIN,
    MAX_OPEN,
    MAX_PENDING,
    MIN_MARGIN,
    REAL_MONEY,
    SERVICE_NAME,
)
from backend.nexus_demo_execution.account_epoch import AccountEpochTracker
from backend.nexus_demo_execution.account_reader import BybitDemoAccountReader, FakeDemoAccountReader
from backend.nexus_demo_execution.allocation import MarginAllocator
from backend.nexus_demo_execution.capital_constitution import CapitalConstitution
from backend.nexus_demo_execution.demo_domain import DemoDomainPolicy
from backend.nexus_demo_execution.kill_switch import KillSwitch
from backend.nexus_demo_execution.orchestration import DemoValidationOrchestrator
from backend.nexus_demo_execution.order_adapter import DemoOrderAdapter
from backend.nexus_demo_execution.persistence import DemoExecutionPersistence
from backend.nexus_demo_execution.safety_gate import DemoExecutionSafetyGate

logger = logging.getLogger(__name__)


def _candidate_data_roots() -> list[Path]:
    preferred = (os.environ.get("NEXUS_DATA_DIR") or "").strip()
    roots: list[Path] = []
    if preferred:
        roots.append(Path(preferred))
    roots.extend(
        [
            Path("data/nexus_demo_validation"),
            Path("/tmp/nexus_demo_validation"),
            Path("/app/data/nexus_demo_validation"),
        ]
    )
    # de-dupe while preserving order
    seen: set[str] = set()
    out: list[Path] = []
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        out.append(root)
    return out


def _probe_writable(root: Path) -> bool:
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception as exc:  # noqa: BLE001 — startup must not crash on storage probe
        logger.warning("data_root_unwritable path=%s err=%s", root, type(exc).__name__)
        return False


def _data_root() -> tuple[Path, bool]:
    """Return (root, writable). Never raises — falls back to /tmp."""
    for root in _candidate_data_roots():
        if _probe_writable(root):
            return root, True
    fallback = Path("/tmp/nexus_demo_validation")
    try:
        fallback.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        fallback = Path(".")
    return fallback, False


def _build_live_or_fake_reader() -> BybitDemoAccountReader:
    """Prefer live Bybit Demo private GET when credentials are present.

    Never call Bybit at module import — only when explicitly constructing a reader.
    """
    key = (os.environ.get("BYBIT_DEMO_API_KEY") or "").strip()
    secret = (os.environ.get("BYBIT_DEMO_API_SECRET") or "").strip()
    if key and secret:
        from backend.nexus_demo_execution.http_demo_reader import HttpDemoAccountReader

        logger.info("demo_account_reader=HttpDemoAccountReader demo_key_present=true")
        return HttpDemoAccountReader(api_key=key, api_secret=secret)
    logger.warning("demo_account_reader=FakeDemoAccountReader credential_missing=true")
    return FakeDemoAccountReader()


READ_ONLY_META = {
    "read_only": True,
    "exchange_write": False,
    "mainnet": MAINNET,
    "real_money": REAL_MONEY,
    "bybit_demo": BYBIT_DEMO,
    "mode": "DEMO_EXECUTION_VALIDATION",
    "service_name": SERVICE_NAME,
    "labels": list(DEMO_EXECUTION_LABELS),
}


class DemoExecutionApiState:
    """Singleton backing store for read-only status endpoints."""

    def __init__(self) -> None:
        self.gate = DemoExecutionSafetyGate()
        self.kill_switch = KillSwitch(gate=self.gate)
        self.constitution = CapitalConstitution()
        self.domain = DemoDomainPolicy()
        self.allocator = MarginAllocator()
        self.epoch_tracker = AccountEpochTracker()
        self.order_adapter = DemoOrderAdapter(gate=self.gate)
        data_root, writable = _data_root()
        self.data_root = data_root
        self.persistence_writable = writable
        self.persistence_blocked = not writable
        try:
            self.persistence = DemoExecutionPersistence(
                db_path=data_root / "validation.sqlite3",
            )
        except Exception as exc:  # noqa: BLE001 — keep web process alive
            logger.error("persistence_init_failed err=%s", type(exc).__name__)
            self.persistence_blocked = True
            # Last-resort in-process path under /tmp
            emergency = Path("/tmp/nexus_demo_validation_emergency")
            emergency.mkdir(parents=True, exist_ok=True)
            self.persistence = DemoExecutionPersistence(
                db_path=emergency / "validation.sqlite3",
            )
            self.data_root = emergency
        self._last_cycle_result: dict[str, Any] | None = None
        self._orchestrator: DemoValidationOrchestrator | None = None
        self._last_smoke_result: dict[str, Any] | None = None
        from backend.nexus_demo_execution.founder_approval import FounderSmokeApprovalStore

        self.approval = FounderSmokeApprovalStore()
        logger.info(
            "demo_api_state_ready data_root=%s persistence_blocked=%s",
            self.data_root,
            self.persistence_blocked,
        )
    def _build_orchestrator(self, reader: BybitDemoAccountReader | None = None) -> DemoValidationOrchestrator:
        export_dir = self.data_root / "artifacts" / "demo_validation"
        try:
            export_dir.mkdir(parents=True, exist_ok=True)
        except Exception:  # noqa: BLE001
            export_dir = Path("/tmp/nexus_demo_validation/artifacts/demo_validation")
            export_dir.mkdir(parents=True, exist_ok=True)
        return DemoValidationOrchestrator(
            gate=self.gate,
            reader=reader or _build_live_or_fake_reader(),
            persistence=self.persistence,
            epoch_tracker=self.epoch_tracker,
            order_adapter=self.order_adapter,
            kill_switch=self.kill_switch,
            export_dir=export_dir,
        )

    def run_readonly_cycle(self, reader: BybitDemoAccountReader | None = None) -> dict[str, Any]:
        """Safe readonly cycle — no exchange writes. Uses live Demo private GET when keyed."""
        if reader is None:
            reader = _build_live_or_fake_reader()
            if isinstance(reader, FakeDemoAccountReader):
                from backend.nexus_demo_execution.account_reader import DemoAccountSnapshot

                # Offline fallback only — never used as capital source when live keys exist.
                reader.set_snapshot(
                    DemoAccountSnapshot(
                        wallet_balance=0.0,
                        equity=0.0,
                        available_balance=0.0,
                        margin_balance=0.0,
                        used_margin=0.0,
                        unrealized_pnl=0.0,
                        realized_pnl=0.0,
                        open_positions=[],
                        open_orders=[],
                    )
                )
        orch = self._build_orchestrator(reader)
        self._orchestrator = orch
        result = orch.run_readonly_cycle()
        payload = result.to_dict()
        self._last_cycle_result = payload
        return payload

    def status_payload(self) -> dict[str, Any]:
        gate_snap = self.gate.snapshot()
        persistence = self.persistence.summary()
        persistence["persistence_blocked"] = self.persistence_blocked
        persistence["data_root"] = str(self.data_root)
        return {
            **READ_ONLY_META,
            "fixed_leverage": FIXED_LEVERAGE,
            "max_open": MAX_OPEN,
            "max_pending": MAX_PENDING,
            "min_margin": MIN_MARGIN,
            "max_margin": MAX_MARGIN,
            "autonomous_mode": gate_snap["autonomous_mode"],
            "current_stage": gate_snap["current_stage"],
            "next_gate": gate_snap["next_gate"],
            "round_terminal": gate_snap.get("round_terminal"),
            "round_complete": gate_snap.get("round_complete", False),
            "first_demo_smoke_order_ready": gate_snap["first_demo_smoke_order_ready"],
            "can_write_orders": gate_snap["can_write_orders"],
            "founder_smoke_approval": self.approval.snapshot(),
            "exchange_write_call_count": self.order_adapter.exchange_write_call_count,
            "kill_switch": self.kill_switch.snapshot(),
            "constitution": self.constitution.snapshot(),
            "domain": self.domain.summary(),
            "persistence": persistence,
            "epoch": self.epoch_tracker.summary(),
            "order_adapter": self.order_adapter.counters(),
            "last_cycle": self._last_cycle_result,
            "last_smoke": self._last_smoke_result,
        }

    def account_payload(self, *, fresh: bool = False) -> dict[str, Any]:
        snap = None
        if fresh:
            try:
                reader = _build_live_or_fake_reader()
                snap = reader.read_with_constitution()
            except Exception as exc:  # noqa: BLE001
                return {"available": False, "reason": f"fresh_read_failed:{type(exc).__name__}"}
        else:
            orch = self._orchestrator
            snap = orch._last_snapshot if orch else None
        if snap is None:
            return {"available": False, "reason": "no_cycle_run"}
        return {
            "wallet_balance": snap.wallet_balance,
            "equity": snap.equity,
            "available_balance": snap.available_balance,
            "used_margin": snap.used_margin,
            "unrealized_pnl": snap.unrealized_pnl,
            "open_positions": len(snap.open_positions),
            "open_orders": len(snap.open_orders),
            "source": snap.source,
            "fresh": fresh,
        }

    def dry_run_latest(self) -> dict[str, Any]:
        if self._orchestrator:
            intent = self._orchestrator.latest_dry_run_intent()
            if intent:
                return {"found": True, "intent": intent}
        rows = self.persistence.read_all("dry_run_intents")
        if rows:
            return {"found": True, "intent": rows[-1]}
        return {"found": False}

    def run_founder_smoke(self, *, async_mode: bool = True) -> dict[str, Any]:
        """One-shot Founder smoke order — requires env FOUNDER gate approval."""
        import threading

        from backend.nexus_demo_execution.demo_write_client import DemoWriteClient
        from backend.nexus_demo_execution.smoke_orchestrator import SmokeOrderOrchestrator

        if getattr(self, "_smoke_running", False):
            return {
                "success": False,
                "recommendation": "FIRST_DEMO_SMOKE_ORDER_BLOCKED",
                "error": "smoke_already_running",
                "smoke_running": True,
                "smoke": self._last_smoke_result,
            }

        export_dir = self.data_root / "artifacts" / "demo_validation"
        export_dir.mkdir(parents=True, exist_ok=True)
        writer = DemoWriteClient()
        orch = SmokeOrderOrchestrator(
            gate=self.gate,
            reader=_build_live_or_fake_reader(),
            persistence=self.persistence,
            epoch_tracker=self.epoch_tracker,
            approval=self.approval,
            kill_switch=self.kill_switch,
            writer=writer,
            export_dir=export_dir,
        )

        if not async_mode:
            result = orch.run_end_to_end()
            payload = result.to_dict()
            self._last_smoke_result = payload
            self.order_adapter.exchange_write_call_count = max(
                self.order_adapter.exchange_write_call_count,
                writer.write_call_count,
            )
            return payload

        self._smoke_running = True
        self._last_smoke_result = {
            "success": None,
            "recommendation": "RUNNING",
            "report": {"status": "STARTED"},
            "error": "",
        }

        def _job() -> None:
            try:
                result = orch.run_end_to_end()
                payload = result.to_dict()
                self._last_smoke_result = payload
                self.order_adapter.exchange_write_call_count = max(
                    self.order_adapter.exchange_write_call_count,
                    writer.write_call_count,
                )
            except Exception as exc:  # noqa: BLE001
                self._last_smoke_result = {
                    "success": False,
                    "recommendation": "FIRST_DEMO_SMOKE_ORDER_FAILED_KILL_SWITCH_APPLIED",
                    "error": type(exc).__name__,
                    "report": {},
                }
                self.approval.close_window("async_exception")
                self.gate.close_smoke_write_window()
            finally:
                self._smoke_running = False

        threading.Thread(target=_job, name="founder-smoke", daemon=True).start()
        return {
            "success": True,
            "recommendation": "RUNNING",
            "error": "",
            "smoke_running": True,
            "report": {"status": "STARTED", "poll": "/api/nexus/demo-execution/founder-smoke/latest"},
        }


_STATE: DemoExecutionApiState | None = None


def get_demo_execution_state() -> DemoExecutionApiState:
    """Lazy init — never crash Flask import if storage probe fails."""
    global _STATE
    if _STATE is None:
        _STATE = DemoExecutionApiState()
    return _STATE


def _wrap(data: dict[str, Any]) -> dict[str, Any]:
    payload = dict(data)
    labels = list(payload.get("labels") or [])
    for label in READ_ONLY_META["labels"]:
        if label not in labels:
            labels.append(label)
    payload["labels"] = labels
    return {**READ_ONLY_META, **payload}


def register_demo_execution_routes(app: Flask) -> None:
    """Register /api/nexus/demo-execution/* routes (readonly + founder smoke)."""
    state = get_demo_execution_state()

    @app.route("/api/nexus/demo-execution/status")
    def demo_execution_status():
        return jsonify(_wrap(get_demo_execution_state().status_payload()))

    @app.route("/api/nexus/demo-execution/gate")
    def demo_execution_gate():
        return jsonify(_wrap(get_demo_execution_state().gate.snapshot()))

    @app.route("/api/nexus/demo-execution/account")
    def demo_execution_account():
        fresh = (os.environ.get("NEXUS_ACCOUNT_FRESH") or "").lower() in {"1", "true"}
        # Prefer fresh query param
        from flask import request

        fresh = fresh or (request.args.get("fresh", "").lower() in {"1", "true", "yes"})
        return jsonify(_wrap(get_demo_execution_state().account_payload(fresh=fresh)))

    @app.route("/api/nexus/demo-execution/epoch")
    def demo_execution_epoch():
        return jsonify(_wrap(get_demo_execution_state().epoch_tracker.summary()))

    @app.route("/api/nexus/demo-execution/dry-run/latest")
    def demo_execution_dry_run_latest():
        return jsonify(_wrap(get_demo_execution_state().dry_run_latest()))

    @app.route("/api/nexus/demo-execution/constitution")
    def demo_execution_constitution():
        return jsonify(_wrap(get_demo_execution_state().constitution.snapshot()))

    @app.route("/api/nexus/demo-execution/domain")
    def demo_execution_domain():
        return jsonify(_wrap(get_demo_execution_state().domain.summary()))

    @app.route("/api/nexus/demo-execution/kill-switch")
    def demo_execution_kill_switch():
        return jsonify(_wrap(get_demo_execution_state().kill_switch.snapshot()))

    @app.route("/api/nexus/demo-execution/persistence")
    def demo_execution_persistence():
        st = get_demo_execution_state()
        payload = st.persistence.summary()
        payload["persistence_blocked"] = st.persistence_blocked
        payload["data_root"] = str(st.data_root)
        return jsonify(_wrap(payload))

    @app.route("/api/nexus/demo-execution/run-readonly-cycle", methods=["GET", "POST"])
    def demo_execution_run_readonly_cycle():
        """Trigger safe readonly validation cycle — live Demo GET when keyed; never exchange write."""
        result = get_demo_execution_state().run_readonly_cycle()
        return jsonify(_wrap({"cycle": result}))

    @app.route("/api/nexus/demo-execution/founder-smoke/preflight", methods=["GET", "POST"])
    def demo_execution_founder_smoke_preflight():
        st = get_demo_execution_state()
        from backend.nexus_demo_execution.demo_write_client import DemoWriteClient
        from backend.nexus_demo_execution.smoke_orchestrator import SmokeOrderOrchestrator

        orch = SmokeOrderOrchestrator(
            gate=st.gate,
            reader=_build_live_or_fake_reader(),
            persistence=st.persistence,
            epoch_tracker=st.epoch_tracker,
            approval=st.approval,
            kill_switch=st.kill_switch,
            writer=DemoWriteClient(),
            export_dir=st.data_root / "artifacts" / "demo_validation",
        )
        pre = orch._preflight()
        # Do not leak snapshot object
        snap = pre.pop("snapshot", None)
        if snap is not None:
            pre["account"] = {
                "wallet_balance": snap.wallet_balance,
                "equity": snap.equity,
                "available_balance": snap.available_balance,
                "used_margin": snap.used_margin,
                "unrealized_pnl": snap.unrealized_pnl,
                "open_positions": len(snap.open_positions),
                "open_orders": len(snap.open_orders),
                "source": snap.source,
            }
        pre["approval"] = st.approval.snapshot()
        pre["gate"] = st.gate.snapshot()
        return jsonify(_wrap(pre))

    @app.route("/api/nexus/demo-execution/founder-smoke/execute", methods=["POST"])
    def demo_execution_founder_smoke_execute():
        """Execute one-shot Founder Demo smoke order. Requires env gate approval."""
        result = get_demo_execution_state().run_founder_smoke()
        return jsonify(_wrap({"smoke": result}))

    @app.route("/api/nexus/demo-execution/founder-smoke/latest")
    def demo_execution_founder_smoke_latest():
        st = get_demo_execution_state()
        return jsonify(_wrap({"found": st._last_smoke_result is not None, "smoke": st._last_smoke_result}))

    logger.info(
        "demo_execution_routes_registered persistence_blocked=%s",
        state.persistence_blocked,
    )