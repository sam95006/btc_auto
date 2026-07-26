import { Link } from "react-router-dom";
import { useMemo } from "react";
import { useLivePrice } from "../market/useLiveMarketFeed";
import { useMarketAnomalies } from "../market/useMarketAnomalies";
import { useMarketScannerOverview } from "../market/useMarketScanner";
import { buildMarketSummary, deriveRegime } from "../market/marketSummary";
import { formatUsd } from "../market/freshness";
import { fmtNum } from "../market/displayNull";
import { OpportunityCard } from "./OpportunityCard";
import { MarketParityStrip } from "./MarketParityStrip";
import { BybitDemoAutonomousCard } from "./BybitDemoAutonomousCard";
import type { MarketCandidate } from "../market/scannerApi";

function TickerChip({ symbol }: { symbol: "BTC" | "ETH" | "SOL" }) {
  const live = useLivePrice(symbol);
  const status = live?.connectionStatus || "DISCONNECTED";
  return (
    <div className="nx-ticker-chip" aria-label={`${symbol} ticker`}>
      <span className="nx-ticker-sym">{symbol}</span>
      <span className="mono nx-ticker-px">{formatUsd(live?.lastPrice)}</span>
      <span className={`nx-fresh nx-fresh-${status.toLowerCase()}`}>{status}</span>
    </div>
  );
}

function deriveReadiness(input: {
  symbolCount?: number;
  confirmed?: number;
  highRisk?: number;
  insuff?: number;
  freshness?: string;
}): { score: number | null; label: string; lines: string[] } {
  const n = input.symbolCount ?? 0;
  if (!n) {
    return {
      score: null,
      label: "資料累積中",
      lines: ["掃描器尚未回報標的數", "不會顯示假分數", "請稍後再看"],
    };
  }
  const insuff = input.insuff ?? 0;
  const readyRatio = Math.max(0, Math.min(1, 1 - insuff / Math.max(1, n)));
  const confBoost = Math.min(20, (input.confirmed ?? 0) * 4);
  const riskPenalty = Math.min(25, (input.highRisk ?? 0) * 3);
  const score = Math.round(readyRatio * 70 + confBoost - riskPenalty + 10);
  const clamped = Math.max(5, Math.min(95, score));
  const label =
    clamped >= 70 ? "結構可觀察" : clamped >= 45 ? "部分就緒" : "仍需等待";
  return {
    score: clamped,
    label,
    lines: [
      `標的覆蓋 ${n} · 資料不足 ${insuff}`,
      `已確認 ${input.confirmed ?? 0} · 高風險 ${input.highRisk ?? 0}`,
      `新鮮度 ${input.freshness || "未知"}`,
    ],
  };
}

function pickFocus(longs: MarketCandidate[], shorts: MarketCandidate[]): MarketCandidate | null {
  const pool = [...longs.slice(0, 3), ...shorts.slice(0, 3)];
  if (!pool.length) return null;
  return pool.sort((a, b) => (b.opportunityScore ?? -1) - (a.opportunityScore ?? -1))[0] || null;
}

function top3(longs: MarketCandidate[], shorts: MarketCandidate[]): MarketCandidate[] {
  return [...longs, ...shorts]
    .sort((a, b) => (b.opportunityScore ?? -1) - (a.opportunityScore ?? -1))
    .slice(0, 3);
}

function stanceLabel(longs: number, shorts: number, insuff: number): "偏多" | "偏空" | "中性" {
  if (longs === 0 && shorts === 0) return "中性";
  if (longs > shorts * 1.2) return "偏多";
  if (shorts > longs * 1.2) return "偏空";
  if (insuff > longs + shorts) return "中性";
  return "中性";
}

/**
 * Product 7 Simple View homepage first screen.
 * Fixed order; answers five operator questions without fake certainty.
 */
