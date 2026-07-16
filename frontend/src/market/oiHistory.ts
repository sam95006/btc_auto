import type { LiveSymbol } from "./types";

type OiSample = { t: number; oi: number };

const WINDOWS_MS = {
  m1: 60_000,
  m5: 5 * 60_000,
  m15: 15 * 60_000,
} as const;

/** In-memory OI rolling samples — no persistence, no secrets (MVP-22B). */
export class OiHistoryBuffer {
  private bySymbol = new Map<LiveSymbol, OiSample[]>();

  push(symbol: LiveSymbol, oi: number | undefined, now = Date.now()) {
    if (oi == null || !Number.isFinite(oi)) return;
    const arr = this.bySymbol.get(symbol) ?? [];
    const last = arr[arr.length - 1];
    // Throttle samples ~5s to limit memory
    if (last && now - last.t < 5_000 && Math.abs(last.oi - oi) < 1e-12) return;
    if (last && now - last.t < 5_000) {
      last.oi = oi;
      last.t = now;
    } else {
      arr.push({ t: now, oi });
    }
    const cutoff = now - WINDOWS_MS.m15 - 60_000;
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
    if (oldest.t > target + 5_000) {
      // not enough history for this window
      return { pct: null, state: "collecting" };
    }
    // find sample closest to target time (at or before)
    let base = oldest;
    for (const s of arr) {
      if (s.t <= target) base = s;
      else break;
    }
    const latest = arr[arr.length - 1];
    if (!base.oi) return { pct: null, state: "collecting" };
    const span = latest.t - base.t;
    if (span < windowMs * 0.85) return { pct: null, state: "collecting" };
    const pct = ((latest.oi - base.oi) / base.oi) * 100;
    return { pct, state: "ready" };
  }

  snapshot(symbol: LiveSymbol, now = Date.now()) {
    const m1 = this.changePct(symbol, WINDOWS_MS.m1, now);
    const m5 = this.changePct(symbol, WINDOWS_MS.m5, now);
    const m15 = this.changePct(symbol, WINDOWS_MS.m15, now);
    return {
      oiChange1mPct: m1.state === "ready" ? m1.pct : null,
      oiChange5mPct: m5.state === "ready" ? m5.pct : null,
      oiChange15mPct: m15.state === "ready" ? m15.pct : null,
      oiWindow: {
        m1: m1.state,
        m5: m5.state,
        m15: m15.state,
      } as const,
    };
  }
}

export const sharedOiHistory = new OiHistoryBuffer();
