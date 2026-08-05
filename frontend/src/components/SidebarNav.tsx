import { NavLink } from "react-router-dom";
import { useState } from "react";
import { MEMBER_ACCOUNT_SUBNAV, MEMBER_NAV } from "../member/routes";

type NavItem = { to: string; label: string; short: string };

const PRIMARY: NavItem[] = MEMBER_NAV.map((i) => ({ ...i }));

const ACCOUNT: NavItem[] = MEMBER_ACCOUNT_SUBNAV.map((i) => ({
  to: i.to,
  label: i.label,
  short: i.label.split(" ")[0] ?? i.label,
}));

function Links({ items }: { items: NavItem[] }) {
  return (
    <>
      {items.map((l) => (
        <NavLink
          key={l.to}
          to={l.to}
          className={({ isActive }) => (isActive ? "active" : undefined)}
          title={l.label}
          end={l.to === "/account"}
        >
          <span className="nav-text-full">{l.label}</span>
          <span className="nav-text-short">{l.short}</span>
        </NavLink>
      ))}
    </>
  );
}

export function MobileBottomNav() {
  const primaryFive = PRIMARY.slice(0, 4);
  return (
    <nav className="w4-mobile-bottom-nav member-mobile-nav" aria-label="Mobile primary">
      {primaryFive.map((l) => (
        <NavLink key={l.to} to={l.to} className={({ isActive }) => (isActive ? "active" : undefined)}>
          <span>{l.short}</span>
        </NavLink>
      ))}
      <details className="w4-mobile-more">
        <summary>More</summary>
        <div className="w4-mobile-more-panel">
          {PRIMARY.slice(4).map((l) => (
            <NavLink key={l.to} to={l.to}>
              {l.label}
            </NavLink>
          ))}
          {ACCOUNT.map((l) => (
            <NavLink key={l.to} to={l.to}>
              {l.label}
            </NavLink>
          ))}
        </div>
      </details>
    </nav>
  );
}

export function SidebarNav() {
  const [accountOpen, setAccountOpen] = useState(true);
  return (
    <>
      <nav
        className="sidebar-nav sidebar-nav-compact nx-nav-member"
        aria-label="Member Platform"
      >
        <div className="sidebar-brand-block">
          <div className="sidebar-product">NEXUS</div>
          <div className="sidebar-product-sub muted">Member Platform</div>
        </div>
        <div className="nav-group">
          <div className="nav-label">Decision Integrity</div>
          <Links items={PRIMARY} />
        </div>
        <div className="nav-group">
          <button
            type="button"
            className="nav-collapse-btn"
            aria-expanded={accountOpen}
            onClick={() => setAccountOpen((v) => !v)}
          >
            Account {accountOpen ? "▾" : "▸"}
          </button>
          {accountOpen ? <Links items={ACCOUNT} /> : null}
        </div>
      </nav>
      <MobileBottomNav />
    </>
  );
}
