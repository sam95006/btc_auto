import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { TIER_LABELS } from "../lib/entitlements";
import { LiveMarketTicker } from "../components/LiveMarketTicker";
import { IconHome } from "../components/MobileLayouts";
import { CommandBar, HeaderControls } from "../components/HeaderControls";
import { useExperience } from "../context/NexusExperience";
import {
  IconBell,
  IconChart,
  IconCrown,
  IconOverview,
  IconStar,
  IconUser,
} from "../components/Icons";

export function MarketingHeader({ active }: { active?: "plans" | "login" | "features" | "faq" }) {
  const { session } = useAuth();
  return (
    <header className="mpv1-mkt-top">
      <Link to="/" className="mpv1-logo">
        NEXUS
      </Link>
      <nav className="mpv1-mkt-links">
        <a href="#features" className={active === "features" ? "is-active" : undefined}>
          產品功能
        </a>
        <Link to="/plans" className={active === "plans" ? "is-active" : undefined}>
          會員方案
        </Link>
        <a href="#faq" className={active === "faq" ? "is-active" : undefined}>
          常見問題
        </a>
        {session ? (
          <Link className="mpv1-btn mpv1-btn-primary mpv1-btn-sm" to="/app">
            進入總覽
          </Link>
        ) : (
          <>
            <Link className="mpv1-link" to="/login" style={{ fontWeight: 600 }}>
              登入
            </Link>
            <Link className="mpv1-btn mpv1-btn-primary mpv1-btn-sm" to="/register">
              開始體驗 →
            </Link>
          </>
        )}
      </nav>
    </header>
  );
}

export function MarketingFooter() {
  return (
    <footer className="mpv1-mkt-footer mpv1-mkt-footer-rich">
      <div className="mpv1-footer-grid">
        <div>
          <div className="mpv1-logo" style={{ color: "#fff", marginBottom: "0.5rem" }}>
            NEXUS
          </div>
          <p>看懂市場，再做決定。加密市場情報與風險解讀平台。</p>
        </div>
        <div>
          <strong>產品</strong>
          <a href="#features">產品功能</a>
          <Link to="/plans">會員方案</Link>
          <Link to="/login">會員登入</Link>
        </div>
        <div>
          <strong>支援</strong>
          <a href="#faq">常見問題</a>
          <a href="#privacy">隱私權政策</a>
          <a href="#terms">服務條款</a>
        </div>
        <div>
          <strong>風險</strong>
          <a href="#risk">風險揭露</a>
          <span className="mpv1-muted" style={{ color: "#94a3b8", fontSize: "0.78rem" }}>
            本平台不下單、不託管資產。
          </span>
        </div>
      </div>
      <div className="mpv1-footer-bottom">
        <span>© 2024 NEXUS. All rights reserved.</span>
        <span>繁體中文</span>
      </div>
    </footer>
  );
}

/** Compact auth footer matching login/register references */
export function AuthFooter() {
  return (
    <footer className="mpv1-mkt-footer">
      <span>© 2024 NEXUS. All rights reserved.</span>
      <div className="mpv1-mkt-footer-links">
        <a href="#privacy">隱私權政策</a>
        <span>|</span>
        <a href="#terms">服務條款</a>
        <span>|</span>
        <a href="#risk">風險揭露</a>
      </div>
    </footer>
  );
}

export function PublicShell() {
  return (
    <div className="mpv1">
      <Outlet />
    </div>
  );
}

const SIDE = [
  { to: "/app", k: "nav_overview", Icon: IconOverview, end: true },
  { to: "/app/markets", k: "nav_markets", Icon: IconChart },
  { to: "/app/intelligence", k: "nav_intel", Icon: IconOverview },
  { to: "/app/watchlist", k: "nav_watchlist", Icon: IconStar },
  { to: "/app/alerts", k: "nav_alerts", Icon: IconBell },
  { to: "/app/membership", k: "nav_plans", Icon: IconCrown },
  { to: "/app/account", k: "nav_account", Icon: IconUser },
];

