import { useEffect, useState, type ReactNode } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useWatchlist } from "../context/WatchlistContext";
import { useLiveMarketHistory } from "../hooks/useLiveMarketHistory";
import { useLiveMarketTickers } from "../hooks/useLiveMarketTickers";
import { HomePage } from "./home/HomePage";
import {
  getLiveMarketRankings, getMarketDerivatives, getMarketLiquidity,
  getMemberNotifications, getMemberProfile, getNotificationPreferences, markMemberNotificationRead,
  updateMemberProfile, updateNotificationPreferences, type LiveMarketRanking, type LiveMarketTelemetry,
} from "../services/stagingApi";

function RequireSession({ children }: { children: ReactNode }) {
  const { session, ready } = useAuth();
  if (!ready) return null;
  return session ? <>{children}</> : <Navigate to="/login" replace />;
}
function fmt(value: number | null | undefined) {
  return typeof value === "number" ? value.toLocaleString(undefined, { maximumFractionDigits: value >= 1 ? 2 : 6 }) : "—";
}
function status(freshness?: string) {
  return freshness === "LIVE" || freshness === "FRESH" ? "LIVE" : freshness === "DATA_DELAYED" || freshness === "STALE" ? "DATA DELAYED" : "UNAVAILABLE";
}
function RuntimeRequired({ title = "進階市場功能即將推出" }: { title?: string }) {
  return <section className="mpv1-card" data-classification="COMING_SOON"><h2 className="mpv1-card-title">{title}</h2><p className="mpv1-muted">進階評分、訊號與風險解讀即將推出。目前不顯示尚未取得的結論，也不會以假資料呈現。</p></section>;
}

// NEXUS-EXPERIENCE-1B: the customer Home is now the answer-first, view-mode-aware
// HomePage (no research/dev terminology, no engineering provider labels, no direct
// third-party news widget). Real backend data with honest COMING_SOON states.
export function DashboardPage() {
  return <RequireSession><HomePage /></RequireSession>;
}

function MarketTable({ rows }: { rows: LiveMarketRanking["rows"] }) {
  if (!rows.length) return <p className="mpv1-muted">公開市場資料暫時無法取得。</p>;
  return <div style={{ overflow: "auto" }}><table className="mpv1-rank-table"><thead><tr><th>資產</th><th>價格</th><th>24h</th><th>24h 成交額</th><th>狀態</th></tr></thead><tbody>{rows.map(row => <tr key={row.symbol}><td><Link to={`/app/market/${row.symbol.replace("USDT", "")}`}>{row.symbol.replace("USDT", "")}</Link></td><td>${fmt(row.current_price)}</td><td className={(row.change_24h_percent || 0) >= 0 ? "mpv1-chg-up" : "mpv1-chg-down"}>{fmt(row.change_24h_percent)}%</td><td>${fmt(row.volume_24h)}</td><td>{status(row.freshness)}</td></tr>)}</tbody></table></div>;
}

export function MarketsPage() {
  const [metric, setMetric] = useState<LiveMarketRanking["ranking_type"]>("gainers");
  const [data, setData] = useState<LiveMarketRanking | null>(null);
  useEffect(() => { void getLiveMarketRankings(metric).then(setData).catch(() => setData(null)); }, [metric]);
  const labels: Record<typeof metric, string> = { gainers: "漲幅排行", losers: "跌幅排行", volume: "成交量排行", volatility: "波動排行", liquidity: "流動性排行" };
  return <RequireSession><div className="mpv1-page-head"><div><h1 className="mpv1-page-title">市場排行</h1><p className="mpv1-page-sub">僅依 交易所公開 24H 統計排序；不是 NEXUS/AI 機會排行。</p></div></div>
    <div className="mpv1-filters">{(Object.keys(labels) as Array<typeof metric>).map(item => <button key={item} type="button" className={`mpv1-filter${metric === item ? " is-on" : ""}`} onClick={() => setMetric(item)}>{labels[item]}</button>)}</div>
    <section className="mpv1-card" data-classification="LIVE_API"><div className="mpv1-card-head"><h2 className="mpv1-card-title">{labels[metric]}</h2><span>{status(data?.freshness)}</span></div><MarketTable rows={data?.rows || []} /><p className="mpv1-muted">來源 · 交易所市場 · {data?.server_timestamp || "—"}</p></section>
    <RuntimeRequired title="進階市場排序尚未啟用" />
  </RequireSession>;
}

