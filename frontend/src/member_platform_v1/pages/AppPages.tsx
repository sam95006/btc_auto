import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { AdviceChip, BiasChip } from "../components/Chips";
import { IconAlert, IconBell, IconCrown, IconLock, IconShield, IconStar, IconTrend } from "../components/Icons";
import { LockedPanel } from "../components/LockedPanel";
import { CandleChart, SparkChart } from "../components/SparkChart";
import { BiasGauge, DonutChart, ScoreRing, ToggleSwitch } from "../components/Viz";
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

function coinClass(symbol: string) {
  if (symbol.startsWith("BTC")) return "mpv1-coin-btc";
  if (symbol.startsWith("ETH")) return "mpv1-coin-eth";
  if (symbol.startsWith("SOL")) return "mpv1-coin-sol";
  return "";
}

function RiskSq({ risk, label }: { risk: string; label: string }) {
  const cls = risk === "high" ? "high" : risk === "low" ? "low" : "med";
  return <span className={`mpv1-risk-sq ${cls}`}>{label}</span>;
}

function rankMedal(i: number) {
  if (i < 3) {
    const colors = ["#f59e0b", "#94a3b8", "#b45309"];
    return (
      <span
        style={{
          display: "inline-grid",
          placeItems: "center",
          width: 22,
          height: 22,
          borderRadius: 999,
          background: colors[i],
          color: "#fff",
          fontSize: "0.7rem",
          fontWeight: 700,
        }}
      >
        {i + 1}
      </span>
    );
  }
  return <span style={{ color: "var(--mp-text-3)", fontWeight: 700 }}>{i + 1}</span>;
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

  const best = data.topAssets.find((r) => r.advice === "watch_closely") || data.topAssets[0];

  return (
    <RequireSession>
      <div className="mpv1-grid mpv1-grid-4" style={{ marginBottom: "0.85rem" }}>
        <article className="mpv1-card mpv1-intel">
          <div className="lbl">市場狀態</div>
          <div className="val bull">{data.overview.biasLabel} ↗</div>
          <BiasGauge position={0.72} />
          <div className="hint">恐懼與貪婪指數 64（貪婪）</div>
        </article>
        <article className="mpv1-card mpv1-intel">
          <div className="lbl">最佳機會</div>
          <div className="meta">
            <strong style={{ fontSize: "1.1rem" }}>{best?.symbol.replace("USDT", "")}</strong>
            <span className="mpv1-chip mpv1-chip-bull">高機會</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginTop: "0.35rem" }}>
            <ScoreRing score={best?.score ?? null} size={52} />
            <div className="hint">{best?.name}<br />{best?.beginnerReason}</div>
          </div>
          <Link className="mpv1-footer-link" to="/app/markets">
            查看機會清單 →
          </Link>
        </article>
        <article className="mpv1-card mpv1-intel">
          <div className="lbl">現在怎麼做</div>
          <div className="val accent" style={{ fontSize: "1.15rem" }}>
            {data.overview.adviceLabel}
          </div>
          <ul className="mpv1-intel-list">
            <li>
              <span className="bullet">•</span>關注強勢主流幣，避免追高雜訊幣
            </li>
            <li>
              <span className="bullet">•</span>先鎖定觀察清單，等待更清楚結構
            </li>
            <li>
              <span className="bullet">•</span>控制一次關注數量，降低資訊過載
            </li>
          </ul>
          <Link className="mpv1-footer-link" to="/app/markets">
            查看策略建議 →
          </Link>
        </article>
        <article className="mpv1-card mpv1-intel">
          <div className="lbl">市場風險</div>
          <div className="val warn">{data.overview.riskLabel}風險</div>
          <ul className="mpv1-intel-list">
            <li>
              <span className="bullet warn">•</span>短線波動上升，追價回撤空間變大
            </li>
            <li>
              <span className="bullet warn">•</span>宏觀事件可能快速切換方向
            </li>
            <li>
              <span className="bullet warn">•</span>部分山寨幣槓桿與情緒偏擁擠
            </li>
          </ul>
          <Link className="mpv1-footer-link" to="/app/alerts">
            查看風險分析 →
          </Link>
        </article>
      </div>

      <div className="mpv1-grid mpv1-grid-pulse" style={{ marginBottom: "0.85rem" }}>
        <article className="mpv1-card">
          <div className="mpv1-card-head">
            <h2 className="mpv1-card-title">市場脈動</h2>
            <div className="mpv1-tabs" style={{ margin: 0, border: 0, padding: 0 }}>
              {data.pulse.tickers.map((t) => (
                <span key={t.symbol} className="mpv1-tab is-on" style={{ pointerEvents: "none" }}>
                  {t.symbol}
                </span>
              ))}
            </div>
          </div>
          <div className="mpv1-pulse-stats">
            <div className="mpv1-pulse-stat">
              <div className="lbl">總市值</div>
              <div className="val">
                {data.pulse.marketCapLabel} <span className="mpv1-chg-up" style={{ fontSize: "0.78rem" }}>+2.35%</span>
              </div>
            </div>
            <div className="mpv1-pulse-stat">
              <div className="lbl">24h 成交量</div>
              <div className="val">$128.6B</div>
            </div>
            <div className="mpv1-pulse-stat">
              <div className="lbl">BTC 主導率</div>
              <div className="val">53.1%</div>
            </div>
            <div className="mpv1-pulse-stat">
              <div className="lbl">ETH 主導率</div>
              <div className="val">17.2%</div>
            </div>
          </div>
          <div className="mpv1-ticker-row" style={{ marginBottom: "0.75rem" }}>
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
          <div className="mpv1-pulse-chart">
            <SparkChart values={data.pulse.trend} tone="accent" />
          </div>
        </article>

        <article className="mpv1-card">
          <h2 className="mpv1-card-title">今日用白話文看市場</h2>
          <ul className="mpv1-feed" style={{ marginTop: "0.75rem" }}>
            {[
              { icon: "↗", t: "今天市場正在發生什麼", b: data.plainLanguage.happening },
              { icon: "★", t: "為什麼市場轉強", b: data.plainLanguage.whyStrong },
              { icon: "!", t: "今天先不要做什麼", b: data.plainLanguage.avoid },
              { icon: "🛡", t: "最需要注意的風險", b: data.plainLanguage.topRisk },
            ].map((x) => (
              <li key={x.t}>
                <span className="mpv1-alert-ico info" style={{ width: 28, height: 28 }}>
                  {x.icon}
                </span>
                <div>
                  <strong>{x.t}</strong>
                  <p>{x.b}</p>
                </div>
                <span />
              </li>
            ))}
          </ul>
          <Link className="mpv1-footer-link" to="/app/markets">
            查看更多解讀 →
          </Link>
        </article>
      </div>

      <div className="mpv1-layout-aside">
        <div className="mpv1-grid">
          <article className="mpv1-card" style={{ padding: 0, overflow: "auto" }}>
            <div className="mpv1-card-head" style={{ padding: "0.85rem 1rem 0" }}>
              <h2 className="mpv1-card-title">市場機會一覽</h2>
              <Link className="mpv1-action-link" to="/app/markets">
                查看全部 →
              </Link>
            </div>
            <table className="mpv1-rank-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>資產</th>
                  <th>價格</th>
                  <th>24h</th>
                  <th className="hide-sm">趨勢</th>
                  <th>狀態</th>
                  <th>Score</th>
                  <th className="hide-sm">原因</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.topAssets.slice(0, 6).map((r, i) => {
                  const up = r.change24hPct >= 0;
                  const base = r.symbol.replace("USDT", "");
                  return (
                    <tr key={r.symbol}>
                      <td>{rankMedal(i)}</td>
                      <td>
                        <Link to={`/app/market/${base}`} className="mpv1-asset-cell">
                          <span className={`mpv1-coin ${coinClass(r.symbol)}`}>{base.slice(0, 1)}</span>
                          <span>
                            <strong>{base}</strong>
                            <span>{r.name}</span>
                          </span>
                        </Link>
                      </td>
                      <td style={{ fontWeight: 600 }}>${fmtPrice(r.price)}</td>
                      <td className={up ? "mpv1-chg-up" : "mpv1-chg-down"}>
                        {up ? "+" : ""}
                        {r.change24hPct.toFixed(2)}%
                      </td>
                      <td className="hide-sm">
                        <SparkChart values={r.sparkline || []} compact tone={up ? "bull" : "bear"} />
                      </td>
                      <td>
                        <AdviceChip advice={r.advice} label={r.adviceLabel} />
                      </td>
                      <td>
                        <ScoreRing score={r.score} size={36} />
                      </td>
                      <td className="hide-sm">
                        <div className="mpv1-reason-cell">{r.beginnerReason}</div>
                      </td>
                      <td>
                        <Link className="mpv1-action-link" to={`/app/market/${base}`}>
                          查看分析 →
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </article>

          <article className="mpv1-card">
            <h2 className="mpv1-card-title">近期變化</h2>
            <div className="mpv1-change-strip">
              {data.signalChanges.map((s) => (
                <div key={s.id} className="mpv1-change-chip">
                  <strong>{s.symbol.replace("USDT", "")}</strong>
                  <span className="arrow">
                    {s.fromLabel} → {s.toLabel}
                  </span>
                  <div className="mpv1-muted" style={{ marginTop: 4 }}>
                    {s.timeLabel}
                  </div>
                </div>
              ))}
            </div>
          </article>
        </div>

        <aside className="mpv1-aside-stack">
          <article className="mpv1-card mpv1-aside-card">
            <div className="mpv1-card-head">
              <h2 className="mpv1-card-title">我的觀察</h2>
              <Link className="mpv1-action-link" to="/app/watchlist">
                →
              </Link>
            </div>
            {canAccess(tier, "watchlist") ? (
              (data.watchlistPreview.length ? data.watchlistPreview : data.topAssets).slice(0, 3).map((r) => (
                <div key={r.symbol} className="mpv1-compact-asset">
                  <span className={`mpv1-coin ${coinClass(r.symbol)}`}>{r.symbol.replace("USDT", "").slice(0, 1)}</span>
                  <div>
                    <strong>{r.symbol.replace("USDT", "")}</strong>
                    <div className={r.change24hPct >= 0 ? "mpv1-chg-up" : "mpv1-chg-down"} style={{ fontSize: "0.75rem" }}>
                      {r.change24hPct >= 0 ? "+" : ""}
                      {r.change24hPct.toFixed(2)}%
                    </div>
                  </div>
                  <SparkChart values={r.sparkline || []} compact tone={r.change24hPct >= 0 ? "bull" : "bear"} />
                </div>
              ))
            ) : (
              <LockedPanel featureLabel="觀察清單" requiredTier={minTierFor("watchlist")} />
            )}
          </article>

          <article className="mpv1-card mpv1-aside-card">
            <div className="mpv1-card-head">
              <h2 className="mpv1-card-title">最新提醒</h2>
              <Link className="mpv1-action-link" to="/app/alerts">
                →
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
        </aside>
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
  const [limit, setLimit] = useState(8);

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

  const top3 = [...rows].sort((a, b) => (b.score || 0) - (a.score || 0)).slice(0, 3);
  const highRisk = rows.filter((r) => r.risk === "high").slice(0, 3);

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
          <p className="mpv1-page-sub">洞察市場趨勢，掌握資金流向與關鍵機會。</p>
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
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
          <label className="mpv1-search" style={{ minWidth: 160 }}>
            <input placeholder="搜尋幣種或關鍵字" value={q} onChange={(e) => setQ(e.target.value)} />
          </label>
          <span className="mpv1-muted" style={{ fontSize: "0.78rem" }}>
            排序依據
          </span>
          <select className="mpv1-filter" value={sort} onChange={(e) => setSort(e.target.value as MarketSort)}>
            <option value="score">綜合評分</option>
            <option value="change">漲跌</option>
            <option value="risk">風險</option>
            <option value="recent">最新變化</option>
          </select>
        </div>
      </div>

      <div className="mpv1-layout-aside">
        <article className="mpv1-card" style={{ padding: 0, overflow: "auto" }}>
          {!canAccess(tier, "full_ranking") ? (
            <p className="mpv1-muted" style={{ padding: "0.75rem 1rem 0" }}>
              入門版顯示精選排行。頂部 Preview 可預覽完整名單。
            </p>
          ) : null}
          <table className="mpv1-rank-table">
            <thead>
              <tr>
                <th>#</th>
                <th>資產</th>
                <th>價格</th>
                <th>24h %</th>
                <th>方向</th>
                <th>NEXUS 狀態</th>
                <th>Score</th>
                <th className="hide-sm">趨勢 (7D)</th>
                <th>風險</th>
                <th className="hide-sm">為何值得關注</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.slice(0, limit).map((r, i) => {
                const up = r.change24hPct >= 0;
                const base = r.symbol.replace("USDT", "");
                return (
                  <tr key={r.symbol}>
                    <td>{rankMedal(i)}</td>
                    <td>
                      <Link to={`/app/market/${base}`} className="mpv1-asset-cell">
                        <span className={`mpv1-coin ${coinClass(r.symbol)}`}>{base.slice(0, 1)}</span>
                        <span>
                          <strong>{base}</strong>
                          <span>{r.name}</span>
                        </span>
                      </Link>
                    </td>
                    <td>
                      <div style={{ fontWeight: 700 }}>${fmtPrice(r.price)}</div>
                    </td>
                    <td className={up ? "mpv1-chg-up" : "mpv1-chg-down"}>
                      {up ? "+" : ""}
                      {r.change24hPct.toFixed(2)}%
                    </td>
                    <td>
                      <BiasChip
                        bias={r.bias}
                        label={r.bias === "bullish" ? "偏多 ↗" : r.bias === "bearish" ? "偏空 ↘" : "中性"}
                      />
                    </td>
                    <td>
                      <AdviceChip advice={r.advice} label={r.adviceLabel} />
                    </td>
                    <td>
                      <ScoreRing score={r.score} size={38} />
                    </td>
                    <td className="hide-sm">
                      <SparkChart values={r.sparkline || []} compact tone={up ? "bull" : "bear"} />
                    </td>
                    <td>
                      <RiskSq risk={r.risk} label={r.riskLabel} />
                    </td>
                    <td className="hide-sm">
                      <div className="mpv1-reason-cell">{r.beginnerReason}</div>
                    </td>
                    <td>
                      <Link className="mpv1-action-link" to={`/app/market/${base}`}>
                        查看分析 →
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {filtered.length > limit ? (
            <button type="button" className="mpv1-load-more" onClick={() => setLimit((n) => n + 8)}>
              載入更多 ↓
            </button>
          ) : null}
          <p className="mpv1-muted" style={{ padding: "0.5rem 1rem 0.85rem", fontSize: "0.72rem" }}>
            資料每分鐘更新一次，僅供參考，不構成投資建議。最後更新：模擬資料
          </p>
        </article>

        <aside className="mpv1-aside-stack">
          <article className="mpv1-card mpv1-aside-card">
            <h2 className="mpv1-card-title">今日最值得關注的 3 個機會</h2>
            {top3.map((r, i) => (
              <div key={r.symbol} className="mpv1-compact-asset">
                <span style={{ fontWeight: 700, color: "var(--mp-text-3)", width: 16 }}>{i + 1}</span>
                <div>
                  <strong>{r.symbol.replace("USDT", "")}</strong>
                  <div className="mpv1-muted" style={{ fontSize: "0.72rem" }}>
                    {r.beginnerReason}
                  </div>
                  <div className={r.change24hPct >= 0 ? "mpv1-chg-up" : "mpv1-chg-down"} style={{ fontSize: "0.75rem" }}>
                    ${fmtPrice(r.price)} · {r.change24hPct >= 0 ? "+" : ""}
                    {r.change24hPct.toFixed(2)}%
                  </div>
                </div>
                <Link className="mpv1-action-link" to={`/app/market/${r.symbol.replace("USDT", "")}`}>
                  查看分析
                </Link>
              </div>
            ))}
          </article>
          <article className="mpv1-card mpv1-aside-card">
            <h2 className="mpv1-card-title">風險最高的幣種</h2>
            {(highRisk.length ? highRisk : rows.slice(-3)).map((r) => (
              <div key={r.symbol} className="mpv1-compact-asset">
                <span className={`mpv1-coin ${coinClass(r.symbol)}`}>{r.symbol.replace("USDT", "").slice(0, 1)}</span>
                <div>
                  <strong>{r.symbol.replace("USDT", "")}</strong>
                  <div className={r.change24hPct >= 0 ? "mpv1-chg-up" : "mpv1-chg-down"} style={{ fontSize: "0.75rem" }}>
                    {r.change24hPct >= 0 ? "+" : ""}
                    {r.change24hPct.toFixed(2)}%
                  </div>
                </div>
                <RiskSq risk={r.risk} label={r.riskLabel} />
              </div>
            ))}
            <Link className="mpv1-footer-link" to="/app/alerts">
              查看完整風險分析 →
            </Link>
          </article>
        </aside>
      </div>
    </RequireSession>
  );
}

export function MarketDetailPage() {
  const { symbol = "" } = useParams();
  const { tier } = useAuth();
  const { has, toggle } = useWatchlist();
  const [asset, setAsset] = useState<AssetDetailDto | null>(null);
  const [tab, setTab] = useState("概覽");

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

  const tabs = ["概覽", "證據", "衍生品", "流動性", "訊號歷史"];
  const base = asset.symbol.replace("USDT", "");

  return (
    <RequireSession>
      <p className="mpv1-muted" style={{ marginBottom: "0.5rem", fontSize: "0.78rem" }}>
        市場 / {base} / USDT
      </p>
      <div className="mpv1-asset-hero">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.55rem" }}>
            <span className={`mpv1-coin ${coinClass(asset.symbol)}`} style={{ width: 36, height: 36 }}>
              {base.slice(0, 1)}
            </span>
            <h1>
              {base} / USDT
            </h1>
            <button
              type="button"
              className="mpv1-btn mpv1-btn-ghost mpv1-btn-sm"
              onClick={() => toggle(asset.symbol)}
              disabled={!canAccess(tier, "watchlist")}
              aria-label="觀察清單"
            >
              <IconStar size={14} /> {has(asset.symbol) ? "已觀察" : "加入觀察"}
            </button>
          </div>
          <div className="mpv1-asset-price">
            ${fmtPrice(asset.price)}
            <span className="mpv1-muted" style={{ fontSize: "0.9rem", fontWeight: 500, marginLeft: "0.5rem" }}>
              ≈ NT$ {(asset.price * 32.8).toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </span>
            <span
              className={asset.change24hPct >= 0 ? "mpv1-chg-up" : "mpv1-chg-down"}
              style={{ marginLeft: "0.65rem", fontSize: "1rem" }}
            >
              {asset.change24hPct >= 0 ? "+" : ""}
              {asset.change24hPct.toFixed(2)}%
            </span>
          </div>
          <div className="mpv1-asset-badges">
            <AdviceChip advice={asset.advice} label={asset.adviceLabel} />
            <ScoreRing score={asset.score} size={44} />
            <span className="mpv1-muted" style={{ fontSize: "0.8rem" }}>
              看多偏強 · 1D
            </span>
          </div>
        </div>
      </div>

      <div className="mpv1-layout-aside" style={{ marginBottom: "0.85rem" }}>
        <article className="mpv1-card">
          <div className="mpv1-card-head">
            <h2 className="mpv1-card-title">行情圖</h2>
            <div className="mpv1-filters">
              {["15m", "1H", "4H", "1D"].map((t) => (
                <span key={t} className={`mpv1-filter${t === "15m" ? " is-on" : ""}`}>
                  {t}
                </span>
              ))}
            </div>
          </div>
          <div className="mpv1-candle-wrap">
            <CandleChart candles={asset.candles || []} />
          </div>
        </article>
        <article className="mpv1-card">
          <h2 className="mpv1-card-title">最簡單結論</h2>
          <p style={{ margin: "0.65rem 0", fontWeight: 700, lineHeight: 1.45 }}>
            偏多，但需留意關鍵壓力與宏觀事件風險。
          </p>
          <ul className="mpv1-list">
            <li>方向：{asset.bias === "bullish" ? "偏多" : asset.bias === "bearish" ? "偏空" : "中性"}</li>
            <li>信心：{asset.score ?? "—"} / 100</li>
            <li>觀察重點：{asset.whyInteresting[0]}</li>
          </ul>
          <div style={{ marginTop: "0.85rem" }}>
            <div className="mpv1-muted" style={{ fontSize: "0.75rem", marginBottom: 4 }}>
              風險等級
            </div>
            <BiasGauge position={asset.risk === "high" ? 0.85 : asset.risk === "low" ? 0.25 : 0.55} />
            <div className="mpv1-muted" style={{ fontSize: "0.78rem" }}>
              {asset.riskLabel}等風險
            </div>
          </div>
        </article>
      </div>

      <div className="mpv1-decision-grid" style={{ marginBottom: "0.85rem" }}>
        <div className="mpv1-decision">
          <h4>現在怎麼看</h4>
          <AdviceChip advice={asset.advice} label={asset.adviceLabel} />
          <p style={{ marginTop: "0.45rem" }}>{asset.whyInteresting[0]}</p>
        </div>
        <div className="mpv1-decision">
          <h4>為什麼</h4>
          <ul className="mpv1-list">
            {asset.whyInteresting.slice(0, 3).map((x) => (
              <li key={x}>· {x}</li>
            ))}
          </ul>
        </div>
        <div className="mpv1-decision">
          <h4>主要風險</h4>
          <ul className="mpv1-list">
            {asset.risks.slice(0, 3).map((x) => (
              <li key={x}>· {x}</li>
            ))}
          </ul>
        </div>
        <div className="mpv1-decision">
          <h4>失效條件</h4>
          <ul className="mpv1-list">
            {asset.invalidation.slice(0, 3).map((x) => (
              <li key={x}>· {x}</li>
            ))}
          </ul>
        </div>
      </div>

      <div className="mpv1-layout-aside">
        <div>
          <div className="mpv1-tabs" role="tablist">
            {tabs.map((t) => (
              <button key={t} type="button" className={`mpv1-tab${tab === t ? " is-on" : ""}`} onClick={() => setTab(t)}>
                {t}
              </button>
            ))}
          </div>
          <article className="mpv1-card">
            {tab === "概覽" && (
              <>
                <p className="mpv1-muted" style={{ marginBottom: "0.75rem" }}>
                  白話解讀：目前{asset.adviceLabel}，結構{asset.bias === "bullish" ? "偏多" : asset.bias === "bearish" ? "偏空" : "不明"}。
                  新手先看結論；專業細節在下方指標與其他分頁。
                </p>
                <div className="mpv1-pulse-stats">
                  <div className="mpv1-pulse-stat">
                    <div className="lbl">價格</div>
                    <div className="val">${fmtPrice(asset.price)}</div>
                  </div>
                  <div className="mpv1-pulse-stat">
                    <div className="lbl">24h</div>
                    <div className="val">{asset.change24hPct.toFixed(2)}%</div>
                  </div>
                  <div className="mpv1-pulse-stat">
                    <div className="lbl">NEXUS Score</div>
                    <div className="val">{asset.score ?? "—"}</div>
                  </div>
                  <div className="mpv1-pulse-stat">
                    <div className="lbl">風險</div>
                    <div className="val">{asset.riskLabel}</div>
                  </div>
                </div>
                <div className="mpv1-ind-grid">
                  {[
                    ["趨勢", "偏多"],
                    ["動能", "轉強"],
                    ["資金", "流入"],
                    ["OI / Funding", asset.derivatives?.fundingLabel || "中性"],
                    ["清算", "正常"],
                    ["支撐壓力", "關注"],
                  ].map(([a, b]) => (
                    <div key={a} className="mpv1-ind">
                      <div className="lbl">{a}</div>
                      <AdviceChip label={b} />
                      <div style={{ marginTop: 6, height: 28 }}>
                        <SparkChart values={asset.sparkline.slice(0, 12)} compact />
                      </div>
                    </div>
                  ))}
                </div>
              </>
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
            {tab === "訊號歷史" &&
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
                <LockedPanel featureLabel="訊號歷史" requiredTier={minTierFor("signal_history")} />
              ))}
          </article>
        </div>

        <aside className="mpv1-aside-stack">
          <article className="mpv1-card mpv1-aside-card">
            <h2 className="mpv1-card-title">關鍵價位</h2>
            <ul className="mpv1-levels">
              <li>
                <span className="tag res">壓力 2</span>
                <span>${fmtPrice(asset.price * 1.06)}</span>
              </li>
              <li>
                <span className="tag res">壓力 1</span>
                <span>${fmtPrice(asset.price * 1.03)}</span>
              </li>
              <li>
                <span className="tag">現價</span>
                <span>${fmtPrice(asset.price)}</span>
              </li>
              <li>
                <span className="tag sup">支撐 1</span>
                <span>${fmtPrice(asset.price * 0.97)}</span>
              </li>
              <li>
                <span className="tag sup">支撐 2</span>
                <span>${fmtPrice(asset.price * 0.94)}</span>
              </li>
            </ul>
          </article>
          <article className="mpv1-card mpv1-aside-card">
            <h2 className="mpv1-card-title">相關事件</h2>
            <ul className="mpv1-feed">
              <li>
                <span className="mpv1-chip mpv1-chip-wait">高</span>
                <div>
                  <strong>美國 CPI 數據</strong>
                  <p>可能放大短線波動</p>
                </div>
                <time>即將</time>
              </li>
              <li>
                <span className="mpv1-chip mpv1-chip-obs">中</span>
                <div>
                  <strong>ETH 生態關注度</strong>
                  <p>資金與活躍度同步觀察</p>
                </div>
                <time>本週</time>
              </li>
            </ul>
          </article>
        </aside>
      </div>
    </RequireSession>
  );
}

export function WatchlistPage() {
  const { tier } = useAuth();
  const { symbols, toggle } = useWatchlist();
  const [rows, setRows] = useState<MarketRankingRowDto[]>([]);
  const [filter, setFilter] = useState<"all" | "watch" | "observing" | "wait" | "changed">("all");
  const [alertsOn, setAlertsOn] = useState<Record<string, boolean>>({});

  useEffect(() => {
    void marketApi.getRanking("enterprise").then((all) => {
      setRows(all.filter((r) => symbols.includes(r.symbol)));
    });
  }, [symbols]);

  const counts = {
    all: rows.length,
    watch: rows.filter((r) => r.advice === "watch_closely").length,
    observing: rows.filter((r) => r.advice === "observing").length,
    wait: rows.filter((r) => r.advice === "wait").length,
    changed: Math.min(2, rows.length),
  };

  const filtered = rows.filter((r) => {
    if (filter === "watch") return r.advice === "watch_closely";
    if (filter === "observing") return r.advice === "observing";
    if (filter === "wait") return r.advice === "wait";
    if (filter === "changed") return Boolean(r.lastChangeLabel);
    return true;
  });

  const priority = [...rows].sort((a, b) => b.change24hPct - a.change24hPct).slice(0, 3);
  const risingRisk = [...rows].filter((r) => r.risk === "high" || r.change24hPct < 0).slice(0, 3);
  const flat = [...rows].filter((r) => Math.abs(r.change24hPct) < 0.5).slice(0, 3);

  return (
    <RequireSession>
      <div className="mpv1-page-head">
        <div>
          <h1 className="mpv1-page-title">
            <IconStar size={20} style={{ verticalAlign: -3, marginRight: 6 }} />
            我的觀察
          </h1>
          <p className="mpv1-page-sub">追蹤你關注的資產，掌握最新變化與機會。</p>
        </div>
      </div>

      {!canAccess(tier, "watchlist") ? (
        <LockedPanel featureLabel="觀察清單" requiredTier={minTierFor("watchlist")} />
      ) : (
        <div className="mpv1-layout-aside">
          <div className="mpv1-grid">
            <div className="mpv1-toolbar">
              <div className="mpv1-filters">
                {(
                  [
                    ["all", `全部 ${counts.all}`],
                    ["watch", `可留意 ${counts.watch}`],
                    ["observing", `觀察中 ${counts.observing}`],
                    ["wait", `先不要急 ${counts.wait}`],
                    ["changed", `已變化 ${counts.changed}`],
                  ] as const
                ).map(([id, label]) => (
                  <button
                    key={id}
                    type="button"
                    className={`mpv1-filter${filter === id ? " is-on" : ""}`}
                    onClick={() => setFilter(id)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <span className="mpv1-filter">最新變化優先</span>
            </div>

            <article className="mpv1-card" style={{ padding: 0, overflow: "auto" }}>
              {filtered.length === 0 ? (
                <p className="mpv1-empty">
                  尚無觀察項目。到 <Link to="/app/markets">市場排行</Link> 加入。
                </p>
              ) : (
                <>
                  <table className="mpv1-rank-table">
                    <thead>
                      <tr>
                        <th>資產</th>
                        <th>價格 / 24h%</th>
                        <th>走勢</th>
                        <th>評分</th>
                        <th>NEXUS 狀態</th>
                        <th className="hide-sm">最後變化</th>
                        <th className="hide-sm">7D</th>
                        <th>提醒</th>
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filtered.map((r) => {
                        const up = r.change24hPct >= 0;
                        const base = r.symbol.replace("USDT", "");
                        const on = alertsOn[r.symbol] ?? true;
                        return (
                          <tr key={r.symbol}>
                            <td>
                              <Link to={`/app/market/${base}`} className="mpv1-asset-cell">
                                <span className={`mpv1-coin ${coinClass(r.symbol)}`}>{base.slice(0, 1)}</span>
                                <span>
                                  <strong>{base}</strong>
                                  <span>{r.name}</span>
                                </span>
                              </Link>
                            </td>
                            <td>
                              <div style={{ fontWeight: 700 }}>${fmtPrice(r.price)}</div>
                              <div className={up ? "mpv1-chg-up" : "mpv1-chg-down"} style={{ fontSize: "0.75rem" }}>
                                {up ? "+" : ""}
                                {r.change24hPct.toFixed(2)}%
                              </div>
                            </td>
                            <td>{up ? "↗" : "↘"}</td>
                            <td>
                              <ScoreRing score={r.score} size={38} />
                            </td>
                            <td>
                              <AdviceChip advice={r.advice} label={r.adviceLabel} />
                            </td>
                            <td className="hide-sm">
                              <div className="mpv1-reason-cell">{r.lastChangeLabel || "狀態維持"}</div>
                            </td>
                            <td className="hide-sm">
                              <SparkChart values={r.sparkline || []} compact tone={up ? "bull" : "bear"} />
                            </td>
                            <td>
                              <ToggleSwitch
                                checked={on}
                                onChange={(v) => setAlertsOn((s) => ({ ...s, [r.symbol]: v }))}
                                label={`${base} 提醒`}
                              />
                            </td>
                            <td>
                              <button type="button" className="mpv1-btn mpv1-btn-danger-ghost" onClick={() => toggle(r.symbol)}>
                                移出
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                  <button type="button" className="mpv1-load-more">
                    載入更多 ↓
                  </button>
                </>
              )}
            </article>

            <article className="mpv1-card">
              <h2 className="mpv1-card-title">自上次查看後有什麼改變</h2>
              <ul className="mpv1-feed" style={{ marginTop: "0.65rem" }}>
                {rows.slice(0, 3).map((r) => (
                  <li key={`chg-${r.symbol}`}>
                    <span className="mpv1-chip mpv1-chip-obs">
                      觀察中 → {r.adviceLabel}
                    </span>
                    <div>
                      <strong>{r.symbol.replace("USDT", "")}</strong>
                      <div className="sub">{r.beginnerReason}</div>
                    </div>
                    <time>{r.lastChangeLabel?.split(" ")[0] || "今天"}</time>
                  </li>
                ))}
              </ul>
              <div style={{ textAlign: "center" }}>
                <Link className="mpv1-footer-link" to="/app/alerts">
                  查看全部變化 →
                </Link>
              </div>
            </article>
          </div>

          <aside className="mpv1-aside-stack">
            <article className="mpv1-card mpv1-aside-card">
              <h2 className="mpv1-card-title">我的觀察總覽</h2>
              <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
                <DonutChart
                  size={110}
                  centerLabel={String(counts.all || 0)}
                  centerSub="總資產"
                  segments={[
                    { value: counts.watch || 1, color: "#059669" },
                    { value: counts.observing || 1, color: "#2563eb" },
                    { value: counts.wait || 1, color: "#d97706" },
                    { value: counts.changed || 1, color: "#7c3aed" },
                  ]}
                />
                <div className="mpv1-legend">
                  <div className="mpv1-legend-row">
                    <span className="mpv1-legend-dot" style={{ background: "#059669" }} />可留意 {counts.watch}
                  </div>
                  <div className="mpv1-legend-row">
                    <span className="mpv1-legend-dot" style={{ background: "#2563eb" }} />觀察中 {counts.observing}
                  </div>
                  <div className="mpv1-legend-row">
                    <span className="mpv1-legend-dot" style={{ background: "#d97706" }} />先不要急 {counts.wait}
                  </div>
                  <div className="mpv1-legend-row">
                    <span className="mpv1-legend-dot" style={{ background: "#7c3aed" }} />已變化 {counts.changed}
                  </div>
                </div>
              </div>
            </article>
            <article className="mpv1-card mpv1-aside-card">
              <h2 className="mpv1-card-title">最值得優先看</h2>
              {priority.map((r) => (
                <div key={r.symbol} className="mpv1-compact-asset">
                  <span className={`mpv1-coin ${coinClass(r.symbol)}`}>{r.symbol.replace("USDT", "").slice(0, 1)}</span>
                  <strong>{r.symbol.replace("USDT", "")}</strong>
                  <span className="mpv1-chg-up">+{Math.abs(r.change24hPct).toFixed(2)}%</span>
                </div>
              ))}
            </article>
            <article className="mpv1-card mpv1-aside-card">
              <h2 className="mpv1-card-title">風險升高</h2>
              {risingRisk.map((r) => (
                <div key={r.symbol} className="mpv1-compact-asset">
                  <span className={`mpv1-coin ${coinClass(r.symbol)}`}>{r.symbol.replace("USDT", "").slice(0, 1)}</span>
                  <strong>{r.symbol.replace("USDT", "")}</strong>
                  <span className="mpv1-chg-down">{r.change24hPct.toFixed(2)}%</span>
                </div>
              ))}
            </article>
            <article className="mpv1-card mpv1-aside-card">
              <h2 className="mpv1-card-title">今天沒有明顯變化</h2>
              {(flat.length ? flat : rows.slice(0, 3)).map((r) => (
                <div key={r.symbol} className="mpv1-compact-asset">
                  <span className={`mpv1-coin ${coinClass(r.symbol)}`}>{r.symbol.replace("USDT", "").slice(0, 1)}</span>
                  <strong>{r.symbol.replace("USDT", "")}</strong>
                  <span className="mpv1-muted">{r.change24hPct.toFixed(2)}%</span>
                </div>
              ))}
            </article>
          </aside>
        </div>
      )}
    </RequireSession>
  );
}

const ALERT_GROUPS: Array<{ id: AlertDto["category"]; label: string; tone: string }> = [
  { id: "priority", label: "高優先提醒", tone: "high" },
  { id: "market", label: "市場變化", tone: "info" },
  { id: "risk", label: "風險提醒", tone: "caution" },
  { id: "watchlist", label: "觀察清單提醒", tone: "info" },
];

export function AlertsPage() {
  const { tier } = useAuth();
  const [alerts, setAlerts] = useState<AlertDto[]>([]);
  const [filter, setFilter] = useState<"all" | AlertDto["category"] | "unread" | "read">("all");

  async function refresh() {
    setAlerts(await alertApi.list());
  }

  useEffect(() => {
    void refresh();
  }, []);

  const visible = alerts.filter((a) => {
    if (filter === "all") return true;
    if (filter === "unread") return !a.read;
    if (filter === "read") return a.read;
    return a.category === filter;
  });

  const unread = alerts.filter((a) => !a.read).length;
  const byCat = {
    priority: alerts.filter((a) => a.category === "priority").length,
    market: alerts.filter((a) => a.category === "market").length,
    risk: alerts.filter((a) => a.category === "risk").length,
    watchlist: alerts.filter((a) => a.category === "watchlist").length,
  };

  return (
    <RequireSession>
      <div className="mpv1-page-head">
        <div>
          <h1 className="mpv1-page-title">
            <IconBell size={18} style={{ verticalAlign: -3, marginRight: 6, color: "var(--mp-accent)" }} />
            風險提醒
          </h1>
          <p className="mpv1-page-sub">用白話告訴你現在該多留意什麼，並依優先級整理事件流。</p>
        </div>
      </div>

      {!canAccess(tier, "risk_alerts") ? (
        <LockedPanel featureLabel="風險提醒" requiredTier={minTierFor("risk_alerts")} />
      ) : (
        <div className="mpv1-layout-aside">
          <div>
            <div className="mpv1-alert-filters">
              {[
                { id: "all" as const, label: "全部" },
                { id: "priority" as const, label: "高優先" },
                { id: "market" as const, label: "市場變化" },
                { id: "risk" as const, label: "風險" },
                { id: "watchlist" as const, label: "觀察清單" },
                { id: "unread" as const, label: "未讀" },
                { id: "read" as const, label: "已讀" },
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
                    <div className="mpv1-card-head">
                      <h3>
                        {g.label} <span className="mpv1-chip mpv1-chip-obs">{items.length}</span>
                      </h3>
                    </div>
                    {items.map((a) => (
                      <article key={a.id} className={`mpv1-alert-card${a.read ? "" : " is-unread"}`}>
                        <div className={`mpv1-alert-ico ${a.severity}`}>
                          {a.severity === "high" ? <IconAlert size={16} /> : a.severity === "caution" ? <IconShield size={16} /> : <IconBell size={16} />}
                        </div>
                        <div>
                          <h4>
                            {a.symbol ? `${a.symbol.replace("USDT", "")} · ` : ""}
                            {a.title}
                            {!a.read ? <span className="mpv1-chip mpv1-chip-obs" style={{ marginLeft: 8 }}>未讀</span> : null}
                          </h4>
                          <p>{a.body}</p>
                          {a.symbol ? (
                            <Link className="mpv1-action-link" to={`/app/market/${a.symbol.replace("USDT", "")}`}>
                              查看 {a.symbol.replace("USDT", "")} 分析 →
                            </Link>
                          ) : null}
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
          </div>

          <aside className="mpv1-aside-stack">
            <article className="mpv1-card mpv1-aside-card">
              <h2 className="mpv1-card-title">今日提醒摘要</h2>
              <div style={{ fontSize: "2rem", fontWeight: 700 }}>{alerts.length}</div>
              <div className="mpv1-muted" style={{ marginBottom: "0.75rem" }}>
                未讀 {unread}
              </div>
              <div className="mpv1-legend">
                <div className="mpv1-legend-row">高優先 {byCat.priority}</div>
                <div className="mpv1-legend-row">市場變化 {byCat.market}</div>
                <div className="mpv1-legend-row">風險 {byCat.risk}</div>
                <div className="mpv1-legend-row">觀察清單 {byCat.watchlist}</div>
              </div>
              <div style={{ marginTop: "0.85rem" }}>
                <DonutChart
                  size={100}
                  centerLabel={`${Math.round((unread / Math.max(alerts.length, 1)) * 100)}%`}
                  centerSub="未讀"
                  segments={[
                    { value: unread || 1, color: "#2563eb" },
                    { value: alerts.length - unread || 1, color: "#e2e8f0" },
                  ]}
                />
              </div>
              <button
                type="button"
                className="mpv1-footer-link"
                style={{ border: 0, background: "transparent", cursor: "pointer", padding: 0 }}
                onClick={() => void Promise.all(alerts.filter((a) => !a.read).map((a) => alertApi.markRead(a.id))).then(refresh)}
              >
                全部標為已讀
              </button>
            </article>
            <article className="mpv1-card mpv1-aside-card">
              <h2 className="mpv1-card-title">最近查看資產</h2>
              {["BTC", "SOL", "ETH", "AVAX"].map((s) => (
                <div key={s} className="mpv1-compact-asset">
                  <span className="mpv1-coin">{s.slice(0, 1)}</span>
                  <strong>{s}</strong>
                  <Link className="mpv1-action-link" to={`/app/market/${s}`}>
                    查看分析
                  </Link>
                </div>
              ))}
              <Link className="mpv1-footer-link" to="/app/watchlist">
                前往我的觀察 →
              </Link>
            </article>
            <article className="mpv1-card mpv1-aside-card">
              <h2 className="mpv1-card-title">提醒設定</h2>
              <p className="mpv1-muted">自訂站內與郵件提醒偏好（Mock）。</p>
              <Link className="mpv1-footer-link" to="/app/account">
                前往設定 →
              </Link>
            </article>
          </aside>
        </div>
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
          <p className="mpv1-page-sub">選擇適合你的資訊深度。目前預覽：{TIER_LABELS[tier]}。</p>
        </div>
      </div>

      <div className="mpv1-plan-grid">
        {plans.map((p) => {
          const hot = p.id === "professional";
          const current = p.id === tier;
          return (
            <article key={p.id} className={`mpv1-plan${hot ? " is-hot" : ""}`}>
              {hot ? <div className="mpv1-plan-badge">最受歡迎</div> : null}
              <div style={{ color: "var(--mp-accent)" }}>
                {p.id === "enterprise" ? <IconShield size={18} /> : p.id === "professional" ? <IconCrown size={18} /> : <IconTrend size={18} />}
              </div>
              <h2 className="mpv1-card-title">{p.name}</h2>
              <div className="audience">{p.audience}</div>
              <div className="price">{p.priceLabel}</div>
              <div className="daily">每天：{p.dailyValue}</div>
              <ul>
                {p.features.map((f) => (
                  <li key={f}>✓ {f}</li>
                ))}
              </ul>
              {current ? (
                <button type="button" className="mpv1-btn mpv1-btn-ghost mpv1-btn-block" disabled>
                  目前方案
                </button>
              ) : (
                <Link
                  className={`mpv1-btn ${hot ? "mpv1-btn-primary" : "mpv1-btn-outline"} mpv1-btn-block`}
                  to={p.id === "enterprise" ? "/register" : "/plans"}
                >
                  {p.id === "enterprise" ? "聯絡我們" : "立即升級"}
                </Link>
              )}
            </article>
          );
        })}
      </div>

      <h2 className="mpv1-card-title" style={{ margin: "1.25rem 0 0.65rem" }}>
        方案功能比較
      </h2>
      <table className="mpv1-compare">
        <thead>
          <tr>
            <th>功能</th>
            <th>入門版</th>
            <th>進階版</th>
            <th>專業版</th>
            <th>企業版</th>
          </tr>
        </thead>
        <tbody>
          {[
            ["市場總覽", "基礎", "完整", "完整", "完整"],
            ["排行深度", "基礎", "多維度", "頂級", "頂級"],
            ["今日重點", "✓", "✓", "✓", "✓"],
            ["觀察清單", "10", "50", "200", "無上限"],
            ["風險提醒", "基礎", "進階", "自訂", "團隊"],
            ["歷史深度", "7 天", "90 天", "365 天", "無上限"],
            ["完整證據", "—", "部分", "✓", "✓"],
            ["API", "—", "—", "有限", "高額度"],
            ["Bridge", "—", "—", "匯出", "完整"],
            ["Team / SSO", "—", "—", "—", "✓"],
          ].map((row) => (
            <tr key={row[0]}>
              {row.map((cell) => (
                <td key={`${row[0]}-${cell}`}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mpv1-muted" style={{ marginTop: "0.85rem", textAlign: "center" }}>
        可隨時升級或降級；正式金流尚未接入，此頁為產品預覽。
      </p>
    </RequireSession>
  );
}

export function AccountPage() {
  const { session, logout, tier } = useAuth();

  return (
    <RequireSession>
      <div className="mpv1-page-head">
        <div>
          <h1 className="mpv1-page-title">帳號設定</h1>
          <p className="mpv1-page-sub">管理個人資料、安全、通知與會員偏好（Mock）。</p>
        </div>
      </div>

      <div className="mpv1-layout-aside">
        <div className="mpv1-settings-main">
          <article className="mpv1-card">
            <h2 className="mpv1-card-title">個人資料</h2>
            <div style={{ display: "flex", gap: "1rem", alignItems: "center", marginTop: "0.75rem" }}>
              <div className="mpv1-avatar-lg">{(session?.displayName || "N").slice(0, 1).toUpperCase()}</div>
              <div className="mpv1-form-grid" style={{ flex: 1 }}>
                <div className="mpv1-field">
                  <label>顯示名稱</label>
                  <div className="mpv1-input">
                    <input defaultValue={session?.displayName} />
                  </div>
                </div>
                <div className="mpv1-field">
                  <label>電子郵件</label>
                  <div className="mpv1-input">
                    <input defaultValue={session?.email} />
                    <span className="mpv1-chip mpv1-chip-bull">已驗證</span>
                  </div>
                </div>
              </div>
            </div>
          </article>

          <article className="mpv1-card">
            <h2 className="mpv1-card-title">登入與安全性</h2>
            <div className="mpv1-toggle-row">
              <span>密碼</span>
              <button type="button" className="mpv1-btn mpv1-btn-ghost mpv1-btn-sm">
                變更密碼
              </button>
            </div>
            <div className="mpv1-toggle-row">
              <span>
                兩步驟驗證 <span className="mpv1-chip mpv1-chip-bull">已啟用</span>
              </span>
              <span className="mpv1-muted">→</span>
            </div>
            <div className="mpv1-toggle-row">
              <span>裝置管理與近期活動</span>
              <span className="mpv1-muted">→</span>
            </div>
          </article>

          <article className="mpv1-card">
            <h2 className="mpv1-card-title">通知偏好</h2>
            <table className="mpv1-notif-table">
              <thead>
                <tr>
                  <th></th>
                  <th>站內通知</th>
                  <th>電子郵件</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ["市場提醒", true, true],
                  ["風險提醒", true, true],
                  ["產品更新", true, false],
                  ["行銷訊息", false, false],
                ].map(([label, a, b]) => (
                  <tr key={String(label)}>
                    <td>{label}</td>
                    <td>
                      <ToggleSwitch checked={Boolean(a)} />
                    </td>
                    <td>
                      <ToggleSwitch checked={Boolean(b)} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </article>

          <article className="mpv1-card">
            <h2 className="mpv1-card-title">語言與時區</h2>
            <div className="mpv1-form-grid">
              <div className="mpv1-field">
                <label>介面語言</label>
                <div className="mpv1-input">
                  <select defaultValue="zh-TW" style={{ width: "100%", border: 0, outline: 0 }}>
                    <option value="zh-TW">繁體中文（台灣）</option>
                    <option value="en">English</option>
                  </select>
                </div>
              </div>
              <div className="mpv1-field">
                <label>時區</label>
                <div className="mpv1-input">
                  <select defaultValue="Asia/Taipei" style={{ width: "100%", border: 0, outline: 0 }}>
                    <option value="Asia/Taipei">(GMT+08:00) 台北</option>
                    <option value="UTC">UTC</option>
                  </select>
                </div>
              </div>
            </div>
          </article>
        </div>

        <aside className="mpv1-aside-stack">
          <article className="mpv1-card mpv1-aside-card">
            <h2 className="mpv1-card-title">
              <IconCrown size={14} /> 會員方案
            </h2>
            <p>
              <strong>{TIER_LABELS[tier]}</strong> <span className="mpv1-chip mpv1-chip-bull">使用中</span>
            </p>
            <p className="mpv1-muted" style={{ margin: "0.45rem 0" }}>
              年繳方案（模擬）· 下次續期 2025/08/15
            </p>
            <Link className="mpv1-btn mpv1-btn-primary mpv1-btn-sm mpv1-btn-block" to="/app/membership">
              管理方案
            </Link>
            <Link className="mpv1-footer-link" to="/plans">
              查看方案比較
            </Link>
          </article>
          <article className="mpv1-card mpv1-aside-card">
            <h2 className="mpv1-card-title">
              <IconShield size={14} /> 資料與隱私
            </h2>
            {["下載我的資料", "隱私設定", "封鎖名單", "清除快取"].map((x) => (
              <div key={x} className="mpv1-toggle-row">
                <span>{x}</span>
                <span className="mpv1-muted">→</span>
              </div>
            ))}
          </article>
          <article className="mpv1-card mpv1-aside-card">
            <h2 className="mpv1-card-title">帳號操作</h2>
            <div className="mpv1-toggle-row">
              <span>變更 Email</span>
              <span className="mpv1-muted">→</span>
            </div>
            <button type="button" className="mpv1-btn mpv1-btn-outline mpv1-btn-block" onClick={logout}>
              登出
            </button>
            <button type="button" className="mpv1-btn mpv1-btn-danger-ghost mpv1-btn-block" style={{ marginTop: "0.5rem" }}>
              <IconLock size={14} /> 刪除帳號（Mock）
            </button>
          </article>
        </aside>
      </div>
    </RequireSession>
  );
}
