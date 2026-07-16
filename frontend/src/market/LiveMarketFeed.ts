import { fetchMainnetRestSnapshot } from "./bybitPublicRest";
import { BybitPublicTickerSocket } from "./bybitPublicWs";
import { ageToStatus } from "./freshness";
import { sharedOiHistory } from "./oiHistory";
import type { LiveMarketPrice, LiveSymbol, MarketConnectionStatus } from "./types";
import { LIVE_SYMBOLS } from "./types";

export type LiveMarketSnapshot = {
  bySymbol: Partial<Record<LiveSymbol, LiveMarketPrice>>;
  feedStatus: MarketConnectionStatus;
  transport: "websocket" | "rest" | "none";
  updatedAt: number;
};

type Listener = (snap: LiveMarketSnapshot) => void;

function mergeTicker(
  prev: LiveMarketPrice | undefined,
  next: Omit<LiveMarketPrice, "ageMs" | "connectionStatus">,
): Omit<LiveMarketPrice, "ageMs" | "connectionStatus"> {
  // WS deltas may omit OI/funding/volume — never wipe prior values with undefined.
  return {
    ...next,
    markPrice: next.markPrice ?? prev?.markPrice,
    indexPrice: next.indexPrice ?? prev?.indexPrice,
    bidPrice: next.bidPrice ?? prev?.bidPrice,
    askPrice: next.askPrice ?? prev?.askPrice,
    change24hPct: next.change24hPct ?? prev?.change24hPct,
    openInterest: next.openInterest ?? prev?.openInterest,
    openInterestValue: next.openInterestValue ?? prev?.openInterestValue,
    fundingRate: next.fundingRate ?? prev?.fundingRate,
    nextFundingTime: next.nextFundingTime ?? prev?.nextFundingTime,
    volume24h: next.volume24h ?? prev?.volume24h,
    turnover24h: next.turnover24h ?? prev?.turnover24h,
  };
}

/**
 * Singleton Mainnet public market feed.
 * REST bootstrap + WS live updates + REST fallback. No mock LIVE prices.
 */
export class LiveMarketFeed {
  private prices = new Map<LiveSymbol, LiveMarketPrice>();
  private listeners = new Set<Listener>();
  private socket: BybitPublicTickerSocket | null = null;
  private started = false;
  private wsOpen = false;
  private reconnecting = false;
  private restFallback = false;
  private ageTimer: ReturnType<typeof setInterval> | null = null;
  private restTimer: ReturnType<typeof setInterval> | null = null;
  private transport: "websocket" | "rest" | "none" = "none";

  start() {
    if (this.started) return;
    this.started = true;
    void this.bootstrapRest();
    this.socket = new BybitPublicTickerSocket({
      onTicker: (partial) => this.applyWsTicker(partial),
      onStatus: (st) => this.onWsStatus(st),
    });
    this.socket.start();
    this.ageTimer = setInterval(() => this.recomputeAgesAndEmit(), 500);
    this.restTimer = setInterval(() => {
      if (!this.wsOpen) void this.bootstrapRest(true);
    }, 12_000);
  }

  stop() {
    this.started = false;
    this.socket?.stop();
    this.socket = null;
    if (this.ageTimer) clearInterval(this.ageTimer);
    if (this.restTimer) clearInterval(this.restTimer);
    this.ageTimer = null;
    this.restTimer = null;
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    listener(this.snapshot());
    return () => this.listeners.delete(listener);
  }

  snapshot(): LiveMarketSnapshot {
    const bySymbol: LiveMarketSnapshot["bySymbol"] = {};
    let latestReceived = 0;
    for (const [k, v] of this.prices) {
      bySymbol[k] = v;
      if (v.receivedAt > latestReceived) latestReceived = v.receivedAt;
    }
    return {
      bySymbol,
      feedStatus: this.feedStatus(),
      transport: this.transport,
      updatedAt: latestReceived || 0,
    };
  }

  get(symbol: LiveSymbol): LiveMarketPrice | undefined {
    return this.prices.get(symbol);
  }

