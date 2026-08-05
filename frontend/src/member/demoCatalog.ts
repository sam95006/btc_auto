/**
 * DEMO DATA - READ ONLY - NOT INVESTMENT ADVICE
 * Public Member Platform fixtures only. demo: true on every record.
 * No live fabrications - UI must show DEMO DATA when this catalog is bound.
 */

import type {
  MemberAlert,
  MarketOverviewCard,
  MembershipTierPublic,
  PublicDecisionDetail,
  ThesisMonitorItem,
} from "./types";

export const MEMBER_DEMO_BANNER =
  "DEMO DATA · READ ONLY · NOT INVESTMENT ADVICE · NO LIVE TRADING · LOCAL/STAGING ONLY";

const AS_OF = "2026-08-05T12:00:00Z";

export const marketOverviewCards: Array<MarketOverviewCard & { demo: true }> = [
  {
    id: "mkt-btc",
    label: "BTC context",
    value: "WATCH · elevated volatility regime label",
    hint: "Public context snapshot · not an order signal",
    freshness: "DEMO",
    demo: true,
  },
  {
    id: "mkt-eth",
    label: "ETH context",
    value: "HOLD posture majority in feed",
    hint: "Aggregated Decision posture labels only",
    freshness: "DEMO",
    demo: true,
  },
  {
    id: "mkt-fresh",
    label: "Feed freshness",
    value: "DEMO",
    hint: "Fixture mode - not LIVE lineage",
    freshness: "DEMO",
    demo: true,
  },
  {
    id: "mkt-avail",
    label: "System availability",
    value: "STAGING_OK",
    hint: "Local/staging Member shell",
    freshness: "DEMO",
    demo: true,
  },
];

export const decisions: Array<PublicDecisionDetail & { demo: true }> = [
  {
    id: "dec-btc-001",
    symbol: "BTC",
    title: "BTC · stand aside into unknown catalyst window",
    posture: "STAND_ASIDE",
    thesis:
      "If funding stays elevated and spot lag persists, initiative long quality degrades until invalidation clears.",
    confidenceLabel: "MEDIUM · dual-calibration pending",
    updatedAt: AS_OF,
    freshness: "DEMO",
    evidenceCount: 2,
    counterEvidenceCount: 1,
    riskOpenCount: 2,
    contextNote:
      "Context Snapshot (demo): BTCUSDT public marks, funding label elevated, completeness DEMO.",
    humanRationale:
      "Prefer recording stand-aside over forcing an initiate posture without fresher contradicting evidence.",
    aiChallenge:
      "Challenge: standing aside may miss mean-reversion; require explicit time-stop and review commitment.",
    evidence: [
      {
        id: "ev-1",
        title: "Funding elevated vs 30d median (demo label)",
        source: "public_market_summary",
        asOf: AS_OF,
        polarity: "SUPPORTING",
        summary: "Supports caution on initiative long quality.",
        freshness: "DEMO",
      },
      {
        id: "ev-2",
        title: "Spot/perp basis unstable (demo label)",
        source: "public_basis_summary",
        asOf: AS_OF,
        polarity: "SUPPORTING",
        summary: "Adds uncertainty to context package.",
        freshness: "DEMO",
      },
    ],
    counterEvidence: [
      {
        id: "cev-1",
        title: "Short-term momentum still constructive (demo)",
        source: "public_momentum_summary",
        asOf: AS_OF,
        polarity: "CONTRADICTING",
        summary: "Argues against premature stand-aside if horizon is very short.",
        freshness: "DEMO",
      },
    ],
    risks: [
      {
        id: "risk-1",
        label: "Invalidation: funding normalizes without spot confirmation",
        severity: "MEDIUM",
        status: "OPEN",
        note: "Advisory user-owned condition · not an exchange stop.",
      },
      {
        id: "risk-2",
        label: "Time-stop: 72h without thesis update",
        severity: "LOW",
        status: "OPEN",
        note: "Thesis Integrity Monitor candidate.",
      },
    ],
    outcomeClass: "PENDING",
    reviewNote: null,
    demo: true,
  },
  {
    id: "dec-eth-002",
    symbol: "ETH",
    title: "ETH · hold thesis while monitoring liquidity stress",
    posture: "HOLD",
    thesis:
      "Existing hold remains valid while liquidations stay contained and evidence freshness is acceptable.",
    confidenceLabel: "LOW-MEDIUM",
    updatedAt: AS_OF,
    freshness: "DEMO",
    evidenceCount: 1,
    counterEvidenceCount: 2,
    riskOpenCount: 1,
    contextNote: "Context Snapshot (demo): ETHUSDT · DEMO completeness.",
    humanRationale: "No new initiate; keep recorded hold and watch invalidation.",
    aiChallenge: "Ask whether hold is inertia vs evidence-backed.",
    evidence: [
      {
        id: "ev-3",
        title: "No fresh liquidation cascade label (demo)",
        source: "public_liq_summary",
        asOf: AS_OF,
        polarity: "SUPPORTING",
        summary: "Supports continued hold monitoring.",
        freshness: "DEMO",
      },
    ],
    counterEvidence: [
      {
        id: "cev-2",
        title: "Breadth deterioration across alts (demo)",
        source: "public_breadth_summary",
        asOf: AS_OF,
        polarity: "CONTRADICTING",
        summary: "Weakens hold confidence.",
        freshness: "DEMO",
      },
      {
        id: "cev-3",
        title: "Narrative catalyst unresolved (demo)",
        source: "public_news_summary",
        asOf: AS_OF,
        polarity: "CONTRADICTING",
        summary: "Raises uncertainty for review.",
        freshness: "DEMO",
      },
    ],
    risks: [
      {
        id: "risk-3",
        label: "Invalidation: ETH underperforms BTC by demo threshold",
        severity: "HIGH",
        status: "OPEN",
        note: "Monitor only · user records outcome.",
      },
    ],
    outcomeClass: "PENDING",
    reviewNote: null,
    demo: true,
  },
  {
    id: "dec-sol-003",
    symbol: "SOL",
    title: "SOL · closed loop with Outcome Review",
    posture: "REDUCE",
    thesis: "Reduce exposure posture after contradicting evidence clustered.",
    confidenceLabel: "CALIBRATED (demo)",
    updatedAt: AS_OF,
    freshness: "DEMO",
    evidenceCount: 1,
    counterEvidenceCount: 1,
    riskOpenCount: 0,
    contextNote: "Historical demo Decision for Outcome Review practice.",
    humanRationale: "Reduce recorded after invalidation proximity.",
    aiChallenge: "Was reduce early or late vs counterfactual marks?",
    evidence: [
      {
        id: "ev-4",
        title: "Invalidation proximity tag (demo)",
        source: "thesis_monitor",
        asOf: AS_OF,
        polarity: "SUPPORTING",
        summary: "Supported reduce posture record.",
        freshness: "DEMO",
      },
    ],
    counterEvidence: [
      {
        id: "cev-4",
        title: "Bounce after reduce timestamp (demo mark)",
        source: "public_mark",
        asOf: AS_OF,
        polarity: "CONTRADICTING",
        summary: "Counterfactual for calibration - not private fills.",
        freshness: "DEMO",
      },
    ],
    risks: [],
    outcomeClass: "PROCESS_OK_OUTCOME_BAD",
    reviewNote:
      "Process acceptable; outcome unfavorable. Keep Decision Graph lesson public-side only.",
    demo: true,
  },
];

