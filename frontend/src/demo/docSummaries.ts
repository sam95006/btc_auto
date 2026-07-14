/**
 * Sanitized static doc summaries for Private Operator (MVP-15).
 * READ ONLY · NOT INVESTMENT ADVICE · excerpts only · no raw /data · no secrets · no control actions
 */

export type GateStatusLabel =
  | "HOLD"
  | "WAIT"
  | "PASS"
  | "PARTIAL"
  | "BLOCKED"
  | "READY";

export type DocSummary = {
  id: string;
  stage: string;
  title: string;
  verdict: string;
  oneLineSummary: string;
  keyConclusion: string;
  nextAction: string;
  gateStatus: GateStatusLabel;
  safetyNote: string;
  relatedArtifactIds: string[];
};

export const DOC_SUMMARIES: DocSummary[] = [
  {
    id: "p2d",
    stage: "4.18-P2D",
    title: "ETH follow-up confirmation prompt repair",
    verdict: "STAGE_4_18P2D_PASS",
    oneLineSummary: "Prompt repair added: previous_watch_context + collapse guards.",
    keyConclusion: "Code-only repair ready; runtime validation still required when ETH watch appears.",
    nextAction: "Wait for ETH watch sample — do not blind-run 30m.",
    gateStatus: "PASS",
    safetyNote: "No MAE/RG/routing/order changes · Stage 4.19 blocked",
    relatedArtifactIds: ["p2d-r1", "p2e", "p2h-ops"],
  },
  {
    id: "p2d-r1",
    stage: "4.18-P2D-R1",
    title: "ETH follow-up prompt runtime regression",
    verdict: "STAGE_4_18P2D_R1_PARTIAL_NO_ETH_WATCH",
    oneLineSummary: "Technical PASS but no ETH watch — repair path never exercised.",
    keyConclusion: "PARTIAL_NO_ETH_WATCH; ETH vw=0 / graduation=0.",
    nextAction: "Diagnose no-watch (P2E) — no 60m.",
    gateStatus: "PARTIAL",
    safetyNote: "mock=0 · order=0 · Stage 4.19 blocked",
    relatedArtifactIds: ["p2d", "p2e", "p2f"],
  },
  {
    id: "p2e",
    stage: "4.18-P2E",
    title: "ETH no-watch diagnostics + wait helper",
    verdict: "STAGE_4_18P2E_PASS",
    oneLineSummary: "Root cause sample_market_no_edge — not prompt over-conservative.",
    keyConclusion: "No ETH edge in sample; wait helper robustness fixed.",
    nextAction: "Define reappearance gate (P2F) — no soak.",
    gateStatus: "PASS",
    safetyNote: "No prompt/MAE/RG/routing edits · Stage 4.19 blocked",
    relatedArtifactIds: ["p2d-r1", "p2f"],
  },
  {
    id: "p2f",
    stage: "4.18-P2F",
    title: "ETH watch reappearance gate",
    verdict: "STAGE_4_18P2F_PASS",
    oneLineSummary: "regression_readiness=false — do not run regression now.",
    keyConclusion: "ETH watch conditions not present; gate closed.",
    nextAction: "wait_for_eth_watch_conditions_reappear_no_60m",
    gateStatus: "WAIT",
    safetyNote: "No auto-run · Stage 4.19 blocked",
    relatedArtifactIds: ["p2e", "p2g", "p2h-ops"],
  },
  {
    id: "p2g",
    stage: "4.18-P2G",
    title: "Operator readiness pack",
    verdict: "STAGE_4_18P2G_PASS",
    oneLineSummary: "Operator pack: next short regression not allowed now.",
    keyConclusion: "BTC prior evidence exists; ETH repair not runtime-validated; dossier not allowed.",
    nextAction: "wait_for_eth_watch_conditions_reappear",
    gateStatus: "WAIT",
    safetyNote: "should_run_30m_now=false · should_run_60m=false · Stage 4.19 blocked",
    relatedArtifactIds: ["p2f", "p2h", "p2h-rel"],
  },
  {
    id: "p2h",
    stage: "4.18-P2H",
    title: "Backend HOLD + passive future gate checker",
    verdict: "STAGE_4_18P2H_PASS",
    oneLineSummary: "Backend HOLD formalized; passive checker never auto-starts runs.",
    keyConclusion: "HOLD = conditional wait until ETH watch conditions reappear.",
    nextAction: "continue_hold_no_regression",
    gateStatus: "HOLD",
    safetyNote: "Manual checker only · no Stage 4.19 start",
    relatedArtifactIds: ["p2g", "p2h-ops", "p2h-qa"],
  },
  {
    id: "p2h-ops",
    stage: "4.18-P2H-OPS",
    title: "Operator HOLD runbook",
    verdict: "STAGE_4_18P2H_OPS_PASS",
    oneLineSummary: "Runbook: when HOLD may lift, how to run future checker, approval checklists.",
    keyConclusion: "operator_may_approve_short_regression ≠ auto-run.",
    nextAction: "Manual future gate checker only — never auto-start",
    gateStatus: "HOLD",
    safetyNote: "Docs/CLI only · no runtime · Stage 4.19 blocked",
    relatedArtifactIds: ["p2h", "p2h-qa", "p2h-rel"],
  },
  {
    id: "p2h-qa",
    stage: "4.18-P2H-QA",
    title: "Repository / release health check",
    verdict: "STAGE_4_18P2H_QA_PASS",
    oneLineSummary: "Release checkpoint ready under HOLD; docs/UI/safety consistent.",
    keyConclusion: "release_checkpoint_ready=true; no order/ARM/billing paths.",
    nextAction: "hold_backend_and_continue_private_operator_ui",
    gateStatus: "READY",
    safetyNote: "No runtime · Stage 4.19 blocked",
    relatedArtifactIds: ["p2h", "p2h-ops", "p2h-rel"],
  },
  {
    id: "p2h-rel",
    stage: "4.18-P2H-REL",
    title: "HOLD release checkpoint",
    verdict: "STAGE_4_18P2H_REL_PASS",
    oneLineSummary: "P2H HOLD archived as stable release checkpoint (suggested tag only).",
    keyConclusion: "Backend HOLD remains active; next runtime only after ETH watch reappears.",
    nextAction: "hold_backend_and_continue_private_operator_ui",
    gateStatus: "HOLD",
    safetyNote: "Docs archive only · git tag not auto-created · Stage 4.19 blocked",
    relatedArtifactIds: ["p2h-qa", "p2h", "p2h-ops"],
  },
  {
    id: "ui-mvp13",
    stage: "UI-MVP-13",
    title: "Private Operator navigation / UX polish",
    verdict: "UI_MVP13_PASS",
    oneLineSummary: "Overview becomes total console; Evidence is report hub; nav regrouped.",
    keyConclusion: "HOLD/BLOCKED/PASS badges consistent; trading routes still absent.",
    nextAction: "Continue Private Operator UX under HOLD",
    gateStatus: "PASS",
    safetyNote: "READ ONLY · no Stage 4.19 start · no trade/order/ARM",
    relatedArtifactIds: ["ui-mvp14", "p2h-rel"],
  },
  {
    id: "ui-mvp14",
    stage: "UI-MVP-14",
    title: "Private Operator deep links / cross navigation",
    verdict: "UI_MVP14_PASS",
    oneLineSummary: "Report / runbook / checkpoint deep links — documentation-only.",
    keyConclusion: "Can navigate Overview → Evidence → Runbook → Gate → Checkpoint without opening /data.",
    nextAction: "Add sanitized one-line excerpts (MVP-15)",
    gateStatus: "PASS",
    safetyNote: "No control buttons · no Run 30m/60m · Stage 4.19 blocked",
    relatedArtifactIds: ["ui-mvp13", "p2h-ops", "p2h-rel"],
  },
];

