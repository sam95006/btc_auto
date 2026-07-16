import type { LiveSymbol } from "./types";

type VolumeSample = { t: number; turnover24h: number };
const WINDOW_MS = 5 * 60_000;

/** Rolling turnover24h samples for expansion detection (MVP-22C). */
export class VolumeHistoryBuffer {
  private bySymbol = new Map<LiveSymbol, VolumeSample[]>();

  push(symbol: LiveSymbol, turnover24h: number | undefined, now = Date.now()) {
    if (turnover24h == null || !Number.isFinite(turnover24h)) return;
    const arr = this.bySymbol.get(symbol) ?? [];
    const last = arr[arr.length - 1];
    if (last && now - last.t < 5_000 && Math.abs(last.turnover24h - turnover24h) < 1) return;
    if (last && now - last.t < 5_000) {
      last.turnover24h = turnover24h;
      last.t = now;
    } else {
      arr.push({ t: now, turnover24h });
    }
    const cutoff = now - WINDOW_MS - 60_000;
    while (arr.length && arr[0].t < cutoff) arr.shift();
    this.bySymbol.set(symbol, arr);
  }

  expansionRatio(symbol: LiveSymbol, now = Date.now()) {
    const arr = this.bySymbol.get(symbol) ?? [];
    if (arr.length < 2) return { ratio: null, state: "collecting" as const };
    const target = now - WINDOW_MS;
    const oldest = arr[0];
    if (oldest.t > target + 5_000) return { ratio: null, state: "collecting" as const };
    let base = oldest;
    for (const s of arr) {
      if (s.t <= target) base = s;
      else break;
    }
    const latest = arr[arr.length - 1];
    if (!base.turnover24h) return { ratio: null, state: "collecting" as const };
    const span = latest.t - base.t;
    if (span < WINDOW_MS * 0.85) return { ratio: null, state: "collecting" as const };
    const ratio = ((latest.turnover24h - base.turnover24h) / base.turnover24h) * 100;
    return { ratio, state: "ready" as const };
  }

  snapshot(symbol: LiveSymbol, now = Date.now()) {
    const exp = this.expansionRatio(symbol, now);
    return {
      volumeExpansion5mPct: exp.state === "ready" ? exp.ratio : null,
      volumeWindow: { m5: exp.state } as const,
    };
  }
}

export const sharedVolumeHistory = new VolumeHistoryBuffer();
