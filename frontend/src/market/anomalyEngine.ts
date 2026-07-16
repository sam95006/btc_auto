import { ANOMALY_CONFIG } from "./anomalyConfig";
import { computeAnomalyScore, severityFromMagnitude } from "./anomalyScoring";
import { fundingBand, fundingRateToPct } from "./fundingConfig";
import { FRESH_DELAYED_MS, FRESH_LIVE_MS } from "./freshness";
import { sharedOiHistory } from "./oiHistory";
import { sharedPriceHistory } from "./priceHistory";
import { classifyPriceOiQuadrant, quadrantExplanation } from "./priceOiQuadrant";
import type {
  AnomalyDirection,
  AnomalyFreshness,
  AnomalySeverity,
  MarketAnomaly,
  MarketAnomalyEvidence,
  MarketAnomalyType,
} from "./anomalyTypes";
import { sharedVolumeHistory } from "./volumeHistory";
import type { LiveMarketPrice, LiveSymbol } from "./types";
import { shortSymbol } from "./types";

export type AnomalyCandidate = Omit<
  MarketAnomaly,
  "id" | "firstSeenAt" | "lastSeenAt" | "status" | "score" | "observedAt"
> & { dedupeKey: string; triggerStrength: number };

function freshnessFromAge(ageMs: number): AnomalyFreshness {
  if (ageMs <= FRESH_LIVE_MS) return "LIVE";
  if (ageMs <= FRESH_DELAYED_MS) return "DELAYED";
  return "STALE";
}

function spreadBps(price: LiveMarketPrice): number | undefined {
  const { bidPrice: bid, askPrice: ask, lastPrice: mid } = price;
  if (bid == null || ask == null || mid == null || mid <= 0) return undefined;
  return ((ask - bid) / mid) * 10_000;
}

function baseCandidate(
  symbol: LiveSymbol,
  type: MarketAnomalyType,
  title: string,
  explanation: string,
  severity: AnomalySeverity,
  direction: AnomalyDirection | undefined,
  price: LiveMarketPrice,
  evidence: MarketAnomalyEvidence,
  triggerStrength: number,
): AnomalyCandidate {
  return {
    dedupeKey: `${symbol}:${type}`,
    symbol,
    type,
    severity,
    direction,
    title,
    explanation,
    source: "BYBIT_MAINNET_LINEAR",
    freshness: freshnessFromAge(price.ageMs),
    evidence,
    triggerStrength,
  };
}