export function MarketDetailPage() {
  const { symbol = "" } = useParams();
  const marketSymbol = `${symbol.toUpperCase().replace("USDT", "")}USDT`;
  const history = useLiveMarketHistory(marketSymbol, "15m");
  const tickers = useLiveMarketTickers();
  const { has, toggle } = useWatchlist();
  const [derivatives, setDerivatives] = useState<LiveMarketTelemetry | null>(null);
  const [liquidity, setLiquidity] = useState<LiveMarketTelemetry | null>(null);
  useEffect(() => {
    void Promise.all([getMarketDerivatives(marketSymbol), getMarketLiquidity(marketSymbol)])
      .then(([d, l]) => { setDerivatives(d); setLiquidity(l); }).catch(() => { setDerivatives(null); setLiquidity(null); });
  }, [marketSymbol]);
  const ticker = tickers.tickers.find(item => item.symbol === marketSymbol);
  const mark = derivatives?.mark_index as Record<string, unknown> | undefined;
  const funding = derivatives?.funding as Record<string, unknown> | undefined;
  const interest = derivatives?.open_interest as Record<string, unknown> | undefined;
  const orderBook = liquidity?.order_book as Record<string, unknown> | undefined;
  return <RequireSession><div className="mpv1-page-head"><div><h1 className="mpv1-page-title">{symbol.toUpperCase()} / USDT</h1><p className="mpv1-page-sub">來源 · 交易所市場</p></div><button className="mpv1-btn mpv1-btn-outline" onClick={() => void toggle(marketSymbol)}>{has(marketSymbol) ? "移出觀察" : "加入觀察"}</button></div>
    <section className="mpv1-card" data-classification="LIVE_API"><div className="mpv1-pulse-stats"><div className="mpv1-pulse-stat"><div className="lbl">價格</div><div className="val">${fmt(ticker?.price)}</div></div><div className="mpv1-pulse-stat"><div className="lbl">24h</div><div className="val">{fmt(ticker?.change24hPct)}%</div></div><div className="mpv1-pulse-stat"><div className="lbl">24h 高 / 低</div><div className="val">${fmt(ticker?.high24h)} / ${fmt(ticker?.low24h)}</div></div><div className="mpv1-pulse-stat"><div className="lbl">成交額</div><div className="val">${fmt(ticker?.volume24h)}</div></div></div><p className="mpv1-muted">{status(history.state)} · 更新時間 {history.updatedAt || "—"}</p></section>
    <section className="mpv1-card" data-classification="LIVE_API"><h2 className="mpv1-card-title">K 線 / 歷史資料</h2><p className="mpv1-muted">{history.candles.length ? `${history.candles.length} 根 15m K 線 · 最新收盤 ${fmt(history.candles[history.candles.length - 1]?.c)}` : "資料暫時無法取得"}</p></section>
    <div className="mpv1-grid mpv1-grid-2"><section className="mpv1-card" data-classification="LIVE_API"><h2 className="mpv1-card-title">衍生品</h2><ul className="mpv1-list"><li>Mark Price: ${fmt(mark?.mark_price as number)}</li><li>Index Price: ${fmt(mark?.index_price as number)}</li><li>Funding: {fmt(funding?.funding_rate as number)}</li><li>Open Interest: {fmt(interest?.open_interest as number)}</li></ul><p className="mpv1-muted">{status(derivatives?.freshness)}</p></section>
      <section className="mpv1-card" data-classification="LIVE_API"><h2 className="mpv1-card-title">流動性</h2><ul className="mpv1-list"><li>Bid / Ask: ${fmt(orderBook?.best_bid as number)} / ${fmt(orderBook?.best_ask as number)}</li><li>Spread: {fmt(liquidity?.spread as number)} ({fmt(liquidity?.spread_bps as number)} bps)</li><li>Bid depth: {fmt(orderBook?.bid_depth as number)}</li><li>Ask depth: {fmt(orderBook?.ask_depth as number)}</li></ul><p className="mpv1-muted">{status(liquidity?.freshness)}</p></section></div>
    <RuntimeRequired />
  </RequireSession>;
}

export function WatchlistPage() {
  const { symbols, toggle } = useWatchlist(); const market = useLiveMarketTickers();
  const rows = market.tickers.filter(row => symbols.includes(row.symbol)).map(row => ({
    symbol: row.symbol, current_price: row.price, change_24h_percent: row.change24hPct,
    high_24h: row.high24h, low_24h: row.low24h, volume_24h: row.volume24h,
    provider_timestamp: null, server_received_timestamp: null, freshness: row.freshness, data_delayed: row.dataDelayed,
  }));
  return <RequireSession><div className="mpv1-page-head"><div><h1 className="mpv1-page-title">我的觀察</h1><p className="mpv1-page-sub">跨裝置與瀏覽器保存你關注的資產。</p></div></div>
    <section className="mpv1-card" data-classification="LIVE_MEMBER_DB">{rows.length ? <MarketTable rows={rows} /> : <p className="mpv1-empty">尚無觀察項目。請從市場排行加入。</p>}<div>{rows.map(row => <button key={row.symbol} className="mpv1-btn mpv1-btn-danger-ghost" onClick={() => void toggle(row.symbol)}>移出 {row.symbol}</button>)}</div></section>
  </RequireSession>;
}

