import { NavLink } from "react-router-dom";

type NavItem = { to: string; label: string; short: string };

const OPERATOR_CORE: NavItem[] = [
  { to: "/overview", label: "Overview", short: "Overview" },
  { to: "/overview#market-command", label: "Market Command", short: "Market" },
  { to: "/evidence", label: "Evidence", short: "Evidence" },
  { to: "/risk-evidence", label: "Risk", short: "Risk" },
];

const RESEARCH: NavItem[] = [
  { to: "/paper-lab", label: "Validation Lab", short: "Lab" },
  { to: "/provider-shadow", label: "Provider Intelligence", short: "Provider" },
  { to: "/evidence#doc-summaries", label: "Reports", short: "Reports" },
  { to: "/evidence#artifact-4-18-p2h-ops", label: "Runbooks", short: "Runbooks" },
];

const FUTURE: NavItem[] = [
  { to: "/academy", label: "Academy", short: "Academy" },
  { to: "/membership", label: "Membership", short: "Member" },
  { to: "/assistant", label: "Public SaaS", short: "SaaS" },
];

function NavGroup({ title, items }: { title: string; items: NavItem[] }) {
  return (
    <div className="nav-group">
      <div className="nav-label">{title}</div>
      {items.map((l) => (
        <NavLink
          key={l.to}
          to={l.to}
          className={({ isActive }) => (isActive ? "active" : undefined)}
          title={l.label}
        >
          <span className="nav-text-full">{l.label}</span>
          <span className="nav-text-short">{l.short}</span>
        </NavLink>
      ))}
    </div>
  );
}

/**
 * Productized Private Operator nav (MVP-20).
 * Forbidden routes absent: /trade, /orders, /arm, /routing-edit
 */
export function SidebarNav() {
  return (
    <nav className="sidebar-nav" aria-label="Primary">
      <div className="sidebar-brand-block">
        <div className="sidebar-product">Operator Console</div>
        <div className="sidebar-product-sub muted">Research · READ ONLY</div>
      </div>
      <NavGroup title="Operator Console" items={OPERATOR_CORE} />
      <NavGroup title="Research" items={RESEARCH} />
      <NavGroup title="Future" items={FUTURE} />
    </nav>
  );
}
