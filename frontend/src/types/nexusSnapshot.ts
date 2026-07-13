/**
 * NEXUS Private Operator snapshot schema — MVP-2.
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
  latestGate: string;
  note: string;
}

export interface SnapshotSymbolStatus {
  symbol: string;
  actualValidWatchCount: number;
  actualGraduationCount: number;
  rootCause?: string;
  statusLabel: string;
  note: string;
}

export interface SnapshotProviderRoutingStatus {
  actualPrimary: string;
  shadowPrimary: string;
  btcExperimentChain: string;
  ethRoutingUnchanged: true;
  routingPermanentChangeSupported: false;
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

/** Canonical Private Operator / demo fixture shape for MVP-2 wiring. */
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
  reports: SnapshotReportMeta[];
}
