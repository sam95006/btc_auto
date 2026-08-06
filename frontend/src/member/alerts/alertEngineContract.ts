/**
 * PUB18 Alert Engine — shared read-only contract mirror (web).
 * Keep kinds/fields aligned with backend.nexus_pub18_alert_engine.constants.
 */

export const PUB18_ALERT_ENGINE_SCHEMA = "pub18_alert_engine_readonly_contract_v1";

export const PUB18_ALERT_KINDS = [
  "OPPORTUNITY_READY",
  "POSTURE_CHANGE",
  "DATA_TRUST_DEGRADED",
  "REGIME_TRANSITION",
  "INVALIDATION",
  "SHADOW_CLOSED",
  "PROVIDER_DEGRADED",
  "MARKET_ANOMALY",
  "MAJOR_RISK",
] as const;

export type Pub18AlertKind = (typeof PUB18_ALERT_KINDS)[number];

export const PUB18_ALERT_KIND_LABELS: Record<Pub18AlertKind, string> = {
  OPPORTUNITY_READY: "Opportunity READY",
  POSTURE_CHANGE: "Posture change",
  DATA_TRUST_DEGRADED: "Data Trust degraded",
  REGIME_TRANSITION: "Regime transition",
  INVALIDATION: "Invalidation",
  SHADOW_CLOSED: "Shadow closed",
  PROVIDER_DEGRADED: "Provider degraded",
  MARKET_ANOMALY: "Market anomaly",
  MAJOR_RISK: "Major risk",
};

/** Required envelope fields shared with mobile. */
export const PUB18_ALERT_REQUIRED_FIELDS = [
  "kind",
  "source",
  "as_of",
  "freshness",
  "data_class",
  "decision_id",
  "reason",
  "severity",
  "public_safe",
] as const;

export type Pub18AlertSeverity = "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export type Pub18AlertFreshness =
  | "FRESH"
  | "STALE"
  | "DEGRADED"
  | "UNAVAILABLE"
  | "DEMO_DATA"
  | "FIXTURE";

export type Pub18AlertDataClass =
  | "LIVE_READ_ONLY"
  | "STALE"
  | "UNAVAILABLE"
  | "FIXTURE"
  | "DEMO_DATA"
  | "PROVIDER_REQUIRED";

export interface Pub18AlertEnvelope {
  alert_id: string;
  kind: Pub18AlertKind;
  source: string;
  as_of: string;
  freshness: Pub18AlertFreshness;
  data_class: Pub18AlertDataClass;
  decision_id: string | null;
  reason: string;
  severity: Pub18AlertSeverity;
  public_safe: true;
  title: string;
  body: string;
  label: string;
  schema?: string;
  schema_version?: string;
  read_only: true;
  actionable_trade: false;
}

/** Banned hype phrases — alerts must never claim execution or guaranteed outcomes. */
export const PUB18_ALERT_HYPE_PHRASES = [
  "already ordered",
  "order already filled",
  "filled for you",
  "guaranteed profit",
  "guaranteed return",
  "guaranteed wins",
  "risk-free",
  "risk free",
  "sure win",
  "sure profit",
  "must buy",
  "must sell",
  "buy now",
  "sell now",
  "trade now",
  "copy trade now",
  "auto-execute",
  "auto execute",
  "locked in profit",
  "profit locked",
  "you are in profit",
  "position opened",
  "order placed",
] as const;

export function containsPub18AlertHype(text: string): string | null {
  const lower = text.toLowerCase();
  for (const phrase of PUB18_ALERT_HYPE_PHRASES) {
    if (lower.includes(phrase)) return phrase;
  }
  return null;
}
