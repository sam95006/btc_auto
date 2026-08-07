/**
 * NEXUS Live Market Ranking — public-safe discovery contract (V18.2.14).
 *
 * Ranking is DISCOVERY only. It must NOT alter eligibility, Risk Gate,
 * strategy qualification, or private execution.
 *
 * Prefer reusing opportunityScore / confirmationScore / riskScore (+ OI/funding/activity).
 * nex_rank_score_v1 is a deterministic, versioned, explainable display score.
 */

import type { CandidateSide, CandidateStage, MarketCandidate, ScannerEvent } from "./scannerApi";
import { partitionOpportunityCandidates } from "./cryptoOpportunityFilter";

export const NEX_RANK_SCORE_VERSION = "nex_rank_score_v1" as const;

/** Ranking universe must not hardcode BTC/ETH/SOL — keep at 0 forever. */
export const FIXED_SYMBOL_DEPENDENCY_COUNT = 0 as const;

export type RankEventKind = "NEW" | "UP" | "DOWN" | "UNCHANGED" | "OUT";

export type LiveRankingRow = {
  symbol: string;
  rank: number;
  previous_rank: number | null;
  rank_delta: number | null;
  rank_event: RankEventKind;
  rank_score: number;
  rank_score_version: typeof NEX_RANK_SCORE_VERSION;
  rank_score_components: {
    opportunity: number;
    confirmation: number;
    risk: number;
    activity: number;
    oi: number;
    funding: number;
  };
  stage: CandidateStage;
  side_bias: CandidateSide;
  price: number | null | undefined;
  change_24h: number | null | undefined;
  volume_24h: number | null | undefined;
  activity_state: string;
  activity_metric: number | null;
  oi_change: number | null | undefined;
  funding_rate: number | null | undefined;
  risk_score: number;
  data_trust: string;
  freshness: string;
  primary_reason: string;
  secondary_reason: string;
  entered_rank_at: number | null;
  last_rank_update: number;
  qualified: boolean;
  candidate_id: string;
};

export type LiveRankEvent = {
  id: string;
  symbol: string;
  rank_event: RankEventKind;
  rank: number | null;
  previous_rank: number | null;
  primary_reason: string;
  market_change: string;
  timestamp: number;
};

export type LiveRankingSnapshot = {
  updated_at: number;
  universe_size: number;
  active_count: number;
  qualified_count: number;
  rows: LiveRankingRow[];
  radar: LiveRankingRow[];
  qualified: LiveRankingRow[];
  events: LiveRankEvent[];
  fixed_symbol_dependency_count: typeof FIXED_SYMBOL_DEPENDENCY_COUNT;
};

const HISTORY_KEY = "nexus.live_rank.history.v1";
const PREV_KEY = "nexus.live_rank.prev.v1";
const MAX_HISTORY = 200;

type StoredPrev = Record<
  string,
  { rank: number; score: number; stage: string; entered_at: number; ts: number }
>;

function clamp(n: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, n));
}

/**
 * nex_rank_score_v1 — deterministic public display score.
 * Mirrors scanner rankScore weights; does not feed Risk Gate / eligibility.
 */
export function computeNexRankScoreV1(c: MarketCandidate): {
  score: number;
  components: LiveRankingRow["rank_score_components"];
} {
  const opportunity = Number(c.opportunityScore ?? 0);
  const confirmation = Number(c.confirmationScore ?? 0);
  const risk = Number(c.riskScore ?? 0);
  const activity = clamp(Math.abs(Number(c.priceChange5mPct ?? 0)) * 8 + Number(c.turnoverPace ?? 0) * 0.02, 0, 40);
  const oi = clamp(Math.abs(Number(c.oiChange5mPct ?? 0)) * 6, 0, 30);
  const funding = clamp(Math.abs(Number(c.fundingRate ?? 0)) * 10000, 0, 20);

  // Primary weights match backend rankScore; activity/OI/funding are explainability additives only.
  let score = opportunity * 0.45 + confirmation * 0.4 - risk * 0.25 + activity * 0.08 + oi * 0.06 + funding * 0.03;
  if (c.side === "NEUTRAL") score -= 20;
  if (c.stage === "OVEREXTENDED" || c.stage === "EXPIRED" || c.stage === "COOLING") score -= 8;
  if (c.collecting || c.stage === "INSUFFICIENT_DATA") score -= 25;

  return {
    score: Math.round(score * 100) / 100,
    components: {
      opportunity,
      confirmation,
      risk,
      activity: Math.round(activity * 10) / 10,
      oi: Math.round(oi * 10) / 10,
      funding: Math.round(funding * 10) / 10,
    },
  };
}

export function deriveRankEvent(
  rank: number | null,
  previousRank: number | null | undefined,
  stillActive: boolean,
): RankEventKind {
  if (!stillActive && previousRank != null) return "OUT";
  if (rank == null) return previousRank != null ? "OUT" : "UNCHANGED";
  if (previousRank == null) return "NEW";
  if (rank < previousRank) return "UP";
  if (rank > previousRank) return "DOWN";
  return "UNCHANGED";
}

