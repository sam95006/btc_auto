import { Link, useParams } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import {
  STAGE_LABEL_ZH,
  fetchScannerSymbol,
  plainReason,
  sideLabelZh,
  type MarketCandidate,
} from "../market/scannerApi";
import { formatUsd } from "../market/freshness";
import { WatchStarButton } from "../components/WatchStarButton";
import { NexusOhlcvChart } from "../components/NexusOhlcvChart";
import { loadViewMode, saveViewMode, type ViewMode } from "../market/viewPrefs";

function fmtPct(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function Sparkline({ points }: { points: { t?: number; price?: number; oi?: number }[] }) {
  const prices = points.map((p) => p.price).filter((n): n is number => n != null && n > 0);
  if (prices.length < 2) {
    return <p className="muted">價格走勢：資料累積中</p>;
  }
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const span = Math.max(1e-9, max - min);
  const w = 320;
  const h = 72;
  const d = prices
    .map((p, i) => {
      const x = (i / (prices.length - 1)) * w;
      const y = h - ((p - min) / span) * (h - 8) - 4;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg className="nx-spark" viewBox={`0 0 ${w} ${h}`} width="100%" height="72" aria-hidden>
      <path d={d} fill="none" stroke="var(--nx-accent, currentColor)" strokeWidth="2" />
    </svg>
  );
}

function PriceOiTrend({ points }: { points: { price?: number; oi?: number }[] }) {
  const slice = points.filter((p) => p.price != null && p.price > 0).slice(-16);
  if (slice.length < 2) return <p className="muted">價格／持倉關係：資料累積中</p>;
  const prices = slice.map((p) => p.price as number);
  const ois = slice.map((p) => (p.oi != null && p.oi > 0 ? p.oi : null));
  const pMin = Math.min(...prices);
  const pMax = Math.max(...prices);
  const oiVals = ois.filter((n): n is number => n != null);
  const oMin = oiVals.length ? Math.min(...oiVals) : 0;
  const oMax = oiVals.length ? Math.max(...oiVals) : 1;
  const w = 320;
  const h = 80;
  const pricePath = prices
    .map((p, i) => {
      const x = (i / (prices.length - 1)) * w;
      const y = h - ((p - pMin) / Math.max(1e-9, pMax - pMin)) * (h - 10) - 5;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const oiPath = ois
    .map((o, i) => {
      if (o == null) return null;
      const x = (i / (prices.length - 1)) * w;
      const y = h - ((o - oMin) / Math.max(1e-9, oMax - oMin)) * (h - 10) - 5;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .filter(Boolean);
  return (
    <svg className="nx-spark" viewBox={`0 0 ${w} ${h}`} width="100%" height="80" aria-hidden>
      <path d={pricePath} fill="none" stroke="var(--nx-text)" strokeWidth="2" />
      {oiPath.length > 1 ? (
        <polyline
          fill="none"
          stroke="var(--nx-long)"
          strokeWidth="1.5"
          strokeDasharray="4 3"
          points={oiPath.join(" ")}
        />
      ) : null}
    </svg>
  );
}

function ScoreBars({ c }: { c: MarketCandidate }) {
  const bd = c.scoreBreakdown;
  const rows: { label: string; value: number }[] = [];
  if (bd) {
    for (const [k, v] of bd.opportunity || []) rows.push({ label: k, value: v });
    for (const [k, v] of bd.confirmation || []) rows.push({ label: k, value: v });
    for (const [k, v] of bd.risk || []) rows.push({ label: `風險·${k}`, value: v });
  } else {
    rows.push(
      { label: "機會", value: c.opportunityScore },
      { label: "確認", value: c.confirmationScore },
      { label: "風險", value: c.riskScore },
    );
  }
  const labelZh = (k: string) =>
    k
      .replace(/momentum/i, "動能")
      .replace(/oi[_ ]?confirm/i, "持倉確認")
      .replace(/activity/i, "活躍度")
      .replace(/liquidity/i, "流動性")
      .replace(/freshness/i, "新鮮度")
      .replace(/crowding/i, "擁擠風險")
      .replace(/overextension/i, "過熱風險");

  return (
    <ul className="nx-score-bars">
      {rows.slice(0, 8).map((r) => (
        <li key={r.label}>
          <span>{labelZh(r.label)}</span>
          <div className="nx-conf-bar">
            <div style={{ width: `${Math.min(100, Math.abs(r.value))}%` }} />
          </div>
          <span className="mono">{Math.round(r.value)}</span>
        </li>
      ))}
    </ul>
  );
}

/**
 * Symbol detail — Phase 2 market intelligence page (research only).
 */
export function MarketSymbolPage() {
  const { symbol = "" } = useParams();
  const [view, setView] = useState<ViewMode>(() => loadViewMode());
  const [error, setError] = useState<string | null>(null);
  const [candidate, setCandidate] = useState<MarketCandidate | null>(null);
  const [snap, setSnap] = useState<Record<string, unknown> | null>(null);
  const [spark, setSpark] = useState<{ t?: number; price?: number; oi?: number }[]>([]);
  const [loading, setLoading] = useState(true);
  const advanced = view === "advanced";
  const simple = view === "simple";

  useEffect(() => {
    const onView = (e: Event) => {
      const mode = (e as CustomEvent<ViewMode>).detail;
      if (mode === "simple" || mode === "advanced") setView(mode);
    };
    window.addEventListener("nexus-view-mode", onView);
    return () => window.removeEventListener("nexus-view-mode", onView);
  }, []);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const body = await fetchScannerSymbol(symbol.toUpperCase());
        if (!alive) return;
        if (!body.ok) {
          setError(body.error || "not_found");
          setCandidate(null);
          setSnap(null);
        } else {
          setError(null);
          setCandidate(body.candidate || null);
          setSnap(body.snapshot || null);
          setSpark(body.sparkline || []);
        }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : "load_failed");
      } finally {
        if (alive) setLoading(false);
      }
    };
    void load();
    const id = window.setInterval(() => void load(), 12_000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [symbol]);

  const c = candidate;
  const price = (snap?.lastPrice as number | undefined) ?? c?.currentPrice;

  const supports = useMemo(() => {
    if (!c) return [] as string[];
    const out: string[] = [];
    for (const r of c.reasons || []) {
      if (out.length >= 4) break;
      out.push(plainReason(r, simple));
    }
    if (out.length === 0 && c.priceChange5mPct != null) {
      out.push(`近 5 分鐘價格變動 ${fmtPct(c.priceChange5mPct)}`);
    }
    return out;
  }, [c, simple]);

  const risks = useMemo(() => {
    if (!c) return [] as string[];
    const out: string[] = [];
    for (const r of c.conflicts || []) {
      if (out.length >= 4) break;
      out.push(plainReason(r, simple));
    }
    if (c.stage === "OVEREXTENDED") out.unshift("過熱勿追：動能可能已過度延伸");
    if (c.riskScore >= 70 && out.length < 4) out.push(`風險分數偏高（${Math.round(c.riskScore)}）`);
    if (out.length === 0) out.push("目前未偵測到明顯衝突");
    return out.slice(0, 4);
  }, [c, simple]);

  return (
    <div className="page-stack nx-symbol-page nx-p2">
      <header className="nx-ov-header">
        <div className="nx-ov-meta">
          <Link to="/overview">總覽</Link>
          <Link to="/scanner">掃描</Link>
          <Link to="/watchlist">關注</Link>
        </div>
        <div className="nx-sym-title-row">
          <h1 className="nx-page-title mono">{symbol.toUpperCase().replace("USDT", "")}</h1>
          <WatchStarButton symbol={symbol.toUpperCase()} />
        </div>
        <p className="nx-status-line">研究模式 · 不執行交易 · 公開市場資料</p>
        <button
          type="button"
          className="nx-text-btn"
          onClick={() => {
            const next: ViewMode = view === "simple" ? "advanced" : "simple";
            setView(next);
            saveViewMode(next);
          }}
        >
          {advanced ? "簡易檢視" : "進階檢視"}
        </button>
      </header>

      {loading ? <p className="muted">載入中…</p> : null}
      {error ? (
        <div className="nx-banner-warn">
          {error === "symbol_not_in_universe"
            ? "此幣種目前不在掃描池（可能流動性不足或尚未納入）"
            : error === "not_found"
              ? "未知標的或尚無資料"
              : "資料暫時無法取得，請稍後重試"}
        </div>
      ) : null}

      <section className="nx-symbol-hero">
        <div className="nx-pulse-num">{formatUsd(price)}</div>
        <div className="nx-cand-moves">
          <span>24h {fmtPct((snap?.change24hPct as number) ?? c?.change24hPct)}</span>
          <span>5m 價 {fmtPct(c?.priceChange5mPct)}</span>
          <span>5m 持倉 {fmtPct(c?.oiChange5mPct)}</span>
          <span className="muted">{c?.freshness || "—"}</span>
        </div>
        {c ? (
          <div className="nx-symbol-badges">
            <span className={`nx-side-mark side-${c.side.toLowerCase()}`}>
              {c.side === "LONG" ? "▲" : "▼"} {sideLabelZh(c.side)}
            </span>
            <span className={`nx-stage-badge nx-stage-${c.stage.toLowerCase()}`}>
              {STAGE_LABEL_ZH[c.stage]}
            </span>
            {c.rank != null ? <span>排名 #{c.rank}</span> : null}
            {c.rankDelta != null && c.rankDelta !== 0 ? (
              <span>{c.rankDelta > 0 ? `↑${c.rankDelta}` : `↓${Math.abs(c.rankDelta)}`}</span>
            ) : null}
          </div>
        ) : (
          <p className="muted">尚無方向候選（可能為中性或資料累積中）</p>
        )}
        {c ? (
          <div className="nx-spot-scores hero">
            <div className="nx-opp-primary">
              <span className="nx-score-label">機會</span>
              <span className="nx-score-val lg">{Math.round(c.opportunityScore)}</span>
            </div>
            <div className="nx-conf-bar-wrap">
              <span className="nx-score-label">確認</span>
              <div className="nx-conf-bar">
                <div style={{ width: `${Math.min(100, c.confirmationScore)}%` }} />
              </div>
            </div>
            <div className={`nx-risk-chip ${c.riskScore >= 70 ? "hot" : ""}`}>
              風險 {Math.round(c.riskScore)}
            </div>
          </div>
        ) : null}
      </section>

      {c ? (
        <section className="nx-why-grid">
          <h2 className="nx-sec-title">為什麼是候選</h2>
          <div className="nx-why-cols">
            <div>
              <h3>支持因素</h3>
              <ul>
                {supports.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </div>
            <div>
              <h3>主要風險</h3>
              <ul>
                {risks.map((s) => (
                  <li key={s} className="conflict">
                    {s}
                  </li>
                ))}
              </ul>
            </div>
          </div>
          {c.invalidationContext ? (
            <p className="muted sm">失效觀察：{plainReason(c.invalidationContext, simple)}</p>
          ) : null}
        </section>
      ) : null}

      <section className="nx-chart-card nx-ohlcv-wrap">
        <h2 className="nx-sec-title">NEXUS 圖表（交易所公開資料）</h2>
        <p className="muted sm">Bybit Public → NEXUS datafeed · 非 TradingView 行情來源</p>
        <NexusOhlcvChart symbol={symbol} advanced={advanced} />
      </section>

      <section className="nx-chart-card">
        <h2 className="nx-sec-title">短期價格走勢（掃描器窗口）</h2>
        <Sparkline points={spark} />
      </section>

      <section className="nx-chart-card">
        <h2 className="nx-sec-title">價格與持倉關係</h2>
        <p className="muted sm">實線＝價格 · 虛線＝持倉（有資料時）</p>
        <PriceOiTrend points={spark} />
      </section>

      <section className="nx-chart-card">
        <h2 className="nx-sec-title">交易活躍度</h2>
        <p className="mono">
          {c?.turnoverPace != null
            ? `活躍度指標 ${c.turnoverPace.toFixed(3)}（相對掃描池）`
            : snap?.turnover24h != null
              ? `24h turnover ${String(snap.turnover24h)}`
              : "活躍度：資料累積中"}
        </p>
      </section>

      {c ? (
        <section className="nx-chart-card">
          <h2 className="nx-sec-title">候選分數結構</h2>
          <ScoreBars c={c} />
          <p className="muted sm">
            階段：{STAGE_LABEL_ZH[c.stage]} · 首次見{" "}
            {c.firstSeenAt ? new Date(c.firstSeenAt).toLocaleTimeString() : "—"} · 更新{" "}
            {c.lastUpdatedAt ? new Date(c.lastUpdatedAt).toLocaleTimeString() : "—"}
          </p>
        </section>
      ) : null}

      {advanced && snap ? (
        <section className="nx-chart-card">
          <h2 className="nx-sec-title">進階市場欄位</h2>
          <dl className="nx-kv mono">
            <div>
              <dt>Mark</dt>
              <dd>{formatUsd(snap.markPrice as number)}</dd>
            </div>
            <div>
              <dt>Index</dt>
              <dd>{formatUsd(snap.indexPrice as number)}</dd>
            </div>
            <div>
              <dt>OI Value</dt>
              <dd>{String(snap.openInterestValue ?? "—")}</dd>
            </div>
            <div>
              <dt>Funding</dt>
              <dd>{String(snap.fundingRate ?? "—")}</dd>
            </div>
            <div>
              <dt>Turnover 24h</dt>
              <dd>{String(snap.turnover24h ?? "—")}</dd>
            </div>
            <div>
              <dt>Spread bps</dt>
              <dd>{String(snap.spreadBps ?? "—")}</dd>
            </div>
            <div>
              <dt>Source</dt>
              <dd>BYBIT_MAINNET_LINEAR</dd>
            </div>
          </dl>
          {c?.scoreBreakdown ? (
            <pre className="mono muted sm">{JSON.stringify(c.scoreBreakdown, null, 2)}</pre>
          ) : null}
        </section>
      ) : null}

      <section className="nx-research-layer">
        <h2 className="nx-sec-title">研究層</h2>
        <div className="nx-research-links">
          <Link to="/anomalies">異動雷達</Link>
          <Link to="/anomaly-outcomes">結果追蹤</Link>
          <Link to="/evidence">證據</Link>
          <Link to="/provider-shadow">Provider 驗證</Link>
          <Link to="/signals">Signal Reference</Link>
        </div>
      </section>
    </div>
  );
}
