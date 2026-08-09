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
import { useLiveMarketFeed } from "../../market/useLiveMarketFeed";
import { useLiveMarketRanking } from "../useLiveMarketRanking";
import { useMarketSummaryHistory } from "../useMarketSummaryHistory";
import {
  filterRankingRows,
  formatDisplayRankScore,
  formatRankMove,
  type RankingTab,
} from "../../market/liveMarketRanking";
import { formatUsd } from "../../market/freshness";
import { SERIES_PRESETS, seriesSparkPoints } from "../../market/marketSeries";
import { rankStepPointsFromEvents } from "../../market/publicRadarApi";
import {
  ActivityBar,
  FundingScale,
  MetricSpark,
  OiDirection,
  RankArrow,
  RankStepSpark,
  RiskBar,
} from "../MetricSpark";
import { TokenIcon } from "../TokenIcon";
import { useMarketSeriesBatch } from "../useMarketSeriesBatch";
import { ContextualUpgrade } from "../ContextualUpgrade";
import { FREE_RADAR_ROW_CAP, isFreePlan } from "../productCapabilities";
import { MarketStateVisual } from "../MarketStateVisual";
import { MarketMapHeat, type MapMetric } from "../MarketMapHeat";
import { OnboardingWizard } from "../../retention/OnboardingWizard";
import { SinceLastVisitPanel } from "../../retention/SinceLastVisitPanel";

