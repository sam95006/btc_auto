import { fetchMainnetRestSnapshot } from "./bybitPublicRest";
import { BybitPublicTickerSocket } from "./bybitPublicWs";
import { ageToStatus } from "./freshness";
import type { LiveMarketPrice, LiveSymbol, MarketConnectionStatus } from "./types";
import { LIVE_SYMBOLS } from "./types";

export type LiveMarketSnapshot = {
  bySymbol: Partial<Record<LiveSymbol, LiveMarketPrice>>;
  feedStatus: MarketConnectionStatus;
  transport: "websocket" | "rest" | "none";
  updatedAt: number;
};

type Listener = (snap: LiveMarketSnapshot) => void;

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
    for (const [k, v] of this.prices) bySymbol[k] = v;
    return {
      bySymbol,
      feedStatus: this.feedStatus(),
      transport: this.transport,
      updatedAt: Date.now(),
    };
  }

  get(symbol: LiveSymbol): LiveMarketPrice | undefined {
    return this.prices.get(symbol);
  }

  private feedStatus(): MarketConnectionStatus {
    if (!this.prices.size) {
      return this.reconnecting ? "RECONNECTING" : "DISCONNECTED";
    }
    const ages = [...this.prices.values()].map((p) => Date.now() - p.receivedAt);
    const worst = Math.max(...ages);
    return ageToStatus(worst, {
      reconnecting: this.reconnecting && !this.wsOpen,
      restFallback: this.restFallback && !this.wsOpen,
      disconnected: !this.wsOpen && !this.restFallback && worst > 15_000,
    });
  }

  private async bootstrapRest(asFallback = false) {
    try {
      const rows = await fetchMainnetRestSnapshot(LIVE_SYMBOLS);
      const now = Date.now();
      for (const row of rows) {
        const existing = this.prices.get(row.symbol);
        // Do not let REST overwrite a fresher WS tick.
        if (existing && existing.receivedAt > now - 1500 && this.wsOpen) continue;
        this.prices.set(row.symbol, {
          ...row,
          receivedAt: now,
          ageMs: 0,
          connectionStatus: ageToStatus(0, { restFallback: asFallback || !this.wsOpen }),
        });
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
    const ageMs = Math.max(0, Date.now() - partial.receivedAt);
    this.prices.set(partial.symbol, {
      ...partial,
      ageMs,
      connectionStatus: ageToStatus(ageMs),
    });
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
