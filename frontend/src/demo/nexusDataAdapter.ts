/**
 * Read-only NEXUS data adapter.
 * MVP-10: defaults to sanitized P2G/P2H HOLD private_operator_snapshot
 * (prefers P2G over P2F/P2E/…).
 * Never writes backend / trading state. No order / ARM / routing APIs.
 */
import {
  demoEvidence,
  demoFleets,
  demoGraduationStatus,
  demoLatestReports,
  demoMarkets,
  demoMembershipTiers,
  demoPaperLab,
  demoPrivateOperatorMode,
  demoProviderShadow,
  demoProviderStatus,
  demoReflection,
  demoRiskFlags,
  demoRoundTable,
  demoSafetyStatus,
  demoSignals,
  demoStageGateStatus,
  demoSystemStatus,
  DEMO_SOURCE,
} from "./demoNexusData";
import { p2aPrivateOperatorSnapshot } from "./snapshots/p2aPrivateOperatorSnapshot";
import { p2bPrivateOperatorSnapshot } from "./snapshots/p2bPrivateOperatorSnapshot";
import { p2cPrivateOperatorSnapshot } from "./snapshots/p2cPrivateOperatorSnapshot";
import { p2dPrivateOperatorSnapshot } from "./snapshots/p2dPrivateOperatorSnapshot";
import { p2dR1PrivateOperatorSnapshot } from "./snapshots/p2dR1PrivateOperatorSnapshot";
import { p2ePrivateOperatorSnapshot } from "./snapshots/p2ePrivateOperatorSnapshot";
import { p2fPrivateOperatorSnapshot } from "./snapshots/p2fPrivateOperatorSnapshot";
import { p2gPrivateOperatorSnapshot } from "./snapshots/p2gPrivateOperatorSnapshot";
import type {
  EvidenceItem,
  FleetStatus,
  GraduationStatusSummary,
  LatestReportMeta,
  MarketCard,
  MembershipTierInfo,
  PaperLabSummary,
  PrivateOperatorMode,
  ProviderShadowSummary,
  ProviderStatusSummary,
  ReflectionSummary,
  RiskEvidenceFlags,
  RoundTableSummary,
  SafetyStatusSummary,
  SignalRow,
  StageGateStatus,
  SystemStatus,
} from "../types/nexus";
import type {
  BackendHoldStateStatus,
  EthConfirmationTimeline,
  FutureRegressionGateStatus,
  NexusSnapshot,
  NexusUiMode,
  PromptRepairStatus,
  RegressionReadinessStatus,
  ReportIndexItem,
  RuntimeRegressionStatus,
  SnapshotStage419Status,
  WatchReappearanceGateStatus,
} from "../types/nexusSnapshot";

/** Default UI mode for Private Operator Dashboard. */
let currentUiMode: NexusUiMode = "private_operator_snapshot";

/** Prefer P2G/P2H HOLD over P2F/P2E/… when sanitized snapshots are available. */
const ACTIVE_PRIVATE_OPERATOR_SNAPSHOT: NexusSnapshot =
  p2gPrivateOperatorSnapshot ??
  p2fPrivateOperatorSnapshot ??
  p2ePrivateOperatorSnapshot ??
  p2dR1PrivateOperatorSnapshot ??
  p2dPrivateOperatorSnapshot ??
  p2cPrivateOperatorSnapshot ??
  p2bPrivateOperatorSnapshot ??
  p2aPrivateOperatorSnapshot;

export function setNexusUiMode(mode: NexusUiMode): void {
  currentUiMode = mode;
}

export function getCurrentUiMode(): NexusUiMode {
  return currentUiMode;
}

function isSnapshotMode(): boolean {
  return currentUiMode === "private_operator_snapshot";
}

export function getPrivateOperatorSnapshot(): NexusSnapshot {
  return ACTIVE_PRIVATE_OPERATOR_SNAPSHOT;
}

export function getNexusSnapshot(): NexusSnapshot {
  if (isSnapshotMode()) {
    return getPrivateOperatorSnapshot();
  }
  return {
    ...ACTIVE_PRIVATE_OPERATOR_SNAPSHOT,
    source: DEMO_SOURCE,
    uiMode: "demo",
    latestBackendStage: demoStageGateStatus.stageLabel,
    latestVerdict: demoStageGateStatus.verdict,
  };
}

