import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import { AdviceChip } from "./Chips";
import {
  IconBell,
  IconChart,
  IconCrown,
  IconLock,
  IconOverview,
  IconSearch,
  IconShield,
  IconUser,
} from "./Icons";
import { SparkChart } from "./SparkChart";
import { BiasGauge, ScoreRing } from "./Viz";
import { TIER_LABELS } from "../lib/entitlements";
import type { AlertDto, DashboardDto, MarketRankingRowDto, MembershipTier, PlanDto } from "../types/dto";

function fmtPrice(n: number) {
  if (n >= 1000) return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (n >= 1) return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return n.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function coinLetter(symbol: string) {
  return symbol.replace("USDT", "").slice(0, 1);
}

export function IconHome(p: { size?: number; className?: string }) {
  return (
    <svg
      width={p.size ?? 20}
      height={p.size ?? 20}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      className={p.className}
    >
      <path
        d="M4 10.5L12 4l8 6.5V20a1 1 0 01-1 1h-5v-6H10v6H5a1 1 0 01-1-1v-9.5z"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function IconChevron(p: { size?: number; className?: string }) {
  return (
    <svg
      width={p.size ?? 16}
      height={p.size ?? 16}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      className={p.className}
    >
      <path d="M9 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IconFilter(p: { size?: number; className?: string }) {
  return (
    <svg
      width={p.size ?? 18}
      height={p.size ?? 18}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      className={p.className}
    >
      <path d="M4 6h16M7 12h10M10 18h4" strokeLinecap="round" />
    </svg>
  );
}

export function IconBack(p: { size?: number; className?: string }) {
  return (
    <svg
      width={p.size ?? 20}
      height={p.size ?? 20}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      className={p.className}
    >
      <path d="M15 6l-6 6 6 6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IconShare(p: { size?: number; className?: string }) {
  return (
    <svg
      width={p.size ?? 18}
      height={p.size ?? 18}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      className={p.className}
    >
      <circle cx="18" cy="5" r="2.5" />
      <circle cx="6" cy="12" r="2.5" />
      <circle cx="18" cy="19" r="2.5" />
      <path d="M8.4 13.2l7.2 4.1M15.6 6.7l-7.2 4.1" />
    </svg>
  );
}

export function MobilePageTitle({ title, right }: { title: string; right?: ReactNode }) {
  return (
    <div className="mpv1-m-pagehead">
      <h1>{title}</h1>
      {right ? <div className="mpv1-m-pagehead-actions">{right}</div> : null}
    </div>
  );
}

export function MobileChipRow({ children }: { children: ReactNode }) {
  return <div className="mpv1-m-chips">{children}</div>;
}

export function MobileDashboard({ data }: { data: DashboardDto }) {
  const best = data.topAssets.find((r) => r.advice === "watch_closely") || data.topAssets[0];
  const top3 = data.topAssets.slice(0, 3);
  const watchChanges = (data.watchlistPreview.length ? data.watchlistPreview : data.topAssets).slice(0, 3);
  const alerts = data.riskAlerts.slice(0, 3);

  return (
    <div className="mpv1-m-stack">
      <article className="mpv1-m-card mpv1-m-card-hero">
        <div className="mpv1-m-kicker">今天市場</div>
        <div className="mpv1-m-hero-row">
          <div>
            <div className="mpv1-m-hero-val bull">{data.overview.biasLabel} ↑</div>
            <div className="mpv1-m-hero-sub">風險：{data.overview.riskLabel}</div>
          </div>
          <div className="mpv1-m-gauge-wrap">
            <BiasGauge position={0.72} />
          </div>
        </div>
        <p className="mpv1-m-one-line">{data.overview.summary}</p>
      </article>

      <article className="mpv1-m-card">
        <div className="mpv1-m-kicker">最佳機會</div>
        <div className="mpv1-m-best">
          <div>
            <strong>{best?.symbol.replace("USDT", "")}</strong>
            <AdviceChip advice={best?.advice || "observing"} label={best?.adviceLabel || "觀察中"} />
            <p>{best?.beginnerReason}</p>
          </div>
          <ScoreRing score={best?.score ?? null} size={52} />
        </div>
        <Link className="mpv1-m-cta" to={`/app/market/${best?.symbol.replace("USDT", "") || "ETH"}`}>
          查看分析 →
        </Link>
      </article>

      <article className="mpv1-m-card">
        <div className="mpv1-m-kicker">現在怎麼做</div>
        <ol className="mpv1-m-actions">
          <li>優先觀察 ETH / SOL</li>
          <li>不要追已大漲標的</li>
          <li>高風險幣先等待</li>
        </ol>
      </article>

      <article className="mpv1-m-card">
        <div className="mpv1-m-card-head">
          <strong>市場脈動</strong>
          <div className="mpv1-m-mini-tabs">
            <span className="is-on">24H</span>
            <span>7D</span>
            <span>30D</span>
          </div>
        </div>
        <div className="mpv1-m-ticker-pills">
          {data.pulse.tickers.map((t) => (
            <span key={t.symbol} className="mpv1-m-pill">
              {t.symbol} {t.change24hPct >= 0 ? "+" : ""}
              {t.change24hPct.toFixed(1)}%
            </span>
          ))}
        </div>
        <div className="mpv1-m-metric">
          <span>總市值</span>
          <strong>
            {data.pulse.marketCapLabel} <em className="up">+2.35%</em>
          </strong>
        </div>
        <div className="mpv1-m-spark">
          <SparkChart values={data.pulse.trend} tone="accent" />
        </div>
      </article>

      <article className="mpv1-m-card">
        <div className="mpv1-m-kicker">今日用白話文看市場</div>
        <ul className="mpv1-m-plain">
          {[
            { ico: "↗", t: "今天市場正在發生什麼", b: data.plainLanguage.happening },
            { ico: "★", t: "為什麼市場轉強", b: data.plainLanguage.whyStrong },
            { ico: "!", t: "今天先不要做什麼", b: data.plainLanguage.avoid },
            { ico: "⚠", t: "最大風險", b: data.plainLanguage.topRisk },
          ].map((x) => (
            <li key={x.t}>
              <span className="ico">{x.ico}</span>
              <div>
                <strong>{x.t}</strong>
                <p>{x.b}</p>
              </div>
              <IconChevron />
            </li>
          ))}
        </ul>
      </article>

      <article className="mpv1-m-card">
        <div className="mpv1-m-card-head">
          <strong>市場機會 Top 3</strong>
        </div>
        <ul className="mpv1-m-list">
          {top3.map((r, i) => {
            const base = r.symbol.replace("USDT", "");
            return (
              <li key={r.symbol}>
                <Link to={`/app/market/${base}`} className="mpv1-m-row">
                  <span className="rank">{i + 1}</span>
                  <span className="coin">{coinLetter(r.symbol)}</span>
                  <div className="meta">
                    <strong>{base}</strong>
                    <span>${fmtPrice(r.price)}</span>
                  </div>
                  <div className="right">
                    <span className={r.change24hPct >= 0 ? "up" : "down"}>
                      {r.change24hPct >= 0 ? "+" : ""}
                      {r.change24hPct.toFixed(2)}%
                    </span>
                    <ScoreRing score={r.score} size={32} />
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
        <Link className="mpv1-m-cta" to="/app/markets">
          查看完整市場排行 →
        </Link>
      </article>

      <article className="mpv1-m-card">
        <div className="mpv1-m-kicker">觀察清單變化</div>
        <ul className="mpv1-m-change">
          {watchChanges.map((r) => (
            <li key={r.symbol}>
              <strong>{r.symbol.replace("USDT", "")}</strong>
              <span className="chg">{r.lastChangeLabel || "狀態維持"}</span>
              <em>{r.beginnerReason}</em>
            </li>
          ))}
        </ul>
      </article>

      <article className="mpv1-m-card">
        <div className="mpv1-m-card-head">
          <strong>最新提醒</strong>
          <Link to="/app/alerts">全部</Link>
        </div>
        <ul className="mpv1-m-alerts">
          {alerts.map((a) => (
            <li key={a.id} className={`tone-${a.severity}`}>
              <IconBell size={14} />
              <div>
                <strong>{a.title}</strong>
                <p>{a.body}</p>
              </div>
              <time>{a.timeLabel}</time>
            </li>
          ))}
        </ul>
      </article>
    </div>
  );
}

export function MobileMarketsList({
  rows,
  filter,
  onFilter,
}: {
  rows: MarketRankingRowDto[];
  filter: string;
  onFilter: (id: string) => void;
}) {
  const chips = [
    ["all", "全部"],
    ["bullish", "偏多"],
    ["bearish", "偏空"],
    ["watch", "可留意"],
    ["observing", "觀察中"],
    ["high_risk", "高風險"],
  ] as const;

  return (
    <div className="mpv1-m-stack">
      <MobilePageTitle
        title="市場排行"
        right={
          <>
            <button type="button" className="mpv1-m-iconbtn" aria-label="搜尋">
              <IconSearch size={18} />
            </button>
            <button type="button" className="mpv1-m-iconbtn" aria-label="排序篩選">
              <IconFilter size={18} />
            </button>
          </>
        }
      />
      <MobileChipRow>
        {chips.map(([id, label]) => (
          <button key={id} type="button" className={filter === id ? "is-on" : undefined} onClick={() => onFilter(id)}>
            {label}
          </button>
        ))}
      </MobileChipRow>
      <ul className="mpv1-m-market-list">
        {rows.slice(0, 12).map((r, i) => {
          const base = r.symbol.replace("USDT", "");
          return (
            <li key={r.symbol}>
              <Link to={`/app/market/${base}`} className="mpv1-m-market-row">
                <span className={`rank${i < 3 ? ` m${i + 1}` : ""}`}>{i + 1}</span>
                <span className="coin">{coinLetter(r.symbol)}</span>
                <div className="main">
                  <div className="top">
                    <strong>{base}</strong>
                    <span className="name">{r.name}</span>
                  </div>
                  <div className="reason">{r.beginnerReason}</div>
                </div>
                <div className="stats">
                  <strong>${fmtPrice(r.price)}</strong>
                  <span className={r.change24hPct >= 0 ? "up" : "down"}>
                    {r.change24hPct >= 0 ? "+" : ""}
                    {r.change24hPct.toFixed(2)}%
                  </span>
                  <AdviceChip advice={r.advice} label={r.adviceLabel} />
                  <ScoreRing score={r.score} size={34} />
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function MobileWatchlist({
  rows,
  counts,
  filter,
  onFilter,
}: {
  rows: MarketRankingRowDto[];
  counts: { all: number; watch: number; observing: number; wait: number; changed: number };
  filter: string;
  onFilter: (id: string) => void;
}) {
  return (
    <div className="mpv1-m-stack">
      <MobilePageTitle
        title="我的觀察"
        right={
          <>
            <button type="button" className="mpv1-m-iconbtn" aria-label="搜尋">
              <IconSearch size={18} />
            </button>
            <button type="button" className="mpv1-m-iconbtn" aria-label="更多">
              ···
            </button>
          </>
        }
      />
      <MobileChipRow>
        {(
          [
            ["all", `全部 ${counts.all}`],
            ["watch", `可留意 ${counts.watch}`],
            ["observing", `觀察中 ${counts.observing}`],
            ["wait", `先等等 ${counts.wait}`],
            ["changed", `已變化 ${counts.changed}`],
          ] as const
        ).map(([id, label]) => (
          <button key={id} type="button" className={filter === id ? "is-on" : undefined} onClick={() => onFilter(id)}>
            {label}
          </button>
        ))}
      </MobileChipRow>
      <p className="mpv1-m-hint">從上次查看後，你的觀察標的發生了什麼？</p>
      <ul className="mpv1-m-watch-list">
        {rows.slice(0, 10).map((r) => {
          const base = r.symbol.replace("USDT", "");
          const improved = /上調|進入可留意/.test(r.lastChangeLabel || "");
          const worse = /轉弱|風險上調/.test(r.lastChangeLabel || "");
          return (
            <li key={r.symbol}>
              <Link to={`/app/market/${base}`} className="mpv1-m-watch-row">
                <span className="coin">{coinLetter(r.symbol)}</span>
                <div className="main">
                  <strong>{base}</strong>
                  <span>
                    ${fmtPrice(r.price)}{" "}
                    <em className={r.change24hPct >= 0 ? "up" : "down"}>
                      {r.change24hPct >= 0 ? "+" : ""}
                      {r.change24hPct.toFixed(2)}%
                    </em>
                  </span>
                  <span className="delta">
                    {improved ? "↑ " : worse ? "↓ " : "— "}
                    {r.lastChangeLabel || "狀態維持"}
                  </span>
                </div>
                <AdviceChip advice={r.advice} label={r.adviceLabel} />
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function MobileAlerts({
  alerts,
  filter,
  onFilter,
}: {
  alerts: AlertDto[];
  filter: string;
  onFilter: (id: string) => void;
}) {
  const chips = [
    ["all", "全部"],
    ["priority", "高優先"],
    ["market", "市場變化"],
    ["risk", "風險"],
    ["watchlist", "觀察清單"],
  ] as const;

  return (
    <div className="mpv1-m-stack">
      <MobilePageTitle title="風險提醒" />
      <MobileChipRow>
        {chips.map(([id, label]) => (
          <button key={id} type="button" className={filter === id ? "is-on" : undefined} onClick={() => onFilter(id)}>
            {label}
          </button>
        ))}
      </MobileChipRow>
      <ul className="mpv1-m-alert-cards">
        {alerts.map((a) => (
          <li key={a.id} className={`mpv1-m-alert-card tone-${a.severity}`}>
            <div className="ico">
              <IconBell size={16} />
            </div>
            <div className="body">
              <div className="top">
                <strong>{a.title}</strong>
                <time>{a.timeLabel}</time>
              </div>
              <p>{a.body}</p>
            </div>
            <IconChevron />
          </li>
        ))}
      </ul>
    </div>
  );
}

export function MobileMembership({ plans }: { plans: PlanDto[] }) {
  return (
    <div className="mpv1-m-stack">
      <MobilePageTitle title="會員方案" />
      <p className="mpv1-m-hint">同一 UI，依等級解鎖更深證據。</p>
      <div className="mpv1-m-plans">
        {plans.map((p) => {
          const hot = p.id === "advanced";
          return (
            <article key={p.id} className={`mpv1-m-plan${hot ? " is-hot" : ""}`}>
              {hot ? <span className="badge">推薦</span> : null}
              <h3>{p.name}</h3>
              <div className="price">{p.priceLabel}</div>
              <p className="who">{p.audience}</p>
              <ul>
                {p.features.slice(0, 4).map((f) => (
                  <li key={f}>✓ {f}</li>
                ))}
              </ul>
              <button type="button" className={`mpv1-btn ${hot ? "mpv1-btn-primary" : "mpv1-btn-outline"} mpv1-btn-block`}>
                {p.id === "enterprise" ? "聯絡我們" : "查看詳情"}
              </button>
            </article>
          );
        })}
      </div>
      <button type="button" className="mpv1-m-compare">
        方案比較 ▾
      </button>
    </div>
  );
}

export function MobileAccount({
  name,
  email,
  tier,
  onLogout,
}: {
  name: string;
  email: string;
  tier: MembershipTier;
  onLogout: () => void;
}) {
  const groups: Array<{
    title: string;
    rows: Array<{ label: string; value?: string; Icon: typeof IconUser; to?: string }>;
  }> = [
    {
      title: "帳戶與安全",
      rows: [
        { label: "密碼與登入", Icon: IconLock },
        { label: "Passkey / Face ID", value: "即將開放", Icon: IconShield },
        { label: "兩步驟驗證", value: "已啟用", Icon: IconShield },
        { label: "信任裝置", Icon: IconUser },
      ],
    },
    {
      title: "通知",
      rows: [{ label: "通知偏好", Icon: IconBell }],
    },
    {
      title: "會員方案",
      rows: [{ label: "目前方案", value: TIER_LABELS[tier], Icon: IconCrown, to: "/app/membership" }],
    },
    {
      title: "語言與時區",
      rows: [{ label: "介面語言", value: "繁體中文", Icon: IconOverview }],
    },
    {
      title: "資料與隱私",
      rows: [{ label: "隱私權政策", Icon: IconLock }],
    },
    {
      title: "關於 NEXUS",
      rows: [{ label: "關於與版本", value: "Mobile V1", Icon: IconChart }],
    },
  ];

  return (
    <div className="mpv1-m-stack">
      <div className="mpv1-m-profile">
        <div className="av">{name.slice(0, 1).toUpperCase()}</div>
        <div>
          <strong>{name}</strong>
          <span>{email}</span>
          <em>{TIER_LABELS[tier]}</em>
        </div>
      </div>
      {groups.map((g) => (
        <section key={g.title} className="mpv1-m-settings-group">
          <h2>{g.title}</h2>
          <ul>
            {g.rows.map((r) => {
              const inner = (
                <>
                  <r.Icon size={16} />
                  <span className="lbl">{r.label}</span>
                  {r.value ? <span className="val">{r.value}</span> : null}
                  <IconChevron />
                </>
              );
              return (
                <li key={r.label}>
                  {r.to ? (
                    <Link to={r.to} className="mpv1-m-settings-row">
                      {inner}
                    </Link>
                  ) : (
                    <button type="button" className="mpv1-m-settings-row">
                      {inner}
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      ))}
      {import.meta.env.VITE_MEMBER_TIER_PREVIEW === "true" ? (
        <section className="mpv1-m-settings-group">
          <h2>Developer Preview</h2>
          <p className="mpv1-m-hint">桌面 Preview 切換請用桌面版；手機僅保留此入口提示。</p>
        </section>
      ) : null}
      <button type="button" className="mpv1-btn mpv1-btn-ghost mpv1-btn-block" onClick={onLogout}>
        登出
      </button>
    </div>
  );
}
