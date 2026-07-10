import { NavLink } from "react-router-dom";

const LINKS: { to: string; label: string }[] = [
  { to: "/overview", label: "Overview" },
  { to: "/fleets", label: "Fleets" },
  { to: "/signals", label: "Signals" },
  { to: "/risk-evidence", label: "Risk & Evidence" },
  { to: "/evidence", label: "Evidence Vault" },
  { to: "/reflection", label: "Reflection" },
  { to: "/provider-shadow", label: "Provider Shadow" },
  { to: "/paper-lab", label: "Paper Lab" },
  { to: "/assistant", label: "Assistant" },
  { to: "/academy", label: "Academy" },
  { to: "/calculator", label: "Calculator" },
  { to: "/membership", label: "Membership" },
];

export function SidebarNav() {
  return (
    <nav className="sidebar-nav" aria-label="Primary">
      <div className="nav-label">Research</div>
      {LINKS.map((l) => (
        <NavLink
          key={l.to}
          to={l.to}
          className={({ isActive }) => (isActive ? "active" : undefined)}
        >
          {l.label}
        </NavLink>
      ))}
    </nav>
  );
}
