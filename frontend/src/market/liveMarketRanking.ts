/**
 * NEXUS Live Market Ranking — public-safe discovery contract (V18.2.15).
 *
 * Pipeline: Scanner universe → data ready enough → RADAR_ELIGIBLE → Live Radar
 * ranking → Trade eligibility → QUALIFIED.
 *
 * RADAR_ELIGIBILITY_CONTRACT_V1 is separate from SCANNER_VISIBILITY and
 * TRADE_ELIGIBILITY. Ranking must NOT alter Risk Gate / private execution.
 */

import type { CandidateSide, CandidateStage, MarketCandidate, ScannerEvent } from "./scannerApi";
import { partitionOpportunityCandidates } from "./cryptoOpportunityFilter";

export const NEX_RANK_SCORE_VERSION = "nex_rank_score_v1" as const;
export const RADAR_ELIGIBILITY_CONTRACT = "RADAR_ELIGIBILITY_CONTRACT_V1" as const;

/** Ranking universe must not hardcode BTC/ETH/SOL — keep at 0 forever. */
export const FIXED_SYMBOL_DEPENDENCY_COUNT = 0 as const;

/** Adjacent-swap hysteresis on normalized 0–100 display score (points). */
export const RANK_HYSTERESIS_SCORE = 2.5 as const;

/**
 * Theoretical raw bounds for nex_rank_score_v1 (component ranges documented):
 * opportunity/confirmation/risk ∈ [0,100]; activity ∈ [0,40]; oi ∈ [0,30]; funding ∈ [0,20];
 * penalties: NEUTRAL −20, stage −8, collecting/insufficient −25.
 */
export const NEX_RANK_RAW_MIN = -78 as const;
export const NEX_RANK_RAW_MAX = 90.6 as const;

export type RankEventKind = "NEW" | "UP" | "DOWN" | "UNCHANGED" | "OUT";

export type LiveRankingRow = {
  symbol: string;
  rank: number;
  previous_rank: number | null;
  rank_delta: number | null;
  rank_event: RankEventKind;
  /** Public 0–100 normalized display score (nex_rank_score_v1). */
  rank_score: number;
  /** Signed raw internal score before normalization. */
  rank_score_raw: number;
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
  price_change_1m: number | null | undefined;
  price_change_5m: number | null | undefined;
  price_change_15m: number | null | undefined;
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
  radar_eligible: boolean;
  trade_eligible: boolean;
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
  scanner_visible_count: number;
  radar_eligible_count: number;
  trade_eligible_count: number;
  active_count: number;
  qualified_count: number;
  rows: LiveRankingRow[];
  radar: LiveRankingRow[];
  closest_watch: LiveRankingRow[];
  qualified: LiveRankingRow[];
  events: LiveRankEvent[];
  fixed_symbol_dependency_count: typeof FIXED_SYMBOL_DEPENDENCY_COUNT;
  radar_eligibility_contract: typeof RADAR_ELIGIBILITY_CONTRACT;
  rank_score_semantics: "normalized_0_100_nex_rank_score_v1";
  rank_persistence: "localStorage_prev_v1_hysteresis" | "server_jsonl_prev_v1_hysteresis";
};

const HISTORY_KEY = "nexus.live_rank.history.v1";
const PREV_KEY = "nexus.live_rank.prev.v1";
const MAX_HISTORY = 200;
const CLOSEST_WATCH_MAX = 5;

type StoredPrev = Record<
  string,
  { rank: number; score: number; stage: string; entered_at: number; ts: number; confirm: number }
>;

function clamp(n: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, n));
}

function freshnessCode(c: MarketCandidate): string {
  return String(c.freshness || "").toUpperCase();
}

/** SCANNER_VISIBILITY — all partitioned crypto candidates (warming included). */
export function isScannerVisible(c: MarketCandidate): boolean {
  return Boolean(c?.symbol);
}

/**
 * RADAR_ELIGIBILITY_CONTRACT_V1
 * Default NOT eligible: INSUFFICIENT_DATA, EXPIRED, STALE, UNAVAILABLE.
 * WARMING alone is NOT a rank reason — needs enough metrics.
 */
