/**
 * Sanitized static doc summaries for Private Operator (MVP-15 / MVP-16).
 * READ ONLY · NOT INVESTMENT ADVICE · excerpts only · no raw /data · no secrets · no control actions
 * Search/filter is local metadata only — no backend calls.
 */

export type GateStatusLabel =
  | "HOLD"
  | "WAIT"
  | "PASS"
  | "PARTIAL"
  | "BLOCKED"
  | "READY";

export type DocCategory =
  | "backend-gate"
  | "prompt-repair"
  | "runtime-regression"
  | "no-watch-diagnostics"
  | "release-checkpoint"
  | "ui"
  | "safety"
  | "routing";

export type ChecklistRefId =
  | "eth-watch-reappearance"
  | "short-regression-approval"
  | "stage-419-dossier"
  | "safety-invariants";

export type ChecklistRef = {
  id: ChecklistRefId;
  label: string;
  href: string;
  description: string;
};

/** Documentation-only anchors for runbook / gate checklist lines. */
export const CHECKLIST_REFS: Record<ChecklistRefId, ChecklistRef> = {
  "eth-watch-reappearance": {
    id: "eth-watch-reappearance",
    label: "ETH watch reappearance checklist",
    href: "/overview#checklist-eth-watch-reappearance",
    description: "Conditions for ETH watch / valid_watch to reappear",
  },
  "short-regression-approval": {
    id: "short-regression-approval",
    label: "Short regression approval checklist",
    href: "/overview#checklist-short-regression-approval",
    description: "Manual approval gates before any short regression",
  },
  "stage-419-dossier": {
    id: "stage-419-dossier",
    label: "Stage 4.19 dossier checklist",
    href: "/overview#checklist-stage-419-dossier",
    description: "Actual BTC+ETH graduation required — dossier not started",
  },
  "safety-invariants": {
    id: "safety-invariants",
    label: "Safety invariants checklist",
    href: "/risk#checklist-safety-invariants",
    description: "No orders / ARM / production / billing / Stage 4.19",
  },
};

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
  category: DocCategory;
  tags: string[];
  checklistRefs: ChecklistRefId[];
  unresolvedGate: boolean;
  operatorPriority: number;
};

const T = {
  HOLD: "HOLD",
  ETH: "ETH",
  BTC: "BTC",
  STAGE419: "Stage 4.19",
  NO60: "no 60m",
  NO_RUNTIME: "no runtime",
  PROMPT: "prompt repair",
  REL: "release checkpoint",
  RO: "read-only",
} as const;

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
    category: "prompt-repair",
    tags: [T.PROMPT, T.ETH, T.STAGE419, T.NO60, T.RO],
    checklistRefs: ["eth-watch-reappearance"],
    unresolvedGate: false,
    operatorPriority: 40,
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
    category: "runtime-regression",
    tags: [T.ETH, T.PROMPT, T.NO60, T.STAGE419, T.RO],
    checklistRefs: ["eth-watch-reappearance"],
    unresolvedGate: true,
    operatorPriority: 25,
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
    category: "no-watch-diagnostics",
    tags: [T.ETH, "P2E", T.NO60, T.STAGE419, T.RO],
    checklistRefs: ["eth-watch-reappearance"],
    unresolvedGate: false,
    operatorPriority: 35,
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
    category: "backend-gate",
    tags: [T.ETH, "ETH watch", T.HOLD, T.NO60, T.STAGE419, T.RO],
    checklistRefs: ["eth-watch-reappearance", "short-regression-approval"],
    unresolvedGate: true,
    operatorPriority: 10,
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
    category: "backend-gate",
    tags: [T.BTC, T.ETH, T.HOLD, T.NO60, T.STAGE419, T.RO],
    checklistRefs: ["short-regression-approval", "stage-419-dossier"],
    unresolvedGate: true,
    operatorPriority: 15,
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
    category: "backend-gate",
    tags: [T.HOLD, T.ETH, T.NO_RUNTIME, T.STAGE419, T.RO],
    checklistRefs: ["eth-watch-reappearance", "short-regression-approval"],
    unresolvedGate: true,
    operatorPriority: 5,
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
    category: "backend-gate",
    tags: [T.HOLD, T.NO_RUNTIME, T.STAGE419, T.RO, "P2H-OPS"],
    checklistRefs: ["short-regression-approval"],
    unresolvedGate: false,
    operatorPriority: 20,
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
    category: "safety",
    tags: [T.REL, T.HOLD, T.STAGE419, T.NO_RUNTIME, T.RO],
    checklistRefs: ["safety-invariants"],
    unresolvedGate: false,
    operatorPriority: 30,
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
    category: "release-checkpoint",
    tags: [T.REL, T.HOLD, T.STAGE419, T.ETH, T.RO],
    checklistRefs: ["stage-419-dossier"],
    unresolvedGate: false,
    operatorPriority: 18,
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
    category: "ui",
    tags: [T.RO, T.HOLD, T.STAGE419],
    checklistRefs: [],
    unresolvedGate: false,
    operatorPriority: 90,
  },
  {
    id: "ui-mvp14",
    stage: "UI-MVP-14",
    title: "Private Operator deep links / cross navigation",
    verdict: "UI_MVP14_PASS",
    oneLineSummary: "Report / runbook / checkpoint deep links — documentation-only.",
    keyConclusion:
      "Can navigate Overview → Evidence → Runbook → Gate → Checkpoint without opening /data.",
    nextAction: "Add sanitized one-line excerpts (MVP-15)",
    gateStatus: "PASS",
    safetyNote: "No control buttons · no Run 30m/60m · Stage 4.19 blocked",
    relatedArtifactIds: ["ui-mvp13", "p2h-ops", "p2h-rel"],
    category: "ui",
    tags: [T.RO, T.HOLD, T.STAGE419],
    checklistRefs: [],
    unresolvedGate: false,
    operatorPriority: 88,
  },
  {
    id: "ui-mvp15",
    stage: "UI-MVP-15",
    title: "Static doc summary viewer / sanitized excerpts",
    verdict: "UI_MVP15_PASS",
    oneLineSummary: "One-line summary / conclusion / next action without opening full reports.",
    keyConclusion: "Operators can glance gate posture from static metadata only.",
    nextAction: "Add static search/filter + checklist links (MVP-16)",
    gateStatus: "PASS",
    safetyNote: "READ ONLY · no /data raw · Stage 4.19 blocked",
    relatedArtifactIds: ["ui-mvp14", "p2h-rel"],
    category: "ui",
    tags: [T.RO, T.HOLD, T.REL, T.STAGE419],
    checklistRefs: [],
    unresolvedGate: false,
    operatorPriority: 85,
  },
];

