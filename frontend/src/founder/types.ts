/** PUB-E / PUB2-D / UX-C Founder Private Operator UI types — Founder-only, never member-bound. */

export type FounderPanelId =
  | "capture"
  | "provider"
  | "decision"
  | "execution_sim"
  | "risk"
  | "ledger"
  | "checkpoint"
  | "reflection"
  | "lesson"
  | "qualification"
  | "storage"
  | "kill_switch";

export type FounderDiagnosticsPanelId =
  | "error_ontology_histogram"
  | "repeated_error_signatures"
  | "counterfactual_deltas"
  | "regime_transitions"
  | "strategy_router_weights"
  | "lesson_pipeline"
  | "calibration_abstention"
  | "provider_health"
  | "data_trust"
  | "portfolio_risk"
  | "memory_graph_health"
  | "v16_module_versions";

export type FounderPanelBinding = {
  mode: "LIVE" | "SIMULATED" | "UNAVAILABLE" | string;
  sourceSurface: string;
  sourceEndpoint?: string;
  sourceField?: string;
  asOf: string;
  retrievedAt: string;
  lineageId: string;
  fabricated: boolean;
  demoData?: boolean;
};

export type FounderOperatorPanel = {
  id: FounderPanelId | FounderDiagnosticsPanelId | string;
  title: string;
  health: string;
  summary: string;
  metrics: Record<string, unknown>;
  notes: string[];
  readOnly: boolean;
  exchangeWriteEnabled: boolean;
  memberVisible: boolean;
  researchOnly?: boolean;
  binding?: FounderPanelBinding;
};

export type FounderOperatorSnapshot = {
  schema: string;
  ok: boolean;
  founderOnly: boolean;
  memberAccessible: boolean;
  researchOnly: boolean;
  realExecutionEnabled: boolean;
  armEnabled: boolean;
  exchangeWriteEnabled: boolean;
  generatedAt: string;
  actor: { tier: string; identitySource: string };
  panels: FounderOperatorPanel[];
  panelIds: string[];
  hardBans: string[];
  note: string;
  liveBinding?: boolean;
  bindings?: {
    panelCount: number;
    liveCount: number;
    simulatedCount: number;
    unavailableCount: number;
    fabricatedLiveValueCount: number;
    memberAccessibleBindingCount: number;
  };
  error?: string;
};

export type FounderDiagnosticsSnapshot = {
  schema: string;
  ok: boolean;
  lane?: string;
  laneName?: string;
  founderOnly: boolean;
  memberAccessible: boolean;
  researchOnly: boolean;
  observeOnly?: boolean;
  authorizeResearchOnly?: boolean;
  realExecutionEnabled: boolean;
  armEnabled: boolean;
  exchangeWriteEnabled: boolean;
  mainnetShortcut?: boolean;
  realTradeShortcut?: boolean;
  statusJsonReport?: boolean;
  generatedAt: string;
  actor: { tier: string; identitySource: string };
  panels: FounderOperatorPanel[];
  panelIds: string[];
  hardBans: string[];
  note: string;
  error?: string;
};

export type ResearchAuthorizeResult = {
  ok: boolean;
  authorized: boolean;
  scope: string;
  error?: string;
  researchOnly?: boolean;
  realExecutionEnabled?: boolean;
  exchangeWriteEnabled?: boolean;
  mainnetShortcut?: boolean;
  realTradeShortcut?: boolean;
  founderOnly?: boolean;
  memberAccessible?: boolean;
  allowedScopes?: string[];
  note?: string;
};

export type FounderStatus = {
  ok: boolean;
  founderOnly?: boolean;
  memberAccessible?: boolean;
  operatorUiEnabled?: boolean;
  tier?: string;
  identitySource?: string;
  realExecutionEnabled?: boolean;
  error?: string;
};

export const FOUNDER_OPERATOR_NAV: { id: FounderPanelId; label: string; hash: string }[] = [
  { id: "capture", label: "Capture", hash: "#capture" },
  { id: "provider", label: "V2.3", hash: "#provider" },
  { id: "decision", label: "Decision", hash: "#decision" },
  { id: "execution_sim", label: "Execution Sim", hash: "#execution_sim" },
  { id: "risk", label: "Risk", hash: "#risk" },
  { id: "ledger", label: "Ledger", hash: "#ledger" },
  { id: "checkpoint", label: "Checkpoint", hash: "#checkpoint" },
  { id: "reflection", label: "Reflection", hash: "#reflection" },
  { id: "lesson", label: "Lesson", hash: "#lesson" },
  { id: "qualification", label: "Qualification", hash: "#qualification" },
  { id: "storage", label: "Storage", hash: "#storage" },
  { id: "kill_switch", label: "Kill-Switch", hash: "#kill_switch" },
];

export const FOUNDER_DIAGNOSTICS_NAV: {
  id: FounderDiagnosticsPanelId;
  label: string;
  hash: string;
}[] = [
  { id: "error_ontology_histogram", label: "Error Ontology", hash: "#error_ontology_histogram" },
  { id: "repeated_error_signatures", label: "Repeat Signatures", hash: "#repeated_error_signatures" },
  { id: "counterfactual_deltas", label: "Counterfactual", hash: "#counterfactual_deltas" },
  { id: "regime_transitions", label: "Regime", hash: "#regime_transitions" },
  { id: "strategy_router_weights", label: "Router Weights", hash: "#strategy_router_weights" },
  { id: "lesson_pipeline", label: "Lesson Pipeline", hash: "#lesson_pipeline" },
  { id: "calibration_abstention", label: "Abstention", hash: "#calibration_abstention" },
  { id: "provider_health", label: "Provider", hash: "#provider_health" },
  { id: "data_trust", label: "Data Trust", hash: "#data_trust" },
  { id: "portfolio_risk", label: "Portfolio Risk", hash: "#portfolio_risk" },
  { id: "memory_graph_health", label: "Memory Graph", hash: "#memory_graph_health" },
  { id: "v16_module_versions", label: "V16 Versions", hash: "#v16_module_versions" },
];
