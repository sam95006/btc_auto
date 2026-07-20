"""Phase 6 Gate C — Research Runtime Bootstrap.

Call bootstrap_research_runtime() at app startup (after route registration).
Idempotent: safe to call multiple times; will not start duplicate jobs.

Startup sequence (Phase 6.1B):
  1. Storage / integrity (via get_research_store)
  2. Durable ledger replay + hash-chain validation
  3. Review case / repository hydration
  4. Simulation policy
  5. AI review cycle job
  6. Paper controller job (SHADOW default; blocked if ledger hydration failed)
  7. Exit policy engine

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

        # ── Step 0: Open research store (migrations + integrity) ──────────────
        try:
            from backend.nexus_research.storage import get_research_store

            store = get_research_store()
            profile = store.sqlite_runtime_profile()
            summary["schemaVersion"] = store.schema_version
            summary["sqliteIntegrity"] = profile.get("integrity_check")
            summary["steps"].append(
                f"storage: OK schema={store.schema_version} integrity={profile.get('integrity_check')}"
            )
        except Exception as exc:  # noqa: BLE001
            msg = f"storage init failed: {exc}"
            logger.warning("[bootstrap] %s", msg)
            errors.append(msg)
            summary["steps"].append(f"storage: FAILED ({exc})")

        # ── Step 1: Ledger replay + runtime hydration (BEFORE paper controller)
        try:
            from backend.nexus_research.runtime_hydration import hydrate_research_runtime

            hyd = hydrate_research_runtime()
            summary["runtimeHydration"] = hyd
            summary["steps"].append(
                "runtime_hydration: OK"
                if hyd.get("ok")
                else f"runtime_hydration: DEGRADED ({hyd.get('steps')})"
            )
            if hyd.get("hydrationFailed"):
                errors.append("ledger_hydration_failed")
        except Exception as exc:  # noqa: BLE001
            msg = f"runtime hydration failed: {exc}"
            logger.warning("[bootstrap] %s", msg)
            errors.append(msg)
            summary["steps"].append(f"runtime_hydration: FAILED ({exc})")

        # ── Step 2: Simulation policy ─────────────────────────────────────────
        try:
            from backend.nexus_research.simulation_policy import get_simulation_policy
            get_simulation_policy()
            summary["steps"].append("simulation_policy: OK")
            summary["policyVersion"] = "6.1b-gate-c"
        except Exception as exc:  # noqa: BLE001
            msg = f"simulation_policy init failed: {exc}"
            logger.warning("[bootstrap] %s", msg)
            errors.append(msg)
            summary["steps"].append(f"simulation_policy: FAILED ({exc})")

        # ── Step 2b: Feature registry seed + observation feed (Phase 6.5) ─────
        try:
            from backend.nexus_research.features.feature_seed import seed_default_feature_definitions
            from backend.nexus_research.features.feature_observation_feed import refresh_feature_observations_from_scanner

            seed_result = seed_default_feature_definitions()
            feed_result = refresh_feature_observations_from_scanner()
            summary["featureRegistry"] = {
                "definitions": seed_result.get("count"),
                "observationsRecorded": feed_result.get("recorded"),
            }
            summary["steps"].append(
                f"feature_registry: seeded defs={seed_result.get('count')} obs={feed_result.get('recorded')}"
            )
        except Exception as exc:  # noqa: BLE001
            msg = f"feature registry seed failed: {exc}"
            logger.warning("[bootstrap] %s", msg)
            summary["steps"].append(f"feature_registry: FAILED ({exc})")

        # ── Step 3: AI review cycle supervisor job ────────────────────────────
        try:
            from backend.nexus_research.ai_review_cycle import start_ai_review_supervisor_job
            start_ai_review_supervisor_job()
            summary["steps"].append("ai_review_cycle_job: registered")
        except Exception as exc:  # noqa: BLE001
            msg = f"ai_review_cycle job registration failed: {exc}"
            logger.warning("[bootstrap] %s", msg)
            errors.append(msg)
            summary["steps"].append(f"ai_review_cycle_job: FAILED ({exc})")

        # ── Step 4: Paper controller job (SHADOW; no orders if hydration failed)
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
            if mode == "PAPER":
                try:
                    from backend.nexus_research.paper_activation import activate_or_resume_paper_session
                    act = activate_or_resume_paper_session()
                    summary["paperActivation"] = {
                        "ok": act.get("ok"),
                        "sessionId": (act.get("session") or {}).get("activationSessionId"),
                        "accountId": (act.get("session") or {}).get("accountId"),
                        "hint": act.get("controllerHint"),
                    }
                    summary["steps"].append(
                        f"paper_activation: {act.get('controllerHint')} ok={act.get('ok')}"
                    )
                except Exception as act_exc:  # noqa: BLE001
                    summary["steps"].append(f"paper_activation: FAILED ({act_exc})")
                    errors.append(f"paper_activation_failed: {act_exc}")
            logger.info(
                "[bootstrap] paper controller registered in mode=%s "
                "(set %s=PAPER to enable paper trading)", mode, _MODE_ENV_VAR
            )
        except Exception as exc:  # noqa: BLE001
            msg = f"paper_controller job registration failed: {exc}"
            logger.warning("[bootstrap] %s", msg)
            errors.append(msg)
            summary["steps"].append(f"paper_controller_job: FAILED ({exc})")

        # ── Step 5: Exit policy engine init ───────────────────────────────────
        try:
            from backend.nexus_research.exit_policies import get_exit_policy_engine
            get_exit_policy_engine()
            summary["steps"].append("exit_policy_engine: OK")
        except Exception as exc:  # noqa: BLE001
            msg = f"exit_policy_engine init failed: {exc}"
            logger.warning("[bootstrap] %s", msg)
            errors.append(msg)
            summary["steps"].append(f"exit_policy_engine: FAILED ({exc})")

        # ── Step 6: Canonical config + startup safety verdict ─────────────────
        try:
            from backend.nexus_research.config import get_effective_config
            from backend.nexus_research.review_cases import get_review_case_manager
            from backend.nexus_research.storage import is_storage_integrity_healthy

            cases = get_review_case_manager().status_summary()
            cfg = get_effective_config(
                refresh=True,
                runtime_context={
                    "durableClaim": True,
                    "restartProof": True,
                    "storageHealthy": is_storage_integrity_healthy(summary.get("sqliteIntegrity")),
                    "runtimeOwnerCount": 1,
                    "schedulerOwnerCount": 1,
                    "scannerOwnerCount": 1,
                    "ledgerOwnerCount": 1,
                    "naturalActiveCapacityAvailable": int(cases.get("capacityAvailable") or 0) > 0,
                    "stage4RuntimePatchEffective": False,
                },
            )
            summary["startupSafetyVerdict"] = (cfg.get("startupSafetyVerdict") or {}).get("verdict")
            summary["autonomousMode"] = (cfg.get("autonomousMode") or {}).get("effective")
            summary["reviewEngineMode"] = (cfg.get("reviewEngineMode") or {}).get("effective")
            summary["steps"].append(
                f"config: OK verdict={summary['startupSafetyVerdict']} mode={summary['autonomousMode']}"
            )
        except Exception as exc:  # noqa: BLE001
            msg = f"config resolver failed: {exc}"
            logger.warning("[bootstrap] %s", msg)
            errors.append(msg)
            summary["steps"].append(f"config: FAILED ({exc})")

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
