import { Link, NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export function PublicShell() {
  const { session } = useAuth();
  return (
    <div className="mpv1 mpv1-public-shell">
      <header className="mpv1-public-top">
        <Link to="/" className="mpv1-brand">
          <span className="mpv1-brand-mark">NEXUS</span>
          <span className="mpv1-brand-sub">市場情報</span>
        </Link>
        <nav className="mpv1-public-nav">
          <Link className="mpv1-btn mpv1-btn-ghost" to="/plans">
            方案
          </Link>
          {session ? (
            <Link className="mpv1-btn mpv1-btn-primary" to="/app">
              進入總覽
            </Link>
          ) : (
            <>
              <Link className="mpv1-btn mpv1-btn-ghost" to="/login">
                登入
              </Link>
              <Link className="mpv1-btn mpv1-btn-primary" to="/register">
                註冊
              </Link>
            </>
          )}
        </nav>
      </header>
      <main className="mpv1-public-main">
        <Outlet />
      </main>
    </div>
  );
}

const SIDE = [
  { to: "/app", label: "總覽", end: true },
  { to: "/app/markets", label: "市場排行" },
  { to: "/app/watchlist", label: "我的觀察" },
  { to: "/app/alerts", label: "風險提醒" },
  { to: "/app/membership", label: "會員方案" },
  { to: "/app/account", label: "帳號設定" },
];

const MOBILE = [
  { to: "/app", label: "首頁", end: true },
  { to: "/app/markets", label: "市場" },
  { to: "/app/watchlist", label: "觀察" },
  { to: "/app/alerts", label: "提醒" },
  { to: "/app/account", label: "我的" },
];

export function AppShell() {
  return (
    <div className="mpv1 mpv1-app-shell">
      <aside className="mpv1-side">
        <Link to="/app" className="mpv1-brand">
          <span className="mpv1-brand-mark">NEXUS</span>
          <span className="mpv1-brand-sub">會員</span>
        </Link>
        <nav className="mpv1-side-nav" aria-label="主要導覽">
          {SIDE.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `mpv1-side-link${isActive ? " is-active" : ""}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="mpv1-side-footer">
          <p className="mpv1-dev-banner">本機 Mock 資料 · 非投資建議 · 無下單功能</p>
          <Link className="mpv1-btn mpv1-btn-ghost" to="/">
            回到介紹
          </Link>
        </div>
      </aside>
      <div className="mpv1-app-main">
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
