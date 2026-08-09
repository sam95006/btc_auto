import { Link, useNavigate, useParams } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import {
  STAGE_LABEL_ZH,
  fetchScannerSymbol,
  plainReason,
  sideLabelZh,
  type MarketCandidate,
} from "../../market/scannerApi";
import { formatUsd } from "../../market/freshness";
import { WatchStarButton } from "../../components/WatchStarButton";
import { NexusLiveCandleChart } from "../../components/NexusLiveCandleChart";
import { useLiveMarketRanking } from "../useLiveMarketRanking";
import {
  formatRankMove,
  rankHistoryForSymbol,
  type LiveRankingRow,
} from "../../market/liveMarketRanking";
import { memberDataTrustLabel } from "../../market/marketMetricFunnel";
import { loadWatchlist } from "../../market/watchlistStore";
import { usePublicEntitlements } from "../../member/public_entitlements_v18_2";
import { usePreviewReviewPlan } from "../../member/usePreviewReviewPlan";
import { ContextualUpgrade } from "../ContextualUpgrade";
import { isFreePlan, requiresResearch } from "../productCapabilities";
import { TokenIcon } from "../TokenIcon";
import { ActivityBar, FundingScale, MetricSpark, OiDirection, RankStepSpark, RiskBar } from "../MetricSpark";
import { rankStepPointsFromEvents } from "../../market/publicRadarApi";
import { SERIES_PRESETS, seriesSparkPoints } from "../../market/marketSeries";
import { useMarketSeriesBatch } from "../useMarketSeriesBatch";

type LowerTab = "overview" | "evidence" | "derivatives" | "liquidity" | "history" | "quality";

