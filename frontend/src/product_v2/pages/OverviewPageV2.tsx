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
  if (!ts) return "-";
  const sec = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.round(sec / 60)}m`;
  return `${Math.round(sec / 3600)}h`;
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
    items.push("\u76ee\u524d\u98a8\u96aa\u689d\u4ef6\u672a\u901a\u904e \u2014 \u5c1a\u7121\u901a\u904e\u5b89\u5168\u9580\u6abb\u7684\u6a19\u7684");
  }
  if ((status.highRiskCandidates ?? 0) > 0) {
    items.push(`\u9ad8\u98a8\u96aa\uff0f\u904e\u71b1\u6a19\u7684 ${status.highRiskCandidates}\uff0c\u512a\u5148\u9632\u5b88`);
  }
  const fresh = String(status.freshness || "").toUpperCase();
  if (
    fresh.includes("STALE") ||
    fresh.includes("DEGRAD") ||
    fresh.includes("DELAY") ||
    fresh.includes("PARTIAL")
  ) {
    items.push("\u90e8\u5206\u5373\u6642\uff0f\u8cc7\u6599\u54c1\u8cea\u4e0b\u964d \u2014 \u89e3\u8b80\u61c9\u66f4\u4fdd\u5b88");
  }
  if (status.lastError) {
    items.push("\u6383\u63cf\u670d\u52d9\u56de\u5831\u7570\u5e38\uff0c\u66ab\u4ee5\u5b89\u5168\u72c0\u614b\u5448\u73fe");
  }
  if (alertCount > 0) {
    items.push(`\u6709 ${alertCount} \u5247\u9700\u95dc\u6ce8\u7684\u8b66\u5831\uff0f\u7570\u52d5`);
  }
  const insuff = status.breadth?.insufficient ?? 0;
  const sym = status.symbolCount ?? 0;
  if (sym > 0 && insuff >= Math.max(1, Math.floor(sym * 0.4))) {
    items.push("\u591a\u6578\u6a19\u7684\u8cc7\u6599\u7a97\u53e3\u4e0d\u8db3\uff0c\u89e3\u8b80\u7a7a\u9593\u53d7\u9650");
  }
  if (items.length === 0) {
    items.push("\u76ee\u524d\u7121\u7a81\u51fa\u9700\u7acb\u5373\u8655\u7406\u4e8b\u9805\uff1b\u53ef\u6301\u7e8c\u6383\u63cf\u8207\u89c0\u5bdf");
  }
  return items.slice(0, 5);
}

function funnelEligibleZero(v: unknown): boolean {
  if (v == null) return false;
  if (typeof v === "number") return v === 0;
  return String(v) === "0";
}

/** Product V2 Overview \u2014 market home / briefing. */
export function OverviewPageV2() {
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

  const trust = memberDataTrustLabel({
    scannerFreshness: error ? "DEGRADED" : status?.freshness,
    confirmedCandidates: status?.confirmedCandidates,
    highRiskCandidates: status?.highRiskCandidates,
    wsConnected: status?.wsConnected,
    lastError: status?.lastError,
  }).label_zh;

  const latestAlerts = useMemo(() => {
    const fromAnom = anomalies
      .filter((a) => a.status === "NEW" || a.status === "ACTIVE")
      .slice(0, 5)
      .map((a) => ({
        id: a.id,
        text: `${a.symbol?.replace("USDT", "") || "-"} \u00b7 ${a.title || a.type || "\u7570\u52d5"}`,
        href: a.symbol ? `/market/${a.symbol}` : "/alerts",
        when: agoLabel(a.lastSeenAt ?? a.observedAt ?? null),
        ts: a.lastSeenAt ?? a.observedAt ?? 0,
      }));
    const fromEvents = events.slice(0, 5).map((e) => ({
      id: e.id,
      text: `${e.symbol.replace("USDT", "")} \u00b7 ${e.explanation}`,
      href: `/market/${e.symbol}`,
      when: agoLabel(e.timestamp ?? null),
      ts: e.timestamp ?? 0,
    }));
    const merged = [...fromAnom, ...fromEvents].sort((a, b) => b.ts - a.ts);
    const seen = new Set<string>();
    return merged
      .filter((m) => {
        if (seen.has(m.id)) return false;
        seen.add(m.id);
        return true;
      })
      .slice(0, 6);
  }, [anomalies, events]);

  const marketFeed = useMemo(() => {
    return events.slice(0, 8).map((e) => ({
      id: e.id,
      text: `${e.symbol.replace("USDT", "")} \u00b7 ${e.type || "\u52d5\u614b"} \u00b7 ${e.explanation}`,
      href: `/market/${e.symbol}`,
      when: agoLabel(e.timestamp ?? null),
    }));
  }, [events]);

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
    market_discovery: "\u767c\u73fe",
    data_valid: "\u6709\u6548",
    runtime_observable: "\u5373\u6642",
    safety_review: "\u5b89\u5168",
    eligible: "\u5408\u683c",
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
    ? `\u5347 ${status.breadth.rising}\uff0f\u964d ${status.breadth.falling}\uff0f\u4e2d\u6027 ${status.breadth.neutral}`
    : "-";

  return (
    <div
      className="mp2-overview"
      data-testid="product-v2-overview"
      data-nexus-product-generation="2"
      data-above-fold-card-count="0"
      data-eligible-zero-false-opportunity-count={falseOppCount}
      data-non-crypto-in-crypto-opportunity-count={0}
    >
      <header style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <p className="mp2-kicker">{"\u5e02\u5834\u9996\u9801"}</p>
          <h1 className="mp2-page-title">{"\u5e02\u5834\u4eca\u5929"}</h1>
          <p className="mp2-page-sub">{"\u7c21\u5831\u512a\u5148 \u00b7 \u975e\u4ea4\u6613\u5efa\u8b70"}</p>
        </div>
        <div className="muted" style={{ fontSize: "0.8125rem", textAlign: "right" }}>
          <div
            data-testid="overview-freshness"
            data-global-live-overclaim={freshDisp.global_live_overclaim ? "1" : "0"}
          >
            {freshDisp.label}
          </div>
          <div>{trust}</div>
          <div>{"\u65b9\u6848"} {plan}</div>
        </div>
      </header>

      <div className="mp2-pulse" aria-label={"\u5e02\u5834\u8108\u52d5"} data-testid="market-pulse">
        <div className="mp2-pulse-cell">
          <span className="lbl">Funding</span>
          <span className="val">
            {funding.status === "live" && funding.value ? funding.value.display : "-"}
          </span>
        </div>
        <div className="mp2-pulse-cell">
          <span className="lbl">OI 5m</span>
          <span className="val">
            {oiSample == null ? "-" : `${oiSample > 0 ? "+" : ""}${oiSample.toFixed(2)}%`}
          </span>
        </div>
        <div className="mp2-pulse-cell">
          <span className="lbl">{"\u77ed\u7dda\u6ce2\u52d5"}</span>
          <span className="val">{volActivity == null ? "-" : `${volActivity.toFixed(2)}%`}</span>
        </div>
        <div className="mp2-pulse-cell">
          <span className="lbl">{"\u5ee3\u5ea6"}</span>
          <span className="val" style={{ fontSize: "0.8125rem" }}>
            {breadthLine}
          </span>
        </div>
      </div>

      <div className="mp2-ov-split" data-testid="overview-editorial-hero">
        <section aria-label={"\u5e02\u5834\u4eca\u5929"} data-testid="overview-market-hero">
          <p className="mp2-kicker">{"\u5e02\u5834\u4eca\u5929"}</p>
          <p
            className={`posture${regime === "\u504f\u591a" ? " pos" : regime === "\u504f\u7a7a" ? " neg" : ""}`}
            data-testid="overview-posture"
          >
            {loading && !status ? "\u8b80\u53d6\u4e2d" : regime}
          </p>
          <p className="lede">
            {loading && !status ? "\u6383\u63cf\u5668\u8cc7\u6599\u7d2f\u7a4d\u4e2d\u2026" : briefSentence}
          </p>

          <div aria-label={"\u5168\u5e02\u5834\u6f0f\u6597"} data-testid="decision-funnel">
            <p className="mp2-kicker" data-testid="funnel-metric-definitions">
              {"\u767c\u73fe \u2192 \u6709\u6548 \u2192 \u5373\u6642 \u2192 \u5b89\u5168 \u2192 \u5408\u683c"}
            </p>
            {!funnel.hasData ? (
              <p className="muted">{NO_DATA}</p>
            ) : (
              <div className="mp2-funnel">
                {funnel.stages.map((s) => (
                  <div
                    key={s.key}
                    className="mp2-funnel-step"
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
            <div className="mp2-banner">
              {"\u6383\u63cf\u5668\u66ab\u4e0d\u53ef\u7528\uff1a"}
              {error}
            </div>
          ) : null}

          <div className="mp2-actions" data-testid="overview-primary-actions">
            <Link to="/scanner" className="mp2-btn mp2-btn-primary">
              {"\u6383\u63cf\u5168\u5e02\u5834"}
            </Link>
            <Link to="/opportunities" className="mp2-btn">
              {"\u627e\u6a5f\u6703"}
            </Link>
          </div>
        </section>

        <aside aria-label={"\u503c\u5f97\u6ce8\u610f"} data-testid="market-risks">
          <p className="mp2-kicker">{"\u503c\u5f97\u6ce8\u610f"}</p>
          <h2 className="mp2-page-title" style={{ fontSize: "1.05rem" }}>
            {"\u512a\u5148\u8655\u7406"}
          </h2>
          <ol className="mp2-rank-list">
            {attention.map((r, i) => (
              <li key={r}>
                <span className="mp2-rank-n">{i + 1}</span>
                <span>{r}</span>
              </li>
            ))}
          </ol>
          <div className="mp2-actions">
            <Link to="/alerts" className="mp2-btn mp2-btn-ghost">
              {"\u8b66\u5831\u6642\u9593\u8ef8 \u2192"}
            </Link>
          </div>
        </aside>
      </div>

      <section className="mp2-section" aria-label={"\u6b63\u5728\u89c0\u5bdf"} data-testid="top-opportunities">
        <header className="mp2-section-head">
          <div>
            <p className="mp2-kicker">{"\u6b63\u5728\u89c0\u5bdf"}</p>
            <h2>
              {eligibleZero
                ? "\u89c0\u5bdf\u5019\u9078\uff08\u975e\u53ef\u4ea4\u6613 Top3\uff09"
                : "\u6392\u540d\u95dc\u6ce8"}
            </h2>
          </div>
          <Link to="/opportunities" className="mp2-btn mp2-btn-ghost">
            {"\u6c7a\u7b56\u5de5\u4f5c\u5340 \u2192"}
          </Link>
        </header>

        {eligibleZero ? (
          <div className="mp2-empty" data-testid="no-eligible-opportunities">
            <strong>{"\u76ee\u524d\u6c92\u6709\u901a\u904e\u5b89\u5168\u689d\u4ef6\u7684\u5e02\u5834\u6a5f\u6703"}</strong>
            <div>{"\u4e0b\u5217\u70ba\u6b63\u5728\u89c0\u5bdf\u7684\u5019\u9078\uff0c\u4e0d\u662f\u53ef\u4ea4\u6613 Top3\u3002"}</div>
          </div>
        ) : null}

        {watch.length === 0 ? (
          <p className="muted" data-testid="no-tradable-top3">
            {loading ? "\u8f09\u5165\u4e2d\u2026" : "\u76ee\u524d\u6c92\u6709\u53ef\u5c55\u793a\u7684\u95dc\u6ce8\u6a19\u7684"}
          </p>
        ) : (
          <table className="mp2-table" data-testid="watch-candidates">
            <thead>
              <tr>
                <th>#</th>
                <th>{"\u6a19\u7684"}</th>
                <th>{"\u968e\u6bb5"}</th>
                <th>{"\u539f\u56e0"}</th>
                <th>{"\u98a8\u96aa"}</th>
                <th>{"\u66f4\u65b0"}</th>
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
                  <td>{plainReason(c.reasons?.[0] || "\u7d50\u69cb\u4ecd\u5728\u89c0\u5bdf", true)}</td>
                  <td className="mono">{c.riskScore == null ? "-" : fmtNum(c.riskScore)}</td>
                  <td className="mono muted">{agoLabel(c.lastUpdatedAt)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="mp2-section" aria-label={"\u5168\u5e02\u5834\u52d5\u614b"}>
        <header className="mp2-section-head">
          <div>
            <p className="mp2-kicker">{"\u5168\u5e02\u5834\u52d5\u614b"}</p>
            <h2>{"\u4e8b\u4ef6\u6d41"}</h2>
          </div>
        </header>
        {marketFeed.length === 0 ? (
          <p className="muted">{"\u76ee\u524d\u6c92\u6709\u5e02\u5834\u52d5\u614b"}</p>
        ) : (
          <ul className="mp2-feed">
            {marketFeed.map((a) => (
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

      <section className="mp2-section" aria-label={"\u6700\u65b0\u8b66\u5831"} data-testid="critical-alerts">
        <header className="mp2-section-head">
          <div>
            <p className="mp2-kicker">{"\u6700\u65b0\u8b66\u5831"}</p>
            <h2>{"\u9700\u95dc\u6ce8"}</h2>
          </div>
          <div className="mp2-actions" style={{ marginTop: 0 }}>
            <Link to="/watchlist" className="mp2-btn mp2-btn-ghost">
              {"\u89c0\u5bdf\u6e05\u55ae"}
            </Link>
            <Link to="/alerts" className="mp2-btn mp2-btn-ghost">
              {"\u5168\u90e8\u8b66\u5831 \u2192"}
            </Link>
          </div>
        </header>
        {latestAlerts.length === 0 ? (
          <p className="muted">{"\u76ee\u524d\u6c92\u6709\u6700\u65b0\u8b66\u5831"}</p>
        ) : (
          <ul className="mp2-feed">
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