export function isRadarEligible(c: MarketCandidate): boolean {
  const stage = c.stage;
  if (stage === "INSUFFICIENT_DATA" || stage === "EXPIRED") return false;
  const fresh = freshnessCode(c);
  if (fresh === "STALE" || fresh === "UNAVAILABLE") return false;

  const radarStage =
    stage === "WATCHING" ||
    stage === "BUILDING" ||
    stage === "AWAITING_CONFIRMATION" ||
    stage === "CONFIRMED" ||
    stage === "OVEREXTENDED" ||
    stage === "COOLING";
  if (!radarStage) return false;

  // Collecting / warming: only enter radar when enough metrics exist.
  const warming = Boolean(c.collecting) || stage === "WATCHING";
  const metricHits = countReadyMetrics(c);
  if (warming && metricHits < 3) return false;
  if (metricHits < 2) return false;
  return true;
}

/** TRADE_ELIGIBILITY — confirmed + directional + not collecting. */
export function isTradeEligible(c: MarketCandidate): boolean {
  return c.stage === "CONFIRMED" && c.side !== "NEUTRAL" && !c.collecting;
}

/** @deprecated alias — use isTradeEligible */
export function isQualifiedCandidate(c: MarketCandidate): boolean {
  return isTradeEligible(c);
}

function countReadyMetrics(c: MarketCandidate): number {
  let n = 0;
  if (c.currentPrice != null || c.markPrice != null) n += 1;
  if (c.change24hPct != null && Number.isFinite(c.change24hPct)) n += 1;
  if (c.priceChange5mPct != null && Number.isFinite(c.priceChange5mPct)) n += 1;
  if (c.oiChange5mPct != null && Number.isFinite(c.oiChange5mPct)) n += 1;
  if (c.fundingRate != null && Number.isFinite(c.fundingRate)) n += 1;
  if (c.turnoverPace != null && Number.isFinite(c.turnoverPace)) n += 1;
  if (c.opportunityScore != null && c.opportunityScore > 0) n += 1;
  if (c.confirmationScore != null && c.confirmationScore > 0) n += 1;
  return n;
}

/**
 * nex_rank_score_v1 — deterministic public display score (0–100).
 * Raw signed score kept for explainability; display uses linear map of theoretical bounds.
 */
