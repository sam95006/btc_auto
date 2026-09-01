/** Compact BTC/ETH/SOL live strip — establishes immediately that the site holds
 * real data. Backend-only; unavailable symbols render explicitly. */
import { useMarket } from "../../context/MarketContext";
import { fmtPct, fmtPrice, symOf } from "../../lib/format";

export function MarketStrip() {
  const m = useMarket();
  if (m.status !== "READY") {
    return <div className="corp-fs-loading" role="status">{m.status === "LOADING" ? "載入即時行情…" : "行情暫不可用"}</div>;
  }
  return (
    <div className="corp-fs-strip" data-testid="market-strip">
      {m.data.symbols.map((s) => {
        const ok = s.availability === "READY" && typeof s.price === "number";
        const up = (s.change_24h_percent ?? 0) >= 0;
        return (
          <div className="corp-fs-strip-cell" key={s.symbol}>
            <div className="l">
              <span className="s">{symOf(s.symbol)}<span style={{ color: "var(--fs-muted-2)" }}>/USDT</span></span>
              <span className="st">{ok ? (s.freshness || "LIVE") : s.availability}</span>
            </div>
            <div className="r">
              <span className="p">{ok ? fmtPrice(s.price) : "—"}</span>
              <span className={`c ${up ? "up" : "down"}`}>{ok ? fmtPct(s.change_24h_percent) : "N/A"}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
