"""Phase 6 Gate C — Research Runtime Bootstrap.

Call bootstrap_research_runtime() at app startup (after route registration).
Idempotent: safe to call multiple times; will not start duplicate jobs.

Startup sequence:
  1. Initialise simulation policy (audit defaults)
  2. Register and start the 6h AI review cycle supervisor job
  3. Register and start the paper controller tick job
  4. Log mode + state summary

Never modifies trading logic, strategy logic, or production config.
Never touches real orders, real funds, or private API.
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

RESEARCH_ONLY: bool = True

_BOOTSTRAP_LOCK = threading.Lock()
_BOOTSTRAPPED = False


def bootstrap_research_runtime() -> dict:
    """Start supervisor + AI review job + paper controller job.

    Idempotent: subsequent calls are no-ops and return cached result.
    Returns a summary dict describing what was started.
    """
    global _BOOTSTRAPPED

    with _BOOTSTRAP_LOCK:
        if _BOOTSTRAPPED:
            return {"ok": True, "alreadyBootstrapped": True, "researchOnly": True}

        summary: dict = {
            "ok": True,
            "researchOnly": True,
            "privateApi": False,
            "steps": [],
        }
        errors: list[str] = []

        # ── Step 1: Simulation policy ─────────────────────────────────────────
        try:
            from backend.nexus_research.simulation_policy import get_simulation_policy
            policy = get_simulation_policy()
            summary["steps"].append("simulation_policy: OK")
            summary["policyVersion"] = "6.0.0-gate-c"
        except Exception as exc:  # noqa: BLE001
            msg = f"simulation_policy init failed: {exc}"
            logger.warning("[bootstrap] %s", msg)
            errors.append(msg)
            summary["steps"].append(f"simulation_policy: FAILED ({exc})")

        # ── Step 2: AI review cycle supervisor job ────────────────────────────
        try:
            from backend.nexus_research.ai_review_cycle import start_ai_review_supervisor_job
            start_ai_review_supervisor_job()
            summary["steps"].append("ai_review_cycle_job: registered")
        except Exception as exc:  # noqa: BLE001
            msg = f"ai_review_cycle job registration failed: {exc}"
            logger.warning("[bootstrap] %s", msg)
            errors.append(msg)
            summary["steps"].append(f"ai_review_cycle_job: FAILED ({exc})")

        # ── Step 3: Paper controller job ──────────────────────────────────────
        try:
            from backend.nexus_research.paper_controller import (
                start_paper_controller_job,
                _read_mode,
                _MODE_ENV_VAR,
                _DEFAULT_MODE,
            )
            mode = _read_mode()
            start_paper_controller_job()
            summary["paperMode"] = mode
            summary["paperModeEnvVar"] = _MODE_ENV_VAR
            summary["paperModeDefault"] = _DEFAULT_MODE
            summary["steps"].append(f"paper_controller_job: registered (mode={mode})")
            logger.info(
                "[bootstrap] paper controller registered in mode=%s "
                "(set %s=PAPER to enable paper trading)", mode, _MODE_ENV_VAR
            )
        except Exception as exc:  # noqa: BLE001
            msg = f"paper_controller job registration failed: {exc}"
            logger.warning("[bootstrap] %s", msg)
            errors.append(msg)
            summary["steps"].append(f"paper_controller_job: FAILED ({exc})")

        # ── Step 4: Exit policy engine init ───────────────────────────────────
        try:
            from backend.nexus_research.exit_policies import get_exit_policy_engine
            get_exit_policy_engine()
            summary["steps"].append("exit_policy_engine: OK")
        except Exception as exc:  # noqa: BLE001
            msg = f"exit_policy_engine init failed: {exc}"
            logger.warning("[bootstrap] %s", msg)
            errors.append(msg)
            summary["steps"].append(f"exit_policy_engine: FAILED ({exc})")

        # ── Finalize ──────────────────────────────────────────────────────────
        summary["errors"] = errors
        summary["bootstrapComplete"] = len(errors) == 0

        if errors:
            logger.warning(
                "[bootstrap] research runtime started with %d deferred error(s): %s",
                len(errors), errors,
            )
        else:
            logger.info(
                "[bootstrap] research runtime fully started (%d steps)",
                len(summary["steps"]),
            )

        _BOOTSTRAPPED = True
        return summary
