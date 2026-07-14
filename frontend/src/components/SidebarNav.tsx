import { NavLink } from "react-router-dom";

type NavItem = { to: string; label: string; short: string };

const OPERATOR_CORE: NavItem[] = [
  { to: "/overview", label: "Overview", short: "Overview" },
  { to: "/evidence", label: "Evidence Center", short: "Evidence" },
  { to: "/risk-evidence", label: "Risk & Safety", short: "Risk" },
  { to: "/paper-lab", label: "Paper Lab", short: "Paper" },
  { to: "/provider-shadow", label: "Provider Shadow", short: "Shadow" },
];

const RESEARCH: NavItem[] = [
  { to: "/fleets", label: "Fleets", short: "Fleets" },
  { to: "/signals", label: "Signals", short: "Signals" },
  { to: "/reflection", label: "Reflection", short: "Reflect" },
];

const FUTURE: NavItem[] = [
  { to: "/assistant", label: "Assistant", short: "Assist" },
  { to: "/academy", label: "Academy", short: "Academy" },
  { to: "/calculator", label: "Calculator", short: "Calc" },
  { to: "/membership", label: "Membership", short: "Member" },
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
 * Private Operator navigation (MVP-13).
 * Explicitly absent (forbidden): /trade, /orders, /arm, /routing-edit
 */
export function SidebarNav() {
  return (
    <nav className="sidebar-nav" aria-label="Primary">
      <NavGroup title="Operator Console" items={OPERATOR_CORE} />
      <NavGroup title="Research" items={RESEARCH} />
      <NavGroup title="Future / Placeholder" items={FUTURE} />
    </nav>
  );
}
