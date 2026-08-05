import { NavLink, Outlet } from "react-router-dom";
import { FounderAuthGate } from "./FounderAuthGate";
import { FOUNDER_DIAGNOSTICS_NAV, FOUNDER_OPERATOR_NAV } from "./types";

/**
 * Separate Founder-only shell — same design tokens, different IA.
 * Intentionally omits member SidebarNav / product primary nav.
 */
export function FounderOperatorShell() {
  return (
    <FounderAuthGate>
      <div className="app-shell nx-founder-operator-shell" data-surface="founder-private">
        <div className="nx-founder-safety" role="status">
          FOUNDER PRIVATE · READ-ONLY OBSERVABILITY · NO EXCHANGE WRITE · NOT MEMBER-ACCESSIBLE
        </div>
        <div className="app-body nx-founder-body">
          <nav className="sidebar-nav nx-founder-nav" aria-label="Founder operator">
            <div className="sidebar-brand-block">
              <div className="sidebar-product">NEXUS</div>
              <div className="sidebar-product-sub muted">Founder Operator</div>
            </div>
            <div className="nav-group">
              <div className="nav-label">私有營運</div>
              <NavLink to="/founder/operator" end className={({ isActive }) => (isActive ? "active" : undefined)}>
                Overview
              </NavLink>
              {FOUNDER_OPERATOR_NAV.map((item) => (
                <a key={item.id} href={`/founder/operator${item.hash}`}>
                  {item.label}
                </a>
              ))}
            </div>
            <div className="nav-group">
              <div className="nav-label">V16 診斷</div>
              <NavLink
                to="/founder/diagnostics"
                end
                className={({ isActive }) => (isActive ? "active" : undefined)}
              >
                Diagnostics
              </NavLink>
              {FOUNDER_DIAGNOSTICS_NAV.map((item) => (
                <a key={item.id} href={`/founder/diagnostics${item.hash}`}>
                  {item.label}
                </a>
              ))}
            </div>
            <div className="nav-group">
              <div className="nav-label">邊界</div>
              <span className="muted sm">member session → 403</span>
              <span className="muted sm">observe/research only</span>
            </div>
          </nav>
          <div className="main-column">
            <main className="main-content">
              <Outlet />
            </main>
          </div>
        </div>
      </div>
    </FounderAuthGate>
  );
}
