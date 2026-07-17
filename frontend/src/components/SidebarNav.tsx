import { NavLink } from "react-router-dom";

type NavItem = { to: string; label: string; short: string; icon: string };

const PRODUCT: NavItem[] = [
  { to: "/overview", label: "市場總覽", short: "總覽", icon: "▣" },
  { to: "/scanner", label: "市場掃描", short: "掃描", icon: "◎" },
  { to: "/anomalies", label: "市場異動", short: "異動", icon: "◉" },
  { to: "/watchlist", label: "關注清單", short: "關注", icon: "★" },
];

const RESEARCH: NavItem[] = [
  { to: "/anomaly-outcomes", label: "Outcome Research", short: "結果", icon: "◌" },
  { to: "/evidence", label: "Evidence", short: "證據", icon: "▤" },
  { to: "/provider-shadow", label: "Provider Validation", short: "Provider", icon: "◇" },
  { to: "/risk-evidence", label: "Risk Evidence", short: "風險", icon: "◈" },
];

const SYSTEM: NavItem[] = [
  { to: "/evidence#doc-summaries", label: "Research Safety", short: "安全", icon: "☰" },
  { to: "/membership", label: "System / Settings", short: "系統", icon: "⚙" },
];

/**
 * Phase 2 nav — product primary, research secondary, system tertiary.
 * Forbidden routes absent: /trade, /orders, /arm, /routing-edit
 */
export function SidebarNav() {
  return (
    <nav className="sidebar-nav sidebar-nav-compact nx-nav-p2" aria-label="Primary">
      <div className="sidebar-brand-block">
        <div className="sidebar-product">NEXUS</div>
        <div className="sidebar-product-sub muted">市場情報 · 研究</div>
      </div>
      <div className="nav-group">
        <div className="nav-label">主要產品</div>
        {PRODUCT.map((l) => (
          <NavLink
            key={l.to}
            to={l.to}
            className={({ isActive }) => (isActive ? "active" : undefined)}
            title={l.label}
          >
            <span className="nav-ico" aria-hidden>
              {l.icon}
            </span>
            <span className="nav-text-full">{l.label}</span>
            <span className="nav-text-short">{l.short}</span>
          </NavLink>
        ))}
      </div>
      <div className="nav-group">
        <div className="nav-label">研究工具</div>
        {RESEARCH.map((l) => (
          <NavLink
            key={l.to}
            to={l.to}
            className={({ isActive }) => (isActive ? "active" : undefined)}
            title={l.label}
          >
            <span className="nav-ico" aria-hidden>
              {l.icon}
            </span>
            <span className="nav-text-full">{l.label}</span>
            <span className="nav-text-short">{l.short}</span>
          </NavLink>
        ))}
      </div>
      <div className="nav-group">
        <div className="nav-label">系統資訊</div>
        {SYSTEM.map((l) => (
          <NavLink key={l.to} to={l.to} title={l.label}>
            <span className="nav-ico" aria-hidden>
              {l.icon}
            </span>
            <span className="nav-text-full">{l.label}</span>
            <span className="nav-text-short">{l.short}</span>
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