export function getEthConfirmationTimeline(): EthConfirmationTimeline | null {
  const snap = getNexusSnapshot();
  return snap.ethConfirmationTimeline ?? null;
}

export function getPromptRepairStatus(): PromptRepairStatus | null {
  const snap = getNexusSnapshot();
  return snap.promptRepairStatus ?? null;
}

export function getRuntimeRegressionStatus(): RuntimeRegressionStatus | null {
  const snap = getNexusSnapshot();
  return snap.runtimeRegressionStatus ?? null;
}

export function getRegressionReadinessStatus(): RegressionReadinessStatus | null {
  const snap = getNexusSnapshot();
  return snap.regressionReadinessStatus ?? null;
}

export function getWatchReappearanceGateStatus(): WatchReappearanceGateStatus | null {
  const snap = getNexusSnapshot();
  return snap.watchReappearanceGateStatus ?? null;
}

export function getReportIndex(): ReportIndexItem[] {
  const snap = getNexusSnapshot();
  return snap.reportIndex ?? [];
}

export function getBackendHoldStateStatus(): BackendHoldStateStatus | null {
  const snap = getNexusSnapshot();
  return snap.backendHoldStateStatus ?? null;
}

export function getFutureRegressionGateStatus(): FutureRegressionGateStatus | null {
  const snap = getNexusSnapshot();
  return snap.futureRegressionGateStatus ?? null;
}

export function getLatestBackendVerdict(): string {
  if (isSnapshotMode()) {
    return getPrivateOperatorSnapshot().latestVerdict;
  }
  return demoStageGateStatus.verdict;
}

export function getStage419Status(): SnapshotStage419Status {
  const snap = isSnapshotMode() ? getPrivateOperatorSnapshot() : null;
  const ready = false as const;
  const start = false as const;
  return {
    stage419Readiness: ready,
    shouldStart419: start,
    blocked: true,
    reason: snap
      ? snap.ethStatus.note
      : demoGraduationStatus.whyBlocked,
  };
}

export function getSystemStatus(): SystemStatus {
  if (isSnapshotMode()) {
    const s = getPrivateOperatorSnapshot();
    return {
      demo: false,
      source: s.source,
      ...s.systemStatus,
    };
  }
  return demoSystemStatus;
}

export function getStageGateStatus(): StageGateStatus {
  if (isSnapshotMode()) {
    const s = getPrivateOperatorSnapshot();
    const g = s.stageGate;
    return {
      demo: false,
      source: s.source,
      stageLabel: g.stageLabel,
      verdict: g.verdict,
      p2aStatus: g.p2hStatus ?? g.p2gStatus ?? g.p2fStatus ?? g.p2eStatus ?? g.p2dR1Status ?? g.p2dStatus ?? g.p2cStatus ?? g.p2bStatus ?? g.p2aStatus,
      latestGate: g.latestGate,
      note: g.note,
    };
  }
  return demoStageGateStatus;
}

export function getProviderStatus(): ProviderStatusSummary {
  if (isSnapshotMode()) {
    const r = getPrivateOperatorSnapshot().providerRoutingStatus;
    return {
      demo: false,
      source: getPrivateOperatorSnapshot().source,
      actualPrimary: r.actualPrimary,
      shadowPrimary: r.shadowPrimary,
      btcExperimentChain: r.btcExperimentChain,
      ethRoutingUnchanged: r.ethRoutingUnchanged,
      health: r.health,
      note: r.note,
    };
  }
  return demoProviderStatus;
}

export function getLatestReports(): LatestReportMeta[] {
  if (isSnapshotMode()) {
    const s = getPrivateOperatorSnapshot();
    return s.reports.map((r) => ({
      demo: false,
      source: s.source,
      ...r,
    }));
  }
  return demoLatestReports;
}

export function getEvidenceVault(): EvidenceItem[] {
  return demoEvidence;
}

/** Alias for getEvidenceVault — Evidence Vault list. */
export function getEvidence(): EvidenceItem[] {
  return getEvidenceVault();
}

export function getGraduationStatus(): GraduationStatusSummary {
  if (isSnapshotMode()) {
    const s = getPrivateOperatorSnapshot();
    return {
      demo: false,
      source: s.source,
      btcGraduationCount: s.btcStatus.actualGraduationCount,
      ethGraduationCount: s.ethStatus.actualGraduationCount,
      shadowExcludedFromGraduation: true,
      actualOnly: true,
      stage419Readiness: false,
      shouldStart419: false,
      whyBlocked: s.ethStatus.note,
    };
  }
  return demoGraduationStatus;
}

