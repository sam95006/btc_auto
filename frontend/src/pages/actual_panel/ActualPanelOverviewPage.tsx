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
 * V18.2.10 — Overview recomposed from zero.
 * Compact header → market pulse → L~65% Market Now+funnel / R~35% 值得注意 →
 * 正在觀察 ranked table → timeline. Actions nestled in sections.
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

  const breadthLine = status?.breadth
    ? `升 ${status.breadth.rising}／降 ${status.breadth.falling}／中性 ${status.breadth.neutral}`
    : "—";

  return (
    <div
      className="nx10-ov"
      data-testid="actual-panel-overview"
      data-product-gen="v18_2_10"
      data-eligible-zero-false-opportunity-count={falseOppCount}
      data-non-crypto-in-crypto-opportunity-count={0}
    >
      <header className="nx10-ov-head">
        <div>
          <h1 className="nx10-page-title">總覽</h1>
          <p className="nx10-page-sub">市場現況與觀察優先級 · 非交易建議</p>
        </div>
        <div className="nx10-ov-head-meta">
          <span
            data-testid="overview-freshness"
            data-global-live-overclaim={freshDisp.global_live_overclaim ? "1" : "0"}
          >
            {freshDisp.label}
          </span>
          <span>{trust}</span>
          <span>方案 {plan}</span>
        </div>
      </header>

      <div className="nx10-pulse" aria-label="市場脈動" data-testid="market-pulse">
        <div className="nx10-pulse-cell">
          <span className="lbl">Funding</span>
          <span className="val">
            {funding.status === "live" && funding.value ? funding.value.display : "—"}
          </span>
        </div>
        <div className="nx10-pulse-cell">
          <span className="lbl">OI 5m</span>
          <span className="val">
            {oiSample == null ? "—" : `${oiSample > 0 ? "+" : ""}${oiSample.toFixed(2)}%`}
          </span>
        </div>
        <div className="nx10-pulse-cell">
          <span className="lbl">短線波動</span>
          <span className="val">{volActivity == null ? "—" : `${volActivity.toFixed(2)}%`}</span>
        </div>
        <div className="nx10-pulse-cell">
          <span className="lbl">廣度</span>
          <span className="val" style={{ fontSize: "0.8125rem" }}>
            {breadthLine}
          </span>
        </div>
      </div>

      <div className="nx10-ov-split" data-testid="overview-editorial-hero">
        <section className="nx10-ov-now" aria-label="市場現在" data-testid="overview-market-hero">
          <p className="nx10-kicker">Market Now</p>
          <p
            className={`nx10-ov-posture${
              regime === "偏多" ? " pos" : regime === "偏空" ? " neg" : ""
            }`}
            data-testid="overview-posture"
          >
            {loading && !status ? "讀取中" : regime}
          </p>
          <p className="nx10-ov-lede">
            {loading && !status ? "掃描器資料累積中…" : briefSentence}
          </p>

          <div aria-label="全市場漏斗" data-testid="decision-funnel">
            <p className="nx10-kicker" data-testid="funnel-metric-definitions">
              發現 → 有效 → 即時 → 安全 → 合格
            </p>
            {!funnel.hasData ? (
              <p className="muted">{NO_DATA}</p>
            ) : (
              <div className="nx10-funnel">
                {funnel.stages.map((s) => (
                  <div
                    key={s.key}
                    className="nx10-funnel-step"
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

          <div className="nx10-actions" data-testid="overview-primary-actions">
            <Link to="/scanner" className="nx10-btn nx10-btn-primary">
              掃描全市場
            </Link>
            <Link to="/opportunities" className="nx10-btn nx10-btn-secondary">
              找機會
            </Link>
          </div>
        </section>

        <aside className="nx10-ov-attn" aria-label="值得注意" data-testid="market-risks">
          <p className="nx10-kicker">值得注意</p>
          <h2 className="nx10-page-title" style={{ fontSize: "1.05rem" }}>
            優先處理
          </h2>
          <ol className="nx10-rank-list">
            {attention.map((r, i) => (
              <li key={r}>
                <span className="nx10-rank-n">{i + 1}</span>
                <span>{r}</span>
              </li>
            ))}
          </ol>
          <div className="nx10-actions">
            <Link to="/alerts" className="nx10-btn nx10-btn-tertiary">
              警報時間軸 →
            </Link>
          </div>
        </aside>
      </div>

      <section aria-label="正在觀察" data-testid="top-opportunities">
        <header className="nx10-section-head">
          <div>
            <p className="nx10-kicker">正在觀察</p>
            <h2>{eligibleZero ? "觀察候選（非可交易 Top3）" : "排名關注"}</h2>
          </div>
          <Link to="/opportunities" className="nx10-btn nx10-btn-tertiary">
            決策工作區 →
          </Link>
        </header>

        {eligibleZero ? (
          <div
            className="nx10-empty"
            data-testid="no-eligible-opportunities"
            data-eligible-zero-false-opportunity-count="0"
          >
            <strong>目前沒有通過安全條件的市場機會</strong>
            下列為正在觀察的候選，不是可交易 Top3。
          </div>
        ) : null}

        {watch.length === 0 ? (
          <p className="muted" data-testid="no-tradable-top3">
            {loading ? "載入中…" : "目前沒有可展示的關注標的"}
          </p>
        ) : (
          <table className="nx10-watch-table" data-testid="watch-candidates">
            <thead>
              <tr>
                <th>#</th>
                <th>標的</th>
                <th>階段</th>
                <th>原因</th>
                <th>風險</th>
                <th>更新</th>
              </tr>
            </thead>
            <tbody>
              {watch.map((c, i) => (
                <tr key={c.id} data-testid="watch-candidate-card" data-tradable="false">
                  <td className="mono muted">{i + 1}</td>
                  <td>
                    <Link to={`/market/${c.symbol}`} className="mono">
                      {c.symbol.replace("USDT", "")}
                    </Link>
                  </td>
                  <td>{STAGE_LABEL_ZH[c.stage] || c.stage}</td>
                  <td>{plainReason(c.reasons?.[0] || "結構仍在觀察", true)}</td>
                  <td className="mono">{c.riskScore == null ? "—" : fmtNum(c.riskScore)}</td>
                  <td className="mono muted">{agoLabel(c.lastUpdatedAt)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section aria-label="最新動態" data-testid="critical-alerts">
        <header className="nx10-section-head">
          <div>
            <p className="nx10-kicker">時間軸</p>
            <h2>最新動態</h2>
          </div>
          <div className="nx10-actions" style={{ marginTop: 0 }}>
            <Link to="/watchlist" className="nx10-btn nx10-btn-tertiary">
              觀察清單
            </Link>
            <Link to="/alerts" className="nx10-btn nx10-btn-tertiary">
              全部警報 →
            </Link>
          </div>
        </header>
        {latestAlerts.length === 0 ? (
          <p className="muted">目前沒有最新警報</p>
        ) : (
          <ul className="nx10-timeline">
            {latestAlerts.map((a) => (
              <li key={a.id}>
                <span className="dot" aria-hidden />
                <div>
                  <Link to={a.href}>{a.text}</Link>
                </div>
                <span className="when">{a.when}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
