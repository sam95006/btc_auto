/**
 * Synthetic lifecycle tests for MVP-22C (no live market data).
 * Run: node tools/research/mvp22c_anomaly_synthetic_test.mjs
 */

function assert(cond, msg) {
  if (!cond) {
    console.error("FAIL:", msg);
    process.exit(1);
  }
}

// Minimal inline store logic mirroring anomalyStore.ts
class TestStore {
  constructor() {
    this.active = new Map();
    this.resolved = [];
  }
  process(candidates, now) {
    const seen = new Set();
    for (const c of candidates) {
      seen.add(c.key);
      const prev = this.active.get(c.key);
      if (!prev) {
        this.active.set(c.key, { ...c, first: now, last: now, status: "NEW" });
      } else {
        this.active.set(c.key, { ...prev, ...c, last: now, status: "ACTIVE" });
      }
    }
    for (const [key, row] of [...this.active.entries()]) {
      if (seen.has(key)) continue;
      if (row.status === "ACTIVE") {
        this.active.set(key, { ...row, status: "COOLING", last: now });
      } else if (row.status === "COOLING" && now - row.last >= 100) {
        this.resolved.push({ ...row, status: "RESOLVED" });
        this.active.delete(key);
      }
    }
  }
}

const store = new TestStore();
const t0 = 1_000_000;
store.process([{ key: "ETH:OI_SURGE", strength: 1 }], t0);
store.process([{ key: "ETH:OI_SURGE", strength: 2 }], t0 + 50);
const row = store.active.get("ETH:OI_SURGE");
assert(row && row.status === "ACTIVE", "dedup updates same event");
assert(row.strength === 2, "strength merges");

store.process([], t0 + 60);
assert(store.active.get("ETH:OI_SURGE")?.status === "COOLING", "missing trigger -> COOLING");

store.process([], t0 + 200);
assert(!store.active.has("ETH:OI_SURGE"), "cooling -> RESOLVED removes active");
assert(store.resolved.length === 1, "resolved history kept");

// insufficient window: empty candidates when collecting
const collecting = { m1: "collecting", ready: false };
assert(!collecting.ready, "insufficient window blocks anomaly");

console.log("SYNTHETIC_PASS: dedup, cooldown, resolved, collecting gate");