export function getSafetyStatus(): SafetyStatusSummary {
  if (isSnapshotMode()) {
    const s = getPrivateOperatorSnapshot();
    return {
      demo: false,
      source: s.source,
      ...s.safetyStatus,
    };
  }
  return demoSafetyStatus;
}

export function getPrivateOperatorMode(): PrivateOperatorMode {
  if (isSnapshotMode()) {
    const s = getPrivateOperatorSnapshot();
    return {
      demo: false,
      source: s.source,
      enabled: true,
      label: "Private Operator Mode ON",
      audience: "Internal operators / researchers only",
      publicSaas: "Future only / Not implemented / No billing",
      readOnly: true,
    };
  }
  return demoPrivateOperatorMode;
}

export function getMarketOverview(): MarketCard[] {
  return demoMarkets;
}

export function getFleetStatus(): FleetStatus[];
export function getFleetStatus(symbol: string): FleetStatus;
export function getFleetStatus(symbol?: string): FleetStatus | FleetStatus[] {
  if (!symbol) return demoFleets;
  const hit = demoFleets.find((f) => f.symbol.toUpperCase() === symbol.toUpperCase());
  return hit ?? demoFleets[0];
}

export function getSignals(): SignalRow[] {
  return demoSignals;
}

export function getReflectionSummary(): ReflectionSummary {
  return demoReflection;
}

export function getProviderShadowSummary(): ProviderShadowSummary {
  if (isSnapshotMode()) {
    const s = getPrivateOperatorSnapshot();
    const p = s.providerShadowStatus;
    return {
      demo: false,
      source: s.source,
      actualProvider: p.actualProvider,
      shadowProvider: p.shadowProvider,
      divergence: p.divergence,
      comparable: p.comparable,
      notes: p.notes,
      shadowExcludedFromPaper: true,
      shadowExcludedFromCalibration: true,
      shadowExcludedFromGraduation: true,
      mustNotAffectStage419: true,
      p1cSummary: p.p1cSummary,
      p2DesignSummary: p.p2DesignSummary,
      p2r1Summary: p.p2r1Summary,
    };
  }
  return demoProviderShadow;
}

export function getPaperLabSummary(): PaperLabSummary {
  if (isSnapshotMode()) {
    const s = getPrivateOperatorSnapshot();
    const p = s.paperLabStatus;
    return {
      demo: false,
      source: s.source,
      wouldEnterCount: p.wouldEnterCount,
      wouldSkipCount: p.wouldSkipCount,
      watchlistCount: p.watchlistCount,
      calibrationStatus: p.calibrationStatus,
      graduationStatus: p.graduationStatus,
      btcGraduationCount: p.btcGraduationCount,
      ethGraduationCount: p.ethGraduationCount,
      stage419Blocked: true,
      whyNotGraduated: p.whyNotGraduated,
      paperLoggerStatus: p.paperLoggerStatus,
    };
  }
  return demoPaperLab;
}

export function getMembershipTiers(): MembershipTierInfo[] {
  return demoMembershipTiers;
}

export function getRoundTable(): RoundTableSummary {
  return demoRoundTable;
}

export function getRiskEvidenceFlags(): RiskEvidenceFlags {
  if (isSnapshotMode()) {
    const s = getPrivateOperatorSnapshot();
    const safety = s.safetyStatus;
    const grad = getGraduationStatus();
    return {
      demo: false,
      source: s.source,
      orderAllowed: false,
      mock: false,
      arm: false,
      production: false,
      paperExecution: false,
      stage419Readiness: false,
      shouldStart419: false,
      validatorStatus: "PASS (sanitized snapshot)",
      calibrationStatus: `actual-only · BTC=${grad.btcGraduationCount} ETH=${grad.ethGraduationCount}`,
      graduationStatus: `BTC=${grad.btcGraduationCount} ETH=${grad.ethGraduationCount} · Stage 4.19 blocked`,
      providerHealth: s.providerRoutingStatus.health,
      resetStatus: "experiment flags not persisted as permanent routing",
      safetyLogSummary: safety.summary,
    };
  }
  return demoRiskFlags;
}
