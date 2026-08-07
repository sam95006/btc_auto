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
import { computeAvgFunding } from "../../market/marketAvgFunding";

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
        c.stage === "AWAITING_CONFIRMATION" ||
        c.stage === "CONFIRMED",
    )
    .sort((a, b) => (b.opportunityScore ?? -1) - (a.opportunityScore ?? -1))
    .slice(0, 8);
}

/** Public-safe attention items — risks / alert / degradation. */
function attentionItems(
  status: ScannerStatus | null | undefined,
  loading: boolean,
  alertCount: number,
): string[] {
  if (loading || !status) return [];
  const items: string[] = [];
  if ((status.confirmedCandidates ?? 0) === 0) {
    items.push("目前風險條件未通過 — 尚無通過安全門檻的標的");
  }
  if ((status.highRiskCandidates ?? 0) > 0) {
    items.push(`高風險／過熱標的 ${status.highRiskCandidates}，優先防守`);
  }
  const fresh = String(status.freshness || "").toUpperCase();
  if (fresh.includes("STALE") || fresh.includes("DEGRAD") || fresh.includes("DELAY") || fresh.includes("PARTIAL")) {
    items.push("部分即時／資料品質下降 — 解讀應更保守");
  }
  if (status.lastError) {
    items.push("掃描服務回報異常，暫以安全狀態呈現");
  }
  if (alertCount > 0) {
    items.push(`有 ${alertCount} 則需關注的警報／異動`);
  }
  const insuff = status.breadth?.insufficient ?? 0;
  const sym = status.symbolCount ?? 0;
  if (sym > 0 && insuff >= Math.max(1, Math.floor(sym * 0.4))) {
    items.push("多數標的資料窗口不足，解讀空間受限");
  }
  if (items.length === 0) {
    items.push("目前無突出需立即處理事項；可持續掃描與觀察");
  }
  return items.slice(0, 5);
}

function funnelEligibleZero(v: unknown): boolean {
  if (v == null) return false;
  if (typeof v === "number") return v === 0;
  return String(v) === "0";
}

