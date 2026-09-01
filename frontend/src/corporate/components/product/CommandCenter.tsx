/**
 * MARKET COMMAND CENTER — a realistic financial product panel (not marketing
 * cards): MARKET | INTELLIGENCE | RISK columns + a live mini-chart timeline.
 * All values backend-provided; unavailable data shown explicitly.
 */
import { useMarket } from "../../context/MarketContext";
import { fmtPct, fmtPrice, symOf } from "../../lib/format";
import { Sparkline } from "./Sparkline";

const REGIME_ZH: Record<string, string> = { RISK_ON: "偏多", RISK_OFF: "防禦", NEUTRAL: "中性" };
const VOL_ZH: Record<string, string> = { high: "偏高", moderate: "中等", low: "偏低" };
const RISK_ZH: Record<string, string> = { elevated: "偏高", moderate: "中等", contained: "受控" };

export function CommandCenter() {
  const m = useMarket();
  const ready = m.status === "READY";
  const d = ready ? m.data : null;
  const primary = d ? (d.symbols.find((s) => s.symbol === "BTCUSDT") || d.symbols[0]) : undefined;
  const regime = d?.regime?.value ?? null;
  const risk = d?.risk?.value ?? null;
  // "watch" = the ready symbol with the widest 24h range (real, backend-derived)
  const watch = d
    ? [...d.symbols].filter((s) => typeof s.range_pct === "number").sort((a, b) => (b.range_pct as number) - (a.range_pct as number))[0]
    : undefined;

  return (
    <div className="corp-fs-cc" data-testid="command-center">
      <div className="corp-fs-cc-top">
        <span className="corp-fs-cc-title">MARKET COMMAND CENTER</span>
        {ready ? <span className="corp-fs-live">LIVE</span> : <span className="corp-fs-badge warn">{m.status}</span>}
      </div>

      <div className="corp-fs-cc-cols">
        <div className="corp-fs-cc-col">
          <h4>Market · 行情</h4>
          {(d?.symbols ?? [{ symbol: "BTCUSDT", availability: "UNAVAILABLE" } as const, { symbol: "ETHUSDT", availability: "UNAVAILABLE" } as const, { symbol: "SOLUSDT", availability: "UNAVAILABLE" } as const]).map((s) => {
            const ok = s.availability === "READY" && typeof s.price === "number";
            return (
              <div className="corp-fs-kv" key={s.symbol}>
                <span className="k">{symOf(s.symbol)}</span>
                <span className={`v ${ok ? ((s.change_24h_percent ?? 0) >= 0 ? "up" : "down") : "muted"}`}>
                  {ok ? `${fmtPrice(s.price)}  ${fmtPct(s.change_24h_percent)}` : "—"}
                </span>
              </div>
            );
          })}
        </div>

        <div className="corp-fs-cc-col">
          <h4>Intelligence · 情報</h4>
          <div className="corp-fs-kv"><span className="k">Regime 市場狀態</span><span className={`v ${regime ? "" : "muted"}`} data-state={regime ?? undefined}>{regime ? REGIME_ZH[regime] : "—"}</span></div>
          <div className="corp-fs-kv"><span className="k">Volatility 波動</span><span className={`v ${primary?.volatility === "high" ? "warn" : ""} ${primary?.volatility ? "" : "muted"}`}>{primary?.volatility ? VOL_ZH[primary.volatility] : "—"}</span></div>
          <div className="corp-fs-kv"><span className="k">24H Range 區間</span><span className={`v ${typeof primary?.range_pct === "number" ? "" : "muted"}`}>{typeof primary?.range_pct === "number" ? `${primary.range_pct.toFixed(2)}%` : "—"}</span></div>
        </div>

        <div className="corp-fs-cc-col">
          <h4>Risk · 風險</h4>
          <div className="corp-fs-kv"><span className="k">Current 當前</span><span className={`v ${risk === "elevated" ? "warn" : ""} ${risk ? "" : "muted"}`}>{risk ? RISK_ZH[risk] || risk : "—"}</span></div>
          <div className="corp-fs-kv"><span className="k">Watch 關注</span><span className={`v ${watch ? "" : "muted"}`}>{watch ? symOf(watch.symbol) : "—"}</span></div>
          <div className="corp-fs-kv"><span className="k">Freshness 鮮度</span><span className={`v ${ready ? "" : "muted"}`}>{ready ? d!.freshness : "—"}</span></div>
        </div>
      </div>

      <div className="corp-fs-cc-timeline">
        <h4><span>Market Timeline · 近況走勢 (1H)</span><span style={{ color: "var(--fs-muted-2)" }}>{ready ? d!.source : ""}</span></h4>
        <div className="corp-fs-cc-charts">
          {(d?.symbols ?? []).map((s) => (
            <div className="corp-fs-cc-chart" key={s.symbol}>
              <div className="s">{symOf(s.symbol)}</div>
              <Sparkline symbol={s.symbol} interval="1h" limit={48} />
            </div>
          ))}
          {!ready ? <div className="corp-fs-loading">走勢資料暫不可用</div> : null}
        </div>
      </div>
    </div>
  );
}
