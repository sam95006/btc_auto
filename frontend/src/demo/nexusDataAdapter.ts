/**
 * Read-only NEXUS data adapter.
 * MVP-1 Private Operator Dashboard returns demo data only.
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
} from "./demoNexusData";
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

export function getSystemStatus(): SystemStatus {
  return demoSystemStatus;
}

export function getStageGateStatus(): StageGateStatus {
  return demoStageGateStatus;
}

export function getProviderStatus(): ProviderStatusSummary {
  return demoProviderStatus;
}

export function getLatestReports(): LatestReportMeta[] {
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
  return demoGraduationStatus;
}

export function getSafetyStatus(): SafetyStatusSummary {
  return demoSafetyStatus;
}

export function getPrivateOperatorMode(): PrivateOperatorMode {
  return demoPrivateOperatorMode;
}

export function getMarketOverview(): MarketCard[] {
  return demoMarkets;
}

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
  return demoProviderShadow;
}

export function getPaperLabSummary(): PaperLabSummary {
  return demoPaperLab;
}

export function getMembershipTiers(): MembershipTierInfo[] {
  return demoMembershipTiers;
}

export function getRoundTable(): RoundTableSummary {
  return demoRoundTable;
}

export function getRiskEvidenceFlags(): RiskEvidenceFlags {
  return demoRiskFlags;
}
