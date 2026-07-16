import type { LiveMarketPrice, LiveSymbol } from "./types";
import { LIVE_SYMBOLS } from "./types";

const WS_URL = "wss://stream.bybit.com/v5/public/linear";

export type WsHandlers = {
  onTicker: (price: Omit<LiveMarketPrice, "ageMs" | "connectionStatus">) => void;
  onStatus: (status: "connecting" | "open" | "reconnecting" | "closed" | "error") => void;
};

function num(v: unknown): number | undefined {
  if (v == null || v === "") return undefined;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : undefined;
}

/**
 * Bybit Mainnet public linear ticker WebSocket.
 * Auto-reconnect with exponential backoff + jitter. No API key.
 * Preserves OI / funding / volume when present in ticker deltas.
 */
export class BybitPublicTickerSocket {
  private ws: WebSocket | null = null;
  private stopped = false;
  private attempt = 0;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly symbols: LiveSymbol[];
  private readonly handlers: WsHandlers;

  constructor(handlers: WsHandlers, symbols: LiveSymbol[] = LIVE_SYMBOLS) {
    this.handlers = handlers;
    this.symbols = symbols;
  }

  start() {
    this.stopped = false;
    this.connect();
  }

  stop() {
    this.stopped = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    this.clearPing();
    if (this.ws) {
      try {
        this.ws.close();
      } catch {
        /* ignore */
      }
      this.ws = null;
    }
    this.handlers.onStatus("closed");
  }

  private clearPing() {
    if (this.pingTimer) clearInterval(this.pingTimer);
    this.pingTimer = null;
  }

  private connect() {
    if (this.stopped) return;
    this.handlers.onStatus(this.attempt === 0 ? "connecting" : "reconnecting");
    let socket: WebSocket;
    try {
      socket = new WebSocket(WS_URL);
    } catch {
      this.handlers.onStatus("error");
      this.scheduleReconnect();
      return;
    }
    this.ws = socket;

    socket.onopen = () => {
      this.attempt = 0;
      this.handlers.onStatus("open");
      const args = this.symbols.map((s) => `tickers.${s}`);
      socket.send(JSON.stringify({ op: "subscribe", args }));
      this.clearPing();
      this.pingTimer = setInterval(() => {
        if (socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ op: "ping" }));
        }
      }, 20_000);
    };

    socket.onmessage = (ev) => {
      try {
        const msg = JSON.parse(String(ev.data)) as {
          topic?: string;
          type?: string;
          ts?: number;
          data?: Record<string, unknown> | Record<string, unknown>[];
          op?: string;
        };
        if (msg.op === "pong") return;
        if (!msg.topic || !String(msg.topic).startsWith("tickers.")) return;
        const raw = Array.isArray(msg.data) ? msg.data[0] : msg.data;
        if (!raw) return;
        const symbol = String(raw.symbol || "") as LiveSymbol;
        if (!this.symbols.includes(symbol)) return;
        const lastPrice = num(raw.lastPrice);
        if (lastPrice == null) return;
        const receivedAt = Date.now();
        const exchangeTimestamp = num(msg.ts) ?? num(raw.ts) ?? receivedAt;
        this.handlers.onTicker({
          symbol,
          source: "BYBIT_MAINNET_LINEAR",
          priceType: "LAST",
          lastPrice,
          markPrice: num(raw.markPrice),
          indexPrice: num(raw.indexPrice),
          bidPrice: num(raw.bid1Price),
          askPrice: num(raw.ask1Price),
          change24hPct: (() => {
            const p = num(raw.price24hPcnt);
            return p == null ? undefined : p * 100;
          })(),
          openInterest: num(raw.openInterest),
          openInterestValue: num(raw.openInterestValue),
          fundingRate: num(raw.fundingRate),
          nextFundingTime: num(raw.nextFundingTime),
          volume24h: num(raw.volume24h),
          turnover24h: num(raw.turnover24h),
          exchangeTimestamp,
          receivedAt,
        });
      } catch {
        /* ignore malformed */
      }
    };

    socket.onerror = () => {
      this.handlers.onStatus("error");
    };

    socket.onclose = () => {
      this.clearPing();
      this.ws = null;
      if (this.stopped) {
        this.handlers.onStatus("closed");
        return;
      }
      this.handlers.onStatus("reconnecting");
      this.scheduleReconnect();
    };
  }

  private scheduleReconnect() {
    if (this.stopped) return;
    this.attempt += 1;
    const base = Math.min(30_000, 800 * 2 ** Math.min(this.attempt, 5));
    const jitter = Math.floor(Math.random() * 400);
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => this.connect(), base + jitter);
  }
}
