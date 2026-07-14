/**
 * Sanitized Private Operator report / runbook / checkpoint index (MVP-14).
 * READ ONLY · NOT INVESTMENT ADVICE · deep links are documentation-only · no /data · no secrets
 */

export type UiTargetPage =
  | "/overview"
  | "/evidence"
  | "/paper-lab"
  | "/risk-evidence"
  | "/provider-shadow";

export type PrivateReportMeta = {
  stage: string;
  title: string;
  verdict: string;
  filePath: string;
  oneLineConclusion: string;
  nextAction: string;
  kind: "report" | "runbook" | "checkpoint";
  relatedReports: string[];
  relatedRunbooks: string[];
  relatedCheckpoint: string;
  nextActionAnchor: string;
  uiTargetPage: UiTargetPage;
};

export type ChecklistItem = {
  id: string;
  label: string;
  ok: boolean;
};

export type DeepLinkAction = {
  id: string;
  label: string;
  to: string;
  description: string;
};

/** Anchor helpers for in-console navigation (docs only — no control actions). */
export function stageAnchorId(stage: string): string {
  return `artifact-${stage.replace(/[^a-zA-Z0-9]+/g, "-").toLowerCase()}`;
}

export function artifactHref(stage: string, page: UiTargetPage = "/evidence"): string {
  return `${page}#${stageAnchorId(stage)}`;
}

/** Research report chain P2D → P2H-QA. */
export const PRIVATE_OPERATOR_REPORTS: PrivateReportMeta[] = [
  {
    stage: "4.18-P2D",
    title: "ETH follow-up confirmation prompt repair",
    verdict: "STAGE_4_18P2D_PASS",
    filePath: "docs/reports/STAGE_4_18P2D_ETH_FOLLOWUP_CONFIRMATION_PROMPT_REVIEW_REPORT.md",
    oneLineConclusion: "Prompt repair added (previous_watch_context + collapse guards)",
    nextAction: "Needs runtime validation when ETH watch appears",
    kind: "report",
    relatedReports: ["4.18-P2D-R1", "4.18-P2E"],
    relatedRunbooks: ["4.18-P2H-OPS"],
    relatedCheckpoint: "4.18-P2H-REL",
    nextActionAnchor: "gate-checklist",
    uiTargetPage: "/paper-lab",
  },
  {
    stage: "4.18-P2D-R1",
    title: "ETH follow-up prompt runtime regression",
    verdict: "STAGE_4_18P2D_R1_PARTIAL_NO_ETH_WATCH",
    filePath: "docs/reports/STAGE_4_18P2D_R1_ETH_FOLLOWUP_PROMPT_RUNTIME_REGRESSION_REPORT.md",
    oneLineConclusion: "Technical PASS but no ETH watch sample",
    nextAction: "Diagnose no-watch (P2E)",
    kind: "report",
    relatedReports: ["4.18-P2D", "4.18-P2E", "4.18-P2F"],
    relatedRunbooks: ["4.18-P2H-OPS"],
    relatedCheckpoint: "4.18-P2H-REL",
    nextActionAnchor: "gate-checklist",
    uiTargetPage: "/paper-lab",
  },
  {
    stage: "4.18-P2E",
    title: "ETH no-watch diagnostics + wait helper",
    verdict: "STAGE_4_18P2E_PASS",
    filePath: "docs/reports/STAGE_4_18P2E_ETH_NO_WATCH_DIAGNOSTICS_AND_WAIT_HELPER_FIX_REPORT.md",
    oneLineConclusion: "sample_market_no_edge; wait helper fixed",
    nextAction: "Define reappearance gate (P2F)",
    kind: "report",
    relatedReports: ["4.18-P2D-R1", "4.18-P2F"],
    relatedRunbooks: ["4.18-P2H-OPS"],
    relatedCheckpoint: "4.18-P2H-REL",
    nextActionAnchor: "gate-checklist",
    uiTargetPage: "/paper-lab",
  },
  {
    stage: "4.18-P2F",
    title: "ETH watch reappearance gate",
    verdict: "STAGE_4_18P2F_PASS",
    filePath: "docs/reports/STAGE_4_18P2F_ETH_WATCH_REAPPEARANCE_GATE_REPORT.md",
    oneLineConclusion: "regression_readiness=false — do not run",
    nextAction: "Operator readiness pack (P2G)",
    kind: "report",
    relatedReports: ["4.18-P2E", "4.18-P2G"],
    relatedRunbooks: ["4.18-P2H-OPS"],
    relatedCheckpoint: "4.18-P2H-REL",
    nextActionAnchor: "gate-checklist",
    uiTargetPage: "/overview",
  },
  {
    stage: "4.18-P2G",
    title: "Operator readiness pack",
    verdict: "STAGE_4_18P2G_PASS",
    filePath: "docs/reports/STAGE_4_18P2G_OPERATOR_READINESS_PACK.md",
    oneLineConclusion: "Wait for ETH watch conditions; no short regression now",
    nextAction: "Enter backend HOLD (P2H)",
    kind: "report",
    relatedReports: ["4.18-P2F", "4.18-P2H"],
    relatedRunbooks: ["4.18-P2H-OPS"],
    relatedCheckpoint: "4.18-P2H-REL",
    nextActionAnchor: "release-checkpoint",
    uiTargetPage: "/provider-shadow",
  },
  {
    stage: "4.18-P2H",
    title: "Backend HOLD + passive future gate checker",
    verdict: "STAGE_4_18P2H_PASS",
    filePath: "docs/reports/STAGE_4_18P2H_BACKEND_HOLD_AND_PASSIVE_GATE_CHECKER_REPORT.md",
    oneLineConclusion: "HOLD + passive checker — no auto-run",
    nextAction: "continue_hold_no_regression",
    kind: "report",
    relatedReports: ["4.18-P2G", "4.18-P2H-QA"],
    relatedRunbooks: ["4.18-P2H-OPS"],
    relatedCheckpoint: "4.18-P2H-REL",
    nextActionAnchor: "release-checkpoint",
    uiTargetPage: "/overview",
  },
  {
    stage: "4.18-P2H-QA",
    title: "Repository / release health check",
    verdict: "STAGE_4_18P2H_QA_PASS",
    filePath: "docs/reports/STAGE_4_18P2H_QA_RELEASE_HEALTH_CHECK_REPORT.md",
    oneLineConclusion: "Release checkpoint ready under HOLD",
    nextAction: "hold_backend_and_continue_private_operator_ui",
    kind: "report",
    relatedReports: ["4.18-P2H"],
    relatedRunbooks: ["4.18-P2H-OPS"],
    relatedCheckpoint: "4.18-P2H-REL",
    nextActionAnchor: "release-checkpoint",
    uiTargetPage: "/risk-evidence",
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
    relatedReports: ["4.18-P2H", "4.18-P2H-QA", "4.18-P2F"],
    relatedRunbooks: [],
    relatedCheckpoint: "4.18-P2H-REL",
    nextActionAnchor: "runbooks",
    uiTargetPage: "/evidence",
  },
];

