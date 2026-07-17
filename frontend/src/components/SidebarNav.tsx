import { NavLink } from "react-router-dom";

type NavItem = { to: string; label: string; short: string; icon: string };

const PRIMARY: NavItem[] = [
  { to: "/overview", label: "市場總覽", short: "總覽", icon: "▣" },
  { to: "/scanner", label: "全市場掃描", short: "掃描", icon: "◎" },
  { to: "/anomalies", label: "異動雷達", short: "異動", icon: "◉" },
  { to: "/anomaly-outcomes", label: "結果研究", short: "結果", icon: "◌" },
  { to: "/evidence", label: "證據中心", short: "證據", icon: "▤" },
  { to: "/risk-evidence", label: "風險中心", short: "風險", icon: "◈" },
  { to: "/provider-shadow", label: "Provider 驗證", short: "Provider", icon: "◇" },
  { to: "/paper-lab", label: "驗證實驗室", short: "Lab", icon: "◎" },
  { to: "/evidence#doc-summaries", label: "報告", short: "報告", icon: "☰" },
  { to: "/evidence#artifact-4-18-p2h-ops", label: "Runbooks", short: "Runbooks", icon: "⇉" },
];

const FUTURE: NavItem[] = [
  { to: "/academy", label: "Academy", short: "Academy", icon: "◇" },
  { to: "/membership", label: "Settings / Future", short: "Future", icon: "⚙" },
];

/**
 * Compact product sidebar (MVP-22).
 * Forbidden routes absent: /trade, /orders, /arm, /routing-edit
 */
export function SidebarNav() {
  return (
    <nav className="sidebar-nav sidebar-nav-compact" aria-label="Primary">
      <div className="sidebar-brand-block">
        <div className="sidebar-product">NEXUS</div>
        <div className="sidebar-product-sub muted">READ ONLY</div>
      </div>
      <div className="nav-group">
        {PRIMARY.map((l) => (
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
        <div className="nav-label">More</div>
        {FUTURE.map((l) => (
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