export function computeNexRankScoreV1(c: MarketCandidate): {
  score: number;
  raw: number;
  components: LiveRankingRow["rank_score_components"];
} {
  const opportunity = Number(c.opportunityScore ?? 0);
  const confirmation = Number(c.confirmationScore ?? 0);
  const risk = Number(c.riskScore ?? 0);
  const activity = clamp(Math.abs(Number(c.priceChange5mPct ?? 0)) * 8 + Number(c.turnoverPace ?? 0) * 0.02, 0, 40);
  const oi = clamp(Math.abs(Number(c.oiChange5mPct ?? 0)) * 6, 0, 30);
  const funding = clamp(Math.abs(Number(c.fundingRate ?? 0)) * 10000, 0, 20);

  let raw = opportunity * 0.45 + confirmation * 0.4 - risk * 0.25 + activity * 0.08 + oi * 0.06 + funding * 0.03;
  if (c.side === "NEUTRAL") raw -= 20;
  if (c.stage === "OVEREXTENDED" || c.stage === "EXPIRED" || c.stage === "COOLING") raw -= 8;
  if (c.collecting || c.stage === "INSUFFICIENT_DATA") raw -= 25;

  const span = NEX_RANK_RAW_MAX - NEX_RANK_RAW_MIN;
  const normalized = clamp(((raw - NEX_RANK_RAW_MIN) / span) * 100, 0, 100);

  return {
    score: Math.round(normalized * 10) / 10,
    raw: Math.round(raw * 100) / 100,
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

type Scored = {
  c: MarketCandidate;
  score: number;
  raw: number;
  components: LiveRankingRow["rank_score_components"];
};

/** Undo adjacent swaps when score gap < hysteresis and prior order preferred. */
function applyRankHysteresis(scored: Scored[], prevMap: StoredPrev): Scored[] {
  const arr = [...scored];
  let changed = true;
  let guard = 0;
  while (changed && guard < arr.length) {
    changed = false;
    guard += 1;
    for (let i = 0; i < arr.length - 1; i += 1) {
      const a = arr[i];
      const b = arr[i + 1];
      if (a.score - b.score >= RANK_HYSTERESIS_SCORE) continue;
      const pa = prevMap[a.c.symbol.toUpperCase()]?.rank;
      const pb = prevMap[b.c.symbol.toUpperCase()]?.rank;
      if (pa == null || pb == null) continue;
      // Prefer previous order when scores are within hysteresis.
      if (pa > pb) {
        arr[i] = b;
        arr[i + 1] = a;
        changed = true;
      }
    }
  }
  return arr;
}

function toRow(
  c: MarketCandidate,
  score: number,
  raw: number,
  components: LiveRankingRow["rank_score_components"],
  rank: number | null,
  prevMap: StoredPrev,
  now: number,
  radarEligible: boolean,
  tradeEligible: boolean,
): LiveRankingRow {
  const key = c.symbol.toUpperCase();
  const prev = prevMap[key];
  const previous_rank = rank != null ? (prev?.rank ?? (typeof c.previousRank === "number" ? c.previousRank : null)) : null;
  const stillActive = rank != null;
  const rank_event = deriveRankEvent(rank, previous_rank, stillActive);
  const rank_delta =
    rank != null && previous_rank != null
      ? previous_rank - rank
      : c.rankDelta != null
        ? c.rankDelta
        : null;
  const entered_rank_at =
    rank != null ? (prev?.entered_at ?? (rank_event === "NEW" ? now : c.firstSeenAt ?? now)) : null;
  const activity_metric =
    c.priceChange5mPct == null && c.turnoverPace == null
      ? null
      : Math.round((Math.abs(Number(c.priceChange5mPct ?? 0)) * 10 + Number(c.turnoverPace ?? 0) * 0.05) * 10) / 10;

  return {
    symbol: key,
    rank: rank ?? 0,
    previous_rank,
    rank_delta,
    rank_event,
    rank_score: score,
    rank_score_raw: raw,
    rank_score_version: NEX_RANK_SCORE_VERSION,
    rank_score_components: components,
    stage: c.stage,
    side_bias: c.side,
    price: c.currentPrice ?? c.markPrice,
    change_24h: c.change24hPct,
    price_change_1m: c.priceChange1mPct,
    price_change_5m: c.priceChange5mPct,
    price_change_15m: c.priceChange15mPct,
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
    radar_eligible: radarEligible,
    trade_eligible: tradeEligible,
    qualified: tradeEligible,
    candidate_id: c.id,
  };
}

/**
 * Build continuous full-market ranking from scanner candidates.
 * Empty Radar is allowed — do not pad with insufficient symbols.
 */
export function buildLiveRanking(
  candidates: MarketCandidate[],
  opts?: { now?: number; persist?: boolean },
): LiveRankingSnapshot {
  const now = opts?.now ?? Date.now();
  const persist = opts?.persist !== false;
  const { crypto } = partitionOpportunityCandidates(candidates);

  const scannerVisible = crypto.filter(isScannerVisible);
  const radarPool = scannerVisible.filter(isRadarEligible);
  const tradePool = scannerVisible.filter(isTradeEligible);

  const scored: Scored[] = radarPool.map((c) => {
    const { score, raw, components } = computeNexRankScoreV1(c);
    return { c, score, raw, components };
  });

  scored.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    return a.c.symbol.localeCompare(b.c.symbol);
  });

  const prevMap = typeof localStorage !== "undefined" ? loadPrev() : {};
  const stable = applyRankHysteresis(scored, prevMap);

  const nextPrev: StoredPrev = {};
  const newEvents: LiveRankEvent[] = [];

  const rows: LiveRankingRow[] = stable.map(({ c, score, raw, components }, idx) => {
    const rank = idx + 1;
    const key = c.symbol.toUpperCase();
    const prev = prevMap[key];
    const previous_rank = prev?.rank ?? (typeof c.previousRank === "number" ? c.previousRank : null);
    const rank_event = deriveRankEvent(rank, previous_rank, true);
    const rank_delta =
      previous_rank != null ? previous_rank - rank : c.rankDelta != null ? c.rankDelta : null;
    const entered_rank_at = prev?.entered_at ?? (rank_event === "NEW" ? now : c.firstSeenAt ?? now);
    const confirm = (prev?.confirm ?? 0) + 1;

    // Debounce flicker: suppress NEW on first sighting if score is marginal and confirm < 2
    // except when truly absent from prev (first session entry still NEW after confirm).
    let event = rank_event;
    if (rank_event === "NEW" && prev == null && confirm < 1) {
      event = "NEW";
    }
    if (
      (rank_event === "UP" || rank_event === "DOWN") &&
      previous_rank != null &&
      Math.abs(previous_rank - rank) === 1 &&
      prev != null &&
      Math.abs(score - prev.score) < RANK_HYSTERESIS_SCORE
    ) {
      event = "UNCHANGED";
    }

    nextPrev[key] = { rank, score, stage: c.stage, entered_at: entered_rank_at, ts: now, confirm };

    if (event !== "UNCHANGED") {
      const change =
        c.change24hPct != null
          ? `24h ${c.change24hPct > 0 ? "+" : ""}${c.change24hPct.toFixed(2)}%`
          : c.priceChange5mPct != null
            ? `5m ${c.priceChange5mPct > 0 ? "+" : ""}${c.priceChange5mPct.toFixed(2)}%`
            : "—";
      newEvents.push({
        id: `${key}:${event}:${rank}:${Math.floor(now / 60000)}`,
        symbol: key,
        rank_event: event,
        rank,
        previous_rank,
        primary_reason: c.reasons?.[0] || `${event} · #${rank}`,
        market_change: change,
        timestamp: now,
      });
    }

    const row = toRow(c, score, raw, components, rank, prevMap, now, true, isTradeEligible(c));
    row.rank_event = event;
    row.rank_delta = event === "UNCHANGED" && Math.abs(rank_delta ?? 0) === 1 ? 0 : rank_delta;
    row.entered_rank_at = entered_rank_at;
    return row;
  });

  for (const [sym, prev] of Object.entries(prevMap)) {
    if (!nextPrev[sym]) {
      newEvents.push({
        id: `${sym}:OUT:${prev.rank}:${Math.floor(now / 60000)}`,
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

  // Closest Watch — near-miss symbols (scanner visible, NOT radar eligible), separately labelled.
  const radarSyms = new Set(rows.map((r) => r.symbol));
  const closestScored = scannerVisible
    .filter((c) => !radarSyms.has(c.symbol.toUpperCase()) && !isRadarEligible(c))
    .map((c) => {
      const { score, raw, components } = computeNexRankScoreV1(c);
      return { c, score, raw, components };
    })
    .sort((a, b) => b.score - a.score || a.c.symbol.localeCompare(b.c.symbol))
    .slice(0, CLOSEST_WATCH_MAX);

  const closest_watch: LiveRankingRow[] = closestScored.map(({ c, score, raw, components }, idx) => {
    const row = toRow(c, score, raw, components, null, prevMap, now, false, isTradeEligible(c));
    row.rank = idx + 1;
    row.rank_event = "UNCHANGED";
    row.primary_reason = row.primary_reason || "Closest Watch · 尚未達 Radar 門檻";
    return row;
  });

  const qualified = rows.filter((r) => r.qualified);

  return {
    updated_at: now,
    universe_size: crypto.length,
    scanner_visible_count: scannerVisible.length,
    radar_eligible_count: rows.length,
    trade_eligible_count: tradePool.length,
    active_count: rows.length,
    qualified_count: qualified.length,
    rows,
    radar: rows,
    closest_watch,
    qualified,
    events: newEvents,
    fixed_symbol_dependency_count: FIXED_SYMBOL_DEPENDENCY_COUNT,
    radar_eligibility_contract: RADAR_ELIGIBILITY_CONTRACT,
    rank_score_semantics: "normalized_0_100_nex_rank_score_v1",
    rank_persistence: "localStorage_prev_v1_hysteresis",
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
  if (row.rank_event === "UP" && row.rank_delta != null && row.rank_delta !== 0)
    return `#${row.rank} ↑${row.rank_delta}`;
  if (row.rank_event === "DOWN" && row.rank_delta != null && row.rank_delta !== 0)
    return `#${row.rank} ↓${Math.abs(row.rank_delta)}`;
  return `#${row.rank}`;
}

export function formatDisplayRankScore(score: number): string {
  return String(Math.round(clamp(score, 0, 100)));
}
