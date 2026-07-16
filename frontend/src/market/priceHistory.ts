import type { LiveSymbol } from "./types";

type PriceSample = { t: number; price: number };

const WINDOWS_MS = { m1: 60_000, m5: 5 * 60_000 } as const;

/** In-memory price rolling samples — no persistence (MVP-22C). */
export class PriceHistoryBuffer {
  private bySymbol = new Map<LiveSymbol, PriceSample[]>();

  push(symbol: LiveSymbol, price: number | undefined, now = Date.now()) {
    if (price == null || !Number.isFinite(price)) return;
    const arr = this.bySymbol.get(symbol) ?? [];
    const last = arr[arr.length - 1];
    if (last && now - last.t < 5_000 && Math.abs(last.price - price) < 1e-12) return;
    if (last && now - last.t < 5_000) {
      last.price = price;
      last.t = now;
    } else {
      arr.push({ t: now, price });
    }
    const cutoff = now - WINDOWS_MS.m5 - 60_000;
    while (arr.length && arr[0].t < cutoff) arr.shift();
    this.bySymbol.set(symbol, arr);
  }

  changePct(
    symbol: LiveSymbol,
    windowMs: number,
    now = Date.now(),
  ): { pct: number | null; state: "ready" | "collecting" } {
    const arr = this.bySymbol.get(symbol) ?? [];
    if (arr.length < 2) return { pct: null, state: "collecting" };
    const target = now - windowMs;
    const oldest = arr[0];
    if (oldest.t > target + 5_000) return { pct: null, state: "collecting" };
    let base = oldest;
    for (const s of arr) {
      if (s.t <= target) base = s;
      else break;
    }
    const latest = arr[arr.length - 1];
    if (!base.price) return { pct: null, state: "collecting" };
    const span = latest.t - base.t;
    if (span < windowMs * 0.85) return { pct: null, state: "collecting" };
    return { pct: ((latest.price - base.price) / base.price) * 100, state: "ready" };
  }

  snapshot(symbol: LiveSymbol, now = Date.now()) {
    const m1 = this.changePct(symbol, WINDOWS_MS.m1, now);
    const m5 = this.changePct(symbol, WINDOWS_MS.m5, now);
    return {
      priceChange1mPct: m1.state === "ready" ? m1.pct : null,
      priceChange5mPct: m5.state === "ready" ? m5.pct : null,
      priceWindow: { m1: m1.state, m5: m5.state } as const,
    };
  }
}

export const sharedPriceHistory = new PriceHistoryBuffer();
