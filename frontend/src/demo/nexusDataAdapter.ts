/**
 * Read-only NEXUS data adapter.
 * MVP-0 returns demo data only. Never writes backend / trading state.
 */
import {
  demoEvidence,
  demoFleets,
  demoMarkets,
  demoMembershipTiers,
  demoPaperLab,
  demoProviderShadow,
  demoReflection,
  demoRiskFlags,
  demoRoundTable,
  demoSignals,
  demoSystemStatus,
} from "./demoNexusData";
import type {
  EvidenceItem,
  FleetStatus,
  MarketCard,
  MembershipTierInfo,
  PaperLabSummary,
  ProviderShadowSummary,
  ReflectionSummary,
  RiskEvidenceFlags,
  RoundTableSummary,
  SignalRow,
  SystemStatus,
} from "../types/nexus";

export function getSystemStatus(): SystemStatus {
  return demoSystemStatus;
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

export function getEvidence(): EvidenceItem[] {
  return demoEvidence;
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
