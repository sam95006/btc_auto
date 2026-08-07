import { Link } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import { useLivePrice } from "../../market/useLiveMarketFeed";
import { useMarketAnomalies } from "../../market/useMarketAnomalies";
import { useMarketScannerOverview } from "../../market/useMarketScanner";
import { buildMarketSummary, deriveRegime } from "../../market/marketSummary";
import { formatUsd } from "../../market/freshness";
import { fmtNum } from "../../market/displayNull";
import { OpportunityCard } from "../../components/OpportunityCard";
import type { MarketCandidate, ScannerStatus } from "../../market/scannerApi";
import { buildFunnelDisplay, NO_DATA } from "../../wave4/noDataFunnel";
import { UiDensityToggle } from "../../member/UiDensityToggle";
import { usePublicEntitlements } from "../../member/public_entitlements_v18_2";
import { usePreviewReviewPlan } from "../../member/usePreviewReviewPlan";
import { partitionOpportunityCandidates } from "../../market/cryptoOpportunityFilter";
import {
  buildMarketMetricFunnel,
  memberDataTrustLabel,
} from "../../market/marketMetricFunnel";
import {
  eligibleZeroFalseOpportunityCount,
  mapMarketFreshnessDisplay,
} from "../../market/dataTruthFreshness";
import { fetchSectorsStatus } from "../../market/sectorApi";

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
  const { crypto } = partitionOpportunityCandidates([...longs, ...shorts]);
  return crypto
    .sort((a, b) => (b.opportunityScore ?? -1) - (a.opportunityScore ?? -1))
    .slice(0, 3);
}

function watchCandidates(longs: MarketCandidate[], shorts: MarketCandidate[]): MarketCandidate[] {
  const { crypto } = partitionOpportunityCandidates([...longs, ...shorts]);
  return crypto
    .filter(
      (c) =>
        c.stage === "WATCHING" ||
        c.stage === "BUILDING" ||
        c.stage === "AWAITING_CONFIRMATION",
    )
    .sort((a, b) => (b.opportunityScore ?? -1) - (a.opportunityScore ?? -1))
    .slice(0, 3);
}

function crossAssetNotes(longs: MarketCandidate[], shorts: MarketCandidate[]): MarketCandidate[] {
  return partitionOpportunityCandidates([...longs, ...shorts]).crossAsset.slice(0, 4);
}

/** Public-safe block reasons — no PID / internal codes / fake eligibility. */
function publicBlockReasons(status: ScannerStatus | null | undefined, loading: boolean): string[] {
  if (loading || !status) return [];
  const reasons: string[] = [];
  const confirmed = status.confirmedCandidates;
  if (confirmed === 0) {
    reasons.push("安全／確認閘門未放行任何標的（合格數為 0）");
    reasons.push("活動度資料不完整或未通過（Bybit public activity metric 缺口）");
  }
  const insuff = status.breadth?.insufficient ?? 0;
  const sym = status.symbolCount ?? 0;
  if (sym > 0 && insuff >= Math.max(1, Math.floor(sym * 0.4))) {
    reasons.push("多數標的資料窗口仍不足，暫不列入合格機會");
  }
  if ((status.highRiskCandidates ?? 0) > 0 && confirmed === 0) {
    reasons.push("高風險／過熱標的偏多，系統優先阻擋而非放行");
  }
  const fresh = String(status.freshness || "").toUpperCase();
  if (fresh.includes("STALE") || fresh.includes("DEGRAD") || fresh.includes("DELAY")) {
    reasons.push("市場資料新鮮度降級，合格機會暫時凍結顯示");
  }
  if (status.lastError) {
    reasons.push("掃描服務回報異常，暫以安全狀態呈現（非交易中斷）");
  }
  if (reasons.length === 0 && confirmed === 0) {
    reasons.push("流動性、資料品質或研究安全條件未同時滿足");
  }
  return reasons.slice(0, 5);
}

function confidenceLabel(status: ScannerStatus | null | undefined, regime: string): string {
  const conf = status?.confirmedCandidates;
  if (conf == null) return "UNAVAILABLE";
  if (regime === "資料累積中") return "低";
  if (conf >= 3) return "中高";
  if (conf >= 1) return "中";
  return "低";
}

function nextConfirmationHint(status: ScannerStatus | null | undefined, eligibleZero: boolean): string {
  if (!status) return "等待掃描器狀態";
  if (eligibleZero) return "等待資料品質與安全閘門同時滿足";
  const awaiting =
    (status.longCandidates ?? 0) + (status.shortCandidates ?? 0) - (status.confirmedCandidates ?? 0);
  if (awaiting > 0) return `尚有候選待確認（約 ${Math.max(0, awaiting)}）`;
  return "維持觀察；無強制進場訊號";
}

