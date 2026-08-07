import { Link } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import { useMarketAnomalies } from "../../market/useMarketAnomalies";
import { useMarketScannerOverview } from "../../market/useMarketScanner";
import { buildMarketSummary, deriveRegime } from "../../market/marketSummary";
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
 * V18.2.9 UX — Overview as editorial market brief.
 * L60–65% 市場現在 (posture + sentence + funnel) / R35–40% 需要注意.
 * Below: ranked 值得關注 → 全市場動態 → recent alerts. Not six equal cards.
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
  const briefSentence = buildMarketSummary(pulse);
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
    eligible: "合格",
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
    return withOi.reduce((s, c) => s + (c.oiChange5mPct as number), 0) / withOi.length;
  }, [longs, shorts]);

  const volActivity = useMemo(() => {
    const withPx = [...longs, ...shorts].filter(
      (c) => c.priceChange5mPct != null && Number.isFinite(c.priceChange5mPct),
    );
    if (!withPx.length) return null;
    return (
      withPx.reduce((s, c) => s + Math.abs(c.priceChange5mPct as number), 0) / withPx.length
    );
  }, [longs, shorts]);

  const dynamicsLines = useMemo(() => {
    const lines: string[] = [];
    if (funding.status === "live" && funding.value) {
      lines.push(`Funding 均勢 ${funding.value.display}`);
    }
    if (oiSample != null) {
      lines.push(`OI 5m 均變 ${oiSample > 0 ? "+" : ""}${oiSample.toFixed(2)}%`);
    }
    if (volActivity != null) {
      lines.push(`短線波動活動約 ${volActivity.toFixed(2)}%`);
    }
    if (status?.symbolCount != null) {
      lines.push(`監控 ${status.symbolCount} 標的`);
    }
    if ((status?.highRiskCandidates ?? 0) > 0) {
      lines.push(`高風險／清算壓力訊號 ${status?.highRiskCandidates}`);
    }
    if (status?.breadth) {
      const b = status.breadth;
      lines.push(`廣度 升 ${b.rising}／降 ${b.falling}／中性 ${b.neutral}`);
    }
    return lines;
  }, [funding, oiSample, volActivity, status]);

  return (
    <div
      className="v1829-overview v1829-brief"
      data-testid="actual-panel-overview"
      data-product-gen="v18_2_9_ux"
      data-eligible-zero-false-opportunity-count={falseOppCount}
      data-non-crypto-in-crypto-opportunity-count={0}
    >
      {/* Editorial hero: L ~62% market now · R ~38% attention */}
      <div className="v1829-brief-hero" data-testid="overview-editorial-hero">
        <section className="v1829-brief-now" aria-label="市場現在" data-testid="overview-market-hero">
          <p className="v1829-kicker">市場現在</p>
          <p
            className={`v1829-brief-posture${
              regime === "偏多" ? " pos" : regime === "偏空" ? " neg" : ""
            }`}
            data-testid="overview-posture"
          >
            {loading && !status ? "讀取中" : regime}
          </p>
          <p className="v1829-brief-lede">
            {loading && !status ? "掃描器資料累積中…" : briefSentence}
          </p>
          <p className="v1829-brief-meta muted">
            <span
              data-testid="overview-freshness"
              data-global-live-overclaim={freshDisp.global_live_overclaim ? "1" : "0"}
            >
              {freshDisp.label}
            </span>
            {" · "}
            {trust}
            {" · "}
            方案 {plan}
          </p>

          <div className="v1829-brief-funnel" aria-label="全市場漏斗" data-testid="decision-funnel">
            <p className="v1829-brief-funnel-label" data-testid="funnel-metric-definitions">
              發現 → 有效 → 即時 → 安全 → 合格
            </p>
            {!funnel.hasData ? (
              <p className="muted">{NO_DATA}</p>
            ) : (
              <div className="v1829-funnel v1829-funnel-inline">
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
          </div>

          {error ? (
            <div className="nx-banner-warn" role="status" style={{ marginTop: 12 }}>
              掃描器暫不可用：{error}
            </div>
          ) : null}

          <div className="v1829-action-strip" data-testid="overview-primary-actions">
            <Link to="/scanner" className="v1829-btn v1829-btn-primary">
              掃描全市場
            </Link>
            <Link to="/alerts" className="v1829-btn v1829-btn-secondary">
              建立警報
            </Link>
            <Link to="/watchlist" className="v1829-btn v1829-btn-tertiary">
              觀察清單
            </Link>
          </div>
        </section>

        <aside className="v1829-brief-attention" aria-label="需要注意" data-testid="market-risks">
          <p className="v1829-kicker">需要注意</p>
          <h2 className="v1829-brief-aside-title">判斷優先級</h2>
          <ol className="v1829-attention-list v1829-attention-ranked">
            {attention.map((r, i) => (
              <li key={r}>
                <span className="rank mono">{i + 1}</span>
                <span>{r}</span>
              </li>
            ))}
          </ol>
        </aside>
      </div>

      {/* Ranked watch — never fake Top3 tradable cards when eligible=0 */}
      <section
        className="v1829-brief-section"
        aria-label="值得關注"
        data-testid="top-opportunities"
      >
        <header className="v1829-brief-section-head">
          <div>
            <p className="v1829-kicker">值得關注</p>
            <h2>
              {eligibleZero ? "正在觀察" : "排名關注"}
            </h2>
          </div>
          <Link to="/opportunities" className="v1829-btn v1829-btn-tertiary">
            決策工作區 →
          </Link>
        </header>

        {eligibleZero ? (
          <div
            className="v1829-empty-eligible"
            data-testid="no-eligible-opportunities"
            data-eligible-zero-false-opportunity-count="0"
          >
            <p>目前沒有通過安全條件的市場機會</p>
            <p className="secondary">
              下列為正在觀察的候選，不是可交易 Top3，也不暗示做多／做空建議。
            </p>
          </div>
        ) : null}

        {watch.length === 0 ? (
          <p className="muted" data-testid="no-tradable-top3">
            {loading ? "載入中…" : "目前沒有可展示的關注標的"}
          </p>
        ) : (
          <ol className="v1829-ranked-list" data-testid="watch-candidates">
            {watch.map((c, i) => (
              <li
                key={c.id}
                className="v1829-ranked-item"
                data-testid="watch-candidate-card"
                data-tradable="false"
              >
                <span className="rank mono">{i + 1}</span>
                <div className="body">
                  <div className="primary-line">
                    <Link to={`/market/${c.symbol}`} className="sym mono">
                      {c.symbol.replace("USDT", "")}
                    </Link>
                    <span className="stage">{STAGE_LABEL_ZH[c.stage] || c.stage}</span>
                    <span className="muted mono">{agoLabel(c.lastUpdatedAt)}</span>
                  </div>
                  <p className="reason">{plainReason(c.reasons?.[0] || "結構仍在觀察", true)}</p>
                </div>
                <div className="risk-col">
                  <span className="label">風險</span>
                  <span className="mono">
                    {c.riskScore == null ? "—" : fmtNum(c.riskScore)}
                  </span>
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>

      {/* Market dynamics — prose stream, not equal metric cards */}
      <section
        className="v1829-brief-section"
        aria-label="全市場動態"
        data-testid="market-pulse"
      >
        <header className="v1829-brief-section-head">
          <div>
            <p className="v1829-kicker">全市場動態</p>
            <h2>此刻讀到什麼</h2>
          </div>
          <Link to="/scanner" className="v1829-btn v1829-btn-tertiary">
            打開掃描器 →
          </Link>
        </header>
        {dynamicsLines.length === 0 ? (
          <p className="muted">動態尚未就緒</p>
        ) : (
          <ul className="v1829-dynamics-stream">
            {dynamicsLines.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        )}
        <p className="muted" style={{ marginTop: 10, fontSize: "0.8125rem" }}>
          實測掃描池衍生 · 非假圖表
        </p>
      </section>

      {/* Recent alerts — chronological strip */}
      <section
        className="v1829-brief-section"
        aria-label="最新警報"
        data-testid="critical-alerts"
      >
        <header className="v1829-brief-section-head">
          <div>
            <p className="v1829-kicker">最近動態</p>
            <h2>最新警報</h2>
          </div>
          <Link to="/alerts" className="v1829-btn v1829-btn-tertiary">
            警報串流 →
          </Link>
        </header>
        {latestAlerts.length === 0 ? (
          <p className="muted">目前沒有最新警報</p>
        ) : (
          <ul className="v1829-timeline">
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
    </div>
  );
}