export const CURRENT_GATE_HIGHLIGHTS = [
  {
    id: "hold",
    title: "Backend HOLD",
    body: "Conditional wait — not a crash. No auto-run.",
  },
  {
    id: "eth",
    title: "ETH watch conditions not reappeared",
    body: "Reappearance gate closed; short regression not justified now.",
  },
  {
    id: "419",
    title: "Stage 4.19 blocked",
    body: "Needs actual non-shadow BTC + ETH graduation — not shadow or packs alone.",
  },
] as const;

export const PAPER_LAB_VALIDATION_SUMMARY = {
  title: "Validation summary",
  bullets: [
    "BTC prior graduation evidence exists",
    "latest regression: no BTC/ETH graduation (latest BTC grad=0)",
    "ETH prompt repair done; runtime validation pending",
    "next_short_regression_allowed_now=false",
  ],
  nextAction: "wait for ETH watch conditions",
  gateStatus: "WAIT" as GateStatusLabel,
  safetyNote: "No paper execution from UI · Stage 4.19 blocked",
};

export const RISK_SAFETY_SUMMARY = {
  title: "Safety summary",
  bullets: [
    "no orders",
    "no ARM",
    "no production",
    "no billing / accounts / API keys",
    "no Stage 4.19",
  ],
  nextAction: "keep HOLD · continue Private Operator read-only",
  gateStatus: "PASS" as GateStatusLabel,
  safetyNote: "READ ONLY · NOT INVESTMENT ADVICE · no control actions",
};

export const PROVIDER_ROUTING_SUMMARY = {
  title: "Routing summary",
  bullets: [
    "BTC Cerebras-first was experiment only",
    "permanent routing change=false",
    "shadow not used for graduation",
    "future routing changes require operator approval",
  ],
  nextAction: "no permanent routing change under HOLD",
  gateStatus: "HOLD" as GateStatusLabel,
  safetyNote: "Routing editor absent · Stage 4.19 blocked",
};

export function getDocSummaries(): DocSummary[] {
  return DOC_SUMMARIES;
}

export function getDocSummaryByStage(stage: string): DocSummary | undefined {
  return DOC_SUMMARIES.find((d) => d.stage === stage);
}

export function getOperatorDocSummaries(): DocSummary[] {
  return DOC_SUMMARIES.filter((d) => d.stage.startsWith("4.18-"));
}
