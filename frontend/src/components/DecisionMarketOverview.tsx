import { Link } from "react-router-dom";
import { useEffect, useMemo, useRef, useState } from "react";
import { SimplifiedMarketDashboard } from "./SimplifiedMarketDashboard";
import { WatchStarButton } from "./WatchStarButton";
import { useLivePrice } from "../market/useLiveMarketFeed";
import { useMarketAnomalies } from "../market/useMarketAnomalies";
import { formatUsd } from "../market/freshness";
import {
  STAGE_LABEL_ZH,
  plainReason,
  sideLabelZh,
  type MarketCandidate,
  type ScannerEvent,
} from "../market/scannerApi";
import { useMarketScannerOverview } from "../market/useMarketScanner";
import { buildMarketSummary, deriveRegime } from "../market/marketSummary";
import { loadViewMode, type ViewMode } from "../market/viewPrefs";
import {
  isHighPriorityEvent,
  loadEventPrefs,
  type EventPrefs,
} from "../market/eventPrefs";
import { shouldEmitNotification } from "../market/notificationPrefs";
import { fetchSectors, type SectorRow } from "../market/sectorApi";

function CollectingPanel({
  startedAt,
  status,
}: {
  startedAt?: number | null;
  status: ReturnType<typeof useMarketScannerOverview>["status"];
}) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);
  const WINDOW_MS = 5 * 60 * 1000;
  const start = startedAt || status?.lastCycleAt || now;
  const elapsed = Math.max(0, now - start);
  const remain = Math.max(0, WINDOW_MS - elapsed);
  const elapsedSec = Math.floor(elapsed / 1000);
  const remainSec = Math.floor(remain / 1000);
  const mm = String(Math.floor(elapsedSec / 60)).padStart(1, "0");
  const ss = String(elapsedSec % 60).padStart(2, "0");
  const rmm = String(Math.floor(remainSec / 60)).padStart(1, "0");
  const rss = String(remainSec % 60).padStart(2, "0");
  const priceReady = (status?.symbolCount || 0) > 0;
  const breadthReady = Boolean(status?.breadth && (status.breadth.rising || status.breadth.falling || status.breadth.neutral));
  const windowReady = Boolean(topCandidatesReady(status));
  return (
    <section className="nx-collecting-panel" aria-label="Collecting progress">
      <div className="nx-collect-head">
        <strong>正在建立短期市場結構</strong>
        <span className="mono muted">
          {mm}:{ss} / 約 5:00 · 剩餘約 {rmm}:{rss}
        </span>
      </div>
      <ul className="nx-collect-checks">
        <li className={priceReady ? "done" : ""}>{priceReady ? "✓" : "○"} 即時價格</li>
        <li className={breadthReady ? "done" : ""}>{breadthReady ? "✓" : "○"} 市場廣度</li>
        <li className="done">✓ Funding（點值）</li>
        <li className="done">✓ 交易活躍度</li>
        <li className={windowReady ? "done" : ""}>{windowReady ? "✓" : "○"} 5m 價格窗口</li>
        <li className={windowReady ? "done" : ""}>{windowReady ? "✓" : "○"} 5m 持倉窗口</li>
      </ul>
      <p className="muted sm">預計約數分鐘後產生候選排名 · 不會顯示假候選</p>
    </section>
  );
}

function topCandidatesReady(status: ReturnType<typeof useMarketScannerOverview>["status"]) {
  const insuff = status?.breadth?.insufficient ?? 0;
  const n = status?.symbolCount ?? 0;
  if (!n) return false;
  return insuff < n * 0.7;
}