const MOBILE = [
  { to: "/app", k: "m_home", Icon: IconHome, end: true },
  { to: "/app/markets", k: "m_markets", Icon: IconChart },
  { to: "/app/watchlist", k: "m_watch", Icon: IconStar },
  { to: "/app/alerts", k: "m_alerts", Icon: IconBell },
  { to: "/app/account", k: "m_me", Icon: IconUser },
];

function mobileTitleKey(pathname: string): string {
  if (pathname.startsWith("/app/markets")) return "nav_markets";
  if (pathname.startsWith("/app/watchlist")) return "nav_watchlist";
  if (pathname.startsWith("/app/alerts")) return "nav_alerts";
  if (pathname.startsWith("/app/membership")) return "nav_plans";
  if (pathname.startsWith("/app/account")) return "nav_account";
  if (pathname.startsWith("/app/market/")) return "today";
  return "__nexus__";
}

export function AppShell() {
  const { session, tier } = useAuth();
  const { t } = useExperience();
  const name = session?.displayName || "Nexus";
  const loc = useLocation();
  const hideMobileChrome = loc.pathname.startsWith("/app/market/");
  const mobileTitle = (p: string) => {
    const key = mobileTitleKey(p);
    return key === "__nexus__" ? "NEXUS" : t(key);
  };

  return (
    <div className="mpv1 mpv1-app-shell">
      <aside className="mpv1-side">
        <Link to="/app" className="mpv1-logo">
          NEXUS
        </Link>
        <nav className="mpv1-side-nav" aria-label="主要導覽">
          {SIDE.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `mpv1-side-link${isActive ? " is-active" : ""}`}
            >
              <item.Icon className="nav-ico" size={17} />
              {t(item.k)}
            </NavLink>
          ))}
        </nav>
        <div className="mpv1-side-promo">
          <div style={{ display: "flex", alignItems: "center", gap: "0.35rem", color: "#fbbf24" }}>
            <IconCrown size={14} />
          </div>
          <h4>{t("promo_title")}</h4>
          <p>{t("promo_body")}</p>
          <Link className="mpv1-btn mpv1-btn-primary mpv1-btn-sm mpv1-btn-block" to="/app/membership">
            {t("promo_cta")}
          </Link>
        </div>
      </aside>

      <div className="mpv1-app-main">
        <div className="mpv1-topbar mpv1-d-only">
          <CommandBar />
          <div className="mpv1-top-actions">
            <HeaderControls />
            <Link className="mpv1-icon-btn" to="/app/alerts" title="提醒" aria-label="提醒">
              <IconBell size={16} />
            </Link>
            <Link className="mpv1-plan-pill" to="/app/membership">
              <IconCrown size={14} /> {TIER_LABELS[tier]}
            </Link>
            <span className="mpv1-user-chip" aria-label={`${name} 的帳號`}>
              <span className="mpv1-avatar">{name.slice(0, 1).toUpperCase()}</span>
              {name}
            </span>
          </div>
        </div>
        <LiveMarketTicker />

        {!hideMobileChrome ? (
          <div className="mpv1-m-topbar mpv1-m-only">
            <div className="mpv1-m-topbar-title">{mobileTitle(loc.pathname)}</div>
            <div className="mpv1-m-topbar-actions">
              <Link className="mpv1-m-iconbtn" to="/app/alerts" aria-label="提醒">
                <IconBell size={18} />
                <span className="mpv1-badge-count">3</span>
              </Link>
              <Link to="/app/account" className="mpv1-m-avatar" aria-label="帳號">
                {name.slice(0, 1).toUpperCase()}
              </Link>
            </div>
          </div>
        ) : null}

        <Outlet />
      </div>

      <nav className="mpv1-mobile-nav" aria-label="行動導覽">
        {MOBILE.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) => (isActive ? "is-active" : undefined)}
          >
            <item.Icon size={20} className="mpv1-m-nav-ico" />
            <span>{t(item.k)}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
