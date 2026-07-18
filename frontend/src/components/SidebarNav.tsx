import { NavLink } from "react-router-dom";
import { useState } from "react";

type NavItem = { to: string; label: string; short: string };

const EXPLORE: NavItem[] = [
  { to: "/overview", label: "市場總覽", short: "總覽" },
  { to: "/scanner", label: "市場掃描", short: "掃描" },
  { to: "/crypto/sectors", label: "幣種版塊", short: "版塊" },
  { to: "/anomalies", label: "市場異動", short: "異動" },
];

const TOOLS: NavItem[] = [
  { to: "/watchlist", label: "關注清單", short: "關注" },
];

const RANKINGS: NavItem[] = [
  { to: "/crypto/oi", label: "OI 排行", short: "OI" },
  { to: "/crypto/funding", label: "Funding 排行", short: "Funding" },
  { to: "/crypto/price-oi", label: "Price／OI 結構", short: "結構" },
];

const EQUITIES: NavItem[] = [
  { to: "/equities/tokenized", label: "美股代幣", short: "代幣" },
  { to: "/equities/analysis", label: "美股分析", short: "美股" },
];

const RESEARCH: NavItem[] = [
  { to: "/ai-reviews", label: "AI 檢討中心", short: "AI" },
  { to: "/anomaly-outcomes", label: "Outcome Research", short: "結果" },
  { to: "/evidence", label: "Evidence", short: "證據" },
  { to: "/provider-shadow", label: "Provider Validation", short: "Provider" },
  { to: "/risk-evidence", label: "Risk Evidence", short: "風險" },
  { to: "/evidence#doc-summaries", label: "Research Safety", short: "安全" },
  { to: "/membership", label: "System Status", short: "系統" },
];

function Links({ items }: { items: NavItem[] }) {
  return (
    <>
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
    </>
  );
}

/**
 * Phase 4–5 nav — explore / tools / rankings / equities + collapsed research (AI 檢討中心).
 * Forbidden: /trade, /orders, /arm, /routing-edit
 */
export function SidebarNav() {
  const [researchOpen, setResearchOpen] = useState(false);
  return (
    <nav className="sidebar-nav sidebar-nav-compact nx-nav-p2 nx-nav-p3 nx-nav-p4" aria-label="Primary">
      <div className="sidebar-brand-block">
        <div className="sidebar-product">NEXUS</div>
        <div className="sidebar-product-sub muted">市場情報</div>
      </div>
      <div className="nav-group">
        <div className="nav-label">探索市場</div>
        <Links items={EXPLORE} />
      </div>
      <div className="nav-group">
        <div className="nav-label">我的工具</div>
        <Links items={TOOLS} />
      </div>
      <div className="nav-group">
        <div className="nav-label">市場排行</div>
        <Links items={RANKINGS} />
      </div>
      <div className="nav-group">
        <div className="nav-label">美股專區</div>
        <Links items={EQUITIES} />
      </div>
      <div className="nav-group nav-research">
        <button
          type="button"
          className="nav-collapse-btn"
          aria-expanded={researchOpen}
          onClick={() => setResearchOpen((v) => !v)}
        >
          研究分析 {researchOpen ? "▾" : "▸"}
        </button>
        {researchOpen ? <Links items={RESEARCH} /> : null}
      </div>
    </nav>
  );
}
