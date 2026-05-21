# NEXUS AI Trading System Agent Rules

## Phase Rules
- Work must stay inside the currently approved Phase.
- Phase 0.1 is `Secret Security Foundation` only.
- Phase 0.2 is `Security Wiring Cleanup` only.
- Phase 0.3 is `Security Verification Freeze` only.
- **Phase 8 (Upgrade Track P0-P3)** is approved for autonomous-trading infrastructure only (see `docs/NEXUS_UPGRADE_ROADMAP_V1.md`). LLM must not bypass risk/execution governance; core fleet strategy engine files remain protected unless explicitly approved.
- Do not move into other Phase 1+ legacy scopes without explicit approval.

## Hard Boundaries
- Do not modify trading logic, strategy logic, order execution logic, or leverage rules.
- Do not modify frontend UI files during Phase 0.1 / 0.2 / 0.3.
- Do not print, log, commit, or expose secrets.
- Do not place API secrets in frontend code or client-visible payloads.
- Do not delete existing project files as part of Phase 0 work.

## Required Output Discipline
- After each change, list the files added and modified.
- After each completion, provide the exact test command(s).
- Report which prohibited areas were intentionally left untouched.

## Phase 0.1 Scope
- Allowed additions:
  - `backend/security/secret_manager.py`
  - `backend/security/request_validator.py`
  - `backend/audit/audit_logger.py`
  - `config/security_config.py`
  - `tests/test_phase0_security.py`
  - `AGENTS.md`
- Allowed minimal edits:
  - backend startup entry for security initialization only
  - config/env loading logic only when needed to support secure environment loading

## Phase 0.1 Acceptance Criteria
- Secrets are read from environment variables.
- Logs never contain full secrets.
- READ / TRADE / EMERGENCY responsibilities are separated.
- Request validation rejects secret-bearing and injection-like payloads.
- Audit logs contain timestamp, actor, action, result, risk level, metadata.
- Audit metadata is sanitized.
- Audit log integrity includes a minimal hash chain.
- Tests exist and pass for the Phase 0.1 security baseline.

## Phase 0.2 Scope
- Keep legacy key fallback active.
- Add `NEXUS_*` environment variable support.
- Bridge `NEXUS_*` credentials into existing runtime env names without changing trading modules.
- Migration helpers may warn about future rotation, but must not block startup.
- Do not modify `.env` automatically.
- Do not rotate, revoke, or invalidate keys automatically.

## Phase 0.2 Acceptance Criteria
- Existing legacy env values still allow the system to start.
- New `NEXUS_*` env values are recognized and can satisfy runtime credential loading.
- Logs remain masked when legacy fallback or env bridge is used.
- Future key migration only requires env changes, not code changes.

## Phase 0.3 Scope
- Verify actual Phase 0.1 / 0.2 file changes.
- Verify AGENTS phase rules are complete.
- Verify `logs/security_audit.log` contains no full secret values.
- Verify tests cover legacy fallback and `NEXUS_*` bridge.
- Verify startup entrypoints only perform security initialization and do not alter trading flow.

## Phase 0.3 Acceptance Criteria
- Security freeze report is produced.
- No forbidden files are modified during verification.
- Secret leak scan passes.
- Phase 0 tests pass.
- Phase 0 may be frozen only after all above checks pass.

## Phase 8 Scope (P0-P3 Upgrade Track)
- Allowed additions under `backend/governance/`, `backend/decision/decision_trace_store.py`, `backend/learning/learning_review_queue.py`, `backend/autonomy/`, `backend/monitoring/`, `backend/news/event_registry.py`, `backend/market/universe_filter_service.py`, `tools/research/performance_report.py`, `tests/test_upgrade_pipeline.py`, minimal wiring in `nexus_runtime.py`, `runtime_store.py`, `server.py`, `config/universe_config.py`, `config/autonomy_config.py`.
- Allowed behavior: proposal → governance → trace → execute; learning review queue with optional auto-apply via `NEXUS_LEARNING_AUTO_APPLY`; expanded RADAR universe; performance report API.
- Still forbidden: unconstrained LLM direct order submission; rewriting core `fleet_*_strategy_engine.py` without approval; deleting production config except user-requested scratch cleanup under `archives/scratch/`.
