import { useEffect, useRef, useState } from "react";
import { getLiveMarketSnapshot, type LiveMarketSnapshot } from "../services/stagingApi";

const POLL_MS = 8_000;

function price(value: number | null) {
  if (value === null) return "—";
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: value >= 1000 ? 2 : 4 })}`;
}

const STRIP_SYMBOLS = new Set(["BTCUSDT", "ETHUSDT", "SOLUSDT"]);

/** LIVE_API strip only. Uses the central staging snapshot; never queries Binance directly. */
export function LiveMarketTicker() {
  const [snapshot, setSnapshot] = useState<LiveMarketSnapshot | null>(null);
  const [delayed, setDelayed] = useState(false);
  const lastSuccess = useRef<LiveMarketSnapshot | null>(null);

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const next = await getLiveMarketSnapshot();
        if (!active) return;
        lastSuccess.current = next;
        setSnapshot(next);
        setDelayed(next.fallback !== "none" || next.symbols.some((row) => row.data_delayed));
      } catch {
        if (active && lastSuccess.current) {
          setSnapshot(lastSuccess.current);
          setDelayed(true);
        }
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), POLL_MS);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  if (!snapshot) {
    return <p className="mpv1-muted" role="status">市場資料載入中 · LIVE_API</p>;
  }

  const rows = snapshot.symbols.filter((row) => STRIP_SYMBOLS.has(row.symbol));

  return (
    <div
      aria-label="即時市場摘要"
      data-classification="LIVE_API"
      style={{
        display: "flex",
        alignItems: "center",
        flexWrap: "wrap",
        gap: "0.7rem",
        padding: "0.4rem 1.25rem",
        fontSize: "0.78rem",
        borderBottom: "1px solid var(--mp-border)",
      }}
    >
      <strong>LIVE 市場</strong>
      {rows.map((row) => {
        const up = (row.change_24h_percent ?? 0) >= 0;
        return (
          <span key={row.symbol} style={{ display: "inline-flex", gap: "0.3rem", alignItems: "baseline" }}>
            <strong>{row.symbol.replace("USDT", "")}</strong>
            <span>{price(row.current_price)}</span>
            <span className={up ? "mpv1-chg-up" : "mpv1-chg-down"}>
              {row.change_24h_percent === null ? "—" : `${up ? "+" : ""}${row.change_24h_percent.toFixed(2)}%`}
            </span>
          </span>
        );
      })}
      <span className="mpv1-muted">
        {delayed ? "DATA DELAYED" : "LIVE"} · {new Date(snapshot.server_timestamp).toLocaleTimeString()}
      </span>
    </div>
  );
}
