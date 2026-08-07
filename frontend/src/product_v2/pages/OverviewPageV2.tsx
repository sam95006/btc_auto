import { Link } from "react-router-dom";
import { useMemo, useState } from "react";
import { STAGE_LABEL_ZH } from "../../market/scannerApi";
import { buildFunnelDisplay, NO_DATA } from "../../wave4/noDataFunnel";
import { usePublicEntitlements } from "../../member/public_entitlements_v18_2";
import { usePreviewReviewPlan } from "../../member/usePreviewReviewPlan";
import {
  buildMarketMetricFunnel,
  memberDataTrustLabel,
} from "../../market/marketMetricFunnel";
import {
  eligibleZeroFalseOpportunityCount,
  mapMarketFreshnessDisplay,
} from "../../market/dataTruthFreshness";
import { deriveRegime } from "../../market/marketSummary";
import { useLiveMarketRanking } from "../useLiveMarketRanking";
import {
  filterRankingRows,
  formatRankMove,
  type RankingTab,
} from "../../market/liveMarketRanking";
import { formatUsd } from "../../market/freshness";

function agoLabel(ts?: number | null) {
  if (!ts) return "?";
  const sec = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.round(sec / 60)}m`;
  return `${Math.round(sec / 3600)}h`;
}

function fmtPct(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "?";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

const TABS: { id: RankingTab; label: string }[] = [
  { id: "ALL", label: "??" },
  { id: "LONG", label: "??" },
  { id: "SHORT", label: "??" },
  { id: "MOVE", label: "??" },
  { id: "OI", label: "OI" },
  { id: "ACTIVITY", label: "Activity" },
  { id: "RISK", label: "??" },
];

/** Product V2 Market Home ? Live Radar first, Market Now secondary. */
export function OverviewPageV2() {
  const ranking = useLiveMarketRanking();
  const { status, events, loading, error, qualified_count, radar, rows } = ranking;
  const previewPlan = usePreviewReviewPlan("FREE");
  const { dto } = usePublicEntitlements(previewPlan);
  const plan = dto?.plan ?? previewPlan;
  const [tab, setTab] = useState<RankingTab>("ALL");
  const [coverageOpen, setCoverageOpen] = useState(false);

  const falseOppCount = eligibleZeroFalseOpportunityCount({
    eligible: status?.confirmedCandidates,
    renderedTradableOpportunityCount: 0,
  });

  const regime = deriveRegime({
    longCandidates: status?.longCandidates,
    shortCandidates: status?.shortCandidates,
    confirmedCandidates: status?.confirmedCandidates,
    highRiskCandidates: status?.highRiskCandidates,
    breadth: status?.breadth,
    symbolCount: status?.symbolCount,
    freshness: status?.freshness,
  });

  const trust = memberDataTrustLabel({
    scannerFreshness: error ? "DEGRADED" : status?.freshness,
    confirmedCandidates: status?.confirmedCandidates,
    highRiskCandidates: status?.highRiskCandidates,
    wsConnected: status?.wsConnected,
    lastError: status?.lastError,
  }).label_zh;

  const freshDisp = mapMarketFreshnessDisplay(status?.freshness, {
    wsConnected: status?.wsConnected,
    lastError: status?.lastError ?? error,
    source: status?.source,
  });

  const displayRows = useMemo(
    () => filterRankingRows(radar.length ? radar : rows, tab).slice(0, 24),
    [radar, rows, tab],
  );

  const qualifiedDisplay =
    status?.confirmedCandidates != null ? status.confirmedCandidates : qualified_count;

  const metricDefs = buildMarketMetricFunnel({
    breadthMarketCount: status?.breadthMarketCount ?? status?.symbolCount,
    symbolCount: status?.symbolCount,
    highRiskCandidates: status?.highRiskCandidates,
    confirmedCandidates: status?.confirmedCandidates,
    longCandidates: status?.longCandidates,
    shortCandidates: status?.shortCandidates,
    freshness: status?.freshness,
  }).filter((m) => m.metric_name !== "candidate");

  const funnelLabels: Record<string, string> = {
    market_discovery: "??",
    data_valid: "??",
    runtime_observable: "??",
    safety_review: "??",
    eligible: "??",
  };

  const funnel = buildFunnelDisplay(
    metricDefs.map((m) => ({
      key: m.metric_name,
      label: funnelLabels[m.metric_name] || m.label_zh,
      value: m.current_value,
    })),
    Boolean(status) && !loading,
  );

  const rankFeed = useMemo(() => {
    const fromRank = ranking.events.slice(0, 8).map((e) => ({
      id: e.id,
      text: `${e.symbol.replace("USDT", "")} � ${e.rank_event}${
        e.rank != null ? ` #${e.rank}` : ""
      }${e.previous_rank != null ? ` (was #${e.previous_rank})` : ""} � ${e.primary_reason}`,
      href: `/market/${e.symbol}`,
      when: agoLabel(e.timestamp),
      ts: e.timestamp,
    }));
    const fromMerged = events.slice(0, 6).map((e) => ({
      id: `m-${e.id}`,
      text: `${e.symbol.replace("USDT", "")} � ${e.primary_reason}`,
      href: `/market/${e.symbol}`,
      when: agoLabel(e.timestamp),
      ts: e.timestamp ?? 0,
    }));
    return [...fromRank, ...fromMerged]
      .sort((a, b) => b.ts - a.ts)
      .filter((m, i, arr) => arr.findIndex((x) => x.id === m.id) === i)
      .slice(0, 8);
  }, [ranking.events, events]);

  const breadthLine = status?.breadth
    ? `? ${status.breadth.rising}?? ${status.breadth.falling}??? ${status.breadth.neutral}`
    : "?";

  return (
    <div
      className="mp2-overview"
      data-testid="product-v2-overview"
      data-nexus-product-generation="2"
      data-above-fold-card-count="0"
      data-eligible-zero-false-opportunity-count={falseOppCount}
      data-non-crypto-in-crypto-opportunity-count={0}
      data-fixed-symbol-dependency-count={ranking.fixed_symbol_dependency_count}
      data-ranking-universe={ranking.universe_size}
      data-ranking-active={ranking.active_count}
      data-ranking-qualified={qualifiedDisplay}
    >
      <header style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h1 className="mp2-page-title">??</h1>
          <p className="mp2-page-sub">??????? � ????</p>
        </div>
        <div className="muted" style={{ fontSize: "0.8125rem", textAlign: "right" }}>
          <div data-testid="overview-freshness">{freshDisp.label}</div>
          <div>{trust}</div>
          <div>{plan}</div>
        </div>
      </header>

      {error ? <div className="mp2-banner">{error}</div> : null}

      <div className="mp2-home-split" data-testid="market-home-layout">
        <section className="mp2-live-radar" aria-label="NEXUS LIVE RADAR" data-testid="live-radar">
          <header className="mp2-section-head">
            <div>
              <p className="mp2-kicker">NEXUS LIVE RADAR</p>
              <h2>
                ???? � {ranking.active_count} ?
                <span className="muted" style={{ fontWeight: 500, fontSize: "0.8125rem", marginLeft: 8 }}>
                  ?? {agoLabel(ranking.updated_at)}
                </span>
              </h2>
            </div>
            <Link to="/opportunities" className="mp2-btn mp2-btn-ghost">
              ?? ?
            </Link>
          </header>

          <div className="mp2-chip-row" role="tablist" aria-label="????">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                className={tab === t.id ? "active" : undefined}
                onClick={() => setTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>

          {loading && !displayRows.length ? <p className="muted">????</p> : null}
          {!loading && !displayRows.length ? (
            <p className="muted" data-testid="radar-empty">
              ????????????
            </p>
          ) : (
            <div className="mp2-scanner-wrap">
              <table className="mp2-table" data-testid="live-radar-table">
                <thead>
                  <tr>
                    <th>Rank</th>
                    <th>Symbol</th>
                    <th>Price</th>
                    <th>24h</th>
                    <th>NEX State</th>
                    <th>Score</th>
                    <th>Activity</th>
                    <th>OI</th>
                    <th>Funding</th>
                    <th>Risk</th>
                    <th>?</th>
                    <th>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {displayRows.map((r) => (
                    <tr key={r.candidate_id}>
                      <td className="mono">{r.rank}</td>
                      <td>
                        <Link to={`/market/${r.symbol}`} className="mono">
                          {r.symbol.replace("USDT", "")}
                        </Link>
                      </td>
                      <td className="mono">{r.price == null ? "?" : formatUsd(r.price)}</td>
                      <td className={`mono ${(r.change_24h ?? 0) >= 0 ? "pos" : "neg"}`}>
                        {fmtPct(r.change_24h)}
                      </td>
                      <td>{STAGE_LABEL_ZH[r.stage] || r.stage}</td>
                      <td className="mono">{Math.round(r.rank_score)}</td>
                      <td className="mono">{r.activity_state}</td>
                      <td className="mono">{fmtPct(r.oi_change)}</td>
                      <td className="mono">
                        {r.funding_rate == null ? "?" : `${(r.funding_rate * 100).toFixed(3)}%`}
                      </td>
                      <td className={`mono ${r.risk_score >= 70 ? "neg" : ""}`}>
                        {Math.round(r.risk_score)}
                      </td>
                      <td className="mono">{formatRankMove(r)}</td>
                      <td className="mono muted">{agoLabel(r.last_rank_update)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <aside className="mp2-market-now" aria-label="MARKET NOW" data-testid="market-now">
          <p className="mp2-kicker">MARKET NOW</p>
          <h2 className="mp2-page-title" style={{ fontSize: "1.05rem" }}>
            {loading && !status ? "???" : regime}
          </h2>
          <dl className="mp2-term-dl">
            <div>
              <dt>??</dt>
              <dd>{breadthLine}</dd>
            </div>
            <div>
              <dt>????</dt>
              <dd className="mono">{status?.highRiskCandidates ?? "?"}</dd>
            </div>
            <div>
              <dt>Data Trust</dt>
              <dd>{trust}</dd>
            </div>
            <div>
              <dt>????</dt>
              <dd className="mono" data-testid="qualified-count">
                {qualifiedDisplay ?? 0}
              </dd>
            </div>
          </dl>
          {qualifiedDisplay === 0 ? (
            <div className="mp2-empty" data-testid="no-eligible-opportunities" style={{ marginTop: 12 }}>
              ????? 0 ? Live Radar ??????
            </div>
          ) : null}

          <p className="mp2-kicker" style={{ marginTop: 16 }}>
            ????
          </p>
          {rankFeed.length === 0 ? (
            <p className="muted">??????</p>
          ) : (
            <ul className="mp2-feed">
              {rankFeed.map((a) => (
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

          <div className="mp2-actions">
            <Link to="/scanner" className="mp2-btn mp2-btn-primary">
              ?????
            </Link>
            <Link to="/alerts" className="mp2-btn">
              ??
            </Link>
          </div>
        </aside>
      </div>

      <section className="mp2-section" aria-label="Market Coverage">
        <header className="mp2-section-head">
          <div>
            <p className="mp2-kicker">Market Coverage</p>
            <h2>??????</h2>
          </div>
          <button type="button" className="mp2-btn mp2-btn-ghost" onClick={() => setCoverageOpen((v) => !v)}>
            {coverageOpen ? "??" : "??"}
          </button>
        </header>
        {coverageOpen ? (
          !funnel.hasData ? (
            <p className="muted">{NO_DATA}</p>
          ) : (
            <div className="mp2-funnel" data-testid="decision-funnel">
              {funnel.stages.map((s) => (
                <div key={s.key} className="mp2-funnel-step">
                  <strong className="mono">{s.display}</strong>
                  <span>{s.label}</span>
                </div>
              ))}
            </div>
          )
        ) : (
          <p className="muted" style={{ fontSize: "0.8125rem" }}>
            ?? ? ?? ? ?? ? ?? ? ??
          </p>
        )}
      </section>
    </div>
  );
}
