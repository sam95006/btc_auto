import { getMarket } from "../api/client";
import { useResource } from "../hooks/useCorporate";
import type { MarketShowcase } from "../types";
import { DataState, Provenance } from "./DataState";

const REGIME_LABEL: Record<string, string> = { RISK_ON: "偏多 Risk-On", RISK_OFF: "防禦 Risk-Off", NEUTRAL: "中性 Neutral" };
const RISK_LABEL: Record<string, string> = { elevated: "偏高", moderate: "中等", contained: "受控" };

/** Real public market showcase. Every value is backend-provided; the visual
 * state (regime ring, risk) is DERIVED from the backend decision — never
 * decided by the frontend, never fabricated. */
export function LiveMarket() {
  const state = useResource<MarketShowcase>(getMarket, []);
  return (
    <div className="corp-live" data-testid="live-market">
      <DataState state={state} label="市場資料">
        {(m) => (
          <>
            <div className={`corp-regime regime-${(m.regime.value || "none").toLowerCase()}`} data-testid="regime">
              <span className="corp-regime-ring" aria-hidden />
              <div>
                <div className="corp-regime-label">市場狀態 / Regime</div>
                <div className="corp-regime-value" data-testid="regime-value">
                  {m.regime.value ? REGIME_LABEL[m.regime.value] : "unavailable"}
                </div>
                <div className="corp-risk">
                  風險 / Risk：<strong>{m.risk.value ? RISK_LABEL[m.risk.value] || m.risk.value : "unavailable"}</strong>
                </div>
              </div>
            </div>
            <div className="corp-tickers">
              {m.symbols.map((s) => (
                <div key={s.symbol} className="corp-ticker" data-testid={`ticker-${s.symbol}`}>
                  <div className="corp-ticker-sym">{s.symbol.replace("USDT", "")}</div>
                  {s.availability === "READY" && typeof s.price === "number" ? (
                    <>
                      <div className="corp-ticker-price">{s.price.toLocaleString()}</div>
                      <div
                        className={`corp-ticker-chg ${(s.change_24h_percent ?? 0) >= 0 ? "up" : "down"}`}
                        data-testid={`chg-${s.symbol}`}
                      >
                        {(s.change_24h_percent ?? 0) >= 0 ? "▲" : "▼"} {Math.abs(s.change_24h_percent ?? 0).toFixed(2)}%
                      </div>
                      <div className="corp-ticker-vol">波動 {s.volatility ?? "—"}</div>
                    </>
                  ) : (
                    <div className="corp-ticker-unavail" data-testid={`unavail-${s.symbol}`}>unavailable</div>
                  )}
                </div>
              ))}
            </div>
            <Provenance source={m.source} updatedAt={m.updated_at} freshness={m.freshness} />
          </>
        )}
      </DataState>
    </div>
  );
}
