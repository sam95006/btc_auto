import { NavLink } from "react-router-dom";

type NavItem = { to: string; label: string; short: string; icon: string };

const PRIMARY: NavItem[] = [
  { to: "/overview", label: "Market Dashboard", short: "Market", icon: "▣" },
  { to: "/anomalies", label: "Anomaly Radar", short: "Anomalies", icon: "◉" },
  { to: "/anomaly-outcomes", label: "Outcome Research", short: "Outcomes", icon: "◌" },
  { to: "/evidence", label: "Evidence Center", short: "Evidence", icon: "▤" },
  { to: "/risk-evidence", label: "Risk Center", short: "Risk", icon: "◈" },
  { to: "/provider-shadow", label: "Provider Intel", short: "Provider", icon: "◇" },
  { to: "/paper-lab", label: "Validation Lab", short: "Lab", icon: "◎" },
  { to: "/evidence#doc-summaries", label: "Reports", short: "Reports", icon: "☰" },
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