export const PRIVATE_OPERATOR_CHECKPOINTS: PrivateReportMeta[] = [
  {
    stage: "4.18-P2H-REL",
    title: "HOLD release checkpoint",
    verdict: "STAGE_4_18P2H_REL_PASS",
    filePath: "docs/releases/STAGE_4_18_P2H_HOLD_RELEASE_CHECKPOINT.md",
    oneLineConclusion: "Archived HOLD release checkpoint — suggested tag only",
    nextAction: "hold_backend_and_continue_private_operator_ui",
    kind: "checkpoint",
    relatedReports: ["4.18-P2H-QA", "4.18-P2H", "4.18-P2G"],
    relatedRunbooks: ["4.18-P2H-OPS"],
    relatedCheckpoint: "4.18-P2H-REL",
    nextActionAnchor: "release-checkpoint",
    uiTargetPage: "/evidence",
  },
];

export const OVERVIEW_QUICK_LINKS: DeepLinkAction[] = [
  {
    id: "evidence",
    label: "Evidence Center",
    to: "/evidence#reports",
    description: "Report / runbook / checkpoint hub",
  },
  {
    id: "runbook",
    label: "HOLD Runbook",
    to: artifactHref("4.18-P2H-OPS"),
    description: "When HOLD may lift · docs only",
  },
  {
    id: "gate",
    label: "Gate Checklist",
    to: "/overview#gate-checklist",
    description: "Short-regression conditions (all false under HOLD)",
  },
  {
    id: "checkpoint",
    label: "Release Checkpoint",
    to: "/evidence#release-checkpoint",
    description: "P2H-REL archived HOLD checkpoint",
  },
];

export const PAPER_LAB_RELATED_STAGES = [
  "4.18-P2D",
  "4.18-P2D-R1",
  "4.18-P2E",
  "4.18-P2F",
] as const;

export const RISK_RELATED_STAGES = ["4.18-P2H-QA", "4.18-P2H-REL"] as const;

export const PROVIDER_RELATED_STAGES = [
  "4.18-P2G",
  "4.18-P2H",
  "4.18-P2H-REL",
] as const;

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
  { id: "orders", label: "orders=false", ok: true },
  { id: "mock", label: "mock=false", ok: true },
  { id: "arm", label: "ARM=false", ok: true },
  { id: "production", label: "production=false", ok: true },
  { id: "btc_auto", label: "btc_auto=false", ok: true },
  { id: "stage_419", label: "Stage 4.19=false (blocked)", ok: true },
  { id: "billing", label: "billing/accounts/API keys=false", ok: true },
  { id: "no_30m", label: "30m now=false", ok: true },
  { id: "no_60m", label: "60m=false", ok: true },
  { id: "hold", label: "backend HOLD", ok: true },
];

export const ROUTING_POLICY_CHECKLIST: ChecklistItem[] = [
  { id: "cerebras_exp", label: "BTC Cerebras-first was experiment only", ok: true },
  { id: "no_permanent", label: "permanent routing change=false", ok: true },
  { id: "shadow_grad", label: "shadow not used for graduation", ok: true },
  { id: "ops_approval", label: "future routing changes require operator approval", ok: true },
  { id: "auto_change", label: "routing auto change=false", ok: true },
  { id: "editor", label: "routing editor absent (forbidden)", ok: true },
];

export function getAllPrivateReportIndex(): PrivateReportMeta[] {
  return [
    ...PRIVATE_OPERATOR_REPORTS,
    ...PRIVATE_OPERATOR_RUNBOOKS,
    ...PRIVATE_OPERATOR_CHECKPOINTS,
  ];
}

export function findArtifact(stage: string): PrivateReportMeta | undefined {
  return getAllPrivateReportIndex().find((a) => a.stage === stage);
}

export function getOrderedChainStages(): string[] {
  return [
    "4.18-P2D",
    "4.18-P2D-R1",
    "4.18-P2E",
    "4.18-P2F",
    "4.18-P2G",
    "4.18-P2H",
    "4.18-P2H-QA",
    "4.18-P2H-OPS",
    "4.18-P2H-REL",
  ];
}