export const DOC_CATEGORIES: DocCategory[] = [
  "backend-gate",
  "prompt-repair",
  "runtime-regression",
  "no-watch-diagnostics",
  "release-checkpoint",
  "ui",
  "safety",
  "routing",
];

export const GATE_STATUS_OPTIONS: GateStatusLabel[] = [
  "HOLD",
  "WAIT",
  "PASS",
  "PARTIAL",
  "BLOCKED",
  "READY",
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

export const UNRESOLVED_GATE_SNAPSHOT = {
  title: "Top unresolved gate",
  currentUnresolved: "ETH watch conditions not reappeared",
  regressionNow: false,
  sixtyM: false,
  stage419: "blocked",
  nextAction: "wait for ETH watch conditions",
} as const;

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

export type DocSummaryFilterState = {
  query: string;
  category: DocCategory | "";
  gateStatus: GateStatusLabel | "";
  unresolvedOnly: boolean;
};

export const EMPTY_DOC_SUMMARY_FILTER: DocSummaryFilterState = {
  query: "",
  category: "",
  gateStatus: "",
  unresolvedOnly: false,
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

export function getChecklistRefs(ids: ChecklistRefId[]): ChecklistRef[] {
  return ids.map((id) => CHECKLIST_REFS[id]).filter(Boolean);
}

function haystack(s: DocSummary): string {
  return [
    s.id,
    s.stage,
    s.title,
    s.verdict,
    s.oneLineSummary,
    s.keyConclusion,
    s.nextAction,
    s.gateStatus,
    s.safetyNote,
    s.category,
    ...s.tags,
  ]
    .join(" ")
    .toLowerCase();
}

/** Local sanitized-metadata filter — no backend, no /data. */
export function filterDocSummaries(
  summaries: DocSummary[],
  filter: DocSummaryFilterState,
): DocSummary[] {
  const q = filter.query.trim().toLowerCase();
  return summaries
    .filter((s) => {
      if (filter.category && s.category !== filter.category) return false;
      if (filter.gateStatus && s.gateStatus !== filter.gateStatus) return false;
      if (filter.unresolvedOnly && !s.unresolvedGate) return false;
      if (q && !haystack(s).includes(q)) return false;
      return true;
    })
    .sort((a, b) => a.operatorPriority - b.operatorPriority);
}
