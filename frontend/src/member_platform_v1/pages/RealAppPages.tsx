import { useEffect, useState, type ReactNode } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useWatchlist } from "../context/WatchlistContext";
import { useLiveMarketHistory } from "../hooks/useLiveMarketHistory";
import { useLiveMarketTickers } from "../hooks/useLiveMarketTickers";
import { TradingViewTopStories } from "../components/TradingViewTopStories";
import {
  getLiveMarketRankings, getMarketDerivatives, getMarketLiquidity, getMemberEntitlements,
  getMemberNotifications, getMemberProfile, getNotificationPreferences, markMemberNotificationRead,
  updateMemberProfile, updateNotificationPreferences, type LiveMarketRanking, type LiveMarketTelemetry,
} from "../services/stagingApi";

function RequireSession({ children }: { children: ReactNode }) {
  const { session } = useAuth();
  return session ? <>{children}</> : <Navigate to="/login" replace />;
}
function fmt(value: number | null | undefined) {
  return typeof value === "number" ? value.toLocaleString(undefined, { maximumFractionDigits: value >= 1 ? 2 : 6 }) : "—";
}
function status(freshness?: string) {
  return freshness === "LIVE" || freshness === "FRESH" ? "LIVE" : freshness === "DATA_DELAYED" || freshness === "STALE" ? "DATA DELAYED" : "UNAVAILABLE";
}
function RuntimeRequired({ title = "進階市場功能尚未啟用" }: { title?: string }) {
  return <section className="mpv1-card" data-classification="RUNTIME_REQUIRED"><h2 className="mpv1-card-title">{title}</h2><p className="mpv1-muted">此功能將在 Runtime 綁定後啟用。目前不顯示評分、訊號、AI 解讀或風險結論。</p></section>;
}

export function DashboardPage() {
  const market = useLiveMarketTickers();
  const [ranking, setRanking] = useState<LiveMarketRanking | null>(null);
  useEffect(() => { void getLiveMarketRankings("gainers").then(setRanking).catch(() => setRanking(null)); }, []);
  return <RequireSession><div className="mpv1-page-head"><div><h1 className="mpv1-page-title">市場總覽</h1><p className="mpv1-page-sub">LIVE_API · Binance USD-M 公開市場資料</p></div></div>
    <section className="mpv1-card" data-classification="LIVE_API"><div className="mpv1-card-head"><h2 className="mpv1-card-title">市場行情</h2><span className="mpv1-muted">{status(market.delayed ? "DATA_DELAYED" : market.tickers.length ? "LIVE" : "UNAVAILABLE")}</span></div>
      <div className="mpv1-ticker-row">{market.tickers.map(t => <Link key={t.symbol} className="mpv1-ticker" to={`/app/market/${t.symbol.replace("USDT", "")}`}><div className="sym">{t.symbol}</div><div className="px">${fmt(t.price)}</div><div className={t.change24hPct >= 0 ? "mpv1-chg-up" : "mpv1-chg-down"}>{t.change24hPct >= 0 ? "+" : ""}{fmt(t.change24hPct)}%</div></Link>)}</div>
      <p className="mpv1-muted">Provider time: {market.updatedAt || "—"} · 由中央 staging API 快取後輪詢</p></section>
    <section className="mpv1-card" data-classification="LIVE_API"><div className="mpv1-card-head"><h2 className="mpv1-card-title">漲幅排行</h2><Link className="mpv1-action-link" to="/app/markets">查看市場排行 →</Link></div>
      <MarketTable rows={ranking?.rows || []} /></section>
    <RuntimeRequired title="進階市場解讀尚未啟用" />
    <TradingViewTopStories title="市場新聞總覽" />
  </RequireSession>;
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
  return <RequireSession><div className="mpv1-page-head"><div><h1 className="mpv1-page-title">市場排行</h1><p className="mpv1-page-sub">僅依 Binance USD-M 公開 24h 統計排序；不是 NEXUS/AI 機會排行。</p></div></div>
    <div className="mpv1-filters">{(Object.keys(labels) as Array<typeof metric>).map(item => <button key={item} type="button" className={`mpv1-filter${metric === item ? " is-on" : ""}`} onClick={() => setMetric(item)}>{labels[item]}</button>)}</div>
    <section className="mpv1-card" data-classification="LIVE_API"><div className="mpv1-card-head"><h2 className="mpv1-card-title">{labels[metric]}</h2><span>{status(data?.freshness)}</span></div><MarketTable rows={data?.rows || []} /><p className="mpv1-muted">Provider: Binance USD-M · {data?.server_timestamp || "—"}</p></section>
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
  return <RequireSession><div className="mpv1-page-head"><div><h1 className="mpv1-page-title">{symbol.toUpperCase()} / USDT</h1><p className="mpv1-page-sub">LIVE_API · Binance USD-M</p></div><button className="mpv1-btn mpv1-btn-outline" onClick={() => void toggle(marketSymbol)}>{has(marketSymbol) ? "移出觀察" : "加入觀察"}</button></div>
    <section className="mpv1-card" data-classification="LIVE_API"><div className="mpv1-pulse-stats"><div className="mpv1-pulse-stat"><div className="lbl">價格</div><div className="val">${fmt(ticker?.price)}</div></div><div className="mpv1-pulse-stat"><div className="lbl">24h</div><div className="val">{fmt(ticker?.change24hPct)}%</div></div><div className="mpv1-pulse-stat"><div className="lbl">24h 高 / 低</div><div className="val">${fmt(ticker?.high24h)} / ${fmt(ticker?.low24h)}</div></div><div className="mpv1-pulse-stat"><div className="lbl">成交額</div><div className="val">${fmt(ticker?.volume24h)}</div></div></div><p className="mpv1-muted">{status(history.state)} · provider timestamp {history.updatedAt || "—"}</p></section>
    <section className="mpv1-card" data-classification="LIVE_API"><h2 className="mpv1-card-title">K 線 / 歷史資料</h2><p className="mpv1-muted">{history.candles.length ? `${history.candles.length} 根 15m K 線 · 最新收盤 ${fmt(history.candles[history.candles.length - 1]?.c)}` : "資料暫時無法取得"}</p></section>
    <div className="mpv1-grid mpv1-grid-2"><section className="mpv1-card" data-classification="LIVE_API"><h2 className="mpv1-card-title">衍生品</h2><ul className="mpv1-list"><li>Mark Price: ${fmt(mark?.mark_price as number)}</li><li>Index Price: ${fmt(mark?.index_price as number)}</li><li>Funding: {fmt(funding?.funding_rate as number)}</li><li>Open Interest: {fmt(interest?.open_interest as number)}</li></ul><p className="mpv1-muted">{status(derivatives?.freshness)}</p></section>
      <section className="mpv1-card" data-classification="LIVE_API"><h2 className="mpv1-card-title">流動性</h2><ul className="mpv1-list"><li>Bid / Ask: ${fmt(orderBook?.best_bid as number)} / ${fmt(orderBook?.best_ask as number)}</li><li>Spread: {fmt(liquidity?.spread as number)} ({fmt(liquidity?.spread_bps as number)} bps)</li><li>Bid depth: {fmt(orderBook?.bid_depth as number)}</li><li>Ask depth: {fmt(orderBook?.ask_depth as number)}</li></ul><p className="mpv1-muted">{status(liquidity?.freshness)}</p></section></div>
    <RuntimeRequired /><TradingViewTopStories title="相關市場新聞" symbol={marketSymbol} />
  </RequireSession>;
}