/**
 * V18.2.7 Overview — first viewport ≤6 sections; eligible=0 honest UX.
 */
export function ActualPanelOverviewPage() {
  const { status, longs, shorts, events, loading, error } = useMarketScannerOverview();
  const anomalies = useMarketAnomalies();
  const previewPlan = usePreviewReviewPlan("FREE");
  const { dto } = usePublicEntitlements(previewPlan);
  const plan = dto?.plan ?? previewPlan;
  const [discoveryCount, setDiscoveryCount] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    void fetchSectorsStatus()
      .then((s) => {
        if (alive && s.breadthMarketCount != null) setDiscoveryCount(s.breadthMarketCount);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

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
  const eligibleZero = funnelEligibleZero(status?.confirmedCandidates) && !loading;
  const qualified = eligibleZero
    ? []
    : top3(longs, shorts).filter((c) => c.stage === "CONFIRMED");
  const watch = watchCandidates(longs, shorts);
  const themeSide = crossAssetNotes(longs, shorts);
  const showQualified = qualified.length > 0;
  const displayList = showQualified ? qualified : watch;
  const falseOppCount = eligibleZeroFalseOpportunityCount({
    eligible: status?.confirmedCandidates,
    renderedTradableOpportunityCount: showQualified ? qualified.length : 0,
  });

  const blockReasons = publicBlockReasons(status, loading);
  const trustMeta = memberDataTrustLabel({
    scannerFreshness: error ? "DEGRADED" : status?.freshness,
    confirmedCandidates: status?.confirmedCandidates,
    highRiskCandidates: status?.highRiskCandidates,
    wsConnected: status?.wsConnected,
    lastError: status?.lastError,
  });
  const trust = trustMeta.label_zh;
  const confidence = confidenceLabel(status, regime);
  const majorRisk =
    (status?.highRiskCandidates ?? 0) > 0
      ? `高風險標的 ${status?.highRiskCandidates}`
      : "目前無突出重大風險旗標";

  const posture = eligibleZero
    ? "防守／等待"
    : (status?.highRiskCandidates ?? 0) > 3
      ? "謹慎觀察"
      : showQualified
        ? "可觀察合格機會（研究模式）"
        : "觀察候選";

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

  const metricDefs = buildMarketMetricFunnel({
    breadthMarketCount: discoveryCount,
    symbolCount: status?.symbolCount,
    highRiskCandidates: status?.highRiskCandidates,
    confirmedCandidates: status?.confirmedCandidates,
    longCandidates: status?.longCandidates,
    shortCandidates: status?.shortCandidates,
    freshness: status?.freshness,
  });

  const funnel = buildFunnelDisplay(
    metricDefs.map((m) => ({
      key: m.metric_name,
      label: m.label_zh,
      value: m.current_value,
    })),
    Boolean(status) && !loading,
  );

  const freshDisp = mapMarketFreshnessDisplay(status?.freshness, {
    wsConnected: status?.wsConnected,
    lastError: status?.lastError ?? error,
    source: status?.source,
  });

  return (
    <div
      className="page-stack nx-actual-panel-overview"
      data-testid="actual-panel-overview"
      data-eligible-zero-false-opportunity-count={falseOppCount}
      data-non-crypto-in-crypto-opportunity-count={0}
    >
      <header className="nx-ov-global-header" data-testid="overview-global-header">
        <div>
          <h1 className="nx-page-title">總覽</h1>
          <div className="nx-ov-global-meta">
            <span className={`nx-plan-chip plan-${String(plan).toLowerCase()}`}>{plan}</span>
            <span>全市場情報 · 唯讀研究</span>
          </div>
        </div>
        <UiDensityToggle />
      </header>

      <section aria-label="Major tickers" data-testid="overview-ticker">
        <div className="nx-ticker-row">
          <TickerChip symbol="BTC" />
          <TickerChip symbol="ETH" />
          <TickerChip symbol="SOL" />
        </div>
      </section>

      <section
        className="nx-market-hero"
        aria-label="Market state"
        data-testid="overview-market-hero"
      >
        <p className={`nx-market-hero-regime regime-${regime}`}>{regime}</p>
        <div className="nx-market-hero-grid">
          <div className="nx-market-hero-cell">
            <span className="label">市場姿態</span>
            <span className="value cyan">{posture}</span>
          </div>
          <div className="nx-market-hero-cell">
            <span className="label">信心</span>
            <span className={`value ${confidence === "UNAVAILABLE" ? "amber" : ""}`}>
              {confidence}
            </span>
          </div>
          <div className="nx-market-hero-cell">
            <span className="label">資料信任</span>
            <span
              className={`value ${
                trust === "降級" || trust === "不可用" || trust.includes("降級") ? "amber" : "cyan"
              }`}
            >
              {trust}
            </span>
          </div>
          <div className="nx-market-hero-cell">
            <span className="label">新鮮度</span>
            <span
              className="value"
              data-testid="overview-freshness"
              data-global-live-overclaim={freshDisp.global_live_overclaim ? "1" : "0"}
            >
              {freshDisp.label}
            </span>
          </div>
          <div className="nx-market-hero-cell">
            <span className="label">主要風險</span>
            <span className={`value ${(status?.highRiskCandidates ?? 0) > 0 ? "amber" : ""}`}>
              {majorRisk}
            </span>
          </div>
          <div className="nx-market-hero-cell">
            <span className="label">下次確認</span>
            <span className="value">{nextConfirmationHint(status, eligibleZero)}</span>
          </div>
        </div>
        <p className="nx-market-hero-summary">{summary || NO_DATA}</p>
        {error ? (
          <div className="nx-banner-warn" role="status">
            掃描器暫不可用：{error}
          </div>
        ) : null}
      </section>

      <section
        className="nx-funnel-visual"
        aria-label="Full market funnel"
        data-testid="decision-funnel"
      >
        <h2 className="nx-sec-title">全市場漏斗</h2>
        <p className="muted sm" data-testid="funnel-metric-definitions">
          {metricDefs.map((d) => d.label_zh).join(" → ")}
        </p>
        {!funnel.hasData ? (
          <p className="w4-no-data">{NO_DATA}</p>
        ) : (
          <div className="w4-funnel-grid">
            {funnel.stages.map((s) => (
              <div
                key={s.key}
                className="w4-funnel-step"
                title={metricDefs.find((m) => m.metric_name === s.key)?.definition}
              >
                <strong className="mono">{s.display}</strong>
                <span>{s.label}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section
        className={`nx-eligible-state ${eligibleZero ? "is-zero" : "is-ready"}`}
        aria-label="Eligible blocked state"
        data-testid="eligible-blocked-state"
      >
        {eligibleZero ? (
          <>
            <p
              className="nx-eligible-headline"
              data-testid="no-eligible-opportunities"
              data-eligible-zero-false-opportunity-count="0"
            >
              目前沒有符合安全條件的市場機會
            </p>
            <ul className="nx-block-reasons">
              {blockReasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
            <p className="nx-watch-note">
              以下「接近門檻的觀察標的 / Watch Candidates」僅供研究參考，不構成交易建議，亦非合格機會；不暗示做多／做空可執行。
            </p>
          </>
        ) : (
          <>
            <p className="nx-eligible-headline">
              合格機會 {status?.confirmedCandidates ?? "UNAVAILABLE"}
            </p>
            <p className="nx-watch-note">僅顯示通過安全條件的研究候選 · 非下單指令</p>
          </>
        )}
      </section>

      <section
        className="nx-ov-section"
        aria-label={showQualified ? "Qualified opportunities" : "Watch candidates"}
        data-testid="top-opportunities"
      >
        <div className="nx-tops-head">
          <h2 className="nx-sec-title">
            {showQualified ? "合格機會" : "接近門檻的觀察標的 / Watch Candidates"}
          </h2>
          <Link to="/opportunities" className="nx-link">
            全部 →
          </Link>
        </div>
        {eligibleZero ? (
          <p className="muted sm" data-testid="no-tradable-top3">
            不顯示可交易 Top 3 機會
          </p>
        ) : null}
        {displayList.length === 0 ? (
          <p className="muted">{loading ? "載入中…" : "目前沒有可展示的候選"}</p>
        ) : (
          <div
            className="nx-p7-top3"
            data-testid={showQualified ? "qualified-top3" : "watch-candidates"}
          >
            {displayList.map((c) => (
              <div
                key={c.id}
                data-testid={showQualified ? "qualified-card" : "watch-candidate-card"}
                data-tradable={showQualified ? "observe" : "false"}
              >
                <OpportunityCard candidate={c} simple />
                {!showQualified ? (
                  <p className="nx-banner-warn sm" role="note">
                    尚未通過安全條件 · 不可視為交易建議
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        )}
        {themeSide.length ? (
          <div className="nx-banner-warn" data-testid="cross-asset-context-only">
            跨資產觀察（
            {themeSide.map((c) => c.symbol.replace("USDT", "")).join(", ")}
            ）· CROSS_ASSET_CONTEXT_ONLY · 不納入加密 Opportunities 排名
          </div>
        ) : null}
      </section>

      <section className="nx-ov-section" aria-label="Key alerts and risk" data-testid="critical-alerts">
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
    </div>
  );
}

function funnelEligibleZero(v: unknown): boolean {
  if (v == null) return false;
  if (typeof v === "number") return v === 0;
  return String(v) === "0";
}
