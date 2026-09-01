/**
 * Hero live-market console — a real product panel, not a marketing card.
 * Primary symbol (BTC) shown large with regime / volatility / risk chips and a
 * backend sparkline; ETH / SOL as compact rows. Every value is backend-provided;
 * unavailable data renders explicitly. Price colour flashes on real updates only.
 */
import { useEffect, useRef, useState } from "react";
import { useMarket } from "../../context/MarketContext";
import { useLocale, type Locale } from "../../i18n";
import { fmtPct, fmtPrice, symOf } from "../../lib/format";
import { regimeLabel, riskLabel, volLabel } from "../../lib/marketLabels";
import type { MarketSymbol } from "../../types";
import { Sparkline } from "./Sparkline";

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
  const { locale, t } = useLocale();

  if (m.status !== "READY") {
    const label = m.status === "LOADING" ? t("st_loading") : t("st_unavailable");
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
          <PrimaryBlock s={primary} regime={regime} risk={risk} locale={locale} />
        ) : (
          <div className="corp-fs-unavail">{t("st_unavailable")}</div>
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
        <span>Source · {d.source}</span>
        <span>{d.freshness}</span>
      </div>
    </div>
  );
}

function PrimaryBlock({ s, regime, risk, locale }: { s: MarketSymbol; regime: string | null; risk: string | null; locale: Locale }) {
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
          <div className={`v ${regime ? "" : "muted"}`} data-state={regime ?? undefined}>{regimeLabel(regime, locale)}</div>
        </div>
        <div className="corp-fs-metric">
          <div className="k">Volatility</div>
          <div className={`v ${s.volatility === "high" ? "warn" : ""} ${s.volatility ? "" : "muted"}`}>{volLabel(s.volatility, locale)}</div>
        </div>
        <div className="corp-fs-metric">
          <div className="k">Risk</div>
          <div className={`v ${risk === "elevated" ? "warn" : ""} ${risk ? "" : "muted"}`}>{riskLabel(risk, locale)}</div>
        </div>
      </div>
    </>
  );
}
