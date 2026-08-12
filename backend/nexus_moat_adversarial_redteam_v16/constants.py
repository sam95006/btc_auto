"""V16 Moat Adversarial Red Team — constants and hard bans."""
from __future__ import annotations

SCHEMA = "v16_moat_adversarial_redteam"
PROGRAM_ID = "NEXUS_V16_MOAT_ADVERSARIAL_REDTEAM"
LANE = "V16-REDTEAM"
LANE_NAME = "MOAT_ADVERSARIAL_REDTEAM"
BRANCH = "feature/v16-moat-adversarial-redteam"
BASE_HEAD = "907abb52063bcf3f64e2455f08312ae44c821032"
PASS_COUNT = 3

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_moat_adversarial_redteam_v16/",
    "tools/research/run_moat_adversarial_redteam_v16.py",
    "tests/moat_adversarial_redteam_v16/",
    "artifacts/readiness/immutable/v16_moat_adversarial_redteam/",
)

HARD_BANS: tuple[str, ...] = (
    "no_pr26_merge",
    "no_pr27_merge",
    "no_auto_integrate",
    "no_deploy",
    "no_demo_orders",
    "no_shadow_orders",
    "no_exchange_write",
    "no_mainnet_client",
    "no_real_money",
    "no_oos_walkforward_execution",
    "no_acceleration_report_edit",
    "no_status_json_lane_artifact",
    "no_g_drive_mutation",
    "no_platform_blocked_as_pass",
    "no_counterfactual_as_real_pnl",
    "no_lesson_active_without_validation",
    "no_future_leakage",
    "no_secret_embed_in_evidence",
)

# Disposition vocabulary — every finding MUST use one of these.
DISPOSITIONS: tuple[str, ...] = (
    "FIXED",
    "EXPLICITLY_BLOCKED",
    "PLATFORM_BLOCKED_NOT_PASS",
)

# Founder-mandated minimum attack inventory.
ATTACK_IDS: tuple[str, ...] = (
    "future_leakage",
    "fake_regime_confidence",
    "ai_high_confidence_overrides_stale_data",
    "counterfactual_counted_as_real_pnl",
    "good_process_loss_mislabeled_bad",
    "bad_process_win_treated_as_good_lesson",
    "lesson_activated_without_validation",
    "public_ui_proprietary_threshold_leak",
    "member_accessing_founder_data",
    "invalid_ai_json",
    "provider_timeout",
    "duplicate_candidate",
    "duplicate_order_intent",
    "replay_mutates_real_ledger",
    "graph_identity_collision",
    "cherry_picking",
    "strategy_thrashing",
    "no_trade_expert_bypass",
    "unavailable_shown_as_0",
    "fixture_as_live",
    "model_agreement_replaces_deterministic_risk",
    "embedded_secrets",
    "exchange_write",
    "mainnet_client",
)

SEVERITY_BY_ATTACK: dict[str, str] = {
    "future_leakage": "CRITICAL",
    "fake_regime_confidence": "HIGH",
    "ai_high_confidence_overrides_stale_data": "CRITICAL",
    "counterfactual_counted_as_real_pnl": "CRITICAL",
    "good_process_loss_mislabeled_bad": "CRITICAL",
    "bad_process_win_treated_as_good_lesson": "CRITICAL",
    "lesson_activated_without_validation": "CRITICAL",
    "public_ui_proprietary_threshold_leak": "CRITICAL",
    "member_accessing_founder_data": "CRITICAL",
    "invalid_ai_json": "HIGH",
    "provider_timeout": "HIGH",
    "duplicate_candidate": "HIGH",
    "duplicate_order_intent": "CRITICAL",
    "replay_mutates_real_ledger": "CRITICAL",
    "graph_identity_collision": "CRITICAL",
    "cherry_picking": "HIGH",
    "strategy_thrashing": "HIGH",
    "no_trade_expert_bypass": "CRITICAL",
    "unavailable_shown_as_0": "HIGH",
    "fixture_as_live": "CRITICAL",
    "model_agreement_replaces_deterministic_risk": "CRITICAL",
    "embedded_secrets": "CRITICAL",
    "exchange_write": "CRITICAL",
    "mainnet_client": "CRITICAL",
}

PASS_RECOMMENDATION = "NEXUS_V16_MOAT_ADVERSARIAL_REDTEAM_PASS"
BLOCKED_RECOMMENDATION = "NEXUS_V16_MOAT_ADVERSARIAL_REDTEAM_SURVIVORS_REMAIN"
FAIL_RECOMMENDATION = "NEXUS_V16_MOAT_ADVERSARIAL_REDTEAM_CRITICAL_OPEN"

EVIDENCE_CLASS = "CONTROL_FIXTURE_ADVERSARIAL_NOT_MARKET_PERFORMANCE"
LABEL = "V16_MOAT_REDTEAM_CONTROL_NOT_REAL_TRADING"
EXECUTION_MODE = "SIMULATED_FAIL_CLOSED_NO_EXCHANGE_WRITE"

ARTIFACT_REL = "artifacts/readiness/immutable/v16_moat_adversarial_redteam"
COORDINATOR_EVIDENCE = r"D:\NEXUS_RUNTIME\evidence_coordinator\v16_redteam.json"
