import { Link } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import { useMarketAnomalies } from "../../market/useMarketAnomalies";
import { useMarketScannerOverview } from "../../market/useMarketScanner";
import { deriveRegime } from "../../market/marketSummary";
import { fmtNum } from "../../market/displayNull";
import type { MarketCandidate, ScannerStatus } from "../../market/scannerApi";
import { STAGE_LABEL_ZH, plainReason } from "../../market/scannerApi";
import { buildFunnelDisplay, NO_DATA } from "../../wave4/noDataFunnel";
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

function agoLabel(ts?: number | null) {
  if (!ts) return "—";
  const sec = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (sec < 60) return `${sec} 秒前`;
  if (sec < 3600) return `${Math.round(sec / 60)} 分鐘前`;
  return `${Math.round(sec / 3600)} 小時前`;
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
    .slice(0, 5);
}

/** Public-safe market risks — no PID / internal codes. */
function publicMarketRisks(status: ScannerStatus | null | undefined, loading: boolean): string[] {
  if (loading || !status) return [];
  const risks: string[] = [];
  const confirmed = status.confirmedCandidates;
  if (confirmed === 0) {
    risks.push("目前無通過安全閘門的合格機會，系統維持防守姿態");
  }
  const insuff = status.breadth?.insufficient ?? 0;
  const sym = status.symbolCount ?? 0;
  if (sym > 0 && insuff >= Math.max(1, Math.floor(sym * 0.4))) {
    risks.push("多數標的資料窗口不足，解讀空間受限");
  }
  if ((status.highRiskCandidates ?? 0) > 0) {
    risks.push(`高風險／過熱標的偏多（${status.highRiskCandidates}），優先阻擋而非放行`);
  }
  const fresh = String(status.freshness || "").toUpperCase();
  if (fresh.includes("STALE") || fresh.includes("DEGRAD") || fresh.includes("DELAY")) {
    risks.push("市場資料新鮮度降級，決策應更保守");
  }
  if (status.lastError) {
    risks.push("掃描服務回報異常，暫以安全狀態呈現");
  }
  if (risks.length === 0) {
    risks.push("目前無突出公開風險旗標；持續留意流動性與資料品質");
  }
  return risks.slice(0, 5);
}

