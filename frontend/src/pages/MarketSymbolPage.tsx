import { Link, useParams } from "react-router-dom";
import { useEffect, useState } from "react";
import {
  STAGE_LABEL_ZH,
  fetchScannerSymbol,
  sideLabelZh,
  type MarketCandidate,
} from "../market/scannerApi";
import { formatUsd } from "../market/freshness";

function fmtPct(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function Sparkline({
  points,
}: {
  points: { t?: number; price?: number; oi?: number }[];
}) {
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
      <path d={d} fill="none" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

/**
 * Symbol detail — research only, no trade buttons.
 */
export function MarketSymbolPage() {
  const { symbol = "" } = useParams();
  const [advanced, setAdvanced] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [candidate, setCandidate] = useState<MarketCandidate | null>(null);
  const [snap, setSnap] = useState<Record<string, unknown> | null>(null);
  const [spark, setSpark] = useState<{ t?: number; price?: number; oi?: number }[]>([]);
  const [loading, setLoading] = useState(true);

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

  return (
    <div className="page-stack nx-symbol-page">
      <header className="nx-ov-header">
        <div className="nx-ov-meta">
          <Link to="/overview">總覽</Link>
          <Link to="/scanner">掃描器</Link>
          <Link to="/anomalies">異動</Link>
          <Link to="/anomaly-outcomes">結果研究</Link>
        </div>
        <h1 className="nx-page-title mono">{symbol.toUpperCase()}</h1>
        <p className="nx-status-line">Research mode · No trading · Public market data</p>
        <button type="button" className="nx-text-btn" onClick={() => setAdvanced((v) => !v)}>
          {advanced ? "簡易檢視" : "進階檢視"}
        </button>
      </header>

      {loading ? <p className="muted">載入中…</p> : null}
      {error ? (
        <div className="nx-banner-warn">
          {error === "symbol_not_in_universe"
            ? "此幣種目前不在掃描池（可能流動性不足或尚未納入）"
            : error}
        </div>
      ) : null}

      <section className="nx-symbol-hero">
        <div className="nx-pulse-num">{formatUsd(price)}</div>
        <div className="nx-cand-moves">
          <span>24h {fmtPct((snap?.change24hPct as number) ?? c?.change24hPct)}</span>
          <span>5m {fmtPct(c?.priceChange5mPct)}</span>
          <span>OI 5m {fmtPct(c?.oiChange5mPct)}</span>
        </div>
        {c ? (
          <div className="nx-symbol-badges">
            <span>{sideLabelZh(c.side)}</span>
            <span className={`nx-stage-badge nx-stage-${c.stage.toLowerCase()}`}>
              {STAGE_LABEL_ZH[c.stage]}
            </span>
            {c.rank != null ? <span>排名 #{c.rank}</span> : null}
          </div>
        ) : (
          <p className="muted">尚無方向候選（可能為中性或資料累積中）</p>
        )}
      </section>

      <section className="nx-chart-card">
        <h2 className="nx-sec-title">價格走勢</h2>
        <Sparkline points={spark} />
        <h3 className="nx-sec-title" style={{ marginTop: 12 }}>
          價格／持倉趨勢
        </h3>
        <div className="nx-dual-trend">
          {spark.slice(-12).map((p, i) => (
            <div key={i} className="nx-dual-col" title={String(p.price)}>
              <div
                className="nx-dual-price"
                style={{
                  height: `${12 + ((p.price || 0) % 40)}px`,
                }}
              />
              <div
                className="nx-dual-oi"
                style={{
                  height: `${8 + ((p.oi || 0) % 30)}px`,
                }}
              />
            </div>
          ))}
        </div>
        <p className="muted sm">上：價格樣本 · 下：持倉樣本（相對高度示意，非交易訊號）</p>
      </section>

      {c ? (
        <section className="nx-scores-block">
          <h2 className="nx-sec-title">分數</h2>
          <div className="nx-cand-scores lg">
            <div>
              <span className="nx-score-label">機會分數</span>
              <span className="nx-score-val">{Math.round(c.opportunityScore)}</span>
            </div>
            <div>
              <span className="nx-score-label">確認程度</span>
              <span className="nx-score-val">{Math.round(c.confirmationScore)}</span>
            </div>
            <div>
              <span className="nx-score-label">風險程度</span>
              <span className="nx-score-val nx-risk">{Math.round(c.riskScore)}</span>
            </div>
          </div>
          {advanced && c.scoreBreakdown ? (
            <div className="nx-breakdown muted">
              <pre className="mono">{JSON.stringify(c.scoreBreakdown, null, 2)}</pre>
            </div>
          ) : null}
          <ul className="nx-reason-list">
            {(c.reasons || []).map((r) => (
              <li key={r}>支持：{r}</li>
            ))}
            {(c.conflicts || []).map((r) => (
              <li key={r} className="conflict">
                衝突：{r}
              </li>
            ))}
          </ul>
          <p className="muted">失效條件：{c.invalidationContext}</p>
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
              <dt>Freshness</dt>
              <dd>{c?.freshness || "—"}</dd>
            </div>
            <div>
              <dt>Source</dt>
              <dd>BYBIT_MAINNET_LINEAR</dd>
            </div>
          </dl>
        </section>
      ) : null}

      <p className="muted">
        此頁為研究情報，不是交易指令。Signal Reference／異動結果請至研究層查看。
      </p>
    </div>
  );
}
