import { useEffect, useState, type ReactNode } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { AdviceChip, BiasChip, RiskChip, ScorePill } from "../components/Chips";
import { LockedPanel } from "../components/LockedPanel";
import { MarketRow } from "../components/MarketRow";
import { SparkChart } from "../components/SparkChart";
import { TierSwitcher } from "../components/TierSwitcher";
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

export function DashboardPage() {
  const { tier } = useAuth();
  const { symbols } = useWatchlist();
  const [data, setData] = useState<DashboardDto | null>(null);

  useEffect(() => {
    void marketApi.getDashboard(tier, symbols).then(setData);
  }, [tier, symbols]);

  if (!data) return <p className="mpv1-muted">載入總覽…</p>;

  return (
    <RequireSession>
      <div className="mpv1-page-head">
        <div>
          <h1 className="mpv1-page-title">總覽</h1>
          <p className="mpv1-page-sub">先看結論：今天市場怎麼了、哪些幣先看、要不要急。</p>
        </div>
        <TierSwitcher />
      </div>

      <div className="mpv1-grid mpv1-grid-4" style={{ marginBottom: "1rem" }}>
        <article className="mpv1-card">
          <p className="mpv1-brand-sub">市場方向</p>
          <h2 style={{ marginTop: "0.5rem" }}>{data.overview.biasLabel}</h2>
        </article>
        <article className="mpv1-card">
          <p className="mpv1-brand-sub">建議動作</p>
          <h2 style={{ marginTop: "0.5rem" }}>{data.overview.adviceLabel}</h2>
        </article>
        <article className="mpv1-card">
          <p className="mpv1-brand-sub">市場風險</p>
          <div style={{ marginTop: "0.65rem" }}>
            <RiskChip risk={data.overview.risk} label={data.overview.riskLabel} />
          </div>
        </article>
        <article className="mpv1-card">
          <p className="mpv1-brand-sub">會員狀態</p>
          <h2 style={{ marginTop: "0.5rem" }}>{data.membership.tierName}</h2>
          <p className="mpv1-muted" style={{ marginTop: "0.35rem", fontSize: "0.85rem" }}>
            {data.membership.renewLabel}
          </p>
        </article>
      </div>

      <div className="mpv1-grid mpv1-grid-2">
        <article className="mpv1-card">
          <h2 className="mpv1-card-title">值得先看的幣</h2>
          <p className="mpv1-muted" style={{ marginBottom: "0.5rem" }}>
            {data.overview.summary}
          </p>
          {data.topAssets.map((r) => (
            <MarketRow key={r.symbol} row={r} />
          ))}
          <Link className="mpv1-btn mpv1-btn-ghost" style={{ marginTop: "0.75rem" }} to="/app/markets">
            看完整排行
          </Link>
        </article>

        <div className="mpv1-grid">
          <article className="mpv1-card">
            <h2 className="mpv1-card-title">今日重點</h2>
            <ul className="mpv1-list">
              {data.highlights.map((h) => (
                <li key={h.id}>
                  <strong>{h.title}</strong>
                  <div className="mpv1-muted">{h.body}</div>
                </li>
              ))}
            </ul>
          </article>
          <article className="mpv1-card">
            <h2 className="mpv1-card-title">風險提醒</h2>
            {canAccess(tier, "risk_alerts") ? (
              data.riskAlerts.length ? (
                <ul className="mpv1-list">
                  {data.riskAlerts.map((a) => (
                    <li key={a.id}>
                      <strong>{a.title}</strong>
                      <div className="mpv1-muted">{a.body}</div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mpv1-empty">目前沒有未讀提醒</p>
              )
            ) : (
              <LockedPanel featureLabel="風險提醒" requiredTier={minTierFor("risk_alerts")} />
            )}
          </article>
          <article className="mpv1-card">
            <h2 className="mpv1-card-title">觀察清單摘要</h2>
            {canAccess(tier, "watchlist") ? (
              data.watchlistPreview.length ? (
                data.watchlistPreview.map((r) => <MarketRow key={r.symbol} row={r} />)
              ) : (
                <p className="mpv1-empty">尚未加入觀察</p>
              )
            ) : (
              <LockedPanel featureLabel="觀察清單" requiredTier={minTierFor("watchlist")} />
            )}
          </article>
        </div>
      </div>
    </RequireSession>
  );
}

export function MarketsPage() {
  const { tier } = useAuth();
  const [rows, setRows] = useState<MarketRankingRowDto[]>([]);
  useEffect(() => {
    void marketApi.getRanking(tier).then(setRows);
  }, [tier]);

  return (
    <RequireSession>
      <div className="mpv1-page-head">
        <div>
          <h1 className="mpv1-page-title">市場排行</h1>
          <p className="mpv1-page-sub">用白話狀態與分數，快速找出值得先看的幣。</p>
        </div>
        <TierSwitcher />
      </div>
      <article className="mpv1-card">
        {!canAccess(tier, "full_ranking") ? (
          <p className="mpv1-muted" style={{ marginBottom: "0.75rem" }}>
            入門版顯示精選排行。切換到進階版可預覽完整名單。
          </p>
        ) : null}
        {rows.map((r) => (
          <MarketRow key={r.symbol} row={r} />
        ))}
      </article>
    </RequireSession>
  );
}

export function MarketDetailPage() {
  const { symbol = "" } = useParams();
  const { tier } = useAuth();
  const { has, toggle } = useWatchlist();
  const [asset, setAsset] = useState<AssetDetailDto | null>(null);
  const [tab, setTab] = useState("市場概況");

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

  const tabs = ["市場概況", "市場證據", "衍生品", "流動性", "訊號紀錄"];

  return (
    <RequireSession>
      <div className="mpv1-page-head">
        <div>
          <h1 className="mpv1-page-title">
            {asset.symbol.replace("USDT", "")} / USDT
          </h1>
          <p className="mpv1-page-sub">{asset.name}</p>
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
          <TierSwitcher />
        </div>
      </div>

      <div className="mpv1-grid mpv1-grid-2">
        <article className="mpv1-card">
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
            <BiasChip bias={asset.bias} label={asset.biasLabel} />
            <AdviceChip label={asset.adviceLabel} />
            <ScorePill score={asset.score} />
          </div>
          <p style={{ marginTop: "1rem", fontSize: "1.6rem", fontWeight: 700 }}>
            ${asset.price.toLocaleString()}
            <span
              className={asset.change24hPct >= 0 ? "mpv1-chg-up" : "mpv1-chg-down"}
              style={{ marginLeft: "0.65rem", fontSize: "1rem" }}
            >
              {asset.change24hPct >= 0 ? "+" : ""}
              {asset.change24hPct.toFixed(2)}%
            </span>
          </p>
          <div style={{ marginTop: "1rem" }}>
            <SparkChart values={asset.sparkline} />
          </div>
        </article>

        <article className="mpv1-card">
          <h2 className="mpv1-card-title">為什麼值得看</h2>
          {canAccess(tier, "why_reasons") ? (
            <ul className="mpv1-list">
              {asset.whyInteresting.map((x) => (
                <li key={x}>{x}</li>
              ))}
            </ul>
          ) : (
            <LockedPanel featureLabel="為什麼值得看" requiredTier={minTierFor("why_reasons")} />
          )}
          <h2 className="mpv1-card-title" style={{ marginTop: "1.25rem" }}>
            有什麼風險
          </h2>
          <ul className="mpv1-list">
            {asset.risks.map((x) => (
              <li key={x}>{x}</li>
            ))}
          </ul>
          <h2 className="mpv1-card-title" style={{ marginTop: "1.25rem" }}>
            什麼情況代表判斷失效
          </h2>
          <ul className="mpv1-list">
            {asset.invalidation.map((x) => (
              <li key={x}>{x}</li>
            ))}
          </ul>
        </article>
      </div>

      <div className="mpv1-tabs" role="tablist">
        {tabs.map((t) => (
          <button
            key={t}
            type="button"
            className={`mpv1-tab${tab === t ? " is-on" : ""}`}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>

      <article className="mpv1-card">
        {tab === "市場概況" && (
          <p className="mpv1-muted">
            目前方向：{asset.biasLabel}。狀態：{asset.adviceLabel}。這是市場情報頁，沒有買賣按鈕。
          </p>
        )}
        {tab === "市場證據" &&
          (canAccess(tier, "evidence") ? (
            <div className="mpv1-grid mpv1-grid-2">
              <div>
                <h3 className="mpv1-card-title">支持</h3>
                <ul className="mpv1-list">
                  {(asset.evidence?.supporting || []).map((x) => (
                    <li key={x}>{x}</li>
                  ))}
                </ul>
              </div>
              <div>
                <h3 className="mpv1-card-title">需留意的反證</h3>
                <ul className="mpv1-list">
                  {(asset.evidence?.contradicting || []).map((x) => (
                    <li key={x}>{x}</li>
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
            <ul className="mpv1-list">
              {(asset.signalHistory || []).map((s) => (
                <li key={s.id}>
                  <strong>{s.timeLabel}</strong> — {s.summary}
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
          <p className="mpv1-page-sub">把值得持續追蹤的幣放在這裡。</p>
        </div>
        <TierSwitcher />
      </div>
      {!canAccess(tier, "watchlist") ? (
        <LockedPanel featureLabel="觀察清單" requiredTier={minTierFor("watchlist")} />
      ) : (
        <article className="mpv1-card">
          {rows.length === 0 ? (
            <p className="mpv1-empty">
              尚無觀察項目。到 <Link to="/app/markets">市場排行</Link> 加入。
            </p>
          ) : (
            rows.map((r) => (
              <div key={r.symbol}>
                <MarketRow row={r} />
                <button type="button" className="mpv1-btn mpv1-btn-ghost" onClick={() => toggle(r.symbol)}>
                  移出
                </button>
              </div>
            ))
          )}
        </article>
      )}
    </RequireSession>
  );
}

export function AlertsPage() {
  const { tier } = useAuth();
  const [alerts, setAlerts] = useState<AlertDto[]>([]);

  async function refresh() {
    setAlerts(await alertApi.list());
  }

  useEffect(() => {
    void refresh();
  }, []);

  return (
    <RequireSession>
      <div className="mpv1-page-head">
        <div>
          <h1 className="mpv1-page-title">風險提醒</h1>
          <p className="mpv1-page-sub">用白話提醒你現在該多留意什麼。</p>
        </div>
        <TierSwitcher />
      </div>
      {!canAccess(tier, "risk_alerts") ? (
        <LockedPanel featureLabel="風險提醒" requiredTier={minTierFor("risk_alerts")} />
      ) : (
        <article className="mpv1-card">
          <ul className="mpv1-list">
            {alerts.map((a) => (
              <li key={a.id} style={{ opacity: a.read ? 0.65 : 1 }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", flexWrap: "wrap" }}>
                  <strong>
                    {a.title}
                    {a.symbol ? ` · ${a.symbol.replace("USDT", "")}` : ""}
                  </strong>
                  <span className="mpv1-muted">{a.timeLabel}</span>
                </div>
                <div className="mpv1-muted">{a.body}</div>
                {!a.read ? (
                  <button
                    type="button"
                    className="mpv1-btn mpv1-btn-ghost"
                    style={{ marginTop: "0.5rem" }}
                    onClick={() => void alertApi.markRead(a.id).then(refresh)}
                  >
                    標示已讀
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        </article>
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
            目前預覽：{TIER_LABELS[tier]}。用上方切換器可快速看各方案解鎖深度。
          </p>
        </div>
        <TierSwitcher />
      </div>
      <div className="mpv1-plan-grid">
        {plans.map((p) => (
          <article key={p.id} className={`mpv1-card mpv1-plan${p.id === tier ? " is-hot" : ""}`}>
            <h2 className="mpv1-card-title">{p.name}</h2>
            <p className="mpv1-muted">{p.tagline}</p>
            <p style={{ marginTop: "0.75rem", fontWeight: 700 }}>{p.priceLabel}</p>
            <ul>
              {p.features.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
            {p.id === "enterprise" && canAccess(tier, "team") ? (
              <p className="mpv1-muted" style={{ marginTop: "0.75rem" }}>
                企業預覽：團隊席位、API 概念、資料匯出入口（佔位）。
              </p>
            ) : null}
          </article>
        ))}
      </div>
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
          <p className="mpv1-page-sub">本機模擬帳號，無真實金流與身分驗證。</p>
        </div>
        <TierSwitcher />
      </div>
      <article className="mpv1-card" style={{ maxWidth: 520 }}>
        <ul className="mpv1-list">
          <li>顯示名稱：{session?.displayName}</li>
          <li>Email：{session?.email}</li>
          <li>帳號類型：{session?.accountType === "enterprise" ? "企業" : "個人"}</li>
          <li>方案預覽：{TIER_LABELS[tier]}</li>
        </ul>
        <button type="button" className="mpv1-btn mpv1-btn-ghost" style={{ marginTop: "1rem" }} onClick={logout}>
          登出
        </button>
      </article>
    </RequireSession>
  );
}
