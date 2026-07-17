/**
 * Bounded in-memory anomaly outcome store (MVP-22D).
 * One tracking row per anomalyId · research only · no persistence of secrets.
 */
import {
  OUTCOME_MAX_TRACKED,
  OUTCOME_MISS_GRACE_MS,
  OUTCOME_TIMESTAMP_TOLERANCE_MS,
  OUTCOME_WINDOWS,
} from "./anomalyOutcomeConfig";
import { forwardReturnPct, updateExcursions } from "./anomalyOutcomeMath";
import type { AnomalyOutcome, AnomalyWindowOutcome } from "./anomalyOutcomeTypes";
import type { MarketAnomaly } from "./anomalyTypes";
import type { LiveMarketPrice, LiveSymbol, MarketConnectionStatus } from "./types";

type InternalWindow = AnomalyWindowOutcome & {
  peakMfe: number;
  peakMae: number;
  bestSample?: { ts: number; price: number; dist: number };
};

type InternalOutcome = Omit<AnomalyOutcome, "outcomes"> & {
  outcomes: InternalWindow[];
};

function clonePublic(row: InternalOutcome): AnomalyOutcome {
  return {
    ...row,
    researchOnly: true,
    outcomes: row.outcomes.map(({ peakMfe: _a, peakMae: _b, bestSample: _c, ...rest }) => rest),
  };
}

export class AnomalyOutcomeStore {
  private byId = new Map<string, InternalOutcome>();
  private order: string[] = [];

  ensureTracking(anomaly: MarketAnomaly, livePrice?: number, now = Date.now()): boolean {
    if (this.byId.has(anomaly.id)) return false;
    const referencePrice =
      anomaly.evidence.currentPrice ??
      livePrice ??
      undefined;
    if (!(referencePrice != null && referencePrice > 0)) return false;

    const observedAt = anomaly.firstSeenAt || anomaly.observedAt || now;
    const outcomes: InternalWindow[] = OUTCOME_WINDOWS.map(({ window, ms }) => ({
      window,
      targetTimestamp: observedAt + ms,
      status: "PENDING" as const,
      peakMfe: 0,
      peakMae: 0,
    }));

    const row: InternalOutcome = {
      anomalyId: anomaly.id,
      symbol: anomaly.symbol,
      anomalyType: anomaly.type,
      severity: anomaly.severity,
      direction: anomaly.direction,
      score: anomaly.score,
      observedAt,
      referencePrice,
      anomalyStatusAtObserve: anomaly.status,
      freshnessAtObserve: anomaly.freshness,
      evidenceSnapshot: { ...anomaly.evidence },
      outcomes,
      source: "BYBIT_MAINNET_LINEAR",
      researchOnly: true,
      lastUpdatedAt: now,
    };
    this.byId.set(anomaly.id, row);
    this.order.unshift(anomaly.id);
    while (this.order.length > OUTCOME_MAX_TRACKED) {
      const drop = this.order.pop();
      if (drop) this.byId.delete(drop);
    }
    return true;
  }

  onPriceTick(
    bySymbol: Partial<Record<LiveSymbol, LiveMarketPrice>>,
    feedStatus: MarketConnectionStatus,
    now = Date.now(),
  ): void {
    const feedBad =
      feedStatus === "STALE" ||
      feedStatus === "DISCONNECTED" ||
      feedStatus === "RECONNECTING";

    for (const row of this.byId.values()) {
      const px = bySymbol[row.symbol]?.lastPrice;
      if (!(px != null && px > 0)) {
        if (feedBad) this.markPendingStale(row, now);
        continue;
      }
      let changed = false;
      for (const w of row.outcomes) {
        if (w.status !== "PENDING") continue;
        const exc = updateExcursions(row.referencePrice, px, row.direction, w.peakMfe, w.peakMae);
        w.peakMfe = exc.mfe;
        w.peakMae = exc.mae;
        w.maxFavorableExcursionPct = w.peakMfe;
        w.maxAdverseExcursionPct = w.peakMae;
        changed = true;

        const dist = Math.abs(now - w.targetTimestamp);
        if (dist <= OUTCOME_TIMESTAMP_TOLERANCE_MS) {
          const prev = w.bestSample;
          if (!prev || dist < prev.dist) {
            w.bestSample = { ts: now, price: px, dist };
          }
        }

        if (now >= w.targetTimestamp - OUTCOME_TIMESTAMP_TOLERANCE_MS) {
          if (w.bestSample && w.bestSample.dist <= OUTCOME_TIMESTAMP_TOLERANCE_MS) {
            w.status = "COMPLETE";
            w.observedTimestamp = w.bestSample.ts;
            w.observedPrice = w.bestSample.price;
            w.forwardReturnPct = forwardReturnPct(row.referencePrice, w.bestSample.price);
            w.maxFavorableExcursionPct = w.peakMfe;
            w.maxAdverseExcursionPct = w.peakMae;
            changed = true;
            continue;
          }
        }

        if (now > w.targetTimestamp + OUTCOME_TIMESTAMP_TOLERANCE_MS + OUTCOME_MISS_GRACE_MS) {
          if (feedBad) {
            w.status = "STALE";
          } else {
            w.status = "MISSED";
          }
          w.maxFavorableExcursionPct = w.peakMfe;
          w.maxAdverseExcursionPct = w.peakMae;
          changed = true;
        }
      }
      if (changed) row.lastUpdatedAt = now;
    }
  }

  private markPendingStale(row: InternalOutcome, now: number): void {
    for (const w of row.outcomes) {
      if (w.status !== "PENDING") continue;
      if (now > w.targetTimestamp + OUTCOME_TIMESTAMP_TOLERANCE_MS + OUTCOME_MISS_GRACE_MS) {
        w.status = "STALE";
        w.maxFavorableExcursionPct = w.peakMfe;
        w.maxAdverseExcursionPct = w.peakMae;
        row.lastUpdatedAt = now;
      }
    }
  }

  get(anomalyId: string): AnomalyOutcome | undefined {
    const row = this.byId.get(anomalyId);
    return row ? clonePublic(row) : undefined;
  }

  list(): AnomalyOutcome[] {
    return this.order
      .map((id) => this.byId.get(id))
      .filter((r): r is InternalOutcome => !!r)
      .map(clonePublic);
  }

  pending(): AnomalyOutcome[] {
    return this.list().filter((r) => r.outcomes.some((o) => o.status === "PENDING"));
  }

  withCompleted(): AnomalyOutcome[] {
    return this.list().filter((r) => r.outcomes.some((o) => o.status === "COMPLETE"));
  }

  reset(): void {
    this.byId.clear();
    this.order = [];
  }

  size(): number {
    return this.byId.size;
  }
}

export const sharedOutcomeStore = new AnomalyOutcomeStore();