export function AlertsPage() {
  const [items, setItems] = useState<Array<{ id: string; category: "market" | "watchlist"; symbol: string | null; title: string; body: string; read: boolean; created_at: string }>>([]);
  const refresh = () => void getMemberNotifications().then(response => setItems(response.notifications)).catch(() => setItems([]));
  useEffect(refresh, []);
  return <RequireSession><div className="mpv1-page-head"><div><h1 className="mpv1-page-title">市場提醒</h1><p className="mpv1-page-sub">市場資料提醒與已讀狀態。</p></div></div>
    <section className="mpv1-card" data-classification="LIVE_MEMBER_DB">{items.length ? items.map(item => <article key={item.id} className="mpv1-alert-card"><div><strong>{item.symbol ? `${item.symbol} · ` : ""}{item.title}</strong><p>{item.body}</p><time>{new Date(item.created_at).toLocaleString()}</time></div>{!item.read && <button className="mpv1-btn mpv1-btn-ghost" onClick={() => void markMemberNotificationRead(item.id).then(refresh)}>標示已讀</button>}</article>) : <p className="mpv1-empty">目前沒有市場提醒。NEXUS 訊號與風險提醒即將推出。</p>}</section>
    <RuntimeRequired title="進階訊號與風險提醒尚未啟用" />
  </RequireSession>;
}

// NEXUS-EXPERIENCE-1B.1: the legacy MembershipPage duplicated a non-canonical plan
// catalog in a frontend constant. The canonical membership surface is
// BillingCenterPage (backend billing plans); the public catalog is the canonical
// /api/v1/personal/catalog. This dead, unrouted duplicate was removed.

export function AccountPage() {
  const { logout } = useAuth(); const navigate = useNavigate();
  const [profile, setProfile] = useState<Awaited<ReturnType<typeof getMemberProfile>>["profile"] | null>(null);
  const [preferences, setPreferences] = useState<Record<string, unknown>>({});
  const [message, setMessage] = useState("");
  useEffect(() => { void Promise.all([getMemberProfile(), getNotificationPreferences()]).then(([p, n]) => { setProfile(p.profile); setPreferences(n.preferences); }).catch(() => setMessage("工作階段暫時無法使用")); }, []);
  const save = async () => { if (!profile) return; const result = await updateMemberProfile(profile, profile.version); await updateNotificationPreferences(preferences); setProfile(result.profile); setMessage("已保存"); };
  return <RequireSession><div className="mpv1-page-head"><div><h1 className="mpv1-page-title">帳號設定</h1><p className="mpv1-page-sub">管理你的帳號與登入資訊。</p></div></div>
    <section className="mpv1-card" data-classification="LIVE_MEMBER_DB"><h2 className="mpv1-card-title">個人資料</h2>{profile ? <div className="mpv1-form-grid"><label className="mpv1-field">顯示名稱<input value={profile.display_name} onChange={e => setProfile({ ...profile, display_name: e.target.value })} /></label><label className="mpv1-field">Email<input value={profile.email} disabled /></label><label className="mpv1-field">語言<select value={profile.locale} onChange={e => setProfile({ ...profile, locale: e.target.value })}><option value="zh-TW">繁體中文（台灣）</option><option value="en">English</option></select></label><label className="mpv1-field">時區<select value={profile.timezone} onChange={e => setProfile({ ...profile, timezone: e.target.value })}><option value="Asia/Taipei">Asia/Taipei</option><option value="UTC">UTC</option></select></label></div> : <p>載入中…</p>}<button className="mpv1-btn mpv1-btn-primary" onClick={() => void save()}>保存</button>{message && <p className="mpv1-muted">{message}</p>}</section>
    <section className="mpv1-card" data-classification="LIVE_MEMBER_DB"><h2 className="mpv1-card-title">通知偏好</h2>{["in_app_enabled", "market_alerts_enabled", "email_enabled"].map(key => <label key={key} className="mpv1-toggle-row"><span>{key}</span><input type="checkbox" checked={Boolean(preferences[key])} onChange={e => setPreferences({ ...preferences, [key]: e.target.checked })} /></label>)}</section>
    <section className="mpv1-card" data-classification="NOT_IMPLEMENTED"><h2 className="mpv1-card-title">安全與隱私</h2><p className="mpv1-muted">密碼重設、MFA 管理、資料下載及刪除帳號尚未開放。</p></section><button className="mpv1-btn mpv1-btn-outline" onClick={() => void logout().then(() => navigate("/login"))}>登出</button>
  </RequireSession>;
}
