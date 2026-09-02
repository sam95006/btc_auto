/**
 * NEXUS-EXPERIENCE-1B — Personal Home. Answer-first, progressive disclosure by
 * view mode (Simple → +Evidence → +Data). All values are backend-provided
 * (member-safe market state + live tickers); nothing is fabricated. Capabilities
 * without licensed data render as honest COMING_SOON. No research/dev terminology.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useExperience } from "../../context/NexusExperience";
import { useWatchlist } from "../../context/WatchlistContext";
import { useLiveMarketTickers } from "../../hooks/useLiveMarketTickers";
import { getPersonalMarketState, type PersonalMarketState, type PersonalMarketSymbol } from "../../services/stagingApi";

const sym = (s: string) => s.replace("USDT", "");
const fmtPrice = (v?: number | null) =>
  typeof v === "number" ? v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: v >= 100 ? 2 : 5 }) : "—";
const fmtPct = (v?: number | null) => (typeof v === "number" ? `${v >= 0 ? "+" : ""}${v.toFixed(2)}%` : "—");

export function HomePage() {
  const { t, locale, view } = useExperience();
  const market = useLiveMarketTickers();
  const { symbols: wl } = useWatchlist();
  const [state, setState] = useState<PersonalMarketState | null | undefined>(undefined);

  useEffect(() => {
    let on = true;
    const load = () => getPersonalMarketState().then((s) => on && setState(s)).catch(() => on && setState(null));
    load();
    const id = window.setInterval(() => { if (!document.hidden) load(); }, 20000);
    return () => { on = false; window.clearInterval(id); };
  }, []);

  const ready = state?.availability === "READY";
  const regime = ready ? state!.regime?.value ?? null : null;
  const risk = ready ? state!.risk?.value ?? null : null;
  const stSymbols: PersonalMarketSymbol[] = ready ? state!.symbols ?? [] : [];

  const regimeLabel = regime === "RISK_ON" ? (locale === "zh-TW" ? "偏多" : "Risk-On")
    : regime === "RISK_OFF" ? (locale === "zh-TW" ? "防禦" : "Risk-Off")
    : regime === "NEUTRAL" ? (locale === "zh-TW" ? "中性" : "Neutral") : "—";
  const riskLabel = risk ? t(`r_${risk}`) : "—";
  const volLabel = (v?: string | null) => (v ? t(`v_${v}`) : "—");

  // What matters now (≤3), derived from real backend volatility/range. Honest.
  const attention = stSymbols
    .map((s) => {
      if (s.volatility === "high") return { s: sym(s.symbol), sev: "high" as const, t: t("attn_vol_high"), why: whyVol(s, locale) };
      if (typeof s.range_pct === "number" && s.range_pct >= 6) return { s: sym(s.symbol), sev: "med" as const, t: t("attn_range"), why: whyRange(s, locale) };
      return null;
    })
    .filter(Boolean)
    .slice(0, 3) as { s: string; sev: "high" | "med"; t: string; why: string }[];

  return (
    <div className="nx-home" data-view={view} data-testid="nx-home">
      <div className="nx-home-head">
        <div>
          <h1 className="nx-home-title">{t("today")}</h1>
          <p className="nx-home-sub">{t("source")}{ready && state!.updated_at ? ` · ${new Date(state!.updated_at).toLocaleTimeString()}` : ""}</p>
        </div>
      </div>

      {/* 1. Market state + risk */}
      <div className="nx-state">
        <div className="nx-state-card"><div className="k">{t("market_state")}</div>
          <div className={`v ${ready ? "" : "muted"}`} data-state={regime ?? undefined}>{ready ? regimeLabel : (state === undefined ? t("loading") : t("unavailable"))}</div></div>
        <div className="nx-state-card"><div className="k">{t("market_risk")}</div>
          <div className={`v ${risk === "elevated" ? "warn" : ""} ${risk ? "" : "muted"}`}>{ready ? riskLabel : "—"}</div></div>
      </div>

      {/* 2. BTC / ETH / SOL live strip */}
      <div className="nx-strip">
        {(market.tickers.length ? market.tickers : [{ symbol: "BTCUSDT", price: NaN, change24hPct: NaN }, { symbol: "ETHUSDT", price: NaN, change24hPct: NaN }, { symbol: "SOLUSDT", price: NaN, change24hPct: NaN }]).slice(0, 3).map((tk) => (
          <Link key={tk.symbol} to={`/app/market/${sym(tk.symbol)}`}>
            <span className="s">{sym(tk.symbol)}</span>
            <span className="p">{Number.isNaN(tk.price) ? "—" : `$${fmtPrice(tk.price)}`}</span>
            <span className={`c ${tk.change24hPct >= 0 ? "bull" : "bear"}`}>{Number.isNaN(tk.change24hPct) ? "—" : fmtPct(tk.change24hPct)}</span>
          </Link>
        ))}
      </div>

      {/* 3. What matters now (≤3) */}
      <section className="nx-sec">
        <div className="nx-sec-h"><h2>{t("what_matters")}</h2></div>
        {attention.length ? (
          <div className="nx-attn">
            {attention.map((a, i) => <AttentionRow key={i} a={a} whyLabel={t("why")} />)}
          </div>
        ) : (
          <p className="nx-empty">{ready ? t("no_attention") : (state === undefined ? t("loading") : t("unavailable"))}</p>
        )}
      </section>

      {/* 4. Watchlist */}
      <section className="nx-sec">
        <div className="nx-sec-h"><h2>{t("watchlist")}</h2><Link className="more" to="/app/watchlist">→</Link></div>
        {wl.length ? (
          <div className="nx-wl">
            {wl.slice(0, 6).map((s) => {
              const tk = market.tickers.find((x) => sym(x.symbol) === sym(s));
              return (
                <Link key={s} to={`/app/market/${sym(s)}`} className="nx-wl-row">
                  <span className="s">{sym(s)}</span>
                  <span className="p">{tk ? `$${fmtPrice(tk.price)}` : "—"}</span>
                  <span className={`c ${tk && tk.change24hPct >= 0 ? "bull" : "bear"}`}>{tk ? fmtPct(tk.change24hPct) : "—"}</span>
                </Link>
              );
            })}
          </div>
        ) : <p className="nx-empty">{t("watchlist_empty")}</p>}
      </section>

      {/* 5. Daily brief — deterministic, PARTIAL (built from backend states only) */}
      <section className="nx-sec nx-brief nx-standard-only">
        <div className="nx-sec-h"><h2>{t("brief")}</h2><span className="nx-badge partial">PARTIAL</span></div>
        {ready ? (
          <>
            {briefLines(regimeLabel, stSymbols, locale, volLabel).map((line, i) => <p key={i}>{line}</p>)}
            <p className="meta">{t("brief_note")}</p>
          </>
        ) : <p className="nx-empty">{state === undefined ? t("loading") : t("unavailable")}</p>}
      </section>

      {/* 6. Latest intelligence — honest COMING_SOON (no licensed data) */}
      <section className="nx-sec">
        <div className="nx-sec-h"><h2>{t("latest_intel")}</h2><span className="nx-badge soon">COMING SOON</span></div>
        <div className="nx-cap-grid">
          {["News", "Social", "Smart Money", "Derivatives"].map((c) => (
            <div className="nx-cap" key={c}><h3>{c} <span className="nx-badge soon">SOON</span></h3><p>{t("intel_soon")}</p></div>
          ))}
        </div>
      </section>

      {/* PRO: provenance / data panel (no fake workspace) */}
      <section className="nx-sec nx-pro-only">
        <div className="nx-sec-h"><h2>Data & provenance</h2></div>
        <div className="nx-wl">
          {stSymbols.map((s) => (
            <div key={s.symbol} className="nx-wl-row">
              <span className="s">{sym(s.symbol)}</span>
              <span className="p">{typeof s.range_pct === "number" ? `24H ${s.range_pct.toFixed(2)}%` : "—"}</span>
              <span className="c">{volLabel(s.volatility)}</span>
            </div>
          ))}
        </div>
        <p className="meta" style={{ marginTop: "0.6rem" }}>{t("source")} · {ready ? state!.freshness : "—"}</p>
      </section>
    </div>
  );
}

