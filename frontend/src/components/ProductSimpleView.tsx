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
import type { MarketCandidate } from "../market/scannerApi";
import { buildFunnelDisplay, NO_DATA } from "../wave4/noDataFunnel";
import { portfolioLeverageBadge } from "../wave4/fixedLeverageLabels";
import { useRealShadowRuntime } from "../wave5/useRealShadowRuntime";

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

/**
 * Wave 4.1 Simple Overview — above-the-fold decision panel.
 * Five questions + readiness gauge + research walls stay in Expand Details.
 */
export function ProductSimpleView() {
  const { status, longs, shorts, events, loading, error } = useMarketScannerOverview();
  const anomalies = useMarketAnomalies();
  const { status: shadowRt, hasRealData: hasShadowRt } = useRealShadowRuntime();

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
  const focus = pickFocus(longs, shorts);
  const opportunities = top3(longs, shorts);
  const longN = status?.longCandidates ?? longs.length;
  const shortN = status?.shortCandidates ?? shorts.length;

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
    return merged
      .filter((m) => {
        if (seen.has(m.id)) return false;
        seen.add(m.id);
        return true;
      })
      .slice(0, 5);
  }, [anomalies, events, longs, shorts]);

  const funnel = hasShadowRt
    ? buildFunnelDisplay(
        [
          { key: "scanned", label: "掃描", value: shadowRt?.funnel?.marketsScanned },
          { key: "eligible", label: "合格", value: shadowRt?.funnel?.marketsEligible },
          { key: "candidates", label: "候選", value: shadowRt?.funnel?.candidatesGenerated },
          { key: "sixRole", label: "六角色", value: shadowRt?.funnel?.sixRoleReviewed },
          { key: "riskPass", label: "風控通過", value: shadowRt?.funnel?.riskCriticPassed },
          { key: "selected", label: "入選", value: shadowRt?.funnel?.portfolioSelected },
        ],
        true,
      )
    : buildFunnelDisplay(
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

  const dqOfflineHint = error ? 1 : 0;

  return (
    <div className="nx-product7-simple w4-overview-grid" id="product-simple-view" aria-label="Product Simple View">
      <header className="nx-p7-header w4-col-12">
        <h1 className="nx-page-title">總覽</h1>
        <p className="muted sm">Research Only · Execution Disabled · 非投資建議</p>
        <div className="nx-ticker-row" aria-label="Benchmark ticker">
          <TickerChip symbol="BTC" />
          <TickerChip symbol="ETH" />
          <TickerChip symbol="SOL" />
        </div>
      </header>

      {error ? (
        <div className="nx-banner-warn w4-col-12" role="status">
          掃描器暫不可用：{error}（詳見 Data Quality）
        </div>
      ) : null}

      {/* Market Pulse — 12 cols */}
      <section className="nx-p7-block w4-col-12" aria-label="Market pulse" data-testid="market-pulse">
        <h2 className="nx-sec-title">Market Pulse</h2>
        <p className={`nx-regime-value regime-${regime}`}>{regime}</p>
        <p className="muted">
          {summary || NO_DATA} · 做多 {longN}／做空 {shortN} · {posture}
        </p>
      </section>

      {/* Decision Funnel — 8 cols */}
      <section className="nx-p7-block w4-col-8" aria-label="Decision funnel" data-testid="decision-funnel">
        <h2 className="nx-sec-title">Decision Funnel</h2>
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

      {/* Portfolio / Risk — 4 cols */}
      <section className="nx-p7-block w4-col-4" aria-label="Portfolio risk" data-testid="portfolio-risk">
        <h2 className="nx-sec-title">Portfolio／Risk</h2>
        <span className="w4-leverage-badge">{portfolioLeverageBadge()}</span>
        <p className="muted sm">
          Shadow {hasShadowRt ? (shadowRt?.funnel?.openShadowPositions ?? 0) : 0}／
          {shadowRt?.max_open ?? 2} · NOT EXECUTED
        </p>
        <p className="muted sm">
          {hasShadowRt ? "PUBLIC MARKET DATA · SHADOW" : `高風險候選 ${status?.highRiskCandidates ?? NO_DATA}`}{" "}
          · <Link to="/portfolio">組合 →</Link>
        </p>
      </section>

      {/* Top Opportunities — 8 cols */}
      <section className="nx-p7-block w4-col-8" aria-label="Top opportunities" data-testid="top-opportunities">
        <div className="nx-tops-head">
          <h2 className="nx-sec-title">Top Opportunities</h2>
          <Link to="/opportunities" className="nx-link">
            全部 →
          </Link>
        </div>
        {opportunities.length === 0 ? (
          <p className="muted">{loading ? "機會建立中…" : NO_DATA}</p>
        ) : (
          <div className="nx-p7-top3">
            {opportunities.map((c) => (
              <OpportunityCard key={c.id} candidate={c} simple />
            ))}
          </div>
        )}
        {focus ? (
          <p className="muted sm">
            焦點：{" "}
            <Link to={`/market/${focus.symbol}`} className="mono">
              {focus.symbol.replace("USDT", "")}
            </Link>{" "}
            · {focus.side}
          </p>
        ) : null}
      </section>

      {/* Critical Alerts — 4 cols */}
      <section className="nx-p7-block w4-col-4" aria-label="Critical alerts" data-testid="critical-alerts">
        <div className="nx-tops-head">
          <h2 className="nx-sec-title">Critical Alerts</h2>
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

      {/* Data Quality compact strip — 12 cols */}
      <section className="nx-p7-block w4-col-12 w4-dq-strip" aria-label="Data quality summary" data-testid="data-quality">
        <p className="sm">
          核心市場資料{error ? "降級" : "正常"} · 外部來源離線提示 {dqOfflineHint} · 新鮮度{" "}
          {(hasShadowRt ? shadowRt?.freshness : status?.freshness) || NO_DATA}
          {hasShadowRt ? " · REAL_PUBLIC_SHADOW_RUNTIME" : ""} ·{" "}
          <Link to="/provider-shadow">Provider Health →</Link>
        </p>
        <details>
          <summary className="muted sm">展開 Provider 診斷</summary>
          <MarketParityStrip expanded={false} />
        </details>
      </section>

      {/* Expand Details — five questions / readiness stay off primary fold */}
      <details className="nx-p7-block w4-col-12 w4-expand-details">
        <summary className="nx-sec-title">Expand Details · 五問與就緒度</summary>
        <ol className="nx-p7-fiveq">
          <li>
            <strong>現在市場怎了？</strong> {summary || NO_DATA}
          </li>
          <li>
            <strong>現在最值得看什麼？</strong>{" "}
            {focus
              ? `${focus.symbol.replace("USDT", "")}（${focus.side}）`
              : loading
                ? "資料建立中…"
                : "暫無明確焦點"}
          </li>
          <li>
            <strong>最大風險是什麼？</strong>{" "}
            {(status?.highRiskCandidates ?? 0) > 0
              ? `高風險標的 ${status?.highRiskCandidates}`
              : critical[0]?.text || "未見集中高風險"}
          </li>
          <li>
            <strong>還要等什麼？</strong> 條件確認與資料新鮮度
          </li>
          <li>
            <strong>該等待或行動？</strong> {posture}（不下單）
          </li>
        </ol>
        <p className="muted sm">
          AI Commander：使用右下 FAB。無 LLM 時僅 RULE_BASED_SUMMARY。
        </p>
      </details>
    </div>
  );
}