export function WatchlistPage() {
  const { symbols, toggle } = useWatchlist(); const market = useLiveMarketTickers();
  const rows = market.tickers.filter(row => symbols.includes(row.symbol)).map(row => ({
    symbol: row.symbol, current_price: row.price, change_24h_percent: row.change24hPct,
    high_24h: row.high24h, low_24h: row.low24h, volume_24h: row.volume24h,
    provider_timestamp: null, server_received_timestamp: null, freshness: row.freshness, data_delayed: row.dataDelayed,
  }));
  return <RequireSession><div className="mpv1-page-head"><div><h1 className="mpv1-page-title">我的觀察</h1><p className="mpv1-page-sub">LIVE_MEMBER_DB · 跨登入與瀏覽器工作階段保存</p></div></div>
    <section className="mpv1-card" data-classification="LIVE_MEMBER_DB">{rows.length ? <MarketTable rows={rows} /> : <p className="mpv1-empty">尚無觀察項目。請從市場排行加入。</p>}<div>{rows.map(row => <button key={row.symbol} className="mpv1-btn mpv1-btn-danger-ghost" onClick={() => void toggle(row.symbol)}>移出 {row.symbol}</button>)}</div></section>
  </RequireSession>;
}

export function AlertsPage() {
  const [items, setItems] = useState<Array<{ id: string; category: "market" | "watchlist"; symbol: string | null; title: string; body: string; read: boolean; created_at: string }>>([]);
  const refresh = () => void getMemberNotifications().then(response => setItems(response.notifications)).catch(() => setItems([]));
  useEffect(refresh, []);
  return <RequireSession><div className="mpv1-page-head"><div><h1 className="mpv1-page-title">市場提醒</h1><p className="mpv1-page-sub">LIVE_MEMBER_DB · 市場資料提醒與成員讀取狀態</p></div></div>
    <section className="mpv1-card" data-classification="LIVE_MEMBER_DB">{items.length ? items.map(item => <article key={item.id} className="mpv1-alert-card"><div><strong>{item.symbol ? `${item.symbol} · ` : ""}{item.title}</strong><p>{item.body}</p><time>{new Date(item.created_at).toLocaleString()}</time></div>{!item.read && <button className="mpv1-btn mpv1-btn-ghost" onClick={() => void markMemberNotificationRead(item.id).then(refresh)}>標示已讀</button>}</article>) : <p className="mpv1-empty">目前沒有已持久化的市場提醒。NEXUS 訊號/風險提醒需要 Runtime。</p>}</section>
    <RuntimeRequired title="進階訊號與風險提醒尚未啟用" />
  </RequireSession>;
}

