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
  p2dR1Status?: string;
  p2eStatus?: string;
  p2fStatus?: string;
  p2gStatus?: string;
  p2hStatus?: string;
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
  p2dR1Summary?: string;
  p2eSummary?: string;
  p2fSummary?: string;
  p2gSummary?: string;
  p2hSummary?: string;
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
  /** MVP-10 operator clarity fields (optional on older snapshots). */
  btcPriorGraduationEvidenceExists?: boolean;
  latestBtcRegressionGraduation?: number;
  ethPromptRepairDone?: boolean;
  ethRuntimeValidationPending?: boolean;
  nextShortRegressionAllowedNow?: false;
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

/** P2D-R1 runtime regression status (sample insufficient for ETH repair validation). */
export interface RuntimeRegressionStatus {
  technicalValid: true;
  tickCount: number;
  effectiveDecisionCount: number;
  parseErrorCount: number;
  promptRepairRuntimePresent: true;
  previousWatchContextSeen: false;
  directionCollapseGuardSeen: false;
  ethValidWatchCount: number;
  ethFollowupCasesCount: number;
  ethGraduationCount: number;
  ethConfirmationPromptRepairEffective: false;
  sampleInsufficientReason: string;
  btcValidWatchCount: number;
  btcValidWatchNote: string;
  btcGraduationCount: number;
  actualNonShadowBtcEthGraduationMet: false;
  stage419Blocked: true;
  nextStep: string;
}

/** P2E / P2F regression readiness (do not run soak unless ETH watch reappears). */
export interface RegressionReadinessStatus {
  readiness: false;
  reason: string;
  noWatchRootCause: string;
  promptRepairOverConservativeSuspected: false;
  needsPromptAdjustment: false;
  shouldRun60m: false;
  waitHelperFixed: true;
  ethWatchConditionsPresent: false;
  stage419Blocked: true;
  nextGate: string;
  nextRecommendation: string;
}

/** P2F ETH watch reappearance gate checklist. */
export interface WatchReappearanceGateStatus {
  regressionReadiness: false;
  doNotRunRegressionNow: true;
  operatorApprovedShortRegressionMayBeJustified: false;
  conditions: {
    hasEthWatchOrValidWatch: false;
    hasLongBuyBias: false;
    confidenceNearReference: false;
    entryTriggerPresent: false;
    invalidationPresent: false;
    maeCapPassed: false;
    contextQualityOk: true;
    regimeNotUnknown: true;
  };
  shouldRun60m: false;
  waitHelperRobustnessStatus: "PASS";
  stage419Blocked: true;
  nextRecommendation: string;
}

export interface ReportIndexItem {
  stage: string;
  verdict: string;
  oneLineConclusion: string;
  reportPath: string;
  nextAction: string;
}

/** P2G/P2H backend hold posture for Private Operator. */
export interface BackendHoldStateStatus {
  state: "HOLD";
  reason: string;
  nextAllowedAction: string;
  shouldRun30mNow: false;
  shouldRun60m: false;
  stage419Blocked: true;
  routingPermanentChangeSupported: false;
  nextShortRegressionAllowedNow: false;
}

/** Passive future checker display — manual only / no auto-run. */
export interface FutureRegressionGateStatus {
  mode: "manual_only";
  autoRun: false;
  ethWatchConditionsReappeared: false;
  operatorMayApproveShortRegression: false;
  shouldRun30mNow: false;
  shouldRun60m: false;
  stage419Blocked: true;
  nextRecommendation: string;
}

/** Canonical Private Operator / demo fixture shape for MVP-2 … MVP-9 wiring. */
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
  runtimeRegressionStatus?: RuntimeRegressionStatus;
  regressionReadinessStatus?: RegressionReadinessStatus;
  watchReappearanceGateStatus?: WatchReappearanceGateStatus;
  backendHoldStateStatus?: BackendHoldStateStatus;
  futureRegressionGateStatus?: FutureRegressionGateStatus;
  reportIndex?: ReportIndexItem[];
  reports: SnapshotReportMeta[];
}
