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

export type FounderLiveOpsPanelId =
  | "adapter_health"
  | "ingest_rate_lag"
  | "partition_health"
  | "universe_funnel"
  | "data_trust_distribution"
  | "regime_distribution"
  | "strategy_distribution"
  | "uncertainty_distribution"
  | "shadow_decision_states"
  | "repeated_error_signatures"
  | "ai_provider_health"
  | "fallback_rate"
  | "token_budget_telemetry"
  | "disk_quota"
  | "pipeline_pause_resume"
  | "emergency_read_only_stop";

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
  id: FounderPanelId | FounderDiagnosticsPanelId | FounderLiveOpsPanelId | string;
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

export type FounderLiveOpsSnapshot = {
  schema: string;
  ok: boolean;
  lane?: string;
  laneName?: string;
  founderOnly: boolean;
  memberAccessible: boolean;
  researchOnly: boolean;
  observeOnly?: boolean;
  realExecutionEnabled: boolean;
  armEnabled: boolean;
  exchangeWriteEnabled: boolean;
  mainnetShortcut?: boolean;
  realTradeShortcut?: boolean;
  generatedAt: string;
  actor: { tier: string; identitySource: string };
  panels: FounderOperatorPanel[];
  panelIds: string[];
  allowedControls: string[];
  bannedControls: string[];
  banned_control_count: number;
  hardBans: string[];
  opsState?: Record<string, unknown>;
  note: string;
  error?: string;
};

export type FounderLiveOpsControlResult = {
  ok: boolean;
  applied: boolean;
  control: string;
  error?: string;
  banned?: boolean;
  exchangeWriteEnabled?: boolean;
  mainnetShortcut?: boolean;
  realExecutionEnabled?: boolean;
  founderOnly?: boolean;
  memberAccessible?: boolean;
  banned_control_count?: number;
  opsState?: Record<string, unknown>;
  evidenceExport?: Record<string, unknown>;
  allowedControls?: string[];
  note?: string;
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

export type FounderFieldProvenance = {
  value: unknown;
  source_timestamp: string | null;
  freshness_sec: number | null;
  lane: string | null;
  provenance: string;
};

/** V18.2.28 Founder-only real demo monitor (members inaccessible). */
export type FounderDemoMonitorSnapshot = {
  schema: string;
  ok: boolean;
  lane?: string;
  laneName?: string;
  founderOnly: boolean;
  memberAccessible: boolean;
  mainnet?: boolean;
  real_money?: boolean;
  member_execution?: number;
  feed_ready: boolean;
  feed_status: string;
  feed_source?: string | null;
  feed_source_stale?: string | null;
  fixture_removed?: boolean;
  fixture_used?: boolean;
  position_state?: "FLAT" | "OPEN" | string;
  source_timestamp?: string | null;
  generatedAt: string;
  actor?: { tier: string; identitySource: string };
  demo_uid_masked: string | null;
  lane_label: "PNL_BEARING_RESEARCH" | "EXECUTION_CANARY" | string | null;
  thesis?: Record<string, unknown> | null;
  field_provenance?: Record<string, FounderFieldProvenance>;
  wallet: {
    equity: number | null;
    wallet_balance: number | null;
    available_balance: number | null;
    delta: number | null;
    settle_coin: string | null;
    demo_account_type: string | null;
  };
  active_position: {
    open: boolean;
    state?: "FLAT" | "OPEN" | string;
    symbol: string | null;
    side: string | null;
    notional: number | null;
    entry: number | null;
    current: number | null;
    stop: number | null;
    target: number | null;
    initial_target?: number | null;
    dynamic_profit_zone?: Record<string, unknown> | null;
    unrealized_pnl: number | null;
    expected_net_target: number | null;
    expected_time_to_target: string | null;
    strategy_horizon: string | null;
    hold_duration: string | null;
    mfe: number | null;
    mae: number | null;
    estimated_net_if_closed?: number | null;
  };
  mfe: number | null;
  mae: number | null;
  trading_intel?: {
    side: string | null;
    position_state: "FLAT" | "OPEN" | string;
    entry: number | null;
    current: number | null;
    stop_loss: number | null;
    initial_target: number | null;
    dynamic_profit_zone: Record<string, unknown> | null;
    unrealized_pnl: number | null;
    estimated_net_if_closed: number | null;
    mfe: number | null;
    mae: number | null;
    mfe_capture_estimate: number | null;
    remaining_net_edge: number | null;
    continuation_score: number | null;
    giveback_risk: number | null;
    ai_thesis: unknown;
    last_ai_position_review: unknown;
    last_exit_reason: string | null;
  };
  performance?: {
    win_rate_long: number | null;
    win_rate_short: number | null;
    win_rate_aggregate: number | null;
    net_pnl: number | null;
    profit_factor: number | null;
  };
  learning?: {
    mistake_signatures: unknown[];
    pending_candidate_lessons: unknown[];
  };
  accounting: {
    last_exit_reason: string | null;
    exchange_closed_pnl: number | null;
    fees: number | null;
    calculated_net: number | null;
    wallet_delta: number | null;
    wallet_reconciliation_status: string | null;
    process_class?: string | null;
    pnl_provenance?: string | null;
  };
  display: {
    live_position: boolean;
    wallet: boolean;
    MFE_MAE: boolean;
    accounting_visible: boolean;
    trading_intel_visible?: boolean;
    performance_visible?: boolean;
    learning_visible?: boolean;
  };
  note?: string;
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

export const FOUNDER_LIVE_OPS_NAV: {
  id: FounderLiveOpsPanelId;
  label: string;
  hash: string;
}[] = [
  { id: "adapter_health", label: "Adapters", hash: "#adapter_health" },
  { id: "ingest_rate_lag", label: "Ingest", hash: "#ingest_rate_lag" },
  { id: "partition_health", label: "Partitions", hash: "#partition_health" },
  { id: "universe_funnel", label: "Universe", hash: "#universe_funnel" },
  { id: "data_trust_distribution", label: "Data Trust", hash: "#data_trust_distribution" },
  { id: "regime_distribution", label: "Regime Dist", hash: "#regime_distribution" },
  { id: "strategy_distribution", label: "Strategy Dist", hash: "#strategy_distribution" },
  { id: "uncertainty_distribution", label: "Uncertainty", hash: "#uncertainty_distribution" },
  { id: "shadow_decision_states", label: "Shadow States", hash: "#shadow_decision_states" },
  { id: "repeated_error_signatures", label: "Error Sigs", hash: "#repeated_error_signatures" },
  { id: "ai_provider_health", label: "AI Providers", hash: "#ai_provider_health" },
  { id: "fallback_rate", label: "Fallback", hash: "#fallback_rate" },
  { id: "token_budget_telemetry", label: "Tokens", hash: "#token_budget_telemetry" },
  { id: "disk_quota", label: "Disk", hash: "#disk_quota" },
  { id: "pipeline_pause_resume", label: "Pause/Resume", hash: "#pipeline_pause_resume" },
  { id: "emergency_read_only_stop", label: "Emergency RO", hash: "#emergency_read_only_stop" },
];
