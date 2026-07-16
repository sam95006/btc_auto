import { ANOMALY_CONFIG } from "./anomalyConfig";
import type { AnomalyCandidate } from "./anomalyEngine";
import { finalizeCandidate } from "./anomalyEngine";
import type { MarketAnomaly, MarketAnomalyType } from "./anomalyTypes";
import type { LiveSymbol } from "./types";

type Stored = MarketAnomaly & { triggerStrength: number; dedupeKey: string };

let idSeq = 0;

function nextId(symbol: LiveSymbol, type: MarketAnomalyType): string {
  idSeq += 1;
  return `${symbol}-${type}-${idSeq}`;
}

/** In-memory anomaly lifecycle — dedup, cooldown, resolve (MVP-22C). */
export class MarketAnomalyStore {
  private active = new Map<string, Stored>();
  private resolved: Stored[] = [];

  process(candidates: AnomalyCandidate[], now = Date.now()): void {
    const cfg = ANOMALY_CONFIG;
    const seenKeys = new Set<string>();

    for (const c of candidates) {
      seenKeys.add(c.dedupeKey);
      const prev = this.active.get(c.dedupeKey);
      if (!prev) {
        const row = finalizeCandidate(c, nextId(c.symbol, c.type), now, now, "NEW");
        this.active.set(c.dedupeKey, { ...row, triggerStrength: c.triggerStrength, dedupeKey: c.dedupeKey });
        continue;
      }
      const use = c.triggerStrength >= prev.triggerStrength ? c : prev;
      const merged = finalizeCandidate(
        {
          ...c,
          title: use.title,
          explanation: use.explanation,
          severity: use.severity,
          evidence: { ...prev.evidence, ...c.evidence },
        },
        prev.id,
        prev.firstSeenAt,
        now,
        prev.status === "NEW" ? "ACTIVE" : prev.status,
      );
      this.active.set(c.dedupeKey, {
        ...merged,
        triggerStrength: Math.max(prev.triggerStrength, c.triggerStrength),
        dedupeKey: c.dedupeKey,
      });
    }

    for (const [key, row] of [...this.active.entries()]) {
      if (seenKeys.has(key)) {
        if (row.status === "NEW") {
          this.active.set(key, { ...row, status: "ACTIVE" });
        }
        continue;
      }
      const elapsed = now - row.lastSeenAt;
      if (row.status === "ACTIVE" || row.status === "NEW") {
        this.active.set(key, {
          ...finalizeCandidate(
            {
              dedupeKey: key,
              symbol: row.symbol,
              type: row.type,
              severity: row.severity,
              direction: row.direction,
              title: row.title,
              explanation: row.explanation,
              source: row.source,
              freshness: row.freshness,
              evidence: row.evidence,
              triggerStrength: row.triggerStrength,
            },
            row.id,
            row.firstSeenAt,
            now,
            "COOLING",
          ),
          triggerStrength: row.triggerStrength,
          dedupeKey: key,
        });
      } else if (row.status === "COOLING" && elapsed >= cfg.resolvedAfterMs) {
        const resolved = finalizeCandidate(
          {
            dedupeKey: key,
            symbol: row.symbol,
            type: row.type,
            severity: row.severity,
            direction: row.direction,
            title: row.title,
            explanation: row.explanation,
            source: row.source,
            freshness: row.freshness,
            evidence: row.evidence,
            triggerStrength: row.triggerStrength,
          },
          row.id,
          row.firstSeenAt,
          now,
          "RESOLVED",
        );
        this.resolved.unshift({ ...resolved, triggerStrength: row.triggerStrength, dedupeKey: key });
        if (this.resolved.length > cfg.maxResolvedHistory) this.resolved.length = cfg.maxResolvedHistory;
        this.active.delete(key);
      }
    }
  }

  listVisible(now = Date.now()): MarketAnomaly[] {
    const cfg = ANOMALY_CONFIG;
    const rows = [
      ...[...this.active.values()].filter((r) => r.status !== "RESOLVED"),
      ...this.resolved.filter((r) => now - r.lastSeenAt < cfg.resolvedAfterMs * 2),
    ];
    return rows
      .map(({ triggerStrength: _t, dedupeKey: _d, ...rest }) => rest)
      .sort((a, b) => b.score - a.score || b.lastSeenAt - a.lastSeenAt);
  }

  top(n: number, now = Date.now()): MarketAnomaly[] {
    return this.listVisible(now)
      .filter((a) => a.status === "NEW" || a.status === "ACTIVE" || a.status === "COOLING")
      .slice(0, n);
  }

  reset(): void {
    this.active.clear();
    this.resolved = [];
    idSeq = 0;
  }
}

export const sharedAnomalyStore = new MarketAnomalyStore();