export function detectSymbolAnomalies(price: LiveMarketPrice, now = Date.now()): AnomalyCandidate[] {
  if (price.connectionStatus === "DISCONNECTED" || price.connectionStatus === "RECONNECTING") {
    return [];
  }
  const isStale = price.ageMs > FRESH_DELAYED_MS;
  const out: AnomalyCandidate[] = [];
  const label = shortSymbol(price.symbol);
  const priceSnap = sharedPriceHistory.snapshot(price.symbol, now);
  const oiSnap = sharedOiHistory.snapshot(price.symbol, now);
  const volSnap = sharedVolumeHistory.snapshot(price.symbol, now);
  const cfg = ANOMALY_CONFIG;

  const evidenceBase: MarketAnomalyEvidence = {
    currentPrice: price.lastPrice,
    priceChange1mPct: priceSnap.priceChange1mPct ?? undefined,
    priceChange5mPct: priceSnap.priceChange5mPct ?? undefined,
    oiChange1mPct: oiSnap.oiChange1mPct ?? undefined,
    oiChange5mPct: oiSnap.oiChange5mPct ?? undefined,
    oiChange15mPct: oiSnap.oiChange15mPct ?? undefined,
    fundingRate: price.fundingRate,
    spreadBps: spreadBps(price),
    volumeRatio: volSnap.volumeExpansion5mPct ?? undefined,
  };

  if (!isStale && priceSnap.priceWindow.m1 === "ready" && priceSnap.priceChange1mPct != null) {
    const abs = Math.abs(priceSnap.priceChange1mPct);
    if (abs >= cfg.priceAcceleration1mPct) {
      out.push(
        baseCandidate(
          price.symbol,
          "PRICE_ACCELERATION",
          `${label} price acceleration (1m)`,
          `1m price change ${priceSnap.priceChange1mPct.toFixed(2)}% exceeds research threshold — context only.`,
          severityFromMagnitude(abs, [cfg.priceAcceleration1mPct, cfg.priceAcceleration1mPct * 2, cfg.priceAcceleration1mPct * 4]),
          priceSnap.priceChange1mPct > 0 ? "UP" : "DOWN",
          price,
          { ...evidenceBase, factorCount: 1 },
          abs,
        ),
      );
    }
  }

  if (!isStale && priceSnap.priceWindow.m5 === "ready" && priceSnap.priceChange5mPct != null) {
    const abs = Math.abs(priceSnap.priceChange5mPct);
    if (abs >= cfg.priceAcceleration5mPct) {
      out.push(
        baseCandidate(
          price.symbol,
          "PRICE_ACCELERATION",
          `${label} price acceleration (5m)`,
          `5m price change ${priceSnap.priceChange5mPct.toFixed(2)}% — market condition requiring attention.`,
          severityFromMagnitude(abs, [cfg.priceAcceleration5mPct, cfg.priceAcceleration5mPct * 1.8, cfg.priceAcceleration5mPct * 3]),
          priceSnap.priceChange5mPct > 0 ? "UP" : "DOWN",
          price,
          { ...evidenceBase, factorCount: 1 },
          abs,
        ),
      );
    }
  }

  const oiChecks: Array<{ pct: number | null; w: string; ready: boolean; surge: number; drop: number }> = [
    { pct: oiSnap.oiChange1mPct, w: "1m", ready: oiSnap.oiWindow.m1 === "ready", surge: cfg.oiSurge1mPct, drop: cfg.oiDrop1mPct },
    { pct: oiSnap.oiChange5mPct, w: "5m", ready: oiSnap.oiWindow.m5 === "ready", surge: cfg.oiSurge5mPct, drop: cfg.oiDrop5mPct },
    { pct: oiSnap.oiChange15mPct, w: "15m", ready: oiSnap.oiWindow.m15 === "ready", surge: cfg.oiSurge15mPct, drop: cfg.oiDrop15mPct },
  ];
  for (const { pct, w, ready, surge, drop } of oiChecks) {
    if (!ready || pct == null || isStale) continue;
    if (pct >= surge) {
      out.push(
        baseCandidate(
          price.symbol,
          "OI_SURGE",
          `${label} OI surge (${w})`,
          `Open interest +${pct.toFixed(2)}% over ${w} — context only; not a trade trigger.`,
          severityFromMagnitude(pct, [surge, surge * 2.5, surge * 5]),
          "UP",
          price,
          { ...evidenceBase, factorCount: 1 },
          pct,
        ),
      );
    } else if (pct <= drop) {
      out.push(
        baseCandidate(
          price.symbol,
          "OI_DROP",
          `${label} OI drop (${w})`,
          `Open interest ${pct.toFixed(2)}% over ${w} — requires confirmation.`,
          severityFromMagnitude(Math.abs(pct), [Math.abs(drop), Math.abs(drop) * 2.5, Math.abs(drop) * 5]),
          "DOWN",
          price,
          { ...evidenceBase, factorCount: 1 },
          Math.abs(pct),
        ),
      );
    }
  }

  const quadrant = classifyPriceOiQuadrant(
    priceSnap.priceChange5mPct,
    oiSnap.oiChange5mPct,
    cfg.divergenceMinPrice5mPct,
    cfg.divergenceMinOi5mPct,
  );
  if (!isStale && (quadrant === "PRICE_UP_OI_DOWN" || quadrant === "PRICE_DOWN_OI_UP")) {
    out.push(
      baseCandidate(
        price.symbol,
        "PRICE_OI_DIVERGENCE",
        `${label} price / OI divergence`,
        quadrantExplanation(quadrant),
        "MEDIUM",
        "MIXED",
        price,
        { ...evidenceBase, priceOiQuadrant: quadrant, factorCount: 2 },
        Math.abs((priceSnap.priceChange5mPct ?? 0) - (oiSnap.oiChange5mPct ?? 0)),
      ),
    );
  }

  if (!isStale && price.fundingRate != null) {
    const band = fundingBand(price.fundingRate);
    if (band === "Extreme Positive" || band === "Extreme Negative") {
      const pct = fundingRateToPct(price.fundingRate);
      out.push(
        baseCandidate(
          price.symbol,
          "FUNDING_EXTREME",
          `${label} funding extreme`,
          `${band} (${pct?.toFixed(4)}%) — context only; not LONG/SHORT instruction.`,
          "HIGH",
          pct != null && pct > 0 ? "UP" : "DOWN",
          price,
          { ...evidenceBase, factorCount: 1 },
          Math.abs(pct ?? 0),
        ),
      );
    }
  }

  if (
    !isStale &&
    volSnap.volumeWindow.m5 === "ready" &&
    volSnap.volumeExpansion5mPct != null &&
    volSnap.volumeExpansion5mPct >= cfg.volumeExpansion5mPct
  ) {
    const r = volSnap.volumeExpansion5mPct;
    out.push(
      baseCandidate(
        price.symbol,
        "VOLUME_EXPANSION",
        `${label} turnover expansion (5m)`,
        `24h turnover pace +${r.toFixed(2)}% vs 5m baseline — research threshold only.`,
        severityFromMagnitude(r, [cfg.volumeExpansion5mPct, cfg.volumeExpansion5mPct * 2, cfg.volumeExpansion5mPct * 3.5]),
        "UP",
        price,
        { ...evidenceBase, volumeRatio: r, factorCount: 1 },
        r,
      ),
    );
  }

  const sbps = spreadBps(price);
  if (!isStale && sbps != null && sbps >= cfg.spreadWidenBps) {
    out.push(
      baseCandidate(
        price.symbol,
        "SPREAD_WIDENING",
        `${label} spread widening`,
        `Bid-ask spread ${sbps.toFixed(1)} bps — liquidity context only.`,
        severityFromMagnitude(sbps, [cfg.spreadWidenBps, cfg.spreadWidenBps * 2, cfg.spreadWidenBps * 4]),
        "NEUTRAL",
        price,
        { ...evidenceBase, spreadBps: sbps, factorCount: 1 },
        sbps,
      ),
    );
  }

  const distinct = new Set(out.map((c) => c.type));
  if (distinct.size >= 2) {
    const types = [...distinct];
    out.push(
      baseCandidate(
        price.symbol,
        "MULTI_FACTOR_ANOMALY",
        `${label} multi-factor anomaly`,
        `${types.length} concurrent signals — attention ranking only.`,
        distinct.size >= 3 ? "HIGH" : "MEDIUM",
        "MIXED",
        price,
        { ...evidenceBase, factorCount: types.length },
        types.length * 10,
      ),
    );
  }

  return out;
}

export function detectAllAnomalies(
  bySymbol: Partial<Record<LiveSymbol, LiveMarketPrice>>,
  now = Date.now(),
): AnomalyCandidate[] {
  const all: AnomalyCandidate[] = [];
  for (const price of Object.values(bySymbol)) {
    if (price) all.push(...detectSymbolAnomalies(price, now));
  }
  return all;
}

export function finalizeCandidate(
  c: AnomalyCandidate,
  id: string,
  firstSeenAt: number,
  lastSeenAt: number,
  status: MarketAnomaly["status"],
): MarketAnomaly {
  return {
    id,
    symbol: c.symbol,
    type: c.type,
    severity: c.severity,
    direction: c.direction,
    title: c.title,
    explanation: c.explanation,
    observedAt: lastSeenAt,
    firstSeenAt,
    lastSeenAt,
    source: c.source,
    freshness: c.freshness,
    evidence: c.evidence,
    status,
    score: computeAnomalyScore(c.severity, c.freshness, c.evidence, firstSeenAt, lastSeenAt),
  };
}