  private feedStatus(): MarketConnectionStatus {
    if (!this.prices.size) {
      if (this.reconnecting) return "RECONNECTING";
      if (this.restFallback) return "REST_FALLBACK";
      return "DISCONNECTED";
    }
    const now = Date.now();
    const ages = [...this.prices.values()].map((p) => now - p.receivedAt);
    const worst = Math.max(...ages);
    if (!this.wsOpen && worst > 15_000 && !this.restFallback) {
      return ageToStatus(worst, { disconnected: true });
    }
    return ageToStatus(worst, {
      reconnecting: this.reconnecting && !this.wsOpen,
      restFallback: this.restFallback && !this.wsOpen,
    });
  }

  private rememberOi(row: LiveMarketPrice) {
    sharedOiHistory.push(row.symbol, row.openInterest, row.receivedAt);
  }

  private async bootstrapRest(asFallback = false) {
    try {
      const rows = await fetchMainnetRestSnapshot(LIVE_SYMBOLS);
      const now = Date.now();
      for (const row of rows) {
        const existing = this.prices.get(row.symbol);
        if (existing && existing.receivedAt > now - 1500 && this.wsOpen) {
          const merged = mergeTicker(existing, {
            ...existing,
            openInterest: row.openInterest ?? existing.openInterest,
            openInterestValue: row.openInterestValue ?? existing.openInterestValue,
            fundingRate: row.fundingRate ?? existing.fundingRate,
            nextFundingTime: row.nextFundingTime ?? existing.nextFundingTime,
            volume24h: row.volume24h ?? existing.volume24h,
            turnover24h: row.turnover24h ?? existing.turnover24h,
            receivedAt: existing.receivedAt,
          });
          const ageMs = Math.max(0, now - existing.receivedAt);
          const next: LiveMarketPrice = {
            ...merged,
            receivedAt: existing.receivedAt,
            ageMs,
            connectionStatus: existing.connectionStatus,
          };
          this.prices.set(row.symbol, next);
          this.rememberOi(next);
          continue;
        }
        const next: LiveMarketPrice = {
          ...row,
          receivedAt: now,
          ageMs: 0,
          connectionStatus: ageToStatus(0, { restFallback: asFallback || !this.wsOpen }),
        };
        this.prices.set(row.symbol, next);
        this.rememberOi(next);
      }
      this.restFallback = !this.wsOpen;
      this.transport = this.wsOpen ? "websocket" : "rest";
      this.emit();
    } catch {
      if (!this.prices.size) {
        this.transport = "none";
        this.emit();
      }
    }
  }

  private applyWsTicker(
    partial: Omit<LiveMarketPrice, "ageMs" | "connectionStatus">,
  ) {
    this.wsOpen = true;
    this.reconnecting = false;
    this.restFallback = false;
    this.transport = "websocket";
    const prev = this.prices.get(partial.symbol);
    const merged = mergeTicker(prev, partial);
    const ageMs = Math.max(0, Date.now() - merged.receivedAt);
    const next: LiveMarketPrice = {
      ...merged,
      ageMs,
      connectionStatus: ageToStatus(ageMs),
    };
    this.prices.set(partial.symbol, next);
    this.rememberOi(next);
    this.emit();
  }

  private onWsStatus(st: "connecting" | "open" | "reconnecting" | "closed" | "error") {
    if (st === "open") {
      this.wsOpen = true;
      this.reconnecting = false;
      this.restFallback = false;
      this.transport = "websocket";
      void this.bootstrapRest(false);
    } else if (st === "reconnecting" || st === "connecting") {
      this.wsOpen = false;
      this.reconnecting = true;
      this.transport = this.prices.size ? "rest" : "none";
      void this.bootstrapRest(true);
    } else if (st === "closed" || st === "error") {
      this.wsOpen = false;
      if (this.started) this.reconnecting = true;
      void this.bootstrapRest(true);
    }
    this.recomputeAgesAndEmit();
  }

  private recomputeAgesAndEmit() {
    const now = Date.now();
    for (const [sym, p] of this.prices) {
      const ageMs = Math.max(0, now - p.receivedAt);
      this.prices.set(sym, {
        ...p,
        ageMs,
        connectionStatus: ageToStatus(ageMs, {
          reconnecting: this.reconnecting && !this.wsOpen,
          restFallback: this.restFallback && !this.wsOpen,
        }),
      });
    }
    this.emit();
  }

  private emit() {
    const snap = this.snapshot();
    for (const l of this.listeners) l(snap);
  }
}

let singleton: LiveMarketFeed | null = null;

export function getLiveMarketFeed(): LiveMarketFeed {
  if (!singleton) singleton = new LiveMarketFeed();
  return singleton;
}