function AttentionRow({ a, whyLabel }: { a: { s: string; sev: string; t: string; why: string }; whyLabel: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <div className="nx-attn-item" data-sev={a.sev}>
        <span className="nx-attn-sym">{a.s}</span>
        <div className="nx-attn-body"><div className="t">{a.t}</div></div>
        <button className="nx-why" aria-expanded={open} onClick={() => setOpen((v) => !v)}>{whyLabel}</button>
      </div>
      {open ? <div className="nx-drawer"><h4>{whyLabel}</h4><p>{a.why}</p></div> : null}
    </div>
  );
}

function whyVol(s: PersonalMarketSymbol, locale: string): string {
  const r = typeof s.range_pct === "number" ? `${s.range_pct.toFixed(2)}%` : "—";
  return locale === "zh-TW"
    ? `後端依 24H 波動區間（${r}）判定波動偏高。此為市場觀察，非交易建議。`
    : `The backend classifies volatility as high from the 24H range (${r}). Observation only — not trading advice.`;
}
function whyRange(s: PersonalMarketSymbol, locale: string): string {
  const r = typeof s.range_pct === "number" ? `${s.range_pct.toFixed(2)}%` : "—";
  return locale === "zh-TW"
    ? `24H 價格區間擴大至 ${r}，代表波動正在增加。`
    : `The 24H price range has widened to ${r}, indicating rising movement.`;
}

function briefLines(regimeLabel: string, symbols: PersonalMarketSymbol[], locale: string, volLabel: (v?: string | null) => string): string[] {
  const lines: string[] = [];
  lines.push(locale === "zh-TW" ? `市場目前${regimeLabel}。` : `The market is currently ${regimeLabel}.`);
  symbols.forEach((s) => {
    if (s.volatility) lines.push(`${sym(s.symbol)} · ${volLabel(s.volatility)}`);
  });
  return lines;
}
