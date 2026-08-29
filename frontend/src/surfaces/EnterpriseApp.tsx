/**
 * ENTERPRISE surface (Surface C) — Enterprise Intelligence Workspace shell.
 *
 * PLATFORM-1 builds only the foundation/shell as an INDEPENDENT site — not an
 * `/enterprise/*` route inside the personal app. It does NOT reuse the personal
 * Billing center, does NOT import the Founder operator, contains NO AI-agent
 * product, and NO private trading controls. Organizations / seats / teams / SSO
 * / shared research begin in ENTERPRISE-1.
 */
import { Link, Navigate, Route, Routes } from "react-router-dom";

function WorkspaceShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="ent-shell" style={{ display: "flex", minHeight: "100vh" }}>
      <aside style={{ width: "13rem", padding: "1rem", borderRight: "1px solid rgba(128,128,128,.3)" }}>
        <Link to="/" style={{ fontWeight: 700 }}>NEXUS Enterprise</Link>
        <nav aria-label="enterprise" style={{ display: "grid", gap: "0.4rem", marginTop: "1rem" }}>
          <Link to="/workspace">工作區</Link>
          <Link to="/organization">組織（即將開放）</Link>
          <Link to="/research">共享研究（即將開放）</Link>
          <Link to="/alerts">警示中心（即將開放）</Link>
          <Link to="/audit">稽核（即將開放）</Link>
        </nav>
      </aside>
      <main style={{ flex: 1, padding: "1.5rem" }}>
        <h1>{title}</h1>
        {children}
      </main>
    </div>
  );
}

function ComingSoon({ label }: { label: string }) {
  return <WorkspaceShell title={label}><p>{label} 功能將於 ENTERPRISE-1 開始建置。</p></WorkspaceShell>;
}

export default function EnterpriseApp() {
  return (
    <Routes>
      <Route
        path="/"
        element={
          <WorkspaceShell title="企業 Intelligence Workspace">
            <p>企業工作區基礎（PLATFORM-1 shell）。組織 / 團隊 / 席位 / 共享研究尚未實作。</p>
            <p data-testid="enterprise-authenticated-placeholder">（未來需企業組織授權層）</p>
          </WorkspaceShell>
        }
      />
      <Route path="/workspace" element={<WorkspaceShell title="工作區"><p>工作區 placeholder。</p></WorkspaceShell>} />
      <Route path="/organization" element={<ComingSoon label="組織管理" />} />
      <Route path="/research" element={<ComingSoon label="共享研究" />} />
      <Route path="/alerts" element={<ComingSoon label="警示中心" />} />
      <Route path="/audit" element={<ComingSoon label="稽核" />} />
      <Route path="/*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