export const thesisMonitors: Array<ThesisMonitorItem & { demo: true }> = decisions.map(
  (d) => ({
    id: `tm-${d.id}`,
    decisionId: d.id,
    thesis: d.thesis,
    status: d.outcomeClass === "PENDING" ? "ACTIVE" : "CLOSED",
    invalidation: d.risks[0]?.label ?? "No open invalidation",
    lastChecked: AS_OF,
    driftNote: d.counterEvidenceCount > 0 ? "Counter-evidence present" : "Stable",
    demo: true,
  }),
);

export const alerts: Array<MemberAlert & { demo: true }> = [
  {
    id: "al-1",
    kind: "THESIS",
    title: "Thesis watch · BTC stand-aside",
    body: "Time-stop approaching · update thesis or close loop.",
    decisionId: "dec-btc-001",
    createdAt: AS_OF,
    severity: "WARN",
    demo: true,
  },
  {
    id: "al-2",
    kind: "RISK",
    title: "Risk condition open · ETH relative underperformance",
    body: "Advisory invalidation still OPEN.",
    decisionId: "dec-eth-002",
    createdAt: AS_OF,
    severity: "HIGH",
    demo: true,
  },
  {
    id: "al-3",
    kind: "OUTCOME",
    title: "Outcome Review due · SOL reduce",
    body: "Complete calibration notes for closed Decision.",
    decisionId: "dec-sol-003",
    createdAt: AS_OF,
    severity: "INFO",
    demo: true,
  },
  {
    id: "al-4",
    kind: "FRESHNESS",
    title: "Feed freshness · DEMO mode",
    body: "Values bound to DEMO DATA catalog - not LIVE lineage.",
    createdAt: AS_OF,
    severity: "INFO",
    demo: true,
  },
];

export const membershipTiers: Array<MembershipTierPublic & { demo: true }> = [
  {
    id: "free",
    name: "Free Preview",
    blurb: "Decision Feed read + Outcome Review practice.",
    entitlements: ["Home", "Market Overview", "Decision Feed (limited)", "NEX AI (limited)"],
    billingNote: "NO LIVE BILLING · UNVALIDATED_HYPOTHESIS",
    demo: true,
  },
  {
    id: "pro",
    name: "Pro",
    blurb: "Thesis Monitor + Counter Evidence depth.",
    entitlements: ["Full Decision Detail", "Thesis Monitor", "Alerts", "Decision Memory"],
    billingNote: "NO LIVE BILLING · architecture label only",
    demo: true,
  },
  {
    id: "elite",
    name: "Elite",
    blurb: "Concierge-ready Decision Integrity workflows.",
    entitlements: ["Outcome Review workflows", "Priority NEX AI challenge prompts"],
    billingNote: "NO LIVE BILLING · not a production SKU",
    demo: true,
  },
  {
    id: "enterprise",
    name: "Enterprise",
    blurb: "Team roles / org entitlements (foundation later).",
    entitlements: ["Org roles (future)", "Export stubs (future)"],
    billingNote: "NO LIVE BILLING · no production customer DB",
    demo: true,
  },
];

export function getDecision(id: string): (PublicDecisionDetail & { demo: true }) | undefined {
  return decisions.find((d) => d.id === id);
}

export function allEvidence() {
  return decisions.flatMap((d) =>
    d.evidence.map((e) => ({ ...e, decisionId: d.id, demo: true as const })),
  );
}

export function allCounterEvidence() {
  return decisions.flatMap((d) =>
    d.counterEvidence.map((e) => ({ ...e, decisionId: d.id, demo: true as const })),
  );
}

export function allRisks() {
  return decisions.flatMap((d) =>
    d.risks.map((r) => ({ ...r, decisionId: d.id, symbol: d.symbol, demo: true as const })),
  );
}