function isRadarStage(stage: CandidateStage): boolean {
  return (
    stage === "WATCHING" ||
    stage === "BUILDING" ||
    stage === "AWAITING_CONFIRMATION" ||
    stage === "CONFIRMED" ||
    stage === "OVEREXTENDED" ||
    stage === "COOLING"
  );
}

/** True eligibility only — never inflate with radar watch states. */
export function isQualifiedCandidate(c: MarketCandidate): boolean {
  return c.stage === "CONFIRMED" && c.side !== "NEUTRAL" && !c.collecting;
}

function activityState(c: MarketCandidate): string {
  if (c.collecting || c.stage === "INSUFFICIENT_DATA") return "WARMING";
  const pace = Number(c.turnoverPace ?? 0);
  const px = Math.abs(Number(c.priceChange5mPct ?? 0));
  if (pace >= 50 || px >= 1.5) return "HOT";
  if (pace >= 15 || px >= 0.4) return "ACTIVE";
  return "QUIET";
}

function loadPrev(): StoredPrev {
  try {
    const raw = localStorage.getItem(PREV_KEY);
    if (!raw) return {};
    return JSON.parse(raw) as StoredPrev;
  } catch {
    return {};
  }
}

function savePrev(prev: StoredPrev) {
  try {
    localStorage.setItem(PREV_KEY, JSON.stringify(prev));
  } catch {
    /* ignore */
  }
}

export function loadRankHistory(): LiveRankEvent[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw) as LiveRankEvent[];
    return Array.isArray(arr) ? arr.slice(0, MAX_HISTORY) : [];
  } catch {
    return [];
  }
}

function appendHistory(events: LiveRankEvent[]) {
  if (!events.length) return;
  try {
    const prev = loadRankHistory();
    const ids = new Set(prev.map((e) => e.id));
    const merged = [...events.filter((e) => !ids.has(e.id)), ...prev].slice(0, MAX_HISTORY);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(merged));
  } catch {
    /* ignore */
  }
}

export function rankHistoryForSymbol(symbol: string): LiveRankEvent[] {
  const sym = symbol.toUpperCase();
  return loadRankHistory().filter((e) => e.symbol === sym);
}

export type RankingTab = "ALL" | "LONG" | "SHORT" | "MOVE" | "OI" | "ACTIVITY" | "RISK";

export function filterRankingRows(rows: LiveRankingRow[], tab: RankingTab): LiveRankingRow[] {
  switch (tab) {
    case "LONG":
      return rows.filter((r) => r.side_bias === "LONG");
    case "SHORT":
      return rows.filter((r) => r.side_bias === "SHORT");
    case "MOVE":
      return [...rows]
        .filter((r) => r.rank_event === "NEW" || r.rank_event === "UP" || r.rank_event === "DOWN" || r.rank_event === "OUT")
        .sort((a, b) => Math.abs(b.rank_delta ?? 0) - Math.abs(a.rank_delta ?? 0));
    case "OI":
      return [...rows].sort((a, b) => Math.abs(b.oi_change ?? 0) - Math.abs(a.oi_change ?? 0));
    case "ACTIVITY":
      return [...rows].sort((a, b) => (b.activity_metric ?? 0) - (a.activity_metric ?? 0));
    case "RISK":
      return [...rows].sort((a, b) => (b.risk_score ?? 0) - (a.risk_score ?? 0));
    default:
      return rows;
  }
}

/**
 * Build continuous full-market ranking from scanner candidates.
 * No fixed BTC/ETH/SOL universe — any supported crypto instrument may enter.
 */
