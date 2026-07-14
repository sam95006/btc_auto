/**
 * Sanitized Private Operator report / runbook index (MVP-11).
 * READ ONLY · NOT INVESTMENT ADVICE · no /data raw files · no secrets
 */

export type PrivateReportMeta = {
  stage: string;
  title: string;
  verdict: string;
  filePath: string;
  oneLineConclusion: string;
  nextAction: string;
  kind: "report" | "runbook";
};

export type ChecklistItem = {
  id: string;
  label: string;
  ok: boolean;
};

/** Research report chain P2D → P2H (+ QA). */
export const PRIVATE_OPERATOR_REPORTS: PrivateReportMeta[] = [
  {
    stage: "4.18-P2D",
    title: "ETH follow-up confirmation prompt repair",
    verdict: "STAGE_4_18P2D_PASS",
    filePath: "docs/reports/STAGE_4_18P2D_ETH_FOLLOWUP_CONFIRMATION_PROMPT_REVIEW_REPORT.md",
    oneLineConclusion: "Prompt repair added (previous_watch_context + collapse guards)",
    nextAction: "Needs runtime validation when ETH watch appears",
    kind: "report",
  },
  {
    stage: "4.18-P2D-R1",
    title: "ETH follow-up prompt runtime regression",
    verdict: "STAGE_4_18P2D_R1_PARTIAL_NO_ETH_WATCH",
    filePath: "docs/reports/STAGE_4_18P2D_R1_ETH_FOLLOWUP_PROMPT_RUNTIME_REGRESSION_REPORT.md",
    oneLineConclusion: "Technical PASS but no ETH watch sample",
    nextAction: "Diagnose no-watch (P2E)",
    kind: "report",
  },
  {
    stage: "4.18-P2E",
    title: "ETH no-watch diagnostics + wait helper",
    verdict: "STAGE_4_18P2E_PASS",
    filePath: "docs/reports/STAGE_4_18P2E_ETH_NO_WATCH_DIAGNOSTICS_AND_WAIT_HELPER_FIX_REPORT.md",
    oneLineConclusion: "sample_market_no_edge; wait helper fixed",
    nextAction: "Define reappearance gate (P2F)",
    kind: "report",
  },
  {
    stage: "4.18-P2F",
    title: "ETH watch reappearance gate",
    verdict: "STAGE_4_18P2F_PASS",
    filePath: "docs/reports/STAGE_4_18P2F_ETH_WATCH_REAPPEARANCE_GATE_REPORT.md",
    oneLineConclusion: "regression_readiness=false — do not run",
    nextAction: "Operator readiness pack (P2G)",
    kind: "report",
  },
  {
    stage: "4.18-P2G",
    title: "Operator readiness pack",
    verdict: "STAGE_4_18P2G_PASS",
    filePath: "docs/reports/STAGE_4_18P2G_OPERATOR_READINESS_PACK.md",
    oneLineConclusion: "Wait for ETH watch conditions; no short regression now",
    nextAction: "Enter backend HOLD (P2H)",
    kind: "report",
  },
  {
    stage: "4.18-P2H",
    title: "Backend HOLD + passive future gate checker",
    verdict: "STAGE_4_18P2H_PASS",
    filePath: "docs/reports/STAGE_4_18P2H_BACKEND_HOLD_AND_PASSIVE_GATE_CHECKER_REPORT.md",
    oneLineConclusion: "HOLD + passive checker — no auto-run",
    nextAction: "continue_hold_no_regression",
    kind: "report",
  },
  {
    stage: "4.18-P2H-QA",
    title: "Repository / release health check",
    verdict: "STAGE_4_18P2H_QA_PASS",
    filePath: "docs/reports/STAGE_4_18P2H_QA_RELEASE_HEALTH_CHECK_REPORT.md",
    oneLineConclusion: "Release checkpoint ready under HOLD",
    nextAction: "hold_backend_and_continue_private_operator_ui",
    kind: "report",
  },
];

export const PRIVATE_OPERATOR_RUNBOOKS: PrivateReportMeta[] = [
  {
    stage: "4.18-P2H-OPS",
    title: "Operator HOLD runbook",
    verdict: "STAGE_4_18P2H_OPS_PASS",
    filePath: "docs/runbooks/STAGE_4_18_P2H_OPERATOR_HOLD_RUNBOOK.md",
    oneLineConclusion:
      "When to lift HOLD, how to run future gate checker, short-regression + 4.19 checklists",
    nextAction: "Manual future gate checker only — never auto-start",
    kind: "runbook",
  },
];

/** Short-regression approval checklist (current HOLD snapshot defaults). */
export const SHORT_REGRESSION_CHECKLIST: ChecklistItem[] = [
  { id: "eth_watch", label: "ETH has watch or valid_watch", ok: false },
  { id: "bias", label: "directional_bias != NONE", ok: false },
  { id: "side", label: "candidate_side != NONE", ok: false },
  { id: "conf", label: "confidence >= 0.45", ok: false },
  { id: "trigger", label: "entry_trigger present", ok: false },
  { id: "invalidation", label: "invalidation present", ok: false },
  { id: "mae", label: "MAE cap passed", ok: false },
  { id: "dq", label: "data_quality ok", ok: false },
  { id: "regime", label: "regime not unknown", ok: false },
];

/** Safety invariants — always asserted in Private Operator UI. */
export const SAFETY_INVARIANTS_CHECKLIST: ChecklistItem[] = [
  { id: "no_order", label: "no order", ok: true },
  { id: "no_mock", label: "no mock", ok: true },
  { id: "no_arm", label: "no ARM", ok: true },
  { id: "no_production", label: "no production", ok: true },
  { id: "no_btc_auto", label: "no btc-auto", ok: true },
  { id: "no_419", label: "no Stage 4.19 start", ok: true },
  { id: "no_30m", label: "no 30m now", ok: true },
  { id: "no_60m", label: "no 60m", ok: true },
  { id: "hold", label: "backend HOLD", ok: true },
];

export const ROUTING_POLICY_CHECKLIST: ChecklistItem[] = [
  { id: "no_permanent", label: "no permanent routing change", ok: true },
  { id: "cerebras_exp", label: "BTC Cerebras-first was experiment only", ok: true },
  { id: "auto_change", label: "routing auto change = false", ok: true },
  { id: "editor", label: "routing editor absent (forbidden)", ok: true },
];

export function getAllPrivateReportIndex(): PrivateReportMeta[] {
  return [...PRIVATE_OPERATOR_REPORTS, ...PRIVATE_OPERATOR_RUNBOOKS];
}