export function ProductSimpleView() {
  const { status, longs, shorts, events, loading, error } = useMarketScannerOverview();
  const anomalies = useMarketAnomalies();

  const pulse = useMemo(
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
  const regime = deriveRegime(pulse);
  const summary = buildMarketSummary(pulse);
  const readiness = deriveReadiness({
    symbolCount: status?.symbolCount,
    confirmed: status?.confirmedCandidates,
    highRisk: status?.highRiskCandidates,
    insuff: status?.breadth?.insufficient,
    freshness: status?.freshness,
  });
  const focus = pickFocus(longs, shorts);
  const opportunities = top3(longs, shorts);
  const longN = status?.longCandidates ?? longs.length;
  const shortN = status?.shortCandidates ?? shorts.length;
  const insuff = status?.breadth?.insufficient ?? 0;
  const stance = stanceLabel(longN, shortN, insuff);

  const critical = useMemo(() => {
    const fromAnom = anomalies
      .filter((a) => a.status === "NEW" || a.status === "ACTIVE")
      .slice(0, 3)
      .map((a) => ({
        id: a.id,
        text: `${a.symbol?.replace("USDT", "") || "—"} · ${a.title || a.type || "anomaly"}`,
        href: a.symbol ? `/market/${a.symbol}` : "/anomalies",
      }));
    const fromEvents = events
      .filter((e) => /OVEREXTENDED|HIGH_RISK|BLOCK|FAIL/i.test(e.type || e.explanation || ""))
      .slice(0, 3)
      .map((e) => ({
        id: e.id,
        text: `${e.symbol.replace("USDT", "")} · ${e.explanation}`,
        href: `/market/${e.symbol}`,
      }));
    const highRisk = [...longs, ...shorts]
      .filter((c) => c.riskScore >= 70 || c.stage === "OVEREXTENDED")
      .slice(0, 2)
      .map((c) => ({
        id: `risk-${c.id}`,
        text: `${c.symbol.replace("USDT", "")} · 風險 ${fmtNum(c.riskScore)} · ${c.stage}`,
        href: `/market/${c.symbol}`,
      }));
    const merged = [...fromAnom, ...fromEvents, ...highRisk];
    const seen = new Set<string>();
    return merged.filter((m) => {
      if (seen.has(m.id)) return false;
      seen.add(m.id);
      return true;
    }).slice(0, 5);
  }, [anomalies, events, longs, shorts]);

  const qWhat = summary;
  const qWatch = focus
    ? `${focus.symbol.replace("USDT", "")}（${focus.side} · 機會 ${fmtNum(focus.opportunityScore)}）`
    : loading
      ? "資料建立中…"
      : "暫無明確焦點標的";
  const qRisk =
    (status?.highRiskCandidates ?? 0) > 0
      ? `高風險／過熱標的 ${status?.highRiskCandidates} 個，勿追價`
      : critical[0]?.text || "目前未見集中高風險警報";
  const qConfirm =
    (status?.confirmedCandidates ?? 0) > 0
      ? `已有 ${status?.confirmedCandidates} 個條件確認候選，其餘仍待確認`
      : "多數候選仍在等待確認，不宜視為訊號";
  const qWait =
    readiness.score == null || readiness.score < 55
      ? "建議等待：資料或結構尚未就緒"
      : regime === "低動能" || regime === "資料累積中"
        ? "建議等待：市場動能不足"
        : "可觀察 Top 機會，但仍為研究模式（不下單）";

  return (
    <div className="nx-product7-simple" id="product-simple-view" aria-label="Product Simple View">
      <header className="nx-p7-header">
        <h1 className="nx-page-title">總覽</h1>
        <p className="muted sm">Simple View · 研究模式 · 非投資建議</p>
      </header>

      {error ? <div className="nx-banner-warn">掃描器暫不可用：{error}</div> : null}

      {/* 0. Bybit Demo autonomous ops */}
      <BybitDemoAutonomousCard />

      {/* 1. Ticker */}
      <section className="nx-p7-block" aria-label="Ticker">
        <div className="nx-ticker-row">
          <TickerChip symbol="BTC" />
          <TickerChip symbol="ETH" />
          <TickerChip symbol="SOL" />
        </div>
      </section>

      {/* 2. Market Status + five questions */}
      <section className="nx-p7-block nx-p7-status" aria-label="Market status">
        <p className="nx-regime-label">市場狀態</p>
        <p className={`nx-regime-value regime-${regime}`}>{regime}</p>
        <ol className="nx-p7-fiveq">
          <li>
            <strong>現在市場怎了？</strong> {qWhat}
          </li>
          <li>
            <strong>現在最值得看什麼？</strong> {qWatch}
          </li>
          <li>
            <strong>最大風險是什麼？</strong> {qRisk}
          </li>
          <li>
            <strong>還要等什麼確認？</strong> {qConfirm}
          </li>
          <li>
            <strong>現在該等還是行動？</strong> {qWait}
          </li>
        </ol>
      </section>

      {/* 3. Focus Market */}
      <section className="nx-p7-block nx-p7-focus" aria-label="Focus market">
        <h2 className="nx-sec-title">焦點市場</h2>
        {focus ? (
          <div className="nx-p7-focus-card">
            <Link to={`/market/${focus.symbol}`} className="mono">
              {focus.symbol.replace("USDT", "")}
            </Link>
            <span>
              {focus.side} · 機會 {fmtNum(focus.opportunityScore)} · 風險 {fmtNum(focus.riskScore)}
            </span>
            <span className="muted">{focus.freshness || "更新時間未知"}</span>
            <p>{focus.reasons?.[0] || "結構仍在觀察"}</p>
          </div>
        ) : (
          <p className="muted">{loading ? "焦點建立中…" : "尚無焦點候選"}</p>
        )}
      </section>

      {/* 4. Long / Short / Neutral */}
      <section className="nx-p7-block" aria-label="Long short neutral">
        <h2 className="nx-sec-title">多／空／中性</h2>
        <p className="nx-p7-stance">
          當前傾向：<strong>{stance}</strong>
        </p>
        <div className="nx-p7-lsn">
          <div>
            <span className="muted">做多</span>
            <strong className="up">{longN}</strong>
          </div>
          <div>
            <span className="muted">做空</span>
            <strong className="down">{shortN}</strong>
          </div>
          <div>
            <span className="muted">資料不足</span>
            <strong>{insuff}</strong>
          </div>
        </div>
        <p className="muted sm">這是掃描候選分布，不是勝率或帳戶持倉比。</p>
      </section>

      {/* 4b. Parity metrics (low density) */}
      <div className="nx-p7-block">
        <MarketParityStrip expanded={false} />
      </div>

      {/* 5. Readiness Gauge */}
      <section className="nx-p7-block readiness-gauge nx-p7-gauge" aria-label="Market readiness">
        <h2 className="nx-sec-title">市場就緒度</h2>
        <div
          className="gauge-ring"
          style={{ ["--gauge-pct" as string]: String(readiness.score ?? 0) }}
        >
          <div className="gauge-inner">
            <div className="gauge-score mono">{readiness.score == null ? "—" : readiness.score}</div>
            <div className="gauge-label">{readiness.label}</div>
          </div>
        </div>
        <ul className="gauge-lines">
          {readiness.lines.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
      </section>

      {/* 6. Top 3 Opportunities */}
      <section className="nx-p7-block" aria-label="Top 3 opportunities">
        <div className="nx-tops-head">
          <h2 className="nx-sec-title">Top 3 機會</h2>
          <Link to="/opportunities" className="nx-link">
            全部機會 →
          </Link>
        </div>
        {opportunities.length === 0 ? (
          <p className="muted">{loading ? "機會排名建立中…" : "暫無機會候選"}</p>
        ) : (
          <div className="nx-p7-top3">
            {opportunities.map((c) => (
              <OpportunityCard key={c.id} candidate={c} simple />
            ))}
          </div>
        )}
      </section>

      {/* 7. Critical Alerts */}
      <section className="nx-p7-block" aria-label="Critical alerts">
        <div className="nx-tops-head">
          <h2 className="nx-sec-title">關鍵警報</h2>
          <Link to="/anomalies" className="nx-link">
            異常中心 →
          </Link>
        </div>
        {critical.length === 0 ? (
          <p className="muted">目前沒有關鍵警報</p>
        ) : (
          <ul className="nx-p7-alerts">
            {critical.map((a) => (
              <li key={a.id}>
                <Link to={a.href}>{a.text}</Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* 8. AI Brief entry */}
      <section className="nx-p7-block nx-p7-ai-entry" aria-label="AI brief entry">
        <h2 className="nx-sec-title">AI 簡報入口</h2>
        <p className="muted sm">無 LLM 時僅提供規則摘要，不會捏造答案。</p>
        <div className="nx-p7-ai-actions">
          <button
            type="button"
            className="nx-p7-ai-btn"
            onClick={() => window.dispatchEvent(new CustomEvent("nexus-open-ai", { detail: "summary" }))}
          >
            今日規則簡報
          </button>
          <Link to="/assistant" className="nx-p7-ai-btn ghost">
            開啟助理頁
          </Link>
        </div>
      </section>
    </div>
  );
}
