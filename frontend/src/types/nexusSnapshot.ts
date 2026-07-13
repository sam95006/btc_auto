/**
 * NEXUS Private Operator snapshot schema — MVP-2 / MVP-3 / MVP-4 / MVP-5.
 * Read-only sanitized research summaries only. No secrets, no /data raw paths.
 */

export type NexusUiMode = "demo" | "private_operator_snapshot";

export interface SnapshotSystemStatus {
  mode: string;
  safetyLine: string;
  stageReadiness: string;
  currentGate: string;
  lastUpdate: string;
  disclaimer: string;
}

export interface SnapshotSafetyStatus {
  orderAllowed: false;
  arm: false;
  production: false;
  stage419Readiness: false;
  shouldStart419: false;
  privateOperatorMode: true;
  defensiveOn: true;
  summary: string;
}

export interface SnapshotStageGate {
  stageLabel: string;
  verdict: string;
  p2aStatus: string;
  p2bStatus?: string;
  p2cStatus?: string;
  p2dStatus?: string;
  latestGate: string;
  note: string;
}

export interface SnapshotSymbolStatus {
  symbol: string;
  actualValidWatchCount: number;
  actualGraduationCount: number;
  rootCause?: string;
  confirmationFailureReason?: string;
  ethDetail?: string;
  statusLabel: string;
  note: string;
}

export interface SnapshotProviderRoutingStatus {
  actualPrimary: string;
  shadowPrimary: string;
  btcExperimentChain: string;
  ethRoutingUnchanged: true;
  routingPermanentChangeSupported: false;
  btcCerebrasFirstExperimentSupported?: boolean;
  health: string;
  note: string;
}

export interface SnapshotProviderShadowStatus {
  actualProvider: string;
  shadowProvider: string;
  divergence: string;
  comparable: boolean;
  notes: string;
  shadowExcludedFromPaper: true;
  shadowExcludedFromCalibration: true;
  shadowExcludedFromGraduation: true;
  mustNotAffectStage419: true;
  p1cSummary: string;
  p2DesignSummary: string;
  p2r1Summary: string;
  p2bSummary?: string;
  p2cSummary?: string;
  p2dSummary?: string;
  actualOnlyGraduation: true;
}

export interface SnapshotPaperLabStatus {
  wouldEnterCount: number;
  wouldSkipCount: number;
  watchlistCount: number;
  calibrationStatus: string;
  graduationStatus: string;
  btcGraduationCount: number;
  ethGraduationCount: number;
  btcPassed: boolean;
  ethBlocked: boolean;
  stage419Blocked: true;
  whyNotGraduated: string;
  paperLoggerStatus: string;
  nextDiagnostic: string;
}

export interface SnapshotReportMeta {
  id: string;
  title: string;
  stageMarker: string;
  verdict: string;
  path: string;
  updatedAt: string;
}

export interface SnapshotStage419Status {
  stage419Readiness: false;
  shouldStart419: false;
  blocked: true;
  reason: string;
}

/** ETH watch → follow-up confirmation timeline (P2B sanitized). */
export interface EthConfirmationTick {
  label: string;
  provider: string;
  intent: string;
  confidence: number;
  directionalBias: string;
  candidateSide: string;
  entryTrigger: string;
  invalidation: string;
  mae: string;
  invalidationBreached: false;
  maeBreached: false;
}

export interface EthMarketContextDelta {
  priceChangePct: number;
  regimeBefore: string;
  regimeAfter: string;
  trendStrengthBefore: number;
  trendStrengthAfter: number;
  dataQualityBefore: string;
  dataQualityAfter: string;
}

export interface EthConfirmationTimeline {
  symbol: string;
  confirmationFailed: true;
  failureReason: string;
  ethDetail: string;
  invalidationBreached: false;
  maeBreached: false;
  confirmationFailureIsMarketValid: false;
  confirmationFailureIsSystemIssue: true;
  marketContextDelta?: EthMarketContextDelta;
  watch: EthConfirmationTick;
  followup: EthConfirmationTick;
  conclusion: string;
  nextStep: string;
  recoveryRecommendation: string;
}

/** P2D prompt repair status (static review; awaiting runtime regression). */
export interface PromptRepairStatus {
  promptRepairAdded: boolean;
  previousWatchContextInjected: boolean;
  entryTriggerRecheckRequired: boolean;
  invalidationRecheckRequired: boolean;
  maeRecheckRequired: boolean;
  contextContinuityCheckRequired: boolean;
  directionCollapseGuardAdded: boolean;
  confidenceCollapseReasonRequired: boolean;
  staticExpectedFollowupBehavior: string;
  wouldPreventUnexplainedCollapse: boolean;
  needsNextRuntimeRegression: boolean;
  nextStep: string;
}

/** Canonical Private Operator / demo fixture shape for MVP-2 … MVP-5 wiring. */
export interface NexusSnapshot {
  source: string;
  uiMode: NexusUiMode;
  systemStatus: SnapshotSystemStatus;
  safetyStatus: SnapshotSafetyStatus;
  stageGate: SnapshotStageGate;
  latestBackendStage: string;
  latestVerdict: string;
  btcStatus: SnapshotSymbolStatus;
  ethStatus: SnapshotSymbolStatus;
  providerRoutingStatus: SnapshotProviderRoutingStatus;
  providerShadowStatus: SnapshotProviderShadowStatus;
  paperLabStatus: SnapshotPaperLabStatus;
  ethConfirmationTimeline?: EthConfirmationTimeline;
  promptRepairStatus?: PromptRepairStatus;
  reports: SnapshotReportMeta[];
}
