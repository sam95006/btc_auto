/**
 * Hero live-market console — a real product panel, not a marketing card.
 * Primary symbol (BTC) shown large with regime / volatility / risk chips and a
 * backend sparkline; ETH / SOL as compact rows. Every value is backend-provided;
 * unavailable data renders explicitly. Price colour flashes on real updates only.
 */
import { useEffect, useRef, useState } from "react";
import { useMarket } from "../../context/MarketContext";
import { fmtPct, fmtPrice, symOf } from "../../lib/format";
import type { MarketSymbol } from "../../types";
import { Sparkline } from "./Sparkline";

const REGIME_ZH: Record<string, string> = { RISK_ON: "偏多", RISK_OFF: "防禦", NEUTRAL: "中性" };
const VOL_ZH: Record<string, string> = { high: "偏高", moderate: "中等", low: "偏低" };
const RISK_ZH: Record<string, string> = { elevated: "偏高", moderate: "中等", contained: "受控" };

function usePriceFlash(price?: number) {
  const prev = useRef<number | null>(null);
  const [dir, setDir] = useState<"" | "up" | "down">("");
  useEffect(() => {
    if (typeof price !== "number") return;
    const p = prev.current;
    if (p !== null && p !== price) {
      setDir(price > p ? "up" : "down");
      const t = window.setTimeout(() => setDir(""), 800);
      prev.current = price;
      return () => window.clearTimeout(t);
    }
    prev.current = price;
  }, [price]);
  return dir;
}

export function LiveConsole() {
  const m = useMarket();

  if (m.status !== "READY") {
    const label = m.status === "LOADING" ? "連線即時市場中…" : "即時市場暫不可用";
    return (
      <div className="corp-fs-console" data-testid="live-console">
        <div className="corp-fs-console-top"><span className="corp-fs-console-sym">BTC / USDT</span><span className="corp-fs-badge warn">{m.status}</span></div>
        <div className="corp-fs-console-body"><div className="corp-fs-loading" role="status">{label}</div></div>
      </div>
    );
  }

  const d = m.data;
  const bySym = (s: string) => d.symbols.find((x) => x.symbol === s);
  const primary = bySym("BTCUSDT") || d.symbols[0];
  const others = d.symbols.filter((s) => s !== primary);
  const regime = d.regime?.value ?? null;
  const risk = d.risk?.value ?? null;

  return (
    <div className="corp-fs-console" data-testid="live-console">
      <div className="corp-fs-console-top">
        <span className="corp-fs-console-sym">{primary ? `${symOf(primary.symbol)} / USDT` : "—"}</span>
        <span className="corp-fs-live">LIVE</span>
      </div>
      <div className="corp-fs-console-body">
        {primary && primary.availability === "READY" && typeof primary.price === "number" ? (
          <PrimaryBlock s={primary} regime={regime} risk={risk} />
        ) : (
          <div className="corp-fs-unavail">主要交易對資料暫不可用</div>
        )}

        <div className="corp-fs-mini">
          {others.map((s) => (
            <div className="corp-fs-mini-row" key={s.symbol} data-testid={`console-row-${s.symbol}`}>
              <span className="s">{symOf(s.symbol)}</span>
              <Sparkline symbol={s.symbol} interval="1h" limit={40} />
              {s.availability === "READY" && typeof s.price === "number" ? (
                <>
                  <span className="p">{fmtPrice(s.price)}</span>
                  <span className={`c ${(s.change_24h_percent ?? 0) >= 0 ? "up" : "down"}`}>{fmtPct(s.change_24h_percent)}</span>
                </>
              ) : (
                <><span className="p">—</span><span className="c">N/A</span></>
              )}
            </div>
          ))}
        </div>
      </div>
      <div className="corp-fs-console-foot">
        <span>來源 · {d.source}</span>
        <span>鮮度 · {d.freshness}</span>
      </div>
    </div>
  );
}

function PrimaryBlock({ s, regime, risk }: { s: MarketSymbol; regime: string | null; risk: string | null }) {
  const flash = usePriceFlash(s.price);
  return (
    <>
      <div className={`corp-fs-price ${flash}`} data-testid="console-price">{fmtPrice(s.price)}</div>
      <div className="corp-fs-price-row">
        <span className={`corp-fs-chg ${(s.change_24h_percent ?? 0) >= 0 ? "up" : "down"}`}>{fmtPct(s.change_24h_percent)}</span>
        <span className="corp-fs-badge">24H</span>
      </div>
      <div className="corp-fs-mini" style={{ marginTop: "0.6rem" }}><Sparkline symbol={s.symbol} interval="1h" limit={48} /></div>
      <div className="corp-fs-metrics">
        <div className="corp-fs-metric">
          <div className="k">Regime</div>
          <div className={`v ${regime ? "" : "muted"}`} data-state={regime ?? undefined}>{regime ? REGIME_ZH[regime] : "—"}</div>
        </div>
        <div className="corp-fs-metric">
          <div className="k">Volatility</div>
          <div className={`v ${s.volatility === "high" ? "warn" : ""} ${s.volatility ? "" : "muted"}`}>{s.volatility ? VOL_ZH[s.volatility] : "—"}</div>
        </div>
        <div className="corp-fs-metric">
          <div className="k">Risk</div>
          <div className={`v ${risk === "elevated" ? "warn" : ""} ${risk ? "" : "muted"}`}>{risk ? RISK_ZH[risk] || risk : "—"}</div>
        </div>
      </div>
    </>
  );
}