const CATALOG = [{ id: "starter", name: "入門" }, { id: "advanced", name: "進階" }, { id: "professional", name: "專業" }, { id: "enterprise", name: "企業" }];
export function MembershipPage() {
  const [entitlements, setEntitlements] = useState<string[]>([]);
  useEffect(() => { void getMemberEntitlements().then(value => setEntitlements(value.entitlements)).catch(() => setEntitlements([])); }, []);
  return <RequireSession><div className="mpv1-page-head"><div><h1 className="mpv1-page-title">會員方案</h1><p className="mpv1-page-sub">產品型錄為 STATIC_PRODUCT_CONFIG；目前權益為 LIVE_MEMBER_DB。</p></div></div>
    <section className="mpv1-card" data-classification="LIVE_MEMBER_DB"><h2 className="mpv1-card-title">目前會員權益</h2><p>{entitlements.length ? entitlements.join("、") : "沒有可用權益"}</p><p className="mpv1-muted">帳務 / 續訂：NOT_IMPLEMENTED</p></section>
    <div className="mpv1-plan-grid" data-classification="STATIC_PRODUCT_CONFIG">{CATALOG.map(plan => <article className="mpv1-plan" key={plan.id}><h2>{plan.name}</h2><p>產品方案資訊；尚未串接帳務。</p><button className="mpv1-btn mpv1-btn-outline" disabled>帳務未開放</button></article>)}</div>
  </RequireSession>;
}

export function AccountPage() {
  const { logout } = useAuth(); const navigate = useNavigate();
  const [profile, setProfile] = useState<Awaited<ReturnType<typeof getMemberProfile>>["profile"] | null>(null);
  const [preferences, setPreferences] = useState<Record<string, unknown>>({});
  const [message, setMessage] = useState("");
  useEffect(() => { void Promise.all([getMemberProfile(), getNotificationPreferences()]).then(([p, n]) => { setProfile(p.profile); setPreferences(n.preferences); }).catch(() => setMessage("Session unavailable")); }, []);
  const save = async () => { if (!profile) return; const result = await updateMemberProfile(profile, profile.version); await updateNotificationPreferences(preferences); setProfile(result.profile); setMessage("已保存至成員資料庫"); };
  return <RequireSession><div className="mpv1-page-head"><div><h1 className="mpv1-page-title">帳號設定</h1><p className="mpv1-page-sub">LIVE_MEMBER_DB · staging-only identity/session</p></div></div>
    <section className="mpv1-card" data-classification="LIVE_MEMBER_DB"><h2 className="mpv1-card-title">個人資料</h2>{profile ? <div className="mpv1-form-grid"><label className="mpv1-field">顯示名稱<input value={profile.display_name} onChange={e => setProfile({ ...profile, display_name: e.target.value })} /></label><label className="mpv1-field">Email<input value={profile.email} disabled /></label><label className="mpv1-field">語言<select value={profile.locale} onChange={e => setProfile({ ...profile, locale: e.target.value })}><option value="zh-TW">繁體中文（台灣）</option><option value="en">English</option></select></label><label className="mpv1-field">時區<select value={profile.timezone} onChange={e => setProfile({ ...profile, timezone: e.target.value })}><option value="Asia/Taipei">Asia/Taipei</option><option value="UTC">UTC</option></select></label></div> : <p>載入中…</p>}<button className="mpv1-btn mpv1-btn-primary" onClick={() => void save()}>保存</button>{message && <p className="mpv1-muted">{message}</p>}</section>
    <section className="mpv1-card" data-classification="LIVE_MEMBER_DB"><h2 className="mpv1-card-title">通知偏好</h2>{["in_app_enabled", "market_alerts_enabled", "email_enabled"].map(key => <label key={key} className="mpv1-toggle-row"><span>{key}</span><input type="checkbox" checked={Boolean(preferences[key])} onChange={e => setPreferences({ ...preferences, [key]: e.target.checked })} /></label>)}</section>
    <section className="mpv1-card" data-classification="NOT_IMPLEMENTED"><h2 className="mpv1-card-title">安全與隱私</h2><p className="mpv1-muted">密碼重設、MFA 管理、資料下載及刪除帳號尚未開放。</p></section><button className="mpv1-btn mpv1-btn-outline" onClick={() => void logout().then(() => navigate("/login"))}>登出</button>
  </RequireSession>;
}