export function buildLiveRanking(
  candidates: MarketCandidate[],
  opts?: { now?: number; persist?: boolean },
): LiveRankingSnapshot {
  const now = opts?.now ?? Date.now();
  const persist = opts?.persist !== false;
  const { crypto } = partitionOpportunityCandidates(candidates);

  const pool = crypto.filter((c) => isRadarStage(c.stage) || isQualifiedCandidate(c));

  const scored = pool.map((c) => {
    const { score, components } = computeNexRankScoreV1(c);
    return { c, score, components };
  });

  // Stable tie-break: score desc, then symbol asc — prevents equal-score flicker.
  scored.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    return a.c.symbol.localeCompare(b.c.symbol);
  });

  const prevMap = typeof localStorage !== "undefined" ? loadPrev() : {};
  const nextPrev: StoredPrev = {};
  const newEvents: LiveRankEvent[] = [];

  const rows: LiveRankingRow[] = scored.map(({ c, score, components }, idx) => {
    const rank = idx + 1;
    const key = c.symbol.toUpperCase();
    const prev = prevMap[key];
    const previous_rank = prev?.rank ?? (typeof c.previousRank === "number" ? c.previousRank : null);
    const rank_event = deriveRankEvent(rank, previous_rank, true);
    const rank_delta =
      previous_rank != null ? previous_rank - rank : c.rankDelta != null ? c.rankDelta : null;
    const entered_rank_at = prev?.entered_at ?? (rank_event === "NEW" ? now : c.firstSeenAt ?? now);
    const qualified = isQualifiedCandidate(c);
    const activity_metric =
      c.priceChange5mPct == null && c.turnoverPace == null
        ? null
        : Math.round((Math.abs(Number(c.priceChange5mPct ?? 0)) * 10 + Number(c.turnoverPace ?? 0) * 0.05) * 10) /
          10;

    nextPrev[key] = { rank, score, stage: c.stage, entered_at: entered_rank_at, ts: now };

    if (rank_event !== "UNCHANGED") {
      const change =
        c.change24hPct != null
          ? `24h ${c.change24hPct > 0 ? "+" : ""}${c.change24hPct.toFixed(2)}%`
          : c.priceChange5mPct != null
            ? `5m ${c.priceChange5mPct > 0 ? "+" : ""}${c.priceChange5mPct.toFixed(2)}%`
            : "—";
      newEvents.push({
        id: `${key}:${rank_event}:${rank}:${Math.floor(now / 1000)}`,
        symbol: key,
        rank_event,
        rank,
        previous_rank,
        primary_reason: c.reasons?.[0] || `${rank_event} · #${rank}`,
        market_change: change,
        timestamp: now,
      });
    }

    return {
      symbol: key,
      rank,
      previous_rank,
      rank_delta,
      rank_event,
      rank_score: score,
      rank_score_version: NEX_RANK_SCORE_VERSION,
      rank_score_components: components,
      stage: c.stage,
      side_bias: c.side,
      price: c.currentPrice ?? c.markPrice,
      change_24h: c.change24hPct,
      volume_24h: (c as MarketCandidate & { volume24h?: number }).volume24h ?? null,
      activity_state: activityState(c),
      activity_metric,
      oi_change: c.oiChange5mPct,
      funding_rate: c.fundingRate,
      risk_score: c.riskScore,
      data_trust: String(c.freshness || "UNKNOWN"),
      freshness: c.freshness,
      primary_reason: c.reasons?.[0] || "結構觀察中",
      secondary_reason: c.reasons?.[1] || c.conflicts?.[0] || "",
      entered_rank_at,
      last_rank_update: c.lastUpdatedAt || now,
      qualified,
      candidate_id: c.id,
    };
  });

  // OUT events for symbols that left the ranking.
  for (const [sym, prev] of Object.entries(prevMap)) {
    if (!nextPrev[sym]) {
      newEvents.push({
        id: `${sym}:OUT:${prev.rank}:${Math.floor(now / 1000)}`,
        symbol: sym,
        rank_event: "OUT",
        rank: null,
        previous_rank: prev.rank,
        primary_reason: "離開 Live Radar",
        market_change: "—",
        timestamp: now,
      });
    }
  }

  if (persist && typeof localStorage !== "undefined") {
    savePrev(nextPrev);
    appendHistory(newEvents);
  }

  const qualified = rows.filter((r) => r.qualified);
  // Radar = discovery states; qualified counted separately (may be 0).
  const radar = rows.filter((r) => !r.qualified || isRadarStage(r.stage));

  return {
    updated_at: now,
    universe_size: crypto.length,
    active_count: rows.length,
    qualified_count: qualified.length,
    rows,
    radar,
    qualified,
    events: newEvents,
    fixed_symbol_dependency_count: FIXED_SYMBOL_DEPENDENCY_COUNT,
  };
}

/** Merge scanner API events that already express ranking movement. */
export function rankingEventsFromScanner(events: ScannerEvent[]): LiveRankEvent[] {
  const out: LiveRankEvent[] = [];
  for (const e of events) {
    const type = String(e.type || "").toUpperCase();
    let kind: RankEventKind | null = null;
    if (type.includes("RANK_UP") || type === "NEW_TOP_CANDIDATE") kind = type.includes("NEW") ? "NEW" : "UP";
    else if (type.includes("RANK_DOWN")) kind = "DOWN";
    else if (type.includes("RANK_OUT") || type.includes("EXPIRED")) kind = "OUT";
    if (!kind) continue;
    out.push({
      id: e.id,
      symbol: e.symbol.toUpperCase(),
      rank_event: kind,
      rank: e.rank ?? null,
      previous_rank: null,
      primary_reason: e.explanation,
      market_change: e.stage || "—",
      timestamp: e.timestamp,
    });
  }
  return out;
}

export function countRankEvents(events: LiveRankEvent[]) {
  const counts = { NEW: 0, UP: 0, DOWN: 0, UNCHANGED: 0, OUT: 0 };
  for (const e of events) counts[e.rank_event] += 1;
  return counts;
}

export function formatRankMove(row: Pick<LiveRankingRow, "rank" | "rank_event" | "rank_delta">): string {
  if (row.rank_event === "NEW") return `NEW → #${row.rank}`;
  if (row.rank_event === "OUT") return "OUT";
  if (row.rank_event === "UP" && row.rank_delta != null) return `#${row.rank} ↑${row.rank_delta}`;
  if (row.rank_event === "DOWN" && row.rank_delta != null) return `#${row.rank} ↓${Math.abs(row.rank_delta)}`;
  return `#${row.rank}`;
}