function agoLabel(ts?: number | null) {
  if (!ts) return "—";
  const sec = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.round(sec / 60)}m`;
  return `${Math.round(sec / 3600)}h`;
}

function fmtPct(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

const TABS: { id: RankingTab; label: string }[] = [
  { id: "ALL", label: "總榜" },
  { id: "LONG", label: "多方" },
  { id: "SHORT", label: "空方" },
  { id: "MOVE", label: "異動" },
  { id: "OI", label: "OI" },
  { id: "ACTIVITY", label: "Activity" },
  { id: "RISK", label: "風險" },
];

const PULSE = ["BTCUSDT", "ETHUSDT", "SOLUSDT"] as const;

function SkeletonBlock({ h = 18 }: { h?: number }) {
  return <div className="mp2-skeleton" style={{ height: h }} aria-hidden />;
}

/** Product V2 Market Home — visual analytics terminal (V18.2.19). */
export function OverviewPageV2() {
  const ranking = useLiveMarketRanking();
  const feed = useLiveMarketFeed();
  const history = useMarketSummaryHistory(24);
  const { status, loading, error, qualified_count, radar, rows, closest_watch } = ranking;
  const previewPlan = usePreviewReviewPlan("FREE");
  const { dto } = usePublicEntitlements(previewPlan);
  const plan = dto?.plan ?? previewPlan;
  const free = isFreePlan(plan);
  const [tab, setTab] = useState<RankingTab>("ALL");
  const [coverageOpen, setCoverageOpen] = useState(false);
  const [reasonSym, setReasonSym] = useState<string | null>(null);
  const [mapMetric, setMapMetric] = useState<MapMetric>("change_24h");

  const pulseSeries = useMarketSeriesBatch([...PULSE], "pulse_24h", 90_000);

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

  const allFiltered = useMemo(
    () => filterRankingRows(radar.length ? radar : rows, tab),
    [radar, rows, tab],
  );
  const displayRows = useMemo(
    () => (free ? allFiltered.slice(0, FREE_RADAR_ROW_CAP) : allFiltered.slice(0, 24)),
    [allFiltered, free],
  );
  const radarSparkSyms = useMemo(() => displayRows.map((r) => r.symbol), [displayRows]);
  const radarSeries = useMarketSeriesBatch(radarSparkSyms, "radar_4h", 90_000);

  const mapRows = useMemo(() => {
    const pool = [...(radar.length ? radar : rows)];
    return [...pool]
      .sort((a, b) => Math.abs(b.change_24h ?? 0) - Math.abs(a.change_24h ?? 0))
      .slice(0, 18);
  }, [radar, rows]);
  const mapSparkSyms = useMemo(() => mapRows.map((r) => r.symbol), [mapRows]);
  const mapSeries = useMarketSeriesBatch(mapSparkSyms, "radar_4h", 120_000);
  const seriesLookup = useMemo(() => {
    const out: Record<string, { points?: { timestamp: number; value: number }[] }> = {};
    for (const sym of mapSparkSyms) {
      out[sym] = { points: seriesSparkPoints(mapSeries.seriesBySymbol[sym]) };
    }
    return out;
  }, [mapSparkSyms, mapSeries.seriesBySymbol]);

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
    market_discovery: "全市場",
    data_valid: "資料有效",
    runtime_observable: "即時監控",
    safety_review: "安全審查",
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

  const EVENT_ICON: Record<string, string> = {
    NEW: "●",
    UP: "↑",
    DOWN: "↓",
    OUT: "×",
    UNCHANGED: "·",
  };
  const eventFeed = useMemo(() => {
    return ranking.events
      .slice(0, 12)
      .map((e) => ({
        id: e.id,
        symbol: e.symbol,
        icon: EVENT_ICON[e.rank_event] || "·",
        event: e.rank_event,
        rank: e.rank,
        metric: e.market_change || (e.primary_reason || "").slice(0, 24) || "—",
        when: agoLabel(e.timestamp),
        ts: e.timestamp,
        href: `/market/${e.symbol}`,
      }))
      .sort((a, b) => b.ts - a.ts)
      .slice(0, 10);
  }, [ranking.events]);

  const breadth = status?.breadth;
  const rising = breadth?.rising ?? 0;
  const falling = breadth?.falling ?? 0;
  const neutral = breadth?.neutral ?? 0;
  const breadthTotal = Math.max(1, rising + falling + neutral);
  const reasonRow = displayRows.find((r) => r.symbol === reasonSym) ?? null;

  return (
    <div
      className="mp2-overview"
      data-testid="product-v2-overview"
      data-nexus-product-generation="2"
      data-above-fold-card-count="0"
      data-true-market-series="1"
      data-browser-tick-spark="0"
      data-fabricated-visual-count={history.fabricated_visual_count}
      data-market-state-visual="1"
      data-eligible-zero-false-opportunity-count={falseOppCount}
      data-non-crypto-in-crypto-opportunity-count={0}
      data-fixed-symbol-dependency-count={ranking.fixed_symbol_dependency_count}
      data-ranking-universe={ranking.universe_size}
      data-ranking-active={ranking.active_count}
      data-ranking-qualified={qualifiedDisplay}
      data-radar-eligible={ranking.radar_eligible_count}
      data-scanner-visible={ranking.scanner_visible_count}
      data-trade-eligible={ranking.trade_eligible_count}
      data-radar-contract={ranking.radar_eligibility_contract}
      data-rank-authority={ranking.rank_authority}
      data-evaluated-count={ranking.evaluated_count}
      data-monitored-count={ranking.monitored_count}
      data-excluded-count={ranking.excluded_count}
    >
      <OnboardingWizard />
      <SinceLastVisitPanel />
      <header className="mp2-home-head">
        <div>
          <h1 className="mp2-page-title">{"市場"}</h1>
          <p className="mp2-page-sub">{"即時脈動 · Live Radar · 市場現況"}</p>
        </div>
        <div className="muted" style={{ fontSize: "0.8125rem", textAlign: "right" }}>
          <div data-testid="overview-freshness">{freshDisp.label}</div>
          <div>{trust}</div>
        </div>
      </header>

      {error ? <div className="mp2-banner">{error}</div> : null}

      <section className="mp2-home-pulse" aria-label="MARKET PULSE" data-testid="market-home-pulse">
        <p className="mp2-kicker">MARKET PULSE · 24h / 15m</p>
        <div className="mp2-pulse-grid">
          {PULSE.map((sym) => {
            const row = feed.bySymbol[sym];
            const px = row?.lastPrice ?? row?.markPrice;
            const ch = row?.change24hPct;
            const series = pulseSeries.seriesBySymbol[sym];
            const sparkPts = seriesSparkPoints(series);
            const tone = ch == null ? "" : ch >= 0 ? " pos" : " neg";
            return (
              <Link key={sym} to={`/market/${sym}`} className={`mp2-pulse-card${tone}`}>
                <div className="mp2-pulse-card-top">
                  <span className="mp2-sym-with-icon">
                    <TokenIcon symbol={sym} size={20} />
                    <span className="sym">{sym.replace("USDT", "")}</span>
                  </span>
                  {sparkPts.length >= 2 ? (
                    <MetricSpark
                      points={sparkPts}
                      expectedIntervalMs={SERIES_PRESETS.pulse_24h.expectedIntervalMs}
                      positive={(ch ?? 0) >= 0}
                      width={72}
                      height={24}
                    />
                  ) : (
                    <span className="mp2-nodata" title="NO DATA">
                      NO DATA
                    </span>
                  )}
                </div>
                <div className="mp2-pulse-card-px mono">{px == null ? "—" : formatUsd(px)}</div>
                <div className={`mono pulse-ch${tone}`}>{fmtPct(ch)}</div>
              </Link>
            );
          })}
          <div className="mp2-pulse-card mp2-pulse-meta">
            <span className="sym">{"廣度"}</span>
            <div className="mp2-breadth-bars" aria-hidden>
              <span className="up" style={{ width: `${(rising / breadthTotal) * 100}%` }} />
              <span className="flat" style={{ width: `${(neutral / breadthTotal) * 100}%` }} />
              <span className="down" style={{ width: `${(falling / breadthTotal) * 100}%` }} />
            </div>
            <div className="muted" style={{ fontSize: "0.75rem" }}>
              {"升"} {rising}{"／降"} {falling}{"／中性"} {neutral}
            </div>
          </div>
          <div className="mp2-pulse-card mp2-pulse-meta">
            <span className="sym">Regime</span>
            <div className={`mp2-regime-badge${regime.includes("多") ? " pos" : regime.includes("空") ? " neg" : ""}`}>
              {loading && !status ? <SkeletonBlock h={22} /> : regime}
            </div>
            <div className="muted" style={{ fontSize: "0.75rem" }}>
              {"資料"} {freshDisp.label} {"·"} {trust}
            </div>
          </div>
        </div>
      </section>

      <div className="mp2-home-split" data-testid="market-home-layout">
        <section className="mp2-live-radar" aria-label="NEXUS LIVE RADAR" data-testid="live-radar">
          <header className="mp2-section-head">
            <div>
              <p className="mp2-kicker">NEXUS LIVE RADAR</p>
              <h2>
                {"活躍異動"} {"·"} {ranking.radar_eligible_count}
                <span className="muted" style={{ fontWeight: 500, fontSize: "0.8125rem", marginLeft: 8 }}>
                  {"評估"} {ranking.evaluated_count ?? ranking.scanner_visible_count}
                  {" / 監控"} {ranking.monitored_count ?? ranking.universe_size}
                  {" · 更新"} {agoLabel(ranking.updated_at)}
                </span>
              </h2>
            </div>
            <Link to="/opportunities" className="mp2-btn mp2-btn-ghost">
              {"探索"} {"→"}
            </Link>
          </header>

          <div className="mp2-chip-row" role="tablist" aria-label={"排行分頁"}>
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

          {loading && !displayRows.length ? (
            <div className="mp2-skeleton-stack" aria-busy="true" aria-label={"載入中"}>
              <SkeletonBlock h={36} />
              <SkeletonBlock h={36} />
              <SkeletonBlock h={36} />
            </div>
          ) : null}

          {!loading && !displayRows.length ? (
            <div className="mp2-empty" data-testid="radar-empty">
              <p>{"目前沒有市場滿足 Radar 條件。"}</p>
              <p className="muted" style={{ fontSize: "0.8125rem" }}>
                No markets currently satisfy Radar criteria.
              </p>
              {closest_watch.length ? (
                <div className="mp2-closest-watch" data-testid="approaching-radar">
                  <p className="mp2-kicker">APPROACHING RADAR</p>
                  <ul>
                    {closest_watch.map((r) => (
                      <li key={r.candidate_id}>
                        <span className="mp2-sym-with-icon">
                          <TokenIcon symbol={r.symbol} size={18} />
                          <Link to={`/market/${r.symbol}`} className="mono">
                            {r.symbol.replace("USDT", "")}
                          </Link>
                        </span>
                        <span className="muted">{STAGE_LABEL_ZH[r.stage] || r.stage}</span>
                        <span className="mono muted">{formatDisplayRankScore(r.rank_score)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

            </div>
          ) : (
            <div className="mp2-radar-list denser" data-testid="live-radar-table">
              <div className="mp2-radar-cols" aria-hidden>
                <span>#</span>
                <span>Symbol</span>
                <span>Price</span>
                <span>24h</span>
                <span>Act</span>
                <span>OI</span>
                <span>Fund</span>
                <span>Risk</span>
                <span>RankΔ</span>
              </div>
              {displayRows.map((r) => {
                const sparkPts = seriesSparkPoints(radarSeries.seriesBySymbol[r.symbol]);
                const stepPts = rankStepPointsFromEvents(ranking.events, r.symbol);
                return (
                  <button
                    key={r.candidate_id}
                    type="button"
                    className={`mp2-radar-row denser${reasonSym === r.symbol ? " is-open" : ""}`}
                    onClick={() => setReasonSym((s) => (s === r.symbol ? null : r.symbol))}
                  >
                    <span className="rank mono">#{r.rank}</span>
                    <span className="sym-block">
                      <span className="mp2-sym-with-icon">
                        <TokenIcon symbol={r.symbol} size={16} />
                        <Link
                          to={`/market/${r.symbol}`}
                          className="mono sym"
                          onClick={(e) => e.stopPropagation()}
                        >
                          {r.symbol.replace("USDT", "")}
                        </Link>
                      </span>
                    </span>
                    <span className="mono px">{r.price == null ? "—" : formatUsd(r.price)}</span>
                    <span className="spark-cell">
                      {sparkPts.length >= 2 ? (
                        <MetricSpark
                          points={sparkPts}
                          expectedIntervalMs={SERIES_PRESETS.radar_4h.expectedIntervalMs}
                          positive={(r.change_24h ?? 0) >= 0}
                          width={56}
                          height={20}
                        />
                      ) : (
                        <span className="mp2-nodata">—</span>
                      )}
                      <span className={`mono ch ${(r.change_24h ?? 0) >= 0 ? "pos" : "neg"}`}>
                        {fmtPct(r.change_24h)}
                      </span>
                    </span>
                    <span className="act">
                      <ActivityBar value={r.activity_metric} />
                    </span>
                    <span className="oi">
                      <OiDirection change={r.oi_change} />
                    </span>
                    <span className="fund">
                      <FundingScale rate={r.funding_rate} />
                    </span>
                    <span className="risk">
                      <RiskBar value={r.risk_score} />
                    </span>
                    <span className="rank-move">
                      {stepPts.length >= 2 ? (
                        <RankStepSpark points={stepPts} width={40} height={16} />
                      ) : (
                        <RankArrow event={r.rank_event} delta={r.rank_delta} />
                      )}
                    </span>
                  </button>
                );
              })}
            </div>
          )}

          {free && allFiltered.length > FREE_RADAR_ROW_CAP ? (
            <ContextualUpgrade
              title={"完整 Live Radar 深度"}
              detail={`目前顯示前 ${FREE_RADAR_ROW_CAP} 名；PRO 解鎖即時完整榜單與排名歷史。`}
              required="PRO"
            />
          ) : null}

          {reasonRow ? (
            <aside className="mp2-radar-drawer" data-testid="radar-reason-drawer">
              <p className="mp2-kicker">{"為什麼在榜"}</p>
              <p>{reasonRow.primary_reason}</p>
              {reasonRow.secondary_reason ? (
                <p className="muted">{reasonRow.secondary_reason}</p>
              ) : null}
              <div className="mp2-actions">
                <Link to={`/market/${reasonRow.symbol}`} className="mp2-btn mp2-btn-primary">
                  {"開啟終端"}
                </Link>
                <span className="mono muted">{formatRankMove(reasonRow)}</span>
              </div>
            </aside>
          ) : null}

          {displayRows.length > 0 && closest_watch.length > 0 ? (
            <div className="mp2-closest-watch muted-section" data-testid="approaching-radar-secondary">
              <p className="mp2-kicker">APPROACHING RADAR</p>
              <div className="mp2-chip-row">
                {closest_watch.map((r) => (
                  <Link key={r.candidate_id} to={`/market/${r.symbol}`} className="mp2-btn mp2-btn-ghost">
                    {r.symbol.replace("USDT", "")}
                  </Link>
                ))}
              </div>
            </div>
          ) : null}

          {mapRows.length > 0 ? (
            <div className="mp2-movers-matrix muted-section" data-testid="market-movers">
              <p className="mp2-kicker">MARKET MAP</p>
              <MarketMapHeat
                rows={mapRows}
                metric={mapMetric}
                onMetricChange={setMapMetric}
                seriesBySymbol={seriesLookup}
              />
            </div>
          ) : null}
        </section>

        <aside className="mp2-market-now" aria-label="MARKET STATE" data-testid="market-now">
          <p className="mp2-kicker">MARKET STATE</p>
          <MarketStateVisual
            rising={rising}
            falling={falling}
            neutral={neutral}
            regime={regime}
            highRisk={status?.highRiskCandidates}
            universe={status?.symbolCount ?? ranking.universe_size}
            scannerCount={ranking.scanner_visible_count}
            radarCount={ranking.radar_eligible_count}
            tradeCount={ranking.trade_eligible_count}
            qualifiedCount={qualifiedDisplay ?? 0}
            history={history.points}
            loading={history.loading}
          />

          <div className="mp2-now-counts muted">
            <span data-testid="evaluated-count">
              {"評估"} {ranking.evaluated_count ?? ranking.scanner_visible_count}
            </span>
            <span data-testid="monitored-count">
              {"監控"} {ranking.monitored_count ?? ranking.universe_size}
            </span>
            <span data-testid="qualified-count">{"合格"} {qualifiedDisplay ?? 0}</span>
          </div>

          {qualifiedDisplay === 0 ? (
            <div className="mp2-empty" data-testid="no-eligible-opportunities" style={{ marginTop: 12 }}>
              {"合格機會為 0；Live Radar 僅供觀察，非交易推薦。"}
            </div>
          ) : null}

          <p className="mp2-kicker" style={{ marginTop: 16 }}>
            {"事件"}
          </p>
          {eventFeed.length === 0 ? (
            <p className="muted">{"尚無排名事件"}</p>
          ) : (
            <ul className="mp2-feed mp2-event-compact" data-testid="rank-event-feed">
              {eventFeed.map((a) => (
                <li key={a.id}>
                  <span className="when mono">{a.when}</span>
                  <Link to={a.href} className="mp2-sym-with-icon">
                    <TokenIcon symbol={a.symbol} size={14} />
                    <span className="mono">{a.symbol.replace("USDT", "")}</span>
                  </Link>
                  <span className={`ev-icon ${a.event === "UP" || a.event === "NEW" ? "pos" : a.event === "DOWN" || a.event === "OUT" ? "neg" : ""}`}>
                    {a.icon}
                  </span>
                  <span className="mono muted">{a.rank != null ? `#${a.rank}` : "OUT"}</span>
                  <span className="metric muted">{a.metric}</span>
                </li>
              ))}
            </ul>
          )}

          <div className="mp2-actions">
            <Link to="/scanner" className="mp2-btn mp2-btn-primary">
              {"開啟掃描器"}
            </Link>
            <Link to="/alerts" className="mp2-btn">
              {"警報"}
            </Link>
          </div>
        </aside>
      </div>

      <section className="mp2-section" aria-label="Market Coverage">
        <header className="mp2-section-head">
          <div>
            <p className="mp2-kicker">Market Coverage</p>
            <h2>{"覆蓋漏斗"}</h2>
          </div>
          <button type="button" className="mp2-btn mp2-btn-ghost" onClick={() => setCoverageOpen((v) => !v)}>
            {coverageOpen ? "收合" : "展開"}
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
            {"全市場 → 資料有效 → 即時監控 → 安全審查 → Eligible"}
          </p>
        )}
      </section>
    </div>
  );
}
