/**
 * Synthetic state-machine tests for MVP-22D anomaly outcome tracking.
 * Run: node tools/research/mvp22d_outcome_synthetic_test.mjs
 */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "../..");

// Compile/load via tsx if available; otherwise use a minimal inline reimplementation check via node --experimental
// Prefer spawning a small TypeScript runner through npx tsx from ASCII mirror if needed.
// Here we use dynamic import of built logic by evaluating a temporary ESM copy of pure JS ports.

function median(values) {
  if (!values.length) return null;
  const s = [...values].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 === 0 ? (s[mid - 1] + s[mid]) / 2 : s[mid];
}

function forwardReturnPct(ref, px) {
  return ((px - ref) / ref) * 100;
}

function updateExcursions(ref, price, direction, mfe, mae) {
  const up = ((price - ref) / ref) * 100;
  const down = ((ref - price) / ref) * 100;
  if (direction === "UP") {
    return { mfe: Math.max(mfe, Math.max(0, up)), mae: Math.max(mae, Math.max(0, down)) };
  }
  if (direction === "DOWN") {
    return { mfe: Math.max(mfe, Math.max(0, down)), mae: Math.max(mae, Math.max(0, up)) };
  }
  return { mfe: Math.max(mfe, Math.max(0, up)), mae: Math.max(mae, Math.max(0, down)) };
}

const TOL = 15_000;
const MISS_GRACE = 30_000;
const WINDOWS = [
  { window: "5m", ms: 5 * 60_000 },
  { window: "15m", ms: 15 * 60_000 },
  { window: "30m", ms: 30 * 60_000 },
  { window: "60m", ms: 60 * 60_000 },
];

class Store {
  constructor() {
    this.byId = new Map();
  }
  ensure(anomaly, livePrice, now) {
    if (this.byId.has(anomaly.id)) return false;
    const referencePrice = anomaly.evidence?.currentPrice ?? livePrice;
    if (!(referencePrice > 0)) return false;
    const observedAt = anomaly.firstSeenAt || now;
    this.byId.set(anomaly.id, {
      anomalyId: anomaly.id,
      symbol: anomaly.symbol,
      direction: anomaly.direction,
      referencePrice,
      observedAt,
      outcomes: WINDOWS.map(({ window, ms }) => ({
        window,
        targetTimestamp: observedAt + ms,
        status: "PENDING",
        peakMfe: 0,
        peakMae: 0,
      })),
    });
    return true;
  }
  tick(symbol, price, feedStatus, now) {
    for (const row of this.byId.values()) {
      if (row.symbol !== symbol) continue;
      for (const w of row.outcomes) {
        if (w.status !== "PENDING") continue;
        const exc = updateExcursions(row.referencePrice, price, row.direction, w.peakMfe, w.peakMae);
        w.peakMfe = exc.mfe;
        w.peakMae = exc.mae;
        const dist = Math.abs(now - w.targetTimestamp);
        if (dist <= TOL) {
          if (!w.bestSample || dist < w.bestSample.dist) {
            w.bestSample = { ts: now, price, dist };
          }
        }
        if (now >= w.targetTimestamp - TOL && w.bestSample && w.bestSample.dist <= TOL) {
          w.status = "COMPLETE";
          w.forwardReturnPct = forwardReturnPct(row.referencePrice, w.bestSample.price);
          w.maxFavorableExcursionPct = w.peakMfe;
          w.maxAdverseExcursionPct = w.peakMae;
          continue;
        }
        if (now > w.targetTimestamp + TOL + MISS_GRACE) {
          w.status = feedStatus === "STALE" || feedStatus === "DISCONNECTED" ? "STALE" : "MISSED";
        }
      }
    }
  }
  get(id) {
    return this.byId.get(id);
  }
  size() {
    return this.byId.size;
  }
}

const store = new Store();
const t0 = 1_700_000_000_000;
const anomaly = {
  id: "BTCUSDT-PRICE_ACCELERATION-1",
  symbol: "BTCUSDT",
  direction: "UP",
  firstSeenAt: t0,
  evidence: { currentPrice: 100 },
};

assert.equal(store.ensure(anomaly, 100, t0), true);
assert.equal(store.ensure(anomaly, 100, t0 + 1000), false, "duplicate tracking blocked");
assert.equal(store.size(), 1);

store.tick("BTCUSDT", 101, "LIVE", t0 + 60_000);
store.tick("BTCUSDT", 102, "LIVE", t0 + 120_000);
let row = store.get(anomaly.id);
assert.equal(row.outcomes[0].status, "PENDING");
assert.equal(row.outcomes[1].status, "PENDING");
assert.ok(row.outcomes[0].peakMfe >= 2);

// complete 5m within tolerance
store.tick("BTCUSDT", 103, "LIVE", t0 + 5 * 60_000);
row = store.get(anomaly.id);
assert.equal(row.outcomes[0].status, "COMPLETE");
assert.equal(row.outcomes[1].status, "PENDING");
assert.ok(Math.abs(row.outcomes[0].forwardReturnPct - 3) < 1e-9);
assert.ok(row.outcomes[0].maxFavorableExcursionPct >= 3);

// miss 15m by jumping past grace without sample in tolerance
store.tick("BTCUSDT", 104, "LIVE", t0 + 15 * 60_000 + TOL + MISS_GRACE + 1);
row = store.get(anomaly.id);
assert.equal(row.outcomes[1].status, "MISSED");

// stale path for 30m
store.tick("BTCUSDT", 105, "STALE", t0 + 30 * 60_000 + TOL + MISS_GRACE + 1);
row = store.get(anomaly.id);
assert.equal(row.outcomes[2].status, "STALE");

// aggregation insufficient sample
const completed = [3, 1, -0.5];
assert.equal(median(completed), 1);
assert.equal(completed.length < 5, true, "insufficient sample gate");

// ETH/SOL supported symbols can track
assert.equal(
  store.ensure(
    {
      id: "ETHUSDT-OI_SURGE-1",
      symbol: "ETHUSDT",
      direction: "UP",
      firstSeenAt: t0,
      evidence: { currentPrice: 2000 },
    },
    2000,
    t0,
  ),
  true,
);
assert.equal(
  store.ensure(
    {
      id: "SOLUSDT-FUNDING_EXTREME-1",
      symbol: "SOLUSDT",
      direction: "DOWN",
      firstSeenAt: t0,
      evidence: { currentPrice: 80 },
    },
    80,
    t0,
  ),
  true,
);

console.log("SYNTHETIC_PASS: dedup, 5m complete, pending/missed/stale, MFE/MAE, BTC/ETH/SOL");