/**
 * V18.2.9 Overview — human workflow (12-col).
 * MARKET NOW + ATTENTION → FUNNEL → FEED+ALERTS → PULSE → action strip.
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

  const latestAlerts = useMemo(() => {
    const fromAnom = anomalies
      .filter((a) => a.status === "NEW" || a.status === "ACTIVE")
      .slice(0, 5)
      .map((a) => ({
        id: a.id,
        text: `${a.symbol?.replace("USDT", "") || "—"} · ${a.title || a.type || "異動"}`,
        href: a.symbol ? `/market/${a.symbol}` : "/alerts",
        when: agoLabel(a.lastSeenAt ?? a.observedAt ?? null),
      }));
    const fromEvents = events.slice(0, 5).map((e) => ({
      id: e.id,
      text: `${e.symbol.replace("USDT", "")} · ${e.explanation}`,
      href: `/market/${e.symbol}`,
      when: agoLabel(e.timestamp ?? null),
    }));
    const merged = [...fromAnom, ...fromEvents];
    const seen = new Set<string>();
    return merged
      .filter((m) => {
        if (seen.has(m.id)) return false;
        seen.add(m.id);
        return true;
      })
      .slice(0, 6);
  }, [anomalies, events]);

  const attention = attentionItems(status, loading, latestAlerts.length);

  const majorChange =
    (status?.highRiskCandidates ?? 0) > 0
      ? `高風險標的增至 ${status?.highRiskCandidates}`
      : eligibleZero
        ? "合格標的仍為 0 — 市場維持防守"
        : `合格標的 ${status?.confirmedCandidates ?? "—"}`;

  const metricDefs = buildMarketMetricFunnel({
    breadthMarketCount: discoveryCount,
    symbolCount: status?.symbolCount,
    highRiskCandidates: status?.highRiskCandidates,
    confirmedCandidates: status?.confirmedCandidates,
    longCandidates: status?.longCandidates,
    shortCandidates: status?.shortCandidates,
    freshness: status?.freshness,
  }).filter((m) => m.metric_name !== "candidate");

  const funnelLabels: Record<string, string> = {
    market_discovery: "發現",
    data_valid: "有效",
    runtime_observable: "即時",
    safety_review: "安全",
    eligible: "Eligible",
  };

  const funnel = buildFunnelDisplay(
    metricDefs.map((m) => ({
      key: m.metric_name,
      label: funnelLabels[m.metric_name] || m.label_zh,
      value: m.current_value,
    })),
    Boolean(status) && !loading,
  );

  const freshDisp = mapMarketFreshnessDisplay(status?.freshness, {
    wsConnected: status?.wsConnected,
    lastError: status?.lastError ?? error,
    source: status?.source,
  });

  const funding = useMemo(
    () => computeAvgFunding([...longs, ...shorts], status?.freshness),
    [longs, shorts, status?.freshness],
  );

  const oiSample = useMemo(() => {
    const withOi = [...longs, ...shorts].filter(
      (c) => c.oiChange5mPct != null && Number.isFinite(c.oiChange5mPct),
    );
    if (!withOi.length) return null;
    const avg =
      withOi.reduce((s, c) => s + (c.oiChange5mPct as number), 0) / withOi.length;
    return avg;
  }, [longs, shorts]);

  const volActivity = useMemo(() => {
    const withPx = [...longs, ...shorts].filter(
      (c) => c.priceChange5mPct != null && Number.isFinite(c.priceChange5mPct),
    );
    if (!withPx.length) return null;
    const avgAbs =
      withPx.reduce((s, c) => s + Math.abs(c.priceChange5mPct as number), 0) /
      withPx.length;
    return avgAbs;
  }, [longs, shorts]);

  const liqProxy = status?.highRiskCandidates ?? null;

  return (
    <div
      className="v1829-overview"
      data-testid="actual-panel-overview"
      data-product-gen="v18_2_9"
      data-eligible-zero-false-opportunity-count={falseOppCount}
      data-non-crypto-in-crypto-opportunity-count={0}
    >
      {/* ROW1: L7 MARKET NOW + R5 ATTENTION */}
      <section
        className="v1829-panel v1829-col-7"
        aria-label="現在市場"
        data-testid="overview-market-hero"
      >
        <p className="v1829-kicker">市場怎麼了</p>
        <h2>現在市場</h2>
        <div className="v1829-market-now">
          <div className="v1829-metric">
            <span className="label">偏向</span>
            <span className="value intel">{regime}</span>
          </div>
          <div className="v1829-metric">
            <span className="label">風險</span>
            <span className={`value ${(status?.highRiskCandidates ?? 0) > 0 ? "warn" : ""}`}>
              {(status?.highRiskCandidates ?? 0) > 0
                ? `高風險 ${status?.highRiskCandidates}`
                : "無突出重大風險"}
            </span>
          </div>
          <div className="v1829-metric">
            <span className="label">Data Trust</span>
            <span
              className={`value ${
                trust.includes("降級") || trust === "不可用" || trust.includes("過期")
                  ? "warn"
                  : "intel"
              }`}
            >
              {trust}
            </span>
          </div>
          <div className="v1829-metric">
            <span className="label">主要變化</span>
            <span
              className="value"
              data-testid="overview-freshness"
              data-global-live-overclaim={freshDisp.global_live_overclaim ? "1" : "0"}
            >
              {majorChange}
              <span className="muted" style={{ display: "block", fontSize: "0.8125rem", fontWeight: 400, marginTop: 2 }}>
                {freshDisp.label}
              </span>
            </span>
          </div>
        </div>
        <p className="muted" style={{ marginTop: 12, fontSize: "0.8125rem" }}>
          方案 {plan} · 全市場情報 · 唯讀
        </p>
        {error ? (
          <div className="nx-banner-warn" role="status" style={{ marginTop: 10 }}>
            掃描器暫不可用：{error}
          </div>
        ) : null}
      </section>

      <section
        className="v1829-panel v1829-col-5"
        aria-label="需要關注"
        data-testid="market-risks"
      >
        <p className="v1829-kicker">哪裡有風險</p>
        <h2>需要關注</h2>
        <ul className="v1829-attention-list">
          {attention.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      </section>

      {/* ROW2: FULL MARKET FUNNEL */}
      <section
        className="v1829-panel v1829-col-12"
        aria-label="全市場漏斗"
        data-testid="decision-funnel"
      >
        <h2>全市場漏斗</h2>
        <p className="muted" style={{ marginTop: -4, marginBottom: 10, fontSize: "0.8125rem" }} data-testid="funnel-metric-definitions">
          發現 → 有效 → 即時 → 安全 → Eligible
        </p>
        {!funnel.hasData ? (
          <p className="muted">{NO_DATA}</p>
        ) : (
          <div className="v1829-funnel">
            {funnel.stages.map((s) => (
              <div
                key={s.key}
                className="v1829-funnel-step"
                title={metricDefs.find((m) => m.metric_name === s.key)?.definition}
              >
                <strong className="mono">{s.display}</strong>
                <span>{s.label}</span>
              </div>
            ))}
          </div>
        )}

        {eligibleZero ? (
          <div
            className="v1829-empty-eligible"
            data-testid="no-eligible-opportunities"
            data-eligible-zero-false-opportunity-count="0"
          >
            <p>目前沒有通過安全門檻的標的</p>
            <p className="secondary">
              可先掃描全市場、查看觀察標的，或建立警報等待條件變化。不顯示可交易 Top3／做多／做空建議。
            </p>
            <div className="v1829-action-strip" style={{ paddingTop: 8 }}>
              <Link to="/watchlist" className="v1829-btn v1829-btn-secondary">
                查看觀察標的
              </Link>
              <Link to="/alerts" className="v1829-btn v1829-btn-secondary">
                建立警報
              </Link>
            </div>
          </div>
        ) : (
          <p className="muted" style={{ marginTop: 12, fontSize: "0.875rem" }}>
            合格標的 {status?.confirmedCandidates ?? "UNAVAILABLE"} · 僅供研究觀察
          </p>
        )}

        {/* Compact action strip — one primary */}
        <div className="v1829-action-strip" data-testid="overview-primary-actions">
          <Link to="/scanner" className="v1829-btn v1829-btn-primary">
            掃描全市場
          </Link>
          <Link to="/alerts" className="v1829-btn v1829-btn-secondary">
            建立警報
          </Link>
          <Link to="/watchlist" className="v1829-btn v1829-btn-secondary">
            查看觀察清單
          </Link>
        </div>
      </section>

      {/* ROW3: L8 FEED + R4 ALERTS */}
      <section
        className="v1829-panel v1829-col-8"
        aria-label="值得關注"
        data-testid="top-opportunities"
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <div>
            <p className="v1829-kicker">哪裡值得看</p>
            <h2 style={{ margin: 0 }}>值得關注</h2>
          </div>
          <Link to="/opportunities" className="v1829-btn v1829-btn-tertiary">
            全部 →
          </Link>
        </div>
        {eligibleZero ? (
          <p className="muted" data-testid="no-tradable-top3" style={{ marginTop: 8, fontSize: "0.8125rem" }}>
            觀察清單 · 非交易機會
          </p>
        ) : null}
        {watch.length === 0 ? (
          <p className="muted" style={{ marginTop: 8 }}>
            {loading ? "載入中…" : "目前沒有可展示的關注標的"}
          </p>
        ) : (
          <div data-testid="watch-candidates" style={{ marginTop: 8 }}>
            <div className="v1829-feed-row v1829-feed-head desktop-only">
              <span>標的</span>
              <span>狀態</span>
              <span>主要原因</span>
              <span>風險</span>
              <span>Trust</span>
              <span>更新</span>
            </div>
            {watch.map((c) => (
              <div
                key={c.id}
                className="v1829-feed-row"
                data-testid="watch-candidate-card"
                data-tradable="false"
              >
                <Link to={`/market/${c.symbol}`} className="sym mono">
                  {c.symbol.replace("USDT", "")}
                </Link>
                <span>{STAGE_LABEL_ZH[c.stage] || c.stage}</span>
                <span>{plainReason(c.reasons?.[0] || "結構仍在觀察", true)}</span>
                <span className="mono">
                  {c.riskScore == null ? "—" : fmtNum(c.riskScore)}
                </span>
                <span className="muted" style={{ fontSize: "0.8125rem" }}>
                  {c.freshness === "LIVE" ? "即時" : c.freshness || "—"}
                </span>
                <span className="muted">{agoLabel(c.lastUpdatedAt)}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section
        className="v1829-panel v1829-col-4"
        aria-label="最新警報"
        data-testid="critical-alerts"
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <h2 style={{ margin: 0 }}>最新警報</h2>
          <Link to="/alerts" className="v1829-btn v1829-btn-tertiary">
            警報 →
          </Link>
        </div>
        {latestAlerts.length === 0 ? (
          <p className="muted" style={{ marginTop: 8 }}>
            目前沒有最新警報
          </p>
        ) : (
          <ul className="v1829-timeline" style={{ marginTop: 8 }}>
            {latestAlerts.map((a) => (
              <li key={a.id}>
                <span className="dot" aria-hidden />
                <div>
                  <Link to={a.href}>{a.text}</Link>
                  <span className="when">{a.when}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* ROW4: MARKET PULSE — real data only */}
      <section className="v1829-panel v1829-col-12" aria-label="市場脈動" data-testid="market-pulse">
        <h2>市場脈動</h2>
        <div className="v1829-pulse">
          <div className="v1829-pulse-cell">
            <div className="label">Funding</div>
            <div className="value mono">
              {funding.status === "live" && funding.value
                ? funding.value.display
                : "UNAVAILABLE"}
            </div>
          </div>
          <div className="v1829-pulse-cell">
            <div className="label">OI 5m 均變</div>
            <div className="value mono">
              {oiSample == null
                ? "UNAVAILABLE"
                : `${oiSample > 0 ? "+" : ""}${oiSample.toFixed(2)}%`}
            </div>
          </div>
          <div className="v1829-pulse-cell">
            <div className="label">波動活動</div>
            <div className="value mono">
              {volActivity == null ? "UNAVAILABLE" : `${volActivity.toFixed(2)}%`}
            </div>
          </div>
          <div className="v1829-pulse-cell">
            <div className="label">監控活動</div>
            <div className="value mono">{status?.symbolCount ?? "UNAVAILABLE"}</div>
          </div>
          <div className="v1829-pulse-cell">
            <div className="label">高風險／清算壓力</div>
            <div className="value mono">{liqProxy == null ? "UNAVAILABLE" : liqProxy}</div>
          </div>
        </div>
        <p className="muted" style={{ marginTop: 8, fontSize: "0.8125rem" }}>
          實測掃描池衍生 · 非假圖表 · Funding／OI 為產業術語
        </p>
      </section>
    </div>
  );
}