function fmtPct(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

function fmtScore(v: number | null | undefined) {
  if (v == null) return "—";
  return Math.round(v).toString();
}

function rankMove(c: MarketCandidate) {
  const d = c.rankDelta;
  if (d == null || d === 0) return { label: "—", cls: "flat" };
  if (d > 0) return { label: `↑${d}`, cls: "up" };
  return { label: `↓${Math.abs(d)}`, cls: "down" };
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

function MiniSpark({ c }: { c: MarketCandidate }) {
  const px = c.priceChange5mPct ?? 0;
  const oi = c.oiChange5mPct ?? 0;
  const w = 72;
  const h = 28;
  const yPx = 14 - Math.max(-12, Math.min(12, px * 2));
  const yOi = 14 - Math.max(-12, Math.min(12, oi * 2));
  return (
    <svg className="nx-mini-spark" viewBox={`0 0 ${w} ${h}`} width={w} height={h} aria-hidden>
      <polyline
        fill="none"
        stroke="var(--nx-text-2)"
        strokeWidth="1.5"
        points={`4,${yPx} 36,${14 - px} 68,${yOi}`}
      />
    </svg>
  );
}

function SpotlightCard({ c, simple }: { c: MarketCandidate; simple: boolean }) {
  const stage = STAGE_LABEL_ZH[c.stage] || c.stage;
  const move = rankMove(c);
  const reason = plainReason(c.reasons?.[0] || "結構仍在觀察", simple);
  const risk = plainReason(c.conflicts?.[0] || (c.riskScore >= 70 ? "風險偏高，請留意過熱" : "主要風險尚低"), simple);
  return (
    <article className={`nx-spotlight side-${c.side.toLowerCase()}`}>
      <div className="nx-spot-head">
        <span className="nx-spot-rank">#{c.rank}</span>
        <span className={`nx-side-mark side-${c.side.toLowerCase()}`}>
          {c.side === "LONG" ? "▲ 做多" : "▼ 做空"}
        </span>
        <WatchStarButton symbol={c.symbol} />
      </div>
      <Link to={`/market/${c.symbol}`} className="nx-spot-main">
        <h3 className="nx-spot-sym mono">{c.symbol.replace("USDT", "")}</h3>
        <div className="nx-spot-price mono">{formatUsd(c.currentPrice)}</div>
        <div className="nx-spot-moves">
          <span>價 5m {fmtPct(c.priceChange5mPct)}</span>
          <span>持倉 5m {fmtPct(c.oiChange5mPct)}</span>
          <span className={`nx-rank-move ${move.cls}`}>{move.label}</span>
        </div>
        <div className="nx-spot-scores">
          <div className="nx-opp-primary">
            <span className="nx-score-label">機會</span>
            <span className="nx-score-val lg">{fmtScore(c.opportunityScore)}</span>
          </div>
          <div className="nx-conf-bar-wrap" title="確認程度">
            <span className="nx-score-label">確認</span>
            <div className="nx-conf-bar">
              <div style={{ width: `${Math.min(100, c.confirmationScore)}%` }} />
            </div>
            <span className="mono sm">{fmtScore(c.confirmationScore)}</span>
          </div>
          <div className={`nx-risk-chip ${c.riskScore >= 70 ? "hot" : ""}`}>
            風險 {fmtScore(c.riskScore)}
          </div>
        </div>
        <p className="nx-spot-stage">{stage}</p>
        <p className="nx-spot-reason">{reason}</p>
        <p className="nx-spot-risk">{risk}</p>
        <div className="nx-spot-foot">
          <MiniSpark c={c} />
          <span className="muted">{c.freshness}</span>
          <span className="nx-spot-cta">查看詳情 →</span>
        </div>
      </Link>
    </article>
  );
}

function CompactRankRow({ c, simple }: { c: MarketCandidate; simple: boolean }) {
  const move = rankMove(c);
  return (
    <Link to={`/market/${c.symbol}`} className="nx-compact-row">
      <span className="nx-cand-rank">#{c.rank}</span>
      <span className="mono nx-cand-sym">{c.symbol.replace("USDT", "")}</span>
      <span className="nx-opp-sm mono">{fmtScore(c.opportunityScore)}</span>
      <span className="nx-stage-sm">{STAGE_LABEL_ZH[c.stage]}</span>
      <span className={`dir ${(c.priceChange5mPct || 0) >= 0 ? "up" : "down"}`}>
        價{fmtPct(c.priceChange5mPct)}
      </span>
      <span className="nx-reason-sm">{plainReason(c.reasons?.[0] || "—", simple)}</span>
      <span className={`nx-risk-dot ${c.riskScore >= 70 ? "hot" : ""}`} title={`風險 ${fmtScore(c.riskScore)}`} />
      <span className={`nx-rank-move ${move.cls}`}>{move.label}</span>
      <WatchStarButton symbol={c.symbol} />
    </Link>
  );
}

function CandidateCard({ c, simple }: { c: MarketCandidate; simple: boolean }) {
  const stage = STAGE_LABEL_ZH[c.stage] || c.stage;
  const move = rankMove(c);
  return (
    <div className="nx-cand-card nx-cand-card-p2">
      <Link to={`/market/${c.symbol}`} className="nx-cand-link">
        <div className="nx-cand-top">
          <span className="nx-cand-rank">#{c.rank}</span>
          <span className="nx-cand-sym mono">{c.symbol.replace("USDT", "")}</span>
          <span className={`nx-side-mark side-${c.side.toLowerCase()}`}>
            {c.side === "LONG" ? "▲" : "▼"} {sideLabelZh(c.side)}
          </span>
        </div>
        <p className="nx-stage-line">{stage}</p>
        <div className="nx-opp-primary inline">
          <span className="nx-score-label">機會</span>
          <span className="nx-score-val">{fmtScore(c.opportunityScore)}</span>
        </div>
        <p className="nx-cand-reason">{plainReason(c.reasons?.[0] || "觀察中", simple)}</p>
        <div className="nx-conf-bar-wrap">
          <span className="nx-score-label">確認</span>
          <div className="nx-conf-bar">
            <div style={{ width: `${Math.min(100, c.confirmationScore)}%` }} />
          </div>
        </div>
        <p className="nx-cand-conflict">
          風險：{plainReason(c.conflicts?.[0] || `分數 ${fmtScore(c.riskScore)}`, simple)}
        </p>
        <div className="nx-cand-moves">
          <span>價 {fmtPct(c.priceChange5mPct)}</span>
          <span>持倉 {fmtPct(c.oiChange5mPct)}</span>
          <span className={`nx-rank-move ${move.cls}`}>{move.label}</span>
        </div>
        <div className="nx-cand-foot muted">{c.freshness}</div>
      </Link>
      <WatchStarButton symbol={c.symbol} className="nx-card-star" />
    </div>
  );
}

function LongShortBalance({ longs, shorts, insuff }: { longs: number; shorts: number; insuff: number }) {
  const total = Math.max(1, longs + shorts + insuff);
  return (
    <div className="nx-balance-block">
      <h3 className="nx-sec-title">多空候選分布</h3>
      <p className="muted sm">這是掃描候選數量分布，不是市場勝率或帳戶持倉比。</p>
      <div className="nx-balance-bar" role="img" aria-label="long short balance">
        <div className="seg long" style={{ width: `${(longs / total) * 100}%` }} title={`做多 ${longs}`} />
        <div className="seg short" style={{ width: `${(shorts / total) * 100}%` }} title={`做空 ${shorts}`} />
        <div className="seg neu" style={{ width: `${(insuff / total) * 100}%` }} title={`資料不足 ${insuff}`} />
      </div>
      <div className="nx-breadth-legend">
        <div>
          <span className="dot up" />做多 <strong>{longs}</strong>
        </div>
        <div>
          <span className="dot down" />做空 <strong>{shorts}</strong>
        </div>
        <div>
          <span className="dot ins" />資料不足 <strong>{insuff}</strong>
        </div>
      </div>
    </div>
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
      <p className="muted sm">價格相對先前掃描偏上／偏下的標的數量。</p>
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
      <h3 className="nx-sec-title">交易活躍度排行</h3>
      <p className="muted sm">觀察近期市場參與是否快速增加（非精確 1m candle volume）。</p>
      <ul className="nx-turn-list">
        {rows.length === 0 ? (
          <li className="muted">等待掃描器資料…</li>
        ) : (
          rows.map((r) => (
            <li key={r.symbol}>
              <Link to={`/market/${r.symbol}`} className="nx-turn-row">
                <span className="mono">{r.symbol.replace("USDT", "")}</span>
                <span className="nx-turn-bar-wrap">
                  <span className="nx-turn-bar" style={{ width: `${((r.turnover24h || 0) / max) * 100}%` }} />
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

function PriceOiQuadrant({
  points,
}: {
  points: {
    symbol: string;
    side: string;
    priceChange5mPct: number;
    oiChange5mPct: number;
    stage?: string;
    opportunityScore?: number;
  }[];
}) {
  const ready = points.filter(
    (p) =>
      Number.isFinite(p.priceChange5mPct) &&
      Number.isFinite(p.oiChange5mPct) &&
      !(p.priceChange5mPct === 0 && p.oiChange5mPct === 0 && p.stage === "INSUFFICIENT_DATA"),
  );
  return (
    <section className="nx-chart-card nx-quadrant">
      <h3 className="nx-sec-title">價格與持倉結構</h3>
      <p className="muted sm">找出價格與未平倉量同步或背離的市場。</p>
      <div className="nx-quad-labels">
        <span>價↑／持倉↑：資金與價格同步</span>
        <span>價↑／持倉↓：上漲但持倉下降</span>
        <span>價↓／持倉↑：下跌且新持倉增加</span>
        <span>價↓／持倉↓：價格與持倉同步下降</span>
      </div>
      <div className="nx-quad-plot">
        {ready.slice(0, 48).map((p) => {
          const top =
            (p.side === "LONG" || p.side === "SHORT") &&
            (p.opportunityScore == null || p.opportunityScore >= 55);
          return (
            <Link
              key={p.symbol}
              to={`/market/${p.symbol}`}
              className={`nx-quad-dot side-${p.side.toLowerCase()} ${top ? "top" : ""}`}
              style={{
                left: `${50 + Math.max(-42, Math.min(42, p.priceChange5mPct * 6))}%`,
                bottom: `${50 + Math.max(-42, Math.min(42, p.oiChange5mPct * 6))}%`,
              }}
              title={`${p.symbol} 價 ${p.priceChange5mPct}% 持倉 ${p.oiChange5mPct}% ${p.side} ${p.stage || ""}`}
            />
          );
        })}
        <span className="nx-quad-axis-x">5m 價格 →</span>
        <span className="nx-quad-axis-y">5m 持倉 ↑</span>
      </div>
      {ready.length === 0 ? <p className="muted">象限資料累積中…</p> : null}
    </section>
  );
}

function EventToast({
  events,
  prefs,
}: {
  events: ScannerEvent[];
  prefs: EventPrefs;
}) {
  const [toast, setToast] = useState<ScannerEvent | null>(null);
  const seen = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!prefs.toast) return;
    // Product 7.1: digest-only / muted defaults suppress realtime spam
    if (!shouldEmitNotification()) return;
    for (const ev of events) {
      if (seen.current.has(ev.id)) continue;
      seen.current.add(ev.id);
      if (seen.current.size > 200) {
        seen.current = new Set([...seen.current].slice(-100));
      }
      if (!isHighPriorityEvent(ev) && Math.abs((ev as { rankDelta?: number }).rankDelta || 0) <= 1) {
        // low priority rank noise — still list in drawer, skip toast
        const t = (ev.type || "").toUpperCase();
        if (t.includes("RANK_") && !t.includes("NEW")) continue;
      }
      setToast(ev);
      if (prefs.sound) {
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
      if (prefs.browserNotify && "Notification" in window && Notification.permission === "granted") {
        try {
          new Notification("NEXUS 市場事件", { body: ev.explanation, silent: true });
        } catch {
          /* ignore */
        }
      }
      break;
    }
  }, [events, prefs]);

  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(null), 4500);
    return () => window.clearTimeout(t);
  }, [toast]);

  if (!toast) return null;
  return (
    <div className="nx-toast nx-motion-ok" role="status">
      <strong>{toast.symbol.replace("USDT", "")}</strong>
      <span>{toast.explanation}</span>
    </div>
  );
}

/**
 * Decision-first overview — Product Transformation Phase 2.
 * Candidates from server-side scanner only (no browser full-market scan).
 */
export function DecisionMarketOverview() {
  const { status, longs, shorts, events, charts, error, loading } = useMarketScannerOverview();
  const anomalies = useMarketAnomalies();
  const [view, setView] = useState<ViewMode>(() => loadViewMode());
  const [mobileSide, setMobileSide] = useState<"LONG" | "SHORT">("LONG");
  const [prefs, setPrefs] = useState<EventPrefs>(() => loadEventPrefs());
  const simple = view === "simple";

  useEffect(() => {
    const onView = (e: Event) => {
      const mode = (e as CustomEvent<ViewMode>).detail;
      if (mode === "simple" || mode === "advanced") setView(mode);
    };
    const onStorage = () => setPrefs(loadEventPrefs());
    window.addEventListener("nexus-view-mode", onView);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener("nexus-view-mode", onView);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  const pulseInput = useMemo(
    () => ({
      longCandidates: status?.longCandidates,
      shortCandidates: status?.shortCandidates,
      confirmedCandidates: status?.confirmedCandidates,
      highRiskCandidates: status?.highRiskCandidates,
      breadth: status?.breadth,
      symbolCount: status?.symbolCount,
      freshness: status?.freshness,
    }),
    [status],
  );
  const regime = deriveRegime(pulseInput);
  const summary = buildMarketSummary(pulseInput);

  const activeAnomalies = useMemo(
    () =>
      anomalies.filter((a) => a.status === "NEW" || a.status === "ACTIVE" || a.status === "COOLING")
        .length,
    [anomalies],
  );

  const topLong = longs[0];
  const topShort = shorts[0];
  const restLong = longs.slice(1);
  const restShort = shorts.slice(1);

  const emptyLongMsg = loading
    ? "資料建立中…"
    : "暫無符合條件的做多機會";
  const emptyShortMsg = loading
    ? "資料建立中…"
    : "暫無符合條件的做空機會";

  const [sectors, setSectors] = useState<SectorRow[]>([]);
  useEffect(() => {
    let alive = true;
    void fetchSectors("performance")
      .then((b) => {
        if (alive) setSectors((b.sectors || []).slice(0, 5));
      })
      .catch(() => undefined);
    const id = window.setInterval(() => {
      void fetchSectors("performance")
        .then((b) => {
          if (alive) setSectors((b.sectors || []).slice(0, 5));
        })
        .catch(() => undefined);
    }, 30000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);

  const collecting =
    !topLong &&
    !topShort &&
    (loading ||
      Boolean(
        status?.breadth?.insufficient &&
          status.breadth.insufficient >= Math.max(1, (status.symbolCount || 1) * 0.5),
      ));

  return (
    <div className="nx-decision-overview nx-p2 nx-p4" id="market-dashboard">
      <p className="sr-only">
        READ ONLY. Research mode. Live Mainnet public market data for display only. No trading.
      </p>

      <header className="nx-ov-header nx-ov-compact nx-ov-p4">
        <div className="nx-ov-title-block">
          <h1 className="nx-page-title">市場機會總覽</h1>
        </div>
        <div className="nx-ticker-row">
          <CompactTickerChip symbol="BTC" />
          <CompactTickerChip symbol="ETH" />
          <CompactTickerChip symbol="SOL" />
        </div>
      </header>

      {error ? (
        <div className="nx-banner-warn">掃描器暫不可用：{error}。請稍後重試。</div>
      ) : null}

      <section className="nx-regime-hero nx-regime-compact" aria-label="Market regime">
        <div className="nx-regime-main">
          <p className="nx-regime-label">市場狀態</p>
          <p className={`nx-regime-value regime-${regime}`}>{regime}</p>
          <p className="nx-regime-summary">{summary}</p>
        </div>
        <div className="nx-regime-stats nx-regime-stats-compact">
          <div>
            <span className="lbl">做多</span>
            <strong className="up">{status?.longCandidates ?? "—"}</strong>
          </div>
          <div>
            <span className="lbl">做空</span>
            <strong className="down">{status?.shortCandidates ?? "—"}</strong>
          </div>
          <div>
            <span className="lbl">確認</span>
            <strong>{status?.confirmedCandidates ?? "—"}</strong>
          </div>
          <div>
            <span className="lbl">風險</span>
            <strong className="risk">{status?.highRiskCandidates ?? "—"}</strong>
          </div>
          <div>
            <span className="lbl">廣度 ↑／↓</span>
            <strong>
              {status?.breadth?.rising ?? "—"}/{status?.breadth?.falling ?? "—"}
            </strong>
          </div>
          <div>
            <span className="lbl">異動</span>
            <strong>{activeAnomalies}</strong>
          </div>
        </div>
      </section>

      {collecting ? (
        <CollectingPanel startedAt={status?.lastCycleAt} status={status} />
      ) : null}

      <section className="nx-spotlight-row" aria-label="Top Long Short spotlight">
        <div className="nx-tops-head">
          <h2 className="nx-sec-title">首選機會</h2>
          <Link to="/scanner" className="nx-link">
            完整掃描 →
          </Link>
        </div>
        {collecting && !topLong && !topShort ? (
          <p className="muted sm">候選排名建立中 — 下方仍可查看廣度、版塊與活躍度。</p>
        ) : (
          <div className="nx-spotlight-grid">
            {topLong ? (
              <SpotlightCard c={topLong} simple={simple} />
            ) : (
              <div className="nx-spotlight empty muted">{emptyLongMsg}</div>
            )}
            {topShort ? (
              <SpotlightCard c={topShort} simple={simple} />
            ) : (
              <div className="nx-spotlight empty muted">{emptyShortMsg}</div>
            )}
          </div>
        )}
      </section>

      {!collecting || topLong || topShort ? (
      <section className="nx-tops nx-rest-tops" aria-label="Remaining top 5">
        <div className="nx-side-tabs mobile-only">
          <button
            type="button"
            className={mobileSide === "LONG" ? "active" : ""}
            onClick={() => setMobileSide("LONG")}
          >
            做多 #2–5
          </button>
          <button
            type="button"
            className={mobileSide === "SHORT" ? "active" : ""}
            onClick={() => setMobileSide("SHORT")}
          >
            做空 #2–5
          </button>
        </div>
        <div className="nx-tops-grid compact">
          <div className={`nx-top-col ${mobileSide === "LONG" ? "show-mobile" : "hide-mobile"}`}>
            <h3 className="nx-col-title up">做多 #2–5</h3>
            <div className="nx-compact-list desktop-only">
              {restLong.length === 0 ? (
                <p className="muted sm">—</p>
              ) : (
                restLong.map((c) => <CompactRankRow key={c.id} c={c} simple={simple} />)
              )}
            </div>
            <div className="nx-cand-list mobile-only">
              {restLong.map((c) => (
                <CandidateCard key={c.id} c={c} simple={simple} />
              ))}
            </div>
          </div>
          <div className={`nx-top-col ${mobileSide === "SHORT" ? "show-mobile" : "hide-mobile"}`}>
            <h3 className="nx-col-title down">做空 #2–5</h3>
            <div className="nx-compact-list desktop-only">
              {restShort.length === 0 ? (
                <p className="muted sm">—</p>
              ) : (
                restShort.map((c) => <CompactRankRow key={c.id} c={c} simple={simple} />)
              )}
            </div>
            <div className="nx-cand-list mobile-only">
              {restShort.map((c) => (
                <CandidateCard key={c.id} c={c} simple={simple} />
              ))}
            </div>
          </div>
        </div>
      </section>
      ) : null}

      <section className="nx-pulse-band nx-pulse-p4" aria-label="Market intelligence charts">
        <h2 className="nx-sec-title">市場情報圖表</h2>
        <LongShortBalance
          longs={status?.longCandidates ?? 0}
          shorts={status?.shortCandidates ?? 0}
          insuff={status?.breadth?.insufficient ?? 0}
        />
        <div className="nx-charts-grid">
          <MarketBreadthChart breadth={charts?.breadth || status?.breadth} />
          <TurnoverChart rows={charts?.turnoverTop10 || []} />
        </div>
        <PriceOiQuadrant points={charts?.priceOiQuadrant || []} />
        <p className="muted sm">
          <Link to="/crypto/price-oi">開啟完整 Price／OI 結構 →</Link>
        </p>
      </section>

      <section className="nx-sector-momentum" aria-label="Sector momentum">
        <div className="nx-tops-head">
          <h2 className="nx-sec-title">版塊動能</h2>
          <Link to="/crypto/sectors" className="nx-link">
            全部版塊 →
          </Link>
        </div>
        <ul className="nx-sector-momentum-list">
          {sectors.length === 0 ? (
            <li className="muted">版塊資料載入中…</li>
          ) : (
            sectors.map((s) => (
              <li key={s.id}>
                <Link to={`/crypto/sectors/${s.slug}`} className="nx-sector-momentum-row">
                  <strong>{s.nameZhTW}</strong>
                  <span>{s.sectorStateLabelZh}</span>
                  <span className="mono">
                    {s.turnoverWeightedReturn24h != null
                      ? `${s.turnoverWeightedReturn24h > 0 ? "+" : ""}${s.turnoverWeightedReturn24h.toFixed(2)}%`
                      : "—"}
                  </span>
                  <span className="muted sm">
                    多 {s.longCandidateCount}／空 {s.shortCandidateCount}
                  </span>
                </Link>
              </li>
            ))
          )}
        </ul>
      </section>

      <section className="nx-events nx-events-preview">
        <div className="nx-tops-head">
          <h2 className="nx-sec-title">近期事件</h2>
          <span className="muted sm">完整列表見頂欄通知</span>
        </div>
        <ul className="nx-event-list">
          {events.length === 0 ? (
            <li className="muted">尚無事件</li>
          ) : (
            events.slice(0, 5).map((ev) => (
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

      <section className="nx-research-layer nx-research-p4">
        <h2 className="nx-sec-title">更多入口</h2>
        <div className="nx-research-links">
          <Link to="/crypto/sectors">幣種版塊</Link>
          <Link to="/crypto/oi">OI 排行</Link>
          <Link to="/crypto/funding">Funding 排行</Link>
          <Link to="/watchlist">關注清單</Link>
          <Link to="/anomalies">市場異動</Link>
          <Link to="/scanner">市場掃描</Link>
        </div>
      </section>

      {!simple ? (
        <details className="nx-legacy-dash">
          <summary className="muted">固定幣種研究儀表板（進階保留）</summary>
          <SimplifiedMarketDashboard />
        </details>
      ) : null}

      <details className="nx-tech-details">
        <summary className="muted">系統與研究安全（見系統狀態）</summary>
        <p className="muted mono">
          Bybit Mainnet Public Linear · server scanner · researchOnly · private_api=false · Backend
          HOLD · Stage 4.19 blocked · No trading
        </p>
      </details>

      <EventToast events={events} prefs={prefs} />
    </div>
  );
}
