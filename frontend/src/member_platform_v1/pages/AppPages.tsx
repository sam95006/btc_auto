import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { AdviceChip, BiasChip, RiskChip, ScorePill } from "../components/Chips";
import { IconAlert, IconBell, IconLock, IconShield, IconTrend } from "../components/Icons";
import { LockedPanel } from "../components/LockedPanel";
import { OppMiniRow, RankTableHeader, RankTableRow } from "../components/MarketRow";
import { CandleChart, SparkChart } from "../components/SparkChart";
import { useAuth } from "../context/AuthContext";
import { useWatchlist } from "../context/WatchlistContext";
import { canAccess, minTierFor, TIER_LABELS } from "../lib/entitlements";
import { alertApi, marketApi, memberApi } from "../services";
import type { AlertDto, AssetDetailDto, DashboardDto, MarketRankingRowDto, PlanDto } from "../types/dto";

function RequireSession({ children }: { children: ReactNode }) {
  const { session } = useAuth();
  if (!session) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function fmtPrice(n: number) {
  if (n >= 1000) return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (n >= 1) return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return n.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

export function DashboardPage() {
  const { tier } = useAuth();
  const { symbols } = useWatchlist();
  const [data, setData] = useState<DashboardDto | null>(null);

  useEffect(() => {
    void marketApi.getDashboard(tier, symbols).then(setData);
  }, [tier, symbols]);

  if (!data) {
    return (
      <RequireSession>
        <p className="mpv1-muted">載入總覽…</p>
      </RequireSession>
    );
  }

  const best = data.topAssets[0];
  const topLong = data.topAssets.filter((r) => r.bias === "bullish").slice(0, 3);
  const topShort = data.topAssets.filter((r) => r.bias === "bearish").slice(0, 3);
  const topWatch = data.topAssets.filter((r) => r.bias === "neutral" || r.advice === "observing").slice(0, 3);

  return (
    <RequireSession>
      <div className="mpv1-grid mpv1-grid-4" style={{ marginBottom: "0.85rem" }}>
        <article className="mpv1-card mpv1-intel">
          <div className="lbl">市場狀態</div>
          <div className="val bull">{data.overview.biasLabel}</div>
          <div className="hint">{data.overview.biasDetail || data.overview.summary}</div>
        </article>
        <article className="mpv1-card mpv1-intel">
          <div className="lbl">最佳機會</div>
          <div className="val accent">{best ? best.symbol.replace("USDT", "") : "—"}</div>
          <div className="meta">
            {best ? <ScorePill score={best.score} /> : null}
            {best ? <AdviceChip advice={best.advice} label={best.adviceLabel} /> : null}
          </div>
          <div className="hint">{best?.beginnerReason}</div>
        </article>
        <article className="mpv1-card mpv1-intel">
          <div className="lbl">現在怎麼做</div>
          <div className="val accent">{data.overview.adviceLabel}</div>
          <div className="hint">{data.overview.actionDetail}</div>
        </article>
        <article className="mpv1-card mpv1-intel">
          <div className="lbl">市場風險</div>
          <div className="val warn">{data.overview.riskLabel}</div>
          <div className="hint">{data.overview.riskDetail}</div>
        </article>
      </div>

      <div className="mpv1-grid mpv1-grid-pulse" style={{ marginBottom: "0.85rem" }}>
        <article className="mpv1-card">
          <div className="mpv1-card-head">
            <h2 className="mpv1-card-title">Market Pulse</h2>
            <span className="mpv1-muted">總市值 {data.pulse.marketCapLabel}</span>
          </div>
          <div className="mpv1-pulse-chart">
            <SparkChart values={data.pulse.trend} tone="accent" />
          </div>
          <div className="mpv1-ticker-row">
            {data.pulse.tickers.map((t) => (
              <div key={t.symbol} className="mpv1-ticker">
                <div className="sym">{t.symbol}</div>
                <div className="px">${fmtPrice(t.price)}</div>
                <div className={t.change24hPct >= 0 ? "mpv1-chg-up" : "mpv1-chg-down"} style={{ fontSize: "0.78rem" }}>
                  {t.change24hPct >= 0 ? "+" : ""}
                  {t.change24hPct.toFixed(2)}%
                </div>
              </div>
            ))}
          </div>
        </article>
        <article className="mpv1-card">
          <h2 className="mpv1-card-title">市場廣度</h2>
          <p className="mpv1-muted" style={{ marginTop: "0.35rem" }}>
            偏多 vs 偏空 平衡（模擬）
          </p>
          <div className="mpv1-breadth">
            <div className="mpv1-breadth-bar">
              <div className="bull" style={{ width: `${data.pulse.breadthBullPct}%` }} />
              <div className="bear" style={{ width: `${data.pulse.breadthBearPct}%` }} />
            </div>
            <div className="mpv1-breadth-meta">
              <span>偏多 {data.pulse.breadthBullPct}%</span>
              <span>偏空 {data.pulse.breadthBearPct}%</span>
            </div>
          </div>
          <div className="mpv1-plain-grid" style={{ marginTop: "1rem" }}>
            <div className="mpv1-plain-item">
              <h4>多方優勢</h4>
              <p>資金較集中在少數相對強勢幣，廣度偏健康。</p>
            </div>
            <div className="mpv1-plain-item caution">
              <h4>注意</h4>
              <p>中性與高波動標的仍多，不宜全面追價。</p>
            </div>
          </div>
        </article>
      </div>

      <article className="mpv1-card" style={{ marginBottom: "0.85rem" }}>
        <div className="mpv1-card-head">
          <h2 className="mpv1-card-title">Top Opportunities</h2>
          <Link className="mpv1-footer-link" style={{ marginTop: 0 }} to="/app/markets">
            完整排行 →
          </Link>
        </div>
        <div className="mpv1-opp-cols">
          <div className="mpv1-opp-col">
            <div className="mpv1-opp-col-head long">Top Long · 偏多</div>
            {topLong.map((r) => (
              <OppMiniRow key={r.symbol} row={r} />
            ))}
            {!topLong.length ? <p className="mpv1-empty">暫無</p> : null}
          </div>
          <div className="mpv1-opp-col">
            <div className="mpv1-opp-col-head short">Top Short · 偏空</div>
            {topShort.length
              ? topShort.map((r) => <OppMiniRow key={r.symbol} row={r} />)
              : data.topAssets
                  .filter((r) => r.change24hPct < 0)
                  .slice(0, 3)
                  .map((r) => <OppMiniRow key={r.symbol} row={r} />)}
          </div>
          <div className="mpv1-opp-col">
            <div className="mpv1-opp-col-head watch">Watch / Neutral</div>
            {topWatch.map((r) => (
              <OppMiniRow key={r.symbol} row={r} />
            ))}
          </div>
        </div>
      </article>

      <div className="mpv1-grid mpv1-grid-dash" style={{ marginBottom: "0.85rem" }}>
        <article className="mpv1-card">
          <h2 className="mpv1-card-title">Today in Plain Language</h2>
          <div className="mpv1-plain-grid" style={{ marginTop: "0.75rem" }}>
            <div className="mpv1-plain-item">
              <h4>今天市場正在發生什麼</h4>
              <p>{data.plainLanguage.happening}</p>
            </div>
            <div className="mpv1-plain-item">
              <h4>為什麼市場轉強</h4>
              <p>{data.plainLanguage.whyStrong}</p>
            </div>
            <div className="mpv1-plain-item caution">
              <h4>今天先不要做什麼</h4>
              <p>{data.plainLanguage.avoid}</p>
            </div>
            <div className="mpv1-plain-item caution">
              <h4>最需要注意的風險</h4>
              <p>{data.plainLanguage.topRisk}</p>
            </div>
          </div>
        </article>

        <div className="mpv1-grid">
          <article className="mpv1-card">
            <div className="mpv1-card-head">
              <h2 className="mpv1-card-title">My Watchlist</h2>
              <Link className="mpv1-footer-link" style={{ marginTop: 0 }} to="/app/watchlist">
                全部 →
              </Link>
            </div>
            {canAccess(tier, "watchlist") ? (
              data.watchlistPreview.length ? (
                data.watchlistPreview.slice(0, 4).map((r) => <OppMiniRow key={r.symbol} row={r} />)
              ) : (
                <p className="mpv1-empty">尚未加入觀察</p>
              )
            ) : (
              <LockedPanel featureLabel="觀察清單" requiredTier={minTierFor("watchlist")} />
            )}
          </article>
          <article className="mpv1-card">
            <div className="mpv1-card-head">
              <h2 className="mpv1-card-title">Latest Alerts</h2>
              <Link className="mpv1-footer-link" style={{ marginTop: 0 }} to="/app/alerts">
                全部 →
              </Link>
            </div>
            {canAccess(tier, "risk_alerts") ? (
              <ul className="mpv1-feed">
                {data.riskAlerts.slice(0, 3).map((a) => (
                  <li key={a.id}>
                    <span className={`mpv1-alert-ico ${a.severity}`} style={{ width: 28, height: 28 }}>
                      <IconAlert size={14} />
                    </span>
                    <div>
                      <strong>{a.title}</strong>
                      <p>{a.body}</p>
                    </div>
                    <time>{a.timeLabel}</time>
                  </li>
                ))}
              </ul>
            ) : (
              <LockedPanel featureLabel="風險提醒" requiredTier={minTierFor("risk_alerts")} />
            )}
          </article>
          <article className="mpv1-card">
            <h2 className="mpv1-card-title">Recent Signal Changes</h2>
            <ul className="mpv1-feed" style={{ marginTop: "0.55rem" }}>
              {data.signalChanges.map((s) => (
                <li key={s.id}>
                  <span className="mpv1-coin" style={{ width: 28, height: 28 }}>
                    {s.symbol.replace("USDT", "").slice(0, 1)}
                  </span>
                  <div>
                    <strong>{s.symbol.replace("USDT", "")}</strong>
                    <div className="sub">
                      {s.fromLabel} → {s.toLabel}
                    </div>
                  </div>
                  <time>{s.timeLabel}</time>
                </li>
              ))}
            </ul>
          </article>
        </div>
      </div>
    </RequireSession>
  );
}

type MarketFilter = "all" | "bullish" | "bearish" | "watch" | "observing" | "high_risk";
type MarketSort = "score" | "change" | "risk" | "recent";

export function MarketsPage() {
  const { tier } = useAuth();
  const [rows, setRows] = useState<MarketRankingRowDto[]>([]);
  const [filter, setFilter] = useState<MarketFilter>("all");
  const [sort, setSort] = useState<MarketSort>("score");
  const [q, setQ] = useState("");

  useEffect(() => {
    void marketApi.getRanking(tier).then(setRows);
  }, [tier]);

  const filtered = useMemo(() => {
    let list = [...rows];
    if (filter === "bullish") list = list.filter((r) => r.bias === "bullish");
    if (filter === "bearish") list = list.filter((r) => r.bias === "bearish");
    if (filter === "watch") list = list.filter((r) => r.advice === "watch_closely");
    if (filter === "observing") list = list.filter((r) => r.advice === "observing");
    if (filter === "high_risk") list = list.filter((r) => r.risk === "high");
    if (q.trim()) {
      const s = q.trim().toUpperCase();
      list = list.filter((r) => r.symbol.includes(s) || r.name.toUpperCase().includes(s));
    }
    list.sort((a, b) => {
      if (sort === "change") return b.change24hPct - a.change24hPct;
      if (sort === "risk") {
        const rank = { high: 3, medium: 2, low: 1 };
        return rank[b.risk] - rank[a.risk];
      }
      if (sort === "recent") return (b.lastChangeLabel || "").localeCompare(a.lastChangeLabel || "");
      return (b.score || 0) - (a.score || 0);
    });
    return list;
  }, [rows, filter, sort, q]);

  const filters: Array<{ id: MarketFilter; label: string }> = [
    { id: "all", label: "全部" },
    { id: "bullish", label: "偏多" },
    { id: "bearish", label: "偏空" },
    { id: "watch", label: "可留意" },
    { id: "observing", label: "觀察中" },
    { id: "high_risk", label: "高風險" },
  ];

  return (
    <RequireSession>
      <div className="mpv1-page-head">
        <div>
          <h1 className="mpv1-page-title">市場排行</h1>
          <p className="mpv1-page-sub">用評分、狀態與風險，快速找出值得先看的幣。</p>
        </div>
      </div>

      <div className="mpv1-toolbar">
        <div className="mpv1-filters">
          {filters.map((f) => (
            <button
              key={f.id}
              type="button"
              className={`mpv1-filter${filter === f.id ? " is-on" : ""}`}
              onClick={() => setFilter(f.id)}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <label className="mpv1-search" style={{ minWidth: 160 }}>
            <input placeholder="搜尋" value={q} onChange={(e) => setQ(e.target.value)} aria-label="搜尋" />
          </label>
          <select
            className="mpv1-filter"
            value={sort}
            onChange={(e) => setSort(e.target.value as MarketSort)}
            aria-label="排序"
          >
            <option value="score">綜合評分</option>
            <option value="change">漲跌</option>
            <option value="risk">風險</option>
            <option value="recent">最新變化</option>
          </select>
        </div>
      </div>

      <article className="mpv1-card" style={{ padding: 0, overflow: "auto" }}>
        {!canAccess(tier, "full_ranking") ? (
          <p className="mpv1-muted" style={{ padding: "0.75rem 1rem 0" }}>
            入門版顯示精選排行。切換 Preview 可預覽完整名單。
          </p>
        ) : null}
        <table className="mpv1-rank-table">
          <RankTableHeader />
          <tbody>
            {filtered.map((r, i) => (
              <RankTableRow key={r.symbol} row={r} rank={i + 1} />
            ))}
          </tbody>
        </table>
        {!filtered.length ? <p className="mpv1-empty">沒有符合條件的幣種</p> : null}
      </article>
    </RequireSession>
  );
}

export function MarketDetailPage() {
  const { symbol = "" } = useParams();
  const { tier } = useAuth();
  const { has, toggle } = useWatchlist();
  const [asset, setAsset] = useState<AssetDetailDto | null>(null);
  const [tab, setTab] = useState("概況");

  useEffect(() => {
    void marketApi.getAsset(symbol).then(setAsset);
  }, [symbol]);

  if (!asset) {
    return (
      <RequireSession>
        <p className="mpv1-muted">載入中或找不到此幣種…</p>
      </RequireSession>
    );
  }

  const tabs = ["概況", "證據", "衍生品", "流動性", "訊號紀錄"];
  const base = asset.symbol.replace("USDT", "");

  return (
    <RequireSession>
      <div className="mpv1-asset-hero">
        <div>
          <h1>
            {base} / USDT
          </h1>
          <div className="mpv1-asset-price">
            ${fmtPrice(asset.price)}
            <span
              className={asset.change24hPct >= 0 ? "mpv1-chg-up" : "mpv1-chg-down"}
              style={{ marginLeft: "0.65rem", fontSize: "1rem" }}
            >
              {asset.change24hPct >= 0 ? "+" : ""}
              {asset.change24hPct.toFixed(2)}%
            </span>
          </div>
          <div className="mpv1-asset-badges">
            <BiasChip bias={asset.bias} label={asset.biasLabel.includes("偏") ? asset.biasLabel : asset.bias === "bullish" ? "偏多" : asset.bias === "bearish" ? "偏空" : "中性"} />
            <AdviceChip advice={asset.advice} label={asset.adviceLabel} />
            <ScorePill score={asset.score} />
            <RiskChip risk={asset.risk} label={asset.riskLabel} />
          </div>
        </div>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <button
            type="button"
            className="mpv1-btn mpv1-btn-soft"
            onClick={() => toggle(asset.symbol)}
            disabled={!canAccess(tier, "watchlist")}
          >
            {has(asset.symbol) ? "移出觀察" : "加入觀察"}
          </button>
          <Link className="mpv1-btn mpv1-btn-ghost" to="/app/markets">
            返回排行
          </Link>
        </div>
      </div>

      <div className="mpv1-grid mpv1-grid-dash" style={{ marginBottom: "0.85rem" }}>
        <article className="mpv1-card">
          <div className="mpv1-card-head">
            <h2 className="mpv1-card-title">市場圖表</h2>
            <span className="mpv1-muted">模擬 K 線 · 非即時</span>
          </div>
          <div className="mpv1-candle-wrap">
            <CandleChart candles={asset.candles || []} />
          </div>
        </article>
        <div className="mpv1-decision-grid" style={{ gridTemplateColumns: "1fr 1fr", alignContent: "start" }}>
          <div className="mpv1-decision">
            <h4>現在怎麼看</h4>
            <p>
              {asset.adviceLabel} · {asset.bias === "bullish" ? "結構偏多" : asset.bias === "bearish" ? "結構偏空" : "方向不明"}
            </p>
          </div>
          <div className="mpv1-decision">
            <h4>為什麼</h4>
            <p>{asset.whyInteresting[0]}</p>
          </div>
          <div className="mpv1-decision">
            <h4>主要風險</h4>
            <p>{asset.risks[0]}</p>
          </div>
          <div className="mpv1-decision">
            <h4>失效條件</h4>
            <p>{asset.invalidation[0]}</p>
          </div>
        </div>
      </div>

      <div className="mpv1-tabs" role="tablist">
        {tabs.map((t) => (
          <button key={t} type="button" className={`mpv1-tab${tab === t ? " is-on" : ""}`} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>

      <article className="mpv1-card">
        {tab === "概況" && (
          <div className="mpv1-grid mpv1-grid-2">
            <div>
              <h3 className="mpv1-card-title">為什麼值得看</h3>
              {canAccess(tier, "why_reasons") ? (
                <ul className="mpv1-list" style={{ marginTop: "0.55rem" }}>
                  {asset.whyInteresting.map((x) => (
                    <li key={x}>· {x}</li>
                  ))}
                </ul>
              ) : (
                <LockedPanel featureLabel="為什麼值得看" requiredTier={minTierFor("why_reasons")} />
              )}
            </div>
            <div>
              <h3 className="mpv1-card-title">風險與失效</h3>
              <ul className="mpv1-list" style={{ marginTop: "0.55rem" }}>
                {asset.risks.map((x) => (
                  <li key={x}>· {x}</li>
                ))}
                {asset.invalidation.map((x) => (
                  <li key={`i-${x}`}>· 失效：{x}</li>
                ))}
              </ul>
            </div>
          </div>
        )}
        {tab === "證據" &&
          (canAccess(tier, "evidence") ? (
            <div className="mpv1-grid mpv1-grid-2">
              <div>
                <h3 className="mpv1-card-title">支持</h3>
                <ul className="mpv1-list" style={{ marginTop: "0.55rem" }}>
                  {(asset.evidence?.supporting || []).map((x) => (
                    <li key={x}>· {x}</li>
                  ))}
                </ul>
              </div>
              <div>
                <h3 className="mpv1-card-title">需留意的反證</h3>
                <ul className="mpv1-list" style={{ marginTop: "0.55rem" }}>
                  {(asset.evidence?.contradicting || []).map((x) => (
                    <li key={x}>· {x}</li>
                  ))}
                </ul>
              </div>
            </div>
          ) : (
            <LockedPanel featureLabel="市場證據" requiredTier={minTierFor("evidence")} />
          ))}
        {tab === "衍生品" &&
          (canAccess(tier, "derivatives") ? (
            <ul className="mpv1-list">
              <li>資金費率：{asset.derivatives?.fundingLabel}</li>
              <li>持倉：{asset.derivatives?.oiLabel}</li>
              <li>{asset.derivatives?.note}</li>
            </ul>
          ) : (
            <LockedPanel featureLabel="衍生品資訊" requiredTier={minTierFor("derivatives")} />
          ))}
        {tab === "流動性" &&
          (canAccess(tier, "liquidity") ? (
            <ul className="mpv1-list">
              <li>價差：{asset.liquidity?.spreadLabel}</li>
              <li>深度：{asset.liquidity?.depthLabel}</li>
              <li>{asset.liquidity?.note}</li>
            </ul>
          ) : (
            <LockedPanel featureLabel="流動性" requiredTier={minTierFor("liquidity")} />
          ))}
        {tab === "訊號紀錄" &&
          (canAccess(tier, "signal_history") ? (
            <ul className="mpv1-feed">
              {(asset.signalHistory || []).map((s) => (
                <li key={s.id}>
                  <span className="mpv1-alert-ico info" style={{ width: 28, height: 28 }}>
                    <IconTrend size={14} />
                  </span>
                  <div>
                    <strong>{s.summary}</strong>
                  </div>
                  <time>{s.timeLabel}</time>
                </li>
              ))}
            </ul>
          ) : (
            <LockedPanel featureLabel="訊號紀錄" requiredTier={minTierFor("signal_history")} />
          ))}
      </article>
    </RequireSession>
  );
}

export function WatchlistPage() {
  const { tier } = useAuth();
  const { symbols, toggle } = useWatchlist();
  const [rows, setRows] = useState<MarketRankingRowDto[]>([]);

  useEffect(() => {
    void marketApi.getRanking("enterprise").then((all) => {
      setRows(all.filter((r) => symbols.includes(r.symbol)));
    });
  }, [symbols]);

  return (
    <RequireSession>
      <div className="mpv1-page-head">
        <div>
          <h1 className="mpv1-page-title">我的觀察</h1>
          <p className="mpv1-page-sub">把值得持續追蹤的幣放在這裡，每天回來先看變化。</p>
        </div>
      </div>

      {!canAccess(tier, "watchlist") ? (
        <LockedPanel featureLabel="觀察清單" requiredTier={minTierFor("watchlist")} />
      ) : (
        <>
          <article className="mpv1-card" style={{ marginBottom: "0.85rem" }}>
            <h2 className="mpv1-card-title">自上次查看後有什麼改變</h2>
            <ul className="mpv1-feed" style={{ marginTop: "0.65rem" }}>
              {rows.slice(0, 4).map((r) => (
                <li key={`chg-${r.symbol}`}>
                  <span className={`mpv1-coin ${r.symbol.startsWith("ETH") ? "mpv1-coin-eth" : ""}`}>
                    {r.symbol.replace("USDT", "").slice(0, 1)}
                  </span>
                  <div>
                    <strong>{r.symbol.replace("USDT", "")}</strong>
                    <div className="sub">{r.lastChangeLabel || "狀態維持"}</div>
                  </div>
                  <AdviceChip advice={r.advice} label={r.adviceLabel} />
                </li>
              ))}
              {!rows.length ? <li><div className="mpv1-empty">尚無觀察項目</div></li> : null}
            </ul>
          </article>

          <article className="mpv1-card" style={{ padding: 0, overflow: "auto" }}>
            {rows.length === 0 ? (
              <p className="mpv1-empty">
                尚無觀察項目。到 <Link to="/app/markets">市場排行</Link> 加入。
              </p>
            ) : (
              <table className="mpv1-rank-table">
                <RankTableHeader />
                <tbody>
                  {rows.map((r, i) => (
                    <RankTableRow
                      key={r.symbol}
                      row={r}
                      rank={i + 1}
                      action={
                        <button type="button" className="mpv1-btn mpv1-btn-danger-ghost" onClick={() => toggle(r.symbol)}>
                          移出
                        </button>
                      }
                    />
                  ))}
                </tbody>
              </table>
            )}
          </article>
        </>
      )}
    </RequireSession>
  );
}

const ALERT_GROUPS: Array<{ id: AlertDto["category"]; label: string }> = [
  { id: "priority", label: "高優先" },
  { id: "market", label: "市場變化" },
  { id: "risk", label: "風險" },
  { id: "watchlist", label: "觀察清單" },
];

export function AlertsPage() {
  const { tier } = useAuth();
  const [alerts, setAlerts] = useState<AlertDto[]>([]);
  const [filter, setFilter] = useState<"all" | AlertDto["category"] | "unread">("all");

  async function refresh() {
    setAlerts(await alertApi.list());
  }

  useEffect(() => {
    void refresh();
  }, []);

  const visible = alerts.filter((a) => {
    if (filter === "all") return true;
    if (filter === "unread") return !a.read;
    return a.category === filter;
  });

  return (
    <RequireSession>
      <div className="mpv1-page-head">
        <div>
          <h1 className="mpv1-page-title">風險提醒</h1>
          <p className="mpv1-page-sub">用白話告訴你現在該多留意什麼。</p>
        </div>
      </div>

      {!canAccess(tier, "risk_alerts") ? (
        <LockedPanel featureLabel="風險提醒" requiredTier={minTierFor("risk_alerts")} />
      ) : (
        <>
          <div className="mpv1-alert-filters">
            {[
              { id: "all" as const, label: "全部" },
              { id: "unread" as const, label: "未讀" },
              ...ALERT_GROUPS,
            ].map((f) => (
              <button
                key={f.id}
                type="button"
                className={`mpv1-filter${filter === f.id ? " is-on" : ""}`}
                onClick={() => setFilter(f.id)}
              >
                {f.label}
              </button>
            ))}
          </div>

          <div className="mpv1-alert-groups">
            {ALERT_GROUPS.map((g) => {
              const items = visible.filter((a) => a.category === g.id);
              if (!items.length) return null;
              return (
                <section key={g.id}>
                  <h3>{g.label}</h3>
                  {items.map((a) => (
                    <article key={a.id} className={`mpv1-alert-card${a.read ? "" : " is-unread"}`}>
                      <div className={`mpv1-alert-ico ${a.severity}`}>
                        {a.severity === "high" ? <IconAlert size={16} /> : a.severity === "caution" ? <IconShield size={16} /> : <IconBell size={16} />}
                      </div>
                      <div>
                        <h4>
                          {a.title}
                          {a.symbol ? (
                            <Link className="mpv1-link" style={{ marginLeft: "0.5rem" }} to={`/app/market/${a.symbol}`}>
                              {a.symbol.replace("USDT", "")}
                            </Link>
                          ) : null}
                        </h4>
                        <p>{a.body}</p>
                      </div>
                      <div className="mpv1-alert-meta">
                        <time>{a.timeLabel}</time>
                        {!a.read ? (
                          <button
                            type="button"
                            className="mpv1-btn mpv1-btn-ghost mpv1-btn-sm"
                            onClick={() => void alertApi.markRead(a.id).then(refresh)}
                          >
                            標示已讀
                          </button>
                        ) : (
                          <span>已讀</span>
                        )}
                      </div>
                    </article>
                  ))}
                </section>
              );
            })}
            {!visible.length ? <p className="mpv1-empty">沒有符合條件的提醒</p> : null}
          </div>
        </>
      )}
    </RequireSession>
  );
}

export function MembershipPage() {
  const { tier } = useAuth();
  const [plans, setPlans] = useState<PlanDto[]>([]);
  useEffect(() => {
    void memberApi.getPlans().then(setPlans);
  }, []);

  return (
    <RequireSession>
      <div className="mpv1-page-head">
        <div>
          <h1 className="mpv1-page-title">會員方案</h1>
          <p className="mpv1-page-sub">
            目前預覽：{TIER_LABELS[tier]}。用頂部 Preview 可快速看各方案解鎖深度。
          </p>
        </div>
      </div>

      <div className="mpv1-plan-grid">
        {plans.map((p) => (
          <article key={p.id} className={`mpv1-plan${p.id === "professional" || p.id === tier ? " is-hot" : ""}`}>
            {p.id === "professional" ? <div className="mpv1-plan-badge">最多人選擇</div> : null}
            <h2 className="mpv1-card-title">{p.name}</h2>
            <div className="price">{p.priceLabel}</div>
            <div className="audience">適合誰：{p.audience}</div>
            <div className="daily">每天：{p.dailyValue}</div>
            <ul>
              {p.features.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
            {p.id === tier ? (
              <span className="mpv1-chip mpv1-chip-obs">目前預覽中</span>
            ) : (
              <Link className={`mpv1-btn ${p.highlighted ? "mpv1-btn-primary" : "mpv1-btn-outline"} mpv1-btn-block`} to="/plans">
                {p.id === "enterprise" ? "聯絡我們" : "瞭解方案"}
              </Link>
            )}
            {p.id === "enterprise" && canAccess(tier, "team") ? (
              <p className="mpv1-muted" style={{ marginTop: "0.35rem" }}>
                企業預覽：團隊席位、API 概念、資料匯出入口（佔位）。
              </p>
            ) : null}
          </article>
        ))}
      </div>

      <table className="mpv1-compare">
        <thead>
          <tr>
            <th>功能比較</th>
            <th>入門</th>
            <th>進階</th>
            <th>專業</th>
            <th>企業</th>
          </tr>
        </thead>
        <tbody>
          {[
            ["市場總覽", "✓", "✓", "✓", "✓"],
            ["排行深度", "Top 20", "Top 50", "Top 100", "Top 100"],
            ["風險提醒", "基礎", "進階", "即時", "即時"],
            ["觀察清單", "10", "50", "無上限", "無上限"],
            ["完整證據", "—", "—", "✓", "✓"],
            ["團隊 / API", "—", "—", "—", "✓"],
          ].map((row) => (
            <tr key={row[0]}>
              {row.map((cell) => (
                <td key={`${row[0]}-${cell}`}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </RequireSession>
  );
}

const ACCOUNT_SECTIONS = [
  "個人資料",
  "登入與安全性",
  "通知偏好",
  "語言",
  "時區",
  "會員方案",
  "資料與隱私",
] as const;

export function AccountPage() {
  const { session, logout, tier } = useAuth();
  const [section, setSection] = useState<(typeof ACCOUNT_SECTIONS)[number]>("個人資料");

  return (
    <RequireSession>
      <div className="mpv1-page-head">
        <div>
          <h1 className="mpv1-page-title">帳號設定</h1>
          <p className="mpv1-page-sub">本機模擬設定，無真實金流與身分驗證。</p>
        </div>
      </div>

      <div className="mpv1-settings">
        <nav className="mpv1-settings-nav" aria-label="設定分類">
          {ACCOUNT_SECTIONS.map((s) => (
            <button key={s} type="button" className={section === s ? "is-on" : undefined} onClick={() => setSection(s)}>
              {s}
            </button>
          ))}
        </nav>

        <article className="mpv1-card mpv1-settings-panel">
          <h2>{section}</h2>
          <p className="mpv1-muted">以下為產品化設定介面預覽（Mock）。</p>

          {section === "個人資料" && (
            <div className="mpv1-form-grid">
              <div className="mpv1-field">
                <label>顯示名稱</label>
                <div className="mpv1-input">
                  <input defaultValue={session?.displayName} readOnly />
                </div>
              </div>
              <div className="mpv1-field">
                <label>Email</label>
                <div className="mpv1-input">
                  <input defaultValue={session?.email} readOnly />
                </div>
              </div>
              <div className="mpv1-field">
                <label>帳號類型</label>
                <div className="mpv1-input">
                  <input defaultValue={session?.accountType === "enterprise" ? "企業會員" : "個人會員"} readOnly />
                </div>
              </div>
            </div>
          )}

          {section === "登入與安全性" && (
            <>
              <div className="mpv1-toggle-row">
                <span>兩步驟驗證（即將推出）</span>
                <span className="mpv1-chip mpv1-chip-neutral">Mock</span>
              </div>
              <div className="mpv1-toggle-row">
                <span>登入裝置管理</span>
                <button type="button" className="mpv1-btn mpv1-btn-ghost mpv1-btn-sm">
                  查看
                </button>
              </div>
              <button type="button" className="mpv1-btn mpv1-btn-outline" style={{ marginTop: "1rem" }} onClick={logout}>
                登出此裝置
              </button>
            </>
          )}

          {section === "通知偏好" && (
            <>
              {["高優先風險提醒", "觀察清單狀態變化", "每日市場摘要", "產品更新"].map((label) => (
                <label key={label} className="mpv1-toggle-row">
                  <span>{label}</span>
                  <input type="checkbox" defaultChecked={label !== "產品更新"} />
                </label>
              ))}
            </>
          )}

          {section === "語言" && (
            <div className="mpv1-field" style={{ maxWidth: 320 }}>
              <label>介面語言</label>
              <div className="mpv1-input">
                <select defaultValue="zh-TW" style={{ width: "100%", border: 0, outline: 0 }}>
                  <option value="zh-TW">繁體中文</option>
                  <option value="en">English（即將推出）</option>
                </select>
              </div>
            </div>
          )}

          {section === "時區" && (
            <div className="mpv1-field" style={{ maxWidth: 320 }}>
              <label>時區</label>
              <div className="mpv1-input">
                <select defaultValue="Asia/Taipei" style={{ width: "100%", border: 0, outline: 0 }}>
                  <option value="Asia/Taipei">Asia/Taipei (UTC+8)</option>
                  <option value="UTC">UTC</option>
                </select>
              </div>
            </div>
          )}

          {section === "會員方案" && (
            <>
              <p>
                目前方案預覽：<strong>{TIER_LABELS[tier]}</strong>
              </p>
              <p className="mpv1-muted" style={{ margin: "0.5rem 0 1rem" }}>
                使用頂部 Preview 切換可查看不同解鎖深度。非正式扣款。
              </p>
              <Link className="mpv1-btn mpv1-btn-primary" to="/app/membership">
                管理方案
              </Link>
            </>
          )}

          {section === "資料與隱私" && (
            <>
              <div className="mpv1-toggle-row">
                <span>匯出我的觀察清單（Mock）</span>
                <button type="button" className="mpv1-btn mpv1-btn-ghost mpv1-btn-sm">
                  匯出
                </button>
              </div>
              <div className="mpv1-toggle-row">
                <span>清除本機預覽資料</span>
                <button
                  type="button"
                  className="mpv1-btn mpv1-btn-ghost mpv1-btn-sm"
                  onClick={() => {
                    localStorage.removeItem("nexus_mp_v1_session");
                    localStorage.removeItem("nexus_mp_v1_tier_preview");
                    localStorage.removeItem("nexus_mp_v1_watchlist");
                    logout();
                  }}
                >
                  清除
                </button>
              </div>
              <p className="mpv1-muted" style={{ marginTop: "1rem", display: "flex", gap: "0.4rem", alignItems: "center" }}>
                <IconLock size={14} /> 你的資料只屬於你。本平台不下單、不託管資產。
              </p>
            </>
          )}
        </article>
      </div>
    </RequireSession>
  );
}
