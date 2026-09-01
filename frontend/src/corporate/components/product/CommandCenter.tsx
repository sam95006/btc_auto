/**
 * MARKET COMMAND CENTER — a realistic financial product panel: MARKET |
 * INTELLIGENCE | RISK columns + a live mini-chart timeline. Field names stay
 * English (technical labels); state VALUES are localized. All values are
 * backend-provided; unavailable data shown explicitly.
 */
import { useMarket } from "../../context/MarketContext";
import { useLocale } from "../../i18n";
import { fmtPct, fmtPrice, symOf } from "../../lib/format";
import { regimeLabel, riskLabel, volLabel } from "../../lib/marketLabels";
import { Sparkline } from "./Sparkline";

export function CommandCenter() {
  const m = useMarket();
  const { locale, t } = useLocale();
  const ready = m.status === "READY";
  const d = ready ? m.data : null;
  const primary = d ? (d.symbols.find((s) => s.symbol === "BTCUSDT") || d.symbols[0]) : undefined;
  const regime = d?.regime?.value ?? null;
  const risk = d?.risk?.value ?? null;
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
          <h4>Market</h4>
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
          <h4>Intelligence</h4>
          <div className="corp-fs-kv"><span className="k">Regime</span><span className={`v ${regime ? "" : "muted"}`} data-state={regime ?? undefined}>{regimeLabel(regime, locale)}</span></div>
          <div className="corp-fs-kv"><span className="k">Volatility</span><span className={`v ${primary?.volatility === "high" ? "warn" : ""} ${primary?.volatility ? "" : "muted"}`}>{volLabel(primary?.volatility, locale)}</span></div>
          <div className="corp-fs-kv"><span className="k">24H Range</span><span className={`v ${typeof primary?.range_pct === "number" ? "" : "muted"}`}>{typeof primary?.range_pct === "number" ? `${primary.range_pct.toFixed(2)}%` : "—"}</span></div>
        </div>

        <div className="corp-fs-cc-col">
          <h4>Risk</h4>
          <div className="corp-fs-kv"><span className="k">Current</span><span className={`v ${risk === "elevated" ? "warn" : ""} ${risk ? "" : "muted"}`}>{riskLabel(risk, locale)}</span></div>
          <div className="corp-fs-kv"><span className="k">Watch</span><span className={`v ${watch ? "" : "muted"}`}>{watch ? symOf(watch.symbol) : "—"}</span></div>
          <div className="corp-fs-kv"><span className="k">Freshness</span><span className={`v ${ready ? "" : "muted"}`}>{ready ? d!.freshness : "—"}</span></div>
        </div>
      </div>

      <div className="corp-fs-cc-timeline">
        <h4><span>Timeline · 1H</span><span style={{ color: "var(--fs-muted-2)" }}>{ready ? d!.source : ""}</span></h4>
        <div className="corp-fs-cc-charts">
          {(d?.symbols ?? []).map((s) => (
            <div className="corp-fs-cc-chart" key={s.symbol}>
              <div className="s">{symOf(s.symbol)}</div>
              <Sparkline symbol={s.symbol} interval="1h" limit={48} />
            </div>
          ))}
          {!ready ? <div className="corp-fs-loading">{t("st_unavailable")}</div> : null}
        </div>
      </div>
    </div>
  );
}
