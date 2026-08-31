/**
 * Real live market showcase. Every value is backend-provided (binance public);
 * the frontend renders explicit READY / STALE / UNAVAILABLE / ERROR states and
 * flashes a colour when a NEW real value arrives — it never interpolates fake
 * intermediate prices, and it never decides regime/risk itself.
 */
import { useEffect, useRef, useState } from "react";
import { useMarket } from "../context/MarketContext";
import type { MarketSymbol } from "../types";

const REGIME_LABEL: Record<string, string> = {
  RISK_ON: "偏多 / Risk-On", RISK_OFF: "防禦 / Risk-Off", NEUTRAL: "中性 / Neutral",
};
const RISK_LABEL: Record<string, string> = {
  elevated: "偏高 / Elevated", moderate: "中等 / Moderate", contained: "受控 / Contained",
};

function fmtTime(iso?: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "—" : d.toLocaleTimeString();
}

function AssetCard({ s }: { s: MarketSymbol }) {
  const ready = s.availability === "READY" && typeof s.price === "number";
  const prev = useRef<number | null>(null);
  const [flash, setFlash] = useState<"" | "tick-up" | "tick-down">("");
  useEffect(() => {
    if (!ready || typeof s.price !== "number") return;
    const p = prev.current;
    if (p !== null && p !== s.price) {
      setFlash(s.price > p ? "tick-up" : "tick-down");
      const t = window.setTimeout(() => setFlash(""), 700);
      prev.current = s.price;
      return () => window.clearTimeout(t);
    }
    prev.current = s.price;
  }, [s.price, ready]);

  const chg = s.change_24h_percent ?? null;
  const fresh = (s.freshness || "").toUpperCase();
  return (
    <div className="corp-asset" data-avail={s.availability} data-testid={`asset-${s.symbol}`}>
      <div className="corp-asset-top">
        <span className="corp-asset-sym">{s.symbol.replace("USDT", "")}</span>
        {ready ? (
          <span className={`corp-asset-badge ${fresh === "FRESH" ? "is-fresh" : fresh === "STALE" ? "is-stale" : ""}`}>
            {fresh || "LIVE"}
          </span>
        ) : (
          <span className="corp-asset-badge">{s.availability}</span>
        )}
      </div>
      {ready ? (
        <>
          <div className={`corp-asset-price ${flash}`} data-testid={`price-${s.symbol}`}>
            {(s.price as number).toLocaleString()}
          </div>
          <div className="corp-asset-row">
            {chg !== null ? (
              <span className={`corp-chg ${chg >= 0 ? "up" : "down"}`}>
                {chg >= 0 ? "▲" : "▼"} {Math.abs(chg).toFixed(2)}%
              </span>
            ) : (
              <span className="corp-chg">—</span>
            )}
            <span className="corp-asset-meta">
              {s.volatility ? `波動 / vol · ${s.volatility}` : "波動 / vol · —"}
            </span>
          </div>
        </>
      ) : (
        <div className="corp-asset-unavail" data-testid={`unavail-${s.symbol}`}>
          資料暫不可用 / unavailable
        </div>
      )}
    </div>
  );
}

export function LiveShowcase() {
  const m = useMarket();

  if (m.status === "LOADING") {
    return <div className="corp-state corp-state-loading" role="status" aria-live="polite">載入市場資料中… / loading market…</div>;
  }
  if (m.status === "ERROR") {
    return <div className="corp-state corp-state-error" role="alert">市場資料載入失敗 / market data error</div>;
  }
  if (m.status === "UNAVAILABLE") {
    return (
      <div className="corp-state corp-state-unavailable" role="status">
        市場資料暫不可用 / market data unavailable{m.reason ? ` · ${m.reason}` : ""}
      </div>
    );
  }

  const d = m.data;
  const regime = d.regime?.value ?? null;
  const risk = d.risk?.value ?? null;
  // Screen-reader summary — no information conveyed by colour/motion alone.
  const srSummary = `Market regime ${regime ?? "unavailable"}. ` +
    d.symbols.map((s) => s.availability === "READY" && typeof s.price === "number"
      ? `${s.symbol.replace("USDT", "")} ${s.price}, 24 hour change ${s.change_24h_percent ?? "unavailable"} percent.`
      : `${s.symbol.replace("USDT", "")} unavailable.`).join(" ");

  return (
    <div className="corp-showcase" data-testid="live-showcase">
      <p className="corp-sr-only">{srSummary}</p>
      <div className="corp-showcase-head">
        <span className="corp-regime-chip" data-state={regime ?? "UNAVAILABLE"} data-testid="regime-chip">
          <span className="corp-state-dot" />
          市場狀態 / Regime · <strong>{regime ? REGIME_LABEL[regime] : "unavailable"}</strong>
        </span>
        <span className="corp-asset-meta">
          風險 / Risk · <strong>{risk ? RISK_LABEL[risk] || risk : "unavailable"}</strong>
        </span>
      </div>

      <div className="corp-grid-assets">
        {d.symbols.map((s) => <AssetCard key={s.symbol} s={s} />)}
      </div>

      <div className="corp-provenance-bar" data-testid="provenance">
        <span>來源 / Source · <b>{d.source}</b></span>
        <span className="corp-dot-sep" aria-hidden />
        <span>更新 / Updated · <b>{fmtTime(d.updated_at)}</b></span>
        <span className="corp-dot-sep" aria-hidden />
        <span>鮮度 / Freshness · <b>{d.freshness}</b></span>
        <span className="corp-dot-sep" aria-hidden />
        <span>可用性 / Availability · <b>{d.availability}</b></span>
      </div>
    </div>
  );
}
