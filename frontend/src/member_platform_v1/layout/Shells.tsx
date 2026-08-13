import { Link, NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { TIER_LABELS } from "../lib/entitlements";
import { TierSwitcher } from "../components/TierSwitcher";
import {
  IconBell,
  IconChart,
  IconCrown,
  IconOverview,
  IconSearch,
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
          <Link className="mpv1-btn mpv1-btn-outline mpv1-btn-sm" to="/login">
            登入
          </Link>
        )}
      </nav>
    </header>
  );
}

export function MarketingFooter() {
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
  { to: "/app", label: "總覽", Icon: IconOverview, end: true },
  { to: "/app/markets", label: "市場排行", Icon: IconChart },
  { to: "/app/watchlist", label: "我的觀察", Icon: IconStar },
  { to: "/app/alerts", label: "風險提醒", Icon: IconBell },
  { to: "/app/membership", label: "會員方案", Icon: IconCrown },
  { to: "/app/account", label: "帳號設定", Icon: IconUser },
];

const MOBILE = [
  { to: "/app", label: "首頁", end: true },
  { to: "/app/markets", label: "市場" },
  { to: "/app/watchlist", label: "觀察" },
  { to: "/app/alerts", label: "提醒" },
  { to: "/app/account", label: "我的" },
];

export function AppShell() {
  const { session, tier } = useAuth();
  const name = session?.displayName || "Nexus 用戶";

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
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="mpv1-side-promo">
          <h4>解鎖更深市場情報</h4>
          <p>專業版提供完整證據、即時風險與更深歷史回溯。</p>
          <Link className="mpv1-btn mpv1-btn-primary mpv1-btn-sm mpv1-btn-block" to="/app/membership">
            瞭解方案
          </Link>
        </div>
      </aside>

      <div className="mpv1-app-main">
        <div className="mpv1-topbar">
          <div className="mpv1-topbar-left">
            <div className="mpv1-market-status" title="市場狀態（模擬）">
              <span className="dot" />
              市場偏多 · 風險中等
            </div>
            <label className="mpv1-search">
              <IconSearch size={15} />
              <input placeholder="搜尋幣種，例如 ETH" aria-label="搜尋幣種" />
            </label>
          </div>
          <div className="mpv1-top-actions">
            <TierSwitcher />
            <Link className="mpv1-plan-pill" to="/app/membership">
              <IconCrown size={14} /> {TIER_LABELS[tier]}
            </Link>
            <Link className="mpv1-icon-btn" to="/app/alerts" title="提醒" aria-label="提醒">
              <IconBell size={16} />
              <i className="mpv1-dot" />
            </Link>
            <Link to="/app/account" className="mpv1-user-chip">
              <span className="mpv1-avatar">{name.slice(0, 1).toUpperCase()}</span>
              {name}
            </Link>
          </div>
        </div>
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
            {item.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
