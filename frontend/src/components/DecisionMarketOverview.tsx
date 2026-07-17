import { Link } from "react-router-dom";
import { useEffect, useMemo, useRef, useState } from "react";
import { CompactSafetyStrip } from "./CompactSafetyStrip";
import { SimplifiedMarketDashboard } from "./SimplifiedMarketDashboard";
import { useLivePrice } from "../market/useLiveMarketFeed";
import { useMarketAnomalies } from "../market/useMarketAnomalies";
import { formatUsd } from "../market/freshness";
import {
  STAGE_LABEL_ZH,
  sideLabelZh,
  type MarketCandidate,
  type ScannerEvent,
} from "../market/scannerApi";
import { useMarketScannerOverview } from "../market/useMarketScanner";

function fmtPct(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

function fmtScore(v: number | null | undefined) {
  if (v == null) return "—";
  return Math.round(v).toString();
}

function CompactTickerChip({ symbol }: { symbol: "BTC" | "ETH" | "SOL" }) {
  const live = useLivePrice(symbol);
  const fresh = live?.connectionStatus || "DISCONNECTED";
  return (
    <div className="nx-ticker-chip">
      <span className="nx-ticker-sym">{symbol}</span>
      <span className="mono nx-ticker-px">{formatUsd(live?.lastPrice)}</span>
      <span className={`nx-fresh nx-fresh-${fresh.toLowerCase()}`}>{fresh}</span>
    </div>
  );
}

function CandidateCard({
  c,
  advanced,
}: {
  c: MarketCandidate;
  advanced: boolean;
}) {
  const stage = STAGE_LABEL_ZH[c.stage] || c.stage;
  return (
    <Link to={`/market/${c.symbol}`} className="nx-cand-card">
      <div className="nx-cand-top">
        <span className="nx-cand-rank">#{c.rank}</span>
        <span className="nx-cand-sym mono">{c.symbol.replace("USDT", "")}</span>
        <span className={`nx-stage-badge nx-stage-${c.stage.toLowerCase()}`}>{stage}</span>
      </div>
      <div className="nx-cand-price mono">{formatUsd(c.currentPrice)}</div>
      <div className="nx-cand-scores">
        <div>
          <span className="nx-score-label">機會</span>
          <span className="nx-score-val">{fmtScore(c.opportunityScore)}</span>
        </div>
        <div>
          <span className="nx-score-label">確認</span>
          <span className="nx-score-val">{fmtScore(c.confirmationScore)}</span>
        </div>
        <div>
          <span className="nx-score-label">風險</span>
          <span className="nx-score-val nx-risk">{fmtScore(c.riskScore)}</span>
        </div>
      </div>
      <div className="nx-cand-moves">
        <span>價 5m {fmtPct(c.priceChange5mPct)}</span>
        <span>OI 5m {fmtPct(c.oiChange5mPct)}</span>
      </div>
      <p className="nx-cand-reason">{c.reasons?.[0] || "觀察中"}</p>
      {advanced && c.conflicts?.[0] ? (
        <p className="nx-cand-conflict muted">衝突：{c.conflicts[0]}</p>
      ) : null}
      <div className="nx-cand-foot muted">
        {c.freshness} · {sideLabelZh(c.side)}
      </div>
    </Link>
  );
}

function MarketBreadthChart({
  breadth,
}: {
  breadth?: { rising: number; falling: number; neutral: number; insufficient: number };
}) {
  const b = breadth || { rising: 0, falling: 0, neutral: 0, insufficient: 0 };
  const total = Math.max(1, b.rising + b.falling + b.neutral + b.insufficient);
  const parts = [
    { key: "上漲", n: b.rising, cls: "up" },
    { key: "下跌", n: b.falling, cls: "down" },
    { key: "中性", n: b.neutral, cls: "neu" },
    { key: "累積中", n: b.insufficient, cls: "ins" },
  ];
  return (
    <div className="nx-chart-card">
      <h3 className="nx-sec-title">市場廣度</h3>
      <div className="nx-breadth-bar" role="img" aria-label="market breadth">
        {parts.map((p) => (
          <div
            key={p.key}
            className={`nx-breadth-seg nx-breadth-${p.cls}`}
            style={{ width: `${(p.n / total) * 100}%` }}
            title={`${p.key} ${p.n}`}
          />
        ))}
      </div>
      <div className="nx-breadth-legend">
        {parts.map((p) => (
          <div key={p.key} className="nx-breadth-item">
            <span className={`dot nx-breadth-${p.cls}`} />
            <span>{p.key}</span>
            <strong className="mono">{p.n}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function TurnoverChart({
  rows,
}: {
  rows: { symbol: string; turnover24h?: number; change24hPct?: number }[];
}) {
  const max = Math.max(1, ...rows.map((r) => r.turnover24h || 0));
  return (
    <div className="nx-chart-card">
      <h3 className="nx-sec-title">交易活躍度 Top 10</h3>
      <ul className="nx-turn-list">
        {rows.length === 0 ? (
          <li className="muted">等待掃描器資料…</li>
        ) : (
          rows.map((r) => (
            <li key={r.symbol}>
              <Link to={`/market/${r.symbol}`} className="nx-turn-row">
                <span className="mono">{r.symbol.replace("USDT", "")}</span>
                <span className="nx-turn-bar-wrap">
                  <span
                    className="nx-turn-bar"
                    style={{ width: `${((r.turnover24h || 0) / max) * 100}%` }}
                  />
                </span>
                <span className={`mono ${(r.change24hPct || 0) >= 0 ? "up" : "down"}`}>
                  {fmtPct(r.change24hPct)}
                </span>
              </Link>
            </li>
          ))
        )}
      </ul>
    </div>
  );
}

function EventToast({
  events,
  soundOn,
}: {
  events: ScannerEvent[];
  soundOn: boolean;
}) {
  const [toast, setToast] = useState<ScannerEvent | null>(null);
  const seen = useRef<Set<string>>(new Set());

  useEffect(() => {
    for (const ev of events) {
      if (seen.current.has(ev.id)) continue;
      seen.current.add(ev.id);
      if (seen.current.size > 200) {
        const arr = [...seen.current].slice(-100);
        seen.current = new Set(arr);
      }
      setToast(ev);
      if (soundOn) {
        try {
          const ctx = new window.AudioContext();
          const o = ctx.createOscillator();
          const g = ctx.createGain();
          o.connect(g);
          g.connect(ctx.destination);
          o.frequency.value = 660;
          g.gain.value = 0.03;
          o.start();
          o.stop(ctx.currentTime + 0.08);
        } catch {
          /* ignore */
        }
      }
      break;
    }
  }, [events, soundOn]);

  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(null), 4500);
    return () => window.clearTimeout(t);
  }, [toast]);

  if (!toast) return null;
  return (
    <div className="nx-toast" role="status">
      <strong>{toast.symbol.replace("USDT", "")}</strong>
      <span>{toast.explanation}</span>
    </div>
  );
}

/**
 * Decision-first market overview — Product Transformation Phase 1.
 * Candidates come from server-side scanner only (no browser full-market scan).
 */
export function DecisionMarketOverview() {
  const { status, longs, shorts, events, charts, error, loading } = useMarketScannerOverview();
  const anomalies = useMarketAnomalies();
  const [advanced, setAdvanced] = useState(false);
  const [mobileSide, setMobileSide] = useState<"LONG" | "SHORT">("LONG");
  const [soundOn, setSoundOn] = useState(false);
  const [notifyOn, setNotifyOn] = useState(false);

  const pulseBias = useMemo(() => {
    const b = status?.breadth;
    if (!b) return "混合";
    if (b.rising > b.falling * 1.25) return "偏多";
    if (b.falling > b.rising * 1.25) return "偏空";
    return "混合";
  }, [status]);

  const activeAnomalies = useMemo(
    () =>
      anomalies.filter((a) => a.status === "NEW" || a.status === "ACTIVE" || a.status === "COOLING")
        .length,
    [anomalies],
  );

  useEffect(() => {
    if (!notifyOn || !("Notification" in window) || Notification.permission !== "granted") return;
    const latest = events[0];
    if (!latest) return;
    try {
      new Notification("NEXUS 市場機會", { body: latest.explanation, silent: true });
    } catch {
      /* ignore */
    }
  }, [events, notifyOn]);

  return (
    <div className="nx-decision-overview" id="market-dashboard">
      <CompactSafetyStrip />
      <p className="sr-only">
        READ ONLY. Research mode. Live Mainnet public market data for display only. No trading.
      </p>

      <header className="nx-ov-header">
        <div className="nx-ov-title-block">
          <h1 className="nx-page-title">市場機會總覽</h1>
          <p className="nx-status-line">Live market data · Research mode · No trading</p>
        </div>
        <div className="nx-ticker-row">
          <CompactTickerChip symbol="BTC" />
          <CompactTickerChip symbol="ETH" />
          <CompactTickerChip symbol="SOL" />
        </div>
        <div className="nx-ov-meta muted">
          <span>{status?.freshness || (loading ? "COLLECTING" : "—")}</span>
          <span>
            更新{" "}
            {status?.lastCycleAt
              ? new Date(status.lastCycleAt).toLocaleTimeString()
              : "—"}
          </span>
          <button type="button" className="nx-text-btn" onClick={() => setAdvanced((v) => !v)}>
            {advanced ? "簡易檢視" : "進階檢視"}
          </button>
        </div>
        <details className="nx-tech-details">
          <summary className="muted">技術來源</summary>
          <p className="muted mono">
            Bybit Mainnet Public Linear · server scanner · researchOnly · private_api=false
          </p>
        </details>
      </header>

      {error ? (
        <div className="nx-banner-warn">掃描器暫不可用：{error}（本機開發需啟動 read-only web）</div>
      ) : null}

      <section className="nx-pulse" aria-label="Market pulse">
        <h2 className="nx-sec-title">市場脈搏</h2>
        <p className="nx-pulse-bias">
          目前市場整體：<strong className={`bias-${pulseBias}`}>{pulseBias}</strong>
        </p>
        <div className="nx-pulse-grid">
          <div className="nx-pulse-cell">
            <div className="nx-pulse-label">掃描幣種</div>
            <div className="nx-pulse-num">{status?.symbolCount ?? "—"}</div>
          </div>
          <div className="nx-pulse-cell">
            <div className="nx-pulse-label">做多機會</div>
            <div className="nx-pulse-num up">{status?.longCandidates ?? "—"}</div>
          </div>
          <div className="nx-pulse-cell">
            <div className="nx-pulse-label">做空機會</div>
            <div className="nx-pulse-num down">{status?.shortCandidates ?? "—"}</div>
          </div>
          <div className="nx-pulse-cell">
            <div className="nx-pulse-label">已確認</div>
            <div className="nx-pulse-num">{status?.confirmedCandidates ?? "—"}</div>
          </div>
          <div className="nx-pulse-cell">
            <div className="nx-pulse-label">過熱／高風險</div>
            <div className="nx-pulse-num risk">{status?.highRiskCandidates ?? "—"}</div>
          </div>
          <div className="nx-pulse-cell">
            <div className="nx-pulse-label">上漲／下跌</div>
            <div className="nx-pulse-num">
              {status?.breadth?.rising ?? "—"}/{status?.breadth?.falling ?? "—"}
            </div>
          </div>
          <div className="nx-pulse-cell">
            <div className="nx-pulse-label">重大異動</div>
            <div className="nx-pulse-num">{activeAnomalies || "0"}</div>
          </div>
          <div className="nx-pulse-cell">
            <div className="nx-pulse-label">掃描新鮮度</div>
            <div className="nx-pulse-num sm">{status?.freshness || "—"}</div>
          </div>
        </div>
      </section>

      <section className="nx-tops" aria-label="Top candidates">
        <div className="nx-tops-head">
          <h2 className="nx-sec-title">頂尖機會</h2>
          <Link to="/scanner" className="nx-link">
            完整掃描器 →
          </Link>
        </div>
        <p className="nx-cadence muted">
          候選約每 {status?.snapshotIntervalSec ?? 20} 秒重新掃描 · 非逐筆成交即時排名 · Research only
        </p>
        <div className="nx-side-tabs mobile-only">
          <button
            type="button"
            className={mobileSide === "LONG" ? "active" : ""}
            onClick={() => setMobileSide("LONG")}
          >
            做多
          </button>
          <button
            type="button"
            className={mobileSide === "SHORT" ? "active" : ""}
            onClick={() => setMobileSide("SHORT")}
          >
            做空
          </button>
        </div>
        <div className="nx-tops-grid">
          <div className={`nx-top-col ${mobileSide === "LONG" ? "show-mobile" : "hide-mobile"}`}>
            <h3 className="nx-col-title up">做多機會 Top 5</h3>
            <div className="nx-cand-list">
              {longs.length === 0 ? (
                <p className="muted">
                  {loading
                    ? "資料累積中…"
                    : status?.breadth?.insufficient &&
                        status.breadth.insufficient >= (status.symbolCount || 0)
                      ? "資料累積中：約 5 分鐘窗口建立後才會產生做多排名"
                      : "暫無符合條件的做多機會"}
                </p>
              ) : (
                longs.map((c) => <CandidateCard key={c.id} c={c} advanced={advanced} />)
              )}
            </div>
          </div>
          <div className={`nx-top-col ${mobileSide === "SHORT" ? "show-mobile" : "hide-mobile"}`}>
            <h3 className="nx-col-title down">做空機會 Top 5</h3>
            <div className="nx-cand-list">
              {shorts.length === 0 ? (
                <p className="muted">
                  {loading
                    ? "資料累積中…"
                    : status?.breadth?.insufficient &&
                        status.breadth.insufficient >= (status.symbolCount || 0)
                      ? "資料累積中：約 5 分鐘窗口建立後才會產生做空排名"
                      : "暫無符合條件的做空機會"}
                </p>
              ) : (
                shorts.map((c) => <CandidateCard key={c.id} c={c} advanced={advanced} />)
              )}
            </div>
          </div>
        </div>
      </section>

      <section className="nx-charts-grid" aria-label="Market charts">
        <MarketBreadthChart breadth={charts?.breadth || status?.breadth} />
        <TurnoverChart rows={charts?.turnoverTop10 || []} />
      </section>

      {advanced && charts?.priceOiQuadrant && charts.priceOiQuadrant.length > 0 ? (
        <section className="nx-chart-card nx-quadrant">
          <h3 className="nx-sec-title">價格／持倉象限（真實 5m 窗口）</h3>
          <div className="nx-quad-plot">
            {charts.priceOiQuadrant.slice(0, 40).map((p) => (
              <Link
                key={p.symbol}
                to={`/market/${p.symbol}`}
                className={`nx-quad-dot side-${p.side.toLowerCase()}`}
                style={{
                  left: `${50 + Math.max(-45, Math.min(45, p.priceChange5mPct * 8))}%`,
                  bottom: `${50 + Math.max(-45, Math.min(45, p.oiChange5mPct * 8))}%`,
                }}
                title={`${p.symbol} px ${p.priceChange5mPct}% oi ${p.oiChange5mPct}%`}
              />
            ))}
            <span className="nx-quad-axis-x">5m 價格 →</span>
            <span className="nx-quad-axis-y">5m OI ↑</span>
          </div>
        </section>
      ) : null}

      <section className="nx-events">
        <div className="nx-tops-head">
          <h2 className="nx-sec-title">即時市場事件</h2>
          <div className="nx-notify-opts">
            <label>
              <input type="checkbox" checked={soundOn} onChange={(e) => setSoundOn(e.target.checked)} />
              聲音
            </label>
            <label>
              <input
                type="checkbox"
                checked={notifyOn}
                onChange={async (e) => {
                  const on = e.target.checked;
                  if (on && "Notification" in window && Notification.permission !== "granted") {
                    await Notification.requestPermission();
                  }
                  setNotifyOn(on);
                }}
              />
              瀏覽器通知
            </label>
          </div>
        </div>
        <ul className="nx-event-list">
          {events.length === 0 ? (
            <li className="muted">尚無事件（排名變動與新機會會出現在此）</li>
          ) : (
            events.slice(0, 8).map((ev) => (
              <li key={ev.id}>
                <Link to={`/market/${ev.symbol}`}>
                  <span className="mono">{ev.symbol.replace("USDT", "")}</span>
                  <span>{ev.explanation}</span>
                  <time className="muted">{new Date(ev.timestamp).toLocaleTimeString()}</time>
                </Link>
              </li>
            ))
          )}
        </ul>
      </section>

      <section className="nx-research-layer">
        <h2 className="nx-sec-title">NEXUS 研究層</h2>
        <div className="nx-research-links">
          <Link to="/anomalies">異動雷達</Link>
          <Link to="/anomaly-outcomes">結果研究</Link>
          <Link to="/evidence">證據中心</Link>
          <Link to="/provider-shadow">Provider 驗證</Link>
          <Link to="/scanner">全市場掃描器</Link>
        </div>
      </section>

      <details className="nx-legacy-dash">
        <summary className="muted">固定幣種研究儀表板（保留）</summary>
        <SimplifiedMarketDashboard />
      </details>

      <EventToast events={events} soundOn={soundOn} />
    </div>
  );
}
