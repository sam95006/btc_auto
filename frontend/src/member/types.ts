/**
 * Public Member Platform Decision Integrity types (fixture / DEMO mode).
 * No private strategy, order, position, or Lesson Memory fields.
 */

export type FreshnessState = "FRESH" | "STALE" | "DEGRADED" | "UNAVAILABLE" | "DEMO";

export type DecisionPosture =
  | "INITIATE"
  | "HOLD"
  | "REDUCE"
  | "STAND_ASIDE"
  | "MONITOR";

export type EvidencePolarity = "SUPPORTING" | "CONTRADICTING" | "NEUTRAL";

export type ThesisStatus =
  | "ACTIVE"
  | "WATCH"
  | "INVALIDATED"
  | "SUPERSEDED"
  | "CLOSED";

export type OutcomeClass =
  | "PROCESS_OK_OUTCOME_OK"
  | "PROCESS_OK_OUTCOME_BAD"
  | "PROCESS_WEAK_OUTCOME_OK"
  | "PROCESS_WEAK_OUTCOME_BAD"
  | "PENDING";

export interface PublicEvidenceItem {
  id: string;
  title: string;
  source: string;
  asOf: string;
  polarity: EvidencePolarity;
  summary: string;
  freshness: FreshnessState;
}

export interface RiskCondition {
  id: string;
  label: string;
  severity: "LOW" | "MEDIUM" | "HIGH";
  status: "OPEN" | "TRIGGERED" | "CLEARED";
  note: string;
}

export interface ThesisMonitorItem {
  id: string;
  decisionId: string;
  thesis: string;
  status: ThesisStatus;
  invalidation: string;
  lastChecked: string;
  driftNote: string;
}

export interface PublicDecisionSummary {
  id: string;
  symbol: string;
  title: string;
  posture: DecisionPosture;
  thesis: string;
  confidenceLabel: string;
  updatedAt: string;
  freshness: FreshnessState;
  evidenceCount: number;
  counterEvidenceCount: number;
  riskOpenCount: number;
}

export interface PublicDecisionDetail extends PublicDecisionSummary {
  contextNote: string;
  humanRationale: string;
  aiChallenge: string;
  evidence: PublicEvidenceItem[];
  counterEvidence: PublicEvidenceItem[];
  risks: RiskCondition[];
  outcomeClass: OutcomeClass;
  reviewNote: string | null;
}

export interface MemberAlert {
  id: string;
  kind: "THESIS" | "RISK" | "FRESHNESS" | "OUTCOME";
  title: string;
  body: string;
  decisionId?: string;
  createdAt: string;
  severity: "INFO" | "WARN" | "HIGH";
}

export interface MarketOverviewCard {
  id: string;
  label: string;
  value: string;
  hint: string;
  freshness: FreshnessState;
}

export interface MembershipTierPublic {
  id: string;
  name: string;
  blurb: string;
  entitlements: string[];
  billingNote: string;
}