/**
 * V18.2.8 Overview — "What should I do now?"
 * First viewport ≤6 groups; eligible=0 honest; no tradable Top 3.
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
  const eligibleZero = funnelEligibleZero(status?.confirmedCandidates) && !loading;
  const watch = watchCandidates(longs, shorts);
  const falseOppCount = eligibleZeroFalseOpportunityCount({
    eligible: status?.confirmedCandidates,
    renderedTradableOpportunityCount: 0,
  });

  const trustMeta = memberDataTrustLabel({
    scannerFreshness: error ? "DEGRADED" : status?.freshness,
    confirmedCandidates: status?.confirmedCandidates,
    highRiskCandidates: status?.highRiskCandidates,
    wsConnected: status?.wsConnected,
    lastError: status?.lastError,
  });
  const trust = trustMeta.label_zh;
  const marketRisks = publicMarketRisks(status, loading);

  const majorRisk =
    (status?.highRiskCandidates ?? 0) > 0
      ? `高風險標的 ${status?.highRiskCandidates}`
      : "目前無突出重大風險旗標";

  const latestAlerts = useMemo(() => {
    const fromAnom = anomalies
      .filter((a) => a.status === "NEW" || a.status === "ACTIVE")
      .slice(0, 4)
      .map((a) => ({
        id: a.id,
        text: `${a.symbol?.replace("USDT", "") || "—"} · ${a.title || a.type || "異動"}`,
        href: a.symbol ? `/market/${a.symbol}` : "/alerts",
      }));
    const fromEvents = events.slice(0, 4).map((e) => ({
      id: e.id,
      text: `${e.symbol.replace("USDT", "")} · ${e.explanation}`,
      href: `/market/${e.symbol}`,
    }));
    const merged = [...fromAnom, ...fromEvents];
    const seen = new Set<string>();
    return merged
      .filter((m) => {
        if (seen.has(m.id)) return false;
        seen.add(m.id);
        return true;
      })
      .slice(0, 5);
  }, [anomalies, events]);

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
      className="v1828-overview"
      data-testid="actual-panel-overview"
      data-eligible-zero-false-opportunity-count={falseOppCount}
      data-non-crypto-in-crypto-opportunity-count={0}
    >
      {/* A — MARKET NOW */}
      <section
        className="v1828-ov-block"
        aria-label="現在市場"
        data-testid="overview-market-hero"
      >
        <p className="v1828-ov-kicker">現在該做什麼？</p>
        <h2>現在市場</h2>
        <div className="v1828-market-now">
          <div className="v1828-metric">
            <span className="label">市場狀態</span>
            <span className="value cyan">{regime}</span>
          </div>
          <div className="v1828-metric">
            <span className="label">主要風險</span>
            <span className={`value ${(status?.highRiskCandidates ?? 0) > 0 ? "amber" : ""}`}>
              {majorRisk}
            </span>
          </div>
          <div className="v1828-metric">
            <span className="label">資料信任</span>
            <span
              className={`value ${
                trust === "降級" || trust === "不可用" || trust.includes("降級") ? "amber" : "cyan"
              }`}
            >
              {trust}
            </span>
          </div>
          <div className="v1828-metric">
            <span className="label">新鮮度</span>
            <span
              className="value"
              data-testid="overview-freshness"
              data-global-live-overclaim={freshDisp.global_live_overclaim ? "1" : "0"}
            >
              {freshDisp.label}
            </span>
          </div>
        </div>
        <p className="muted sm" style={{ marginTop: 12 }}>
          方案 {plan} · 全市場情報 · 唯讀研究
        </p>
        {error ? (
          <div className="nx-banner-warn" role="status">
            掃描器暫不可用：{error}
          </div>
        ) : null}
      </section>

      {/* B — FULL MARKET FUNNEL */}
      <section
        className="v1828-ov-block"
        aria-label="全市場漏斗"
        data-testid="decision-funnel"
      >
        <h2>全市場漏斗</h2>
        <p className="muted sm" data-testid="funnel-metric-definitions">
          發現 ≠ 監控 ≠ 合格 · {metricDefs.map((d) => d.label_zh).join(" → ")}
        </p>
        {!funnel.hasData ? (
          <p className="muted">{NO_DATA}</p>
        ) : (
          <div className="v1828-funnel">
            {funnel.stages.map((s) => (
              <div
                key={s.key}
                className="v1828-funnel-step"
                title={metricDefs.find((m) => m.metric_name === s.key)?.definition}
              >
                <strong className="mono">{s.display}</strong>
                <span>{s.label}</span>
              </div>
            ))}
          </div>
        )}
        {eligibleZero ? (
          <p
            className="muted sm"
            style={{ marginTop: 12 }}
            data-testid="no-eligible-opportunities"
            data-eligible-zero-false-opportunity-count="0"
          >
            目前沒有符合安全條件的市場機會（合格數 = 0）
          </p>
        ) : (
          <p className="muted sm" style={{ marginTop: 12 }}>
            合格機會 {status?.confirmedCandidates ?? "UNAVAILABLE"} · 僅供研究觀察
          </p>
        )}
      </section>

      {/* C — PRIMARY ACTIONS */}
      <section className="v1828-ov-block" aria-label="主要行動" data-testid="overview-primary-actions">
        <h2>主要行動</h2>
        <div className="v1828-actions">
          <Link to="/opportunities" className="v1828-action-btn">
            找市場機會
          </Link>
          <Link to="/scanner" className="v1828-action-btn secondary">
            掃描全市場
          </Link>
          <Link to="/alerts" className="v1828-action-btn secondary">
            建立警報
          </Link>
        </div>
      </section>

      {/* D — WATCH CANDIDATES (when eligible=0: 值得關注 NOT 交易機會) */}
      <section
        className="v1828-ov-block"
        aria-label="值得關注"
        data-testid="top-opportunities"
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <h2 style={{ margin: 0 }}>值得關注</h2>
          <Link to="/opportunities" className="muted sm" style={{ textDecoration: "none" }}>
            全部 →
          </Link>
        </div>
        {eligibleZero ? (
          <p className="muted sm" data-testid="no-tradable-top3" style={{ marginTop: 8 }}>
            非交易機會 · 不顯示可交易 Top 3
          </p>
        ) : null}
        {watch.length === 0 ? (
          <p className="muted" style={{ marginTop: 8 }}>
            {loading ? "載入中…" : "目前沒有可展示的關注標的"}
          </p>
        ) : (
          <div data-testid="watch-candidates" style={{ marginTop: 8 }}>
            <div className="v1828-watch-row muted sm desktop-only" style={{ borderBottom: "1px solid var(--nx-border)" }}>
              <span>標的</span>
              <span>狀態</span>
              <span>原因</span>
              <span>風險</span>
              <span>更新</span>
            </div>
            {watch.map((c) => (
              <div
                key={c.id}
                className="v1828-watch-row"
                data-testid="watch-candidate-card"
                data-tradable="false"
              >
                <Link to={`/market/${c.symbol}`} className="sym mono">
                  {c.symbol.replace("USDT", "")}
                </Link>
                <span>{STAGE_LABEL_ZH[c.stage] || c.stage}</span>
                <span>{plainReason(c.reasons?.[0] || "結構仍在觀察", true)}</span>
                <span className="mono">
                  {c.riskScore == null ? "UNAVAILABLE" : fmtNum(c.riskScore)}
                </span>
                <span className="muted">{agoLabel(c.lastUpdatedAt)}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* E — MARKET RISKS */}
      <section className="v1828-ov-block" aria-label="市場風險" data-testid="market-risks">
        <h2>市場風險</h2>
        <ul className="v1828-risk-list">
          {marketRisks.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      </section>

      {/* F — LATEST ALERTS */}
      <section className="v1828-ov-block" aria-label="最新警報" data-testid="critical-alerts">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <h2 style={{ margin: 0 }}>最新警報</h2>
          <Link to="/alerts" className="muted sm" style={{ textDecoration: "none" }}>
            警報 →
          </Link>
        </div>
        {latestAlerts.length === 0 ? (
          <p className="muted" style={{ marginTop: 8 }}>
            目前沒有最新警報
          </p>
        ) : (
          <ul className="v1828-alert-list" style={{ marginTop: 8 }}>
            {latestAlerts.map((a) => (
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