function fmtPct(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function agoLabel(ts?: number | null) {
  if (!ts) return "—";
  const sec = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.round(sec / 60)}m`;
  return `${Math.round(sec / 3600)}h`;
}

function decisionState(c: MarketCandidate | null): string {
  if (!c) return "WAIT";
  if (c.stage === "CONFIRMED") return "READY";
  if (c.stage === "OVEREXTENDED" || c.stage === "EXPIRED") return "BLOCK";
  if (c.stage === "AWAITING_CONFIRMATION") return "WAIT";
  if (c.stage === "WATCHING" || c.stage === "BUILDING") return "WATCH";
  if (c.stage === "COOLING") return "WAIT";
  if (c.collecting || c.stage === "INSUFFICIENT_DATA") return "WAIT";
  return "WATCH";
}

/**
 * Product V2 Market Terminal — exchange-density workspace (V18.2.19 visuals).
 */
export function MarketTerminalPageV2() {
  const { symbol = "" } = useParams();
  const navigate = useNavigate();
  const sym = symbol.toUpperCase();
  const ranking = useLiveMarketRanking();
  const previewPlan = usePreviewReviewPlan("FREE");
  const { dto } = usePublicEntitlements(previewPlan);
  const plan = dto?.plan ?? previewPlan;
  const free = isFreePlan(plan);
  const researchLocked = requiresResearch(plan);
  const [error, setError] = useState<string | null>(null);
  const [candidate, setCandidate] = useState<MarketCandidate | null>(null);
  const [snap, setSnap] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<LowerTab>("overview");
  const [listQ, setListQ] = useState("");
  const [listMode, setListMode] = useState<"radar" | "watch">("radar");

  const termSeries = useMarketSeriesBatch([sym], "pulse_24h", 90_000);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const body = await fetchScannerSymbol(sym);
        if (!alive) return;
        if (!body.ok) {
          setError(body.error || "not_found");
          setCandidate(null);
          setSnap(null);
        } else {
          setError(null);
          setCandidate(body.candidate || null);
          setSnap(body.snapshot || null);
        }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : "load_failed");
      } finally {
        if (alive) setLoading(false);
      }
    };
    void load();
    const id = window.setInterval(() => void load(), 12_000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [sym]);

  const rankRow: LiveRankingRow | undefined = ranking.rows.find((r) => r.symbol === sym);
  const history = useMemo(
    () => rankHistoryForSymbol(sym, ranking.events),
    [sym, ranking.events, ranking.updated_at],
  );
  const stepPts = useMemo(
    () => rankStepPointsFromEvents(ranking.events, sym),
    [ranking.events, sym],
  );
  const sparkPts = seriesSparkPoints(termSeries.seriesBySymbol[sym]);

  const price =
    (snap?.lastPrice as number | undefined) ??
    candidate?.currentPrice ??
    (snap?.markPrice as number | undefined);
  const high24 = snap?.highPrice24h as number | undefined;
  const low24 = snap?.lowPrice24h as number | undefined;
  const vol24 =
    (snap?.volume24h as number | undefined) ??
    (candidate as MarketCandidate & { volume24h?: number })?.volume24h;
  const funding = candidate?.fundingRate ?? (snap?.fundingRate as number | undefined);
  const oi =
    candidate?.openInterestValue ??
    (snap?.openInterestValue as number | undefined) ??
    (snap?.openInterest as number | undefined);
  const spread = candidate?.spreadBps;
  const ch24 = candidate?.change24hPct ?? (snap?.change24hPct as number | undefined);

  const trust = memberDataTrustLabel({
    scannerFreshness: candidate?.freshness ?? ranking.status?.freshness,
    confirmedCandidates: candidate?.stage === "CONFIRMED" ? 1 : 0,
  });

  const state = decisionState(candidate);
  const supports = (candidate?.reasons || []).slice(0, 4).map((r) => plainReason(r, false));
  const against = (candidate?.conflicts || []).slice(0, 4).map((r) => plainReason(r, false));

  const watchSymbols = useMemo(
    () => new Set(loadWatchlist().items.filter((i) => i.assetClass === "CRYPTO").map((i) => i.symbol)),
    [sym, ranking.updated_at],
  );

  const marketList = useMemo(() => {
    let rows = ranking.rows;
    if (listMode === "watch") {
      rows = rows.filter((r) => watchSymbols.has(r.symbol));
      if (!rows.length) {
        return [...watchSymbols].map((s) => ({
          symbol: s,
          rank: null as number | null,
          price: null as number | null,
          change: null as number | null,
          activity: null as number | null,
        }));
      }
    }
    const qq = listQ.trim().toUpperCase();
    if (qq) rows = rows.filter((r) => r.symbol.includes(qq));
    return rows.slice(0, 40).map((r) => ({
      symbol: r.symbol,
      rank: r.rank as number | null,
      price: r.price ?? null,
      change: r.change_24h ?? null,
      activity: r.activity_metric ?? null,
    }));
  }, [ranking.rows, listQ, listMode, watchSymbols]);

  const tabs: { id: LowerTab; label: string }[] = [
    { id: "overview", label: "總覽" },
    { id: "evidence", label: "證據" },
    { id: "derivatives", label: "衍生品" },
    { id: "liquidity", label: "流動性" },
    { id: "history", label: "歷史" },
    { id: "quality", label: "資料品質" },
  ];

  return (
    <div
      className="mp2-terminal denser"
      data-testid="product-v2-market-terminal"
      data-nexus-product-generation="2"
      data-market-terminal-v2="1"
      data-fabricated-visual-count="0"
    >
      <header className="mp2-term-header" data-testid="terminal-symbol-header">
        <div className="mp2-term-title">
          <TokenIcon symbol={sym} size={28} />
          <h1 className="mono">{sym.replace("USDT", "")}</h1>
          <span className="muted">USDT Perp</span>
          {rankRow ? (
            <span className="mp2-term-rank mono" data-testid="terminal-rank">
              {formatRankMove(rankRow)}
            </span>
          ) : null}
          {sparkPts.length >= 2 ? (
            <MetricSpark
              points={sparkPts}
              expectedIntervalMs={SERIES_PRESETS.pulse_24h.expectedIntervalMs}
              positive={(ch24 ?? 0) >= 0}
              width={80}
              height={26}
            />
          ) : (
            <span className="mp2-nodata">NO DATA</span>
          )}
        </div>
        <div className="mp2-term-metrics denser">
          <div>
            <span className="lbl">Price</span>
            <span className="val mono">{formatUsd(price)}</span>
          </div>
          <div>
            <span className="lbl">24h</span>
            <span className={`val mono ${(ch24 ?? 0) >= 0 ? "pos" : "neg"}`}>{fmtPct(ch24)}</span>
          </div>
          <div>
            <span className="lbl">High</span>
            <span className="val mono">{high24 == null ? "—" : formatUsd(high24)}</span>
          </div>
          <div>
            <span className="lbl">Low</span>
            <span className="val mono">{low24 == null ? "—" : formatUsd(low24)}</span>
          </div>
          <div>
            <span className="lbl">Volume</span>
            <span className="val mono">{vol24 == null ? "—" : Number(vol24).toLocaleString()}</span>
          </div>
          <div>
            <span className="lbl">Funding</span>
            <FundingScale rate={funding} />
          </div>
          <div>
            <span className="lbl">OI</span>
            <span className="val mono">{oi == null ? "—" : Number(oi).toLocaleString()}</span>
            <OiDirection change={candidate?.oiChange5mPct} />
          </div>
          <div>
            <span className="lbl">Risk</span>
            <RiskBar value={candidate?.riskScore ?? rankRow?.risk_score} />
          </div>
          <div>
            <span className="lbl">資料</span>
            <span className="val">{trust.label_zh}</span>
          </div>
        </div>
        <div className="mp2-term-actions">
          <WatchStarButton symbol={sym} />
          <Link to="/alerts" className="mp2-btn mp2-btn-primary">
            設警報
          </Link>
        </div>
      </header>

      {error ? <div className="mp2-banner">{error}</div> : null}
      {loading && !candidate && !snap ? (
        <div className="mp2-skeleton-stack" aria-busy="true" aria-label="載入中">
          <div className="mp2-skeleton" style={{ height: 28 }} />
          <div className="mp2-skeleton" style={{ height: 220 }} />
        </div>
      ) : null}

      <div className="mp2-term-grid">
        <aside className="mp2-term-list denser" aria-label="市場清單">
          <div className="mp2-term-list-tools">
            <input
              value={listQ}
              onChange={(e) => setListQ(e.target.value)}
              placeholder="搜尋"
              aria-label="清單搜尋"
            />
            <div className="mp2-chip-row">
              <button
                type="button"
                className={listMode === "radar" ? "active" : undefined}
                onClick={() => setListMode("radar")}
              >
                Radar
              </button>
              <button
                type="button"
                className={listMode === "watch" ? "active" : undefined}
                onClick={() => setListMode("watch")}
              >
                自選
              </button>
            </div>
          </div>
          <ul>
            {marketList.map((r) => (
              <li key={r.symbol}>
                <button
                  type="button"
                  className={r.symbol === sym ? "is-active" : undefined}
                  onClick={() => navigate(`/market/${r.symbol}`)}
                >
                  <span className="mono">
                    {r.rank != null ? `#${r.rank} ` : ""}
                    {r.symbol.replace("USDT", "")}
                  </span>
                  <ActivityBar value={r.activity} max={40} />
                  <span className={`mono ${(r.change ?? 0) >= 0 ? "pos" : "neg"}`}>
                    {r.change == null ? "—" : fmtPct(r.change)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <section className="mp2-term-center" aria-label="圖表">
          <div className="mp2-term-chart" data-testid="terminal-chart">
            <NexusLiveCandleChart symbol={sym} advanced />
          </div>
          <div className="mp2-term-tabs" role="tablist" aria-label="終端分頁">
            {tabs.map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={tab === t.id}
                className={tab === t.id ? "active" : undefined}
                onClick={() => setTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>
          <div className="mp2-term-tab-body" data-testid={`terminal-tab-${tab}`}>
            {tab === "overview" ? (
              <div className="mp2-term-overview-grid">
                <div>
                  <p className="mp2-kicker">目前</p>
                  <p>
                    {candidate
                      ? `${sideLabelZh(candidate.side)} · ${STAGE_LABEL_ZH[candidate.stage] || candidate.stage}`
                      : "尚無候選狀態"}
                  </p>
                </div>
                <div>
                  <p className="mp2-kicker">為什麼</p>
                  <p>{plainReason(candidate?.reasons?.[0] || "結構仍在觀察", false)}</p>
                </div>
                <div>
                  <p className="mp2-kicker">風險</p>
                  <RiskBar value={candidate?.riskScore} />
                </div>
                <div>
                  <p className="mp2-kicker">Rank 軌跡</p>
                  {stepPts.length >= 2 ? (
                    <RankStepSpark points={stepPts} width={120} height={28} />
                  ) : (
                    <span className="mp2-nodata">NO DATA</span>
                  )}
                </div>
              </div>
            ) : null}
            {tab === "evidence" ? (
              <div>
                <p className="mp2-kicker">支持</p>
                <ul>
                  {supports.length ? supports.map((s) => <li key={s}>{s}</li>) : <li className="muted">尚無</li>}
                </ul>
                <p className="mp2-kicker">反對</p>
                <ul>
                  {against.length ? against.map((s) => <li key={s}>{s}</li>) : <li className="muted">尚無</li>}
                </ul>
                <p className="mp2-kicker">失效</p>
                <p>{candidate?.invalidationContext || "尚無明確失效條件"}</p>
              </div>
            ) : null}
            {tab === "derivatives" ? (
              <dl className="mp2-term-dl">
                <div>
                  <dt>Funding</dt>
                  <dd>
                    <FundingScale rate={funding} />
                  </dd>
                </div>
                <div>
                  <dt>OI 5m</dt>
                  <dd className="mono">
                    <OiDirection change={candidate?.oiChange5mPct} /> {fmtPct(candidate?.oiChange5mPct)}
                  </dd>
                </div>
                <div>
                  <dt>未平倉</dt>
                  <dd className="mono">{oi == null ? "—" : Number(oi).toLocaleString()}</dd>
                </div>
              </dl>
            ) : null}
            {tab === "liquidity" ? (
              <dl className="mp2-term-dl">
                <div>
                  <dt>價差</dt>
                  <dd className="mono">{spread == null ? "—" : `${spread.toFixed(1)} bps`}</dd>
                </div>
                <div>
                  <dt>成交節奏</dt>
                  <dd className="mono">{candidate?.turnoverPace == null ? "—" : candidate.turnoverPace}</dd>
                </div>
                <div>
                  <dt>Volume 24h</dt>
                  <dd className="mono">{vol24 == null ? "—" : Number(vol24).toLocaleString()}</dd>
                </div>
              </dl>
            ) : null}
            {tab === "history" ? (
              <div data-testid="terminal-rank-history">
                <p className="mp2-kicker">Ranking History · SERVER</p>
                {free ? (
                  <ContextualUpgrade
                    title="排名歷史"
                    detail="PRO 解鎖完整 rank history 與進出 Radar 軌跡。"
                    required="PRO"
                  />
                ) : history.length === 0 ? (
                  <p className="muted">NO DATA · 尚無已記錄的排名事件（不回溯虛構）。</p>
                ) : (
                  <ol className="mp2-rank-history">
                    {history.slice(0, 24).map((h) => (
                      <li key={h.id}>
                        <span className="mono">{h.rank_event}</span>
                        <span>
                          {h.previous_rank != null ? `#${h.previous_rank}` : "—"} →{" "}
                          {h.rank != null ? `#${h.rank}` : "OUT"}
                        </span>
                        <span className="muted">{agoLabel(h.timestamp)}</span>
                        <span>{h.market_change || h.primary_reason}</span>
                      </li>
                    ))}
                  </ol>
                )}
                {!free && stepPts.length >= 2 ? (
                  <div style={{ marginTop: 10 }}>
                    <RankStepSpark points={stepPts} width={220} height={36} />
                  </div>
                ) : null}
              </div>
            ) : null}
            {tab === "quality" ? (
              researchLocked ? (
                <ContextualUpgrade
                  title="資料品質工具"
                  detail="RESEARCH 方案解鎖深度 freshness / source 診斷。"
                  required="RESEARCH"
                />
              ) : (
                <dl className="mp2-term-dl">
                  <div>
                    <dt>資料信任</dt>
                    <dd>{trust.label_zh}</dd>
                  </div>
                  <div>
                    <dt>Freshness</dt>
                    <dd className="mono">{candidate?.freshness || ranking.status?.freshness || "—"}</dd>
                  </div>
                  <div>
                    <dt>來源</dt>
                    <dd className="mono">{candidate?.source || "BYBIT_PUBLIC"}</dd>
                  </div>
                </dl>
              )
            ) : null}
          </div>
        </section>

        <aside className="mp2-term-decision denser" aria-label="NEXUS 決策面板" data-testid="nexus-decision-panel">
          <p className="mp2-kicker">NEXUS INTELLIGENCE</p>
          <div className="mp2-decision-block">
            <h3>STATE</h3>
            <p className="mp2-term-state" data-testid="terminal-decision-state">
              {state}
            </p>
            <p className="muted" style={{ fontSize: "0.8125rem" }}>
              {candidate
                ? `${STAGE_LABEL_ZH[candidate.stage] || candidate.stage} · ${sideLabelZh(candidate.side)}`
                : "尚無決策狀態"}
            </p>
          </div>
          {rankRow ? (
            <div className="mp2-decision-block">
              <h3>RANK</h3>
              <p className="mono">{formatRankMove(rankRow)}</p>
              {stepPts.length >= 2 ? <RankStepSpark points={stepPts} width={100} height={22} /> : null}
            </div>
          ) : null}
          <div className="mp2-decision-block">
            <h3>TRUST</h3>
            <p>{trust.label_zh}</p>
          </div>
          <div className="mp2-decision-block">
            <h3>RISK</h3>
            <RiskBar value={candidate?.riskScore ?? rankRow?.risk_score} />
          </div>
          <div className="mp2-decision-block">
            <h3>WHY NOW</h3>
            <ul>
              {supports.slice(0, 3).map((s) => (
                <li key={s}>{s}</li>
              ))}
              {!supports.length ? <li className="muted">結構仍在觀察</li> : null}
            </ul>
          </div>
          <div className="mp2-decision-block against">
            <h3>AGAINST</h3>
            {against.length ? (
              <ul>
                {against.slice(0, 3).map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            ) : (
              <p className="muted">尚無</p>
            )}
          </div>
          <div className="mp2-decision-block">
            <h3>INVALIDATION</h3>
            <p>{candidate?.invalidationContext || "尚無明確失效條件"}</p>
          </div>
          <div className="mp2-actions">
            <Link to="/alerts" className="mp2-btn mp2-btn-primary">
              設警報
            </Link>
            <WatchStarButton symbol={sym} />
            <Link to="/intelligence" className="mp2-btn">
              深入研究
            </Link>
          </div>
          <p className="muted" style={{ fontSize: "0.6875rem", marginTop: 12 }}>
            Research only · 無會員下單
          </p>
        </aside>
      </div>
    </div>
  );
}
