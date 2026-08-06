import { Link } from "react-router-dom";
import { useMemo } from "react";
import { useLivePrice } from "../../market/useLiveMarketFeed";
import { useMarketAnomalies } from "../../market/useMarketAnomalies";
import { useMarketScannerOverview } from "../../market/useMarketScanner";
import { buildMarketSummary, deriveRegime } from "../../market/marketSummary";
import { formatUsd } from "../../market/freshness";
import { fmtNum } from "../../market/displayNull";
import { OpportunityCard } from "../../components/OpportunityCard";
import type { MarketCandidate } from "../../market/scannerApi";
import { buildFunnelDisplay, NO_DATA } from "../../wave4/noDataFunnel";
import { UiDensityToggle } from "../../member/UiDensityToggle";

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

function top3(longs: MarketCandidate[], shorts: MarketCandidate[]): MarketCandidate[] {
  return [...longs, ...shorts]
    .sort((a, b) => (b.opportunityScore ?? -1) - (a.opportunityScore ?? -1))
    .slice(0, 3);
}

/** V18.2.1 overview — max 6 above-the-fold sections; no portfolio / founder diagnostics. */
export function ActualPanelOverviewPage() {
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
  const opportunities = top3(longs, shorts);
  const longN = status?.longCandidates ?? longs.length;
  const shortN = status?.shortCandidates ?? shorts.length;

  const eligibleZero =
    funnelEligibleZero(status?.confirmedCandidates) && !loading;

  const critical = useMemo(() => {
    const fromAnom = anomalies
      .filter((a) => a.status === "NEW" || a.status === "ACTIVE")
      .slice(0, 3)
      .map((a) => ({
        id: a.id,
        text: `${a.symbol?.replace("USDT", "") || "—"} · ${a.title || a.type || "異動"}`,
        href: a.symbol ? `/market/${a.symbol}` : "/alerts",
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
      .filter((c) => (c.riskScore ?? 0) >= 70 || c.stage === "OVEREXTENDED")
      .slice(0, 2)
      .map((c) => ({
        id: `risk-${c.id}`,
        text: `${c.symbol.replace("USDT", "")} · 風險 ${fmtNum(c.riskScore)} · ${c.stage}`,
        href: `/market/${c.symbol}`,
      }));
    const merged = [...fromAnom, ...fromEvents, ...highRisk];
    const seen = new Set<string>();
    return merged
      .filter((m) => {
        if (seen.has(m.id)) return false;
        seen.add(m.id);
        return true;
      })
      .slice(0, 5);
  }, [anomalies, events, longs, shorts]);

  const funnel = buildFunnelDisplay(
    [
      { key: "scanned", label: "掃描", value: status?.symbolCount },
      { key: "eligible", label: "合格", value: status?.confirmedCandidates },
      {
        key: "candidates",
        label: "候選",
        value: (() => {
          const n = (status?.longCandidates ?? 0) + (status?.shortCandidates ?? 0);
          return n > 0 ? n : undefined;
        })(),
      },
      { key: "risk", label: "高風險", value: status?.highRiskCandidates },
    ],
    Boolean(status) && !loading,
  );

  const posture =
    (status?.highRiskCandidates ?? 0) > 3
      ? "目前等待（高風險偏多）"
      : opportunities.length
        ? "可觀察 Top 機會（研究模式）"
        : "目前等待";

  return (
    <div className="page-stack nx-actual-panel-overview" data-testid="actual-panel-overview">
      <header className="nx-p7-header">
        <UiDensityToggle />
        <h1 className="nx-page-title">總覽</h1>
        <p className="muted sm">唯讀研究 · 非投資建議 · 無下單</p>
      </header>

      <section aria-label="Market ticker" data-testid="overview-ticker">
        <div className="nx-ticker-row">
          <TickerChip symbol="BTC" />
          <TickerChip symbol="ETH" />
          <TickerChip symbol="SOL" />
        </div>
      </section>

      <section aria-label="Status strip" data-testid="overview-status-strip" className="nx-p7-block">
        <p className={`nx-regime-value regime-${regime}`}>{regime}</p>
        <p className="muted">
          {summary || NO_DATA} · 做多 {longN}／做空 {shortN} · {posture}
        </p>
        {error ? (
          <div className="nx-banner-warn" role="status">
            掃描器暫不可用：{error}
          </div>
        ) : null}
        {eligibleZero ? (
          <p className="nx-banner-warn" role="status" data-testid="no-eligible-opportunities">
            目前無合格候選（eligible=0）— 可能因流動性、資料品質或安全閘門而暫停顯示，並非「沒有市場」。
          </p>
        ) : null}
      </section>

      <section aria-label="Top 3 opportunities" data-testid="top-opportunities" className="nx-p7-block">
        <div className="nx-tops-head">
          <h2 className="nx-sec-title">Top 3 機會</h2>
          <Link to="/opportunities" className="nx-link">
            全部 →
          </Link>
        </div>
        {opportunities.length === 0 ? (
          <p className="muted">{loading ? "載入中…" : NO_DATA}</p>
        ) : (
          <div className="nx-p7-top3">
            {opportunities.map((c) => (
              <OpportunityCard key={c.id} candidate={c} simple />
            ))}
          </div>
        )}
      </section>

      <section aria-label="Scanner funnel" data-testid="decision-funnel" className="nx-p7-block">
        <h2 className="nx-sec-title">掃描漏斗</h2>
        {!funnel.hasData ? (
          <p className="w4-no-data">{NO_DATA}</p>
        ) : (
          <div className="w4-funnel-grid">
            {funnel.stages.map((s) => (
              <div key={s.key} className="w4-funnel-step">
                <strong className="mono">{s.display}</strong>
                <span>{s.label}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section aria-label="Key alerts and risk" data-testid="critical-alerts" className="nx-p7-block">
        <div className="nx-tops-head">
          <h2 className="nx-sec-title">關鍵警報／風險</h2>
          <Link to="/alerts" className="nx-link">
            警報 →
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

      <section aria-label="Ask AI" data-testid="ask-ai" className="nx-p7-block">
        <h2 className="nx-sec-title">Ask AI</h2>
        <p className="muted sm">以市場脈絡提問 — 不下單、不連交易所。</p>
        <Link to="/assistant" className="nx-link">
          開啟 AI 助理 →
        </Link>
      </section>
    </div>
  );
}

function funnelEligibleZero(v: unknown): boolean {
  if (v == null) return false;
  if (typeof v === "number") return v === 0;
  return String(v) === "0";
}
