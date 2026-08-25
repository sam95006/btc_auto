"""Install certified bounded runtime wiring at process startup."""
from __future__ import annotations

from typing import Any

CERTIFIED_BOUNDED_RUNTIME_ACTIVE = False


def certified_bounded_runtime_active() -> bool:
    return CERTIFIED_BOUNDED_RUNTIME_ACTIVE


class _UnavailableBounded6HSession:
    """Fail-closed placeholder — never exposes legacy bounded runtime."""

    def start(self, start_request: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "ok": False,
            "reason": "certified_bounded_runtime_unavailable",
            "hold": True,
            "CERTIFIED_BOUNDED_RUNTIME_ACTIVE": False,
        }

    def status(self) -> dict[str, Any]:
        return {"status": "UNAVAILABLE", "CERTIFIED_BOUNDED_RUNTIME_ACTIVE": False}

    def stop(self, reason: str = "OPERATOR_STOP") -> None:
        del reason


def install_certified_bounded_runtime() -> bool:
    global CERTIFIED_BOUNDED_RUNTIME_ACTIVE
    import backend.nexus_demo_execution.bounded_6h_session as bounded_6h_module

    try:
        from backend.nexus_bounded_runtime.certified_session import CertifiedBounded6HSession

        bounded_6h_module.Bounded6HSession = CertifiedBounded6HSession
        CERTIFIED_BOUNDED_RUNTIME_ACTIVE = True
        return True
    except Exception:
        bounded_6h_module.Bounded6HSession = _UnavailableBounded6HSession  # type: ignore[misc,assignment]
        CERTIFIED_BOUNDED_RUNTIME_ACTIVE = False
        return False


def patch_bounded_6h_start_handler() -> None:
    """Route bounded-6h/start through signed POST body — no Zeabur env lease authority."""
    from backend.nexus_bounded_runtime.bootstrap import certified_bounded_runtime_active
    from backend.nexus_demo_execution.api_routes import DemoExecutionApiState

    def start_bounded_6h_signed(self):  # type: ignore[no-untyped-def]
        with self._bounded_owner_start_lock:
            if not certified_bounded_runtime_active():
                return {
                    "ok": False,
                    "reason": "certified_bounded_runtime_unavailable",
                    "hold": True,
                    "CERTIFIED_BOUNDED_RUNTIME_ACTIVE": False,
                }
            blocked = self._bounded_owner_blocked("_bounded_6h")
            if blocked:
                return blocked
            try:
                from flask import has_request_context, request

                body = request.get_json(silent=True) if has_request_context() else None
            except Exception:
                body = None
            if self._bounded_6h is None:
                from backend.nexus_demo_execution.bounded_6h_session import Bounded6HSession
                from backend.nexus_demo_execution.demo_write_client import DemoWriteClient
                from backend.nexus_demo_execution.api_routes import _build_live_or_fake_reader

                export_dir = self.data_root / "artifacts" / "demo_validation_6h_v2"
                export_dir.mkdir(parents=True, exist_ok=True)
                self._bounded_6h = Bounded6HSession(
                    gate=self.gate,
                    reader=_build_live_or_fake_reader(),
                    persistence=self.persistence,
                    epoch_tracker=self.epoch_tracker,
                    kill_switch=self.kill_switch,
                    writer=DemoWriteClient(),
                    approval=self.approval,
                    export_dir=export_dir,
                    data_root=self.data_root,
                )
            return self._bounded_6h.start(start_request=body if isinstance(body, dict) else None)

    DemoExecutionApiState.start_bounded_6h = start_bounded_6h_signed  # type: ignore[method-assign]

    original_status = DemoExecutionApiState.bounded_6h_status

    def bounded_6h_status_signed(self):  # type: ignore[no-untyped-def]
        from backend.nexus_bounded_runtime.runtime_lease_storage_proof import prove_runtime_durable_lease_storage

        payload = original_status(self)
        payload["CERTIFIED_BOUNDED_RUNTIME_ACTIVE"] = certified_bounded_runtime_active()
        payload.update(prove_runtime_durable_lease_storage(self.data_root))
        return payload

    DemoExecutionApiState.bounded_6h_status = bounded_6h_status_signed  # type: ignore[method-assign]
