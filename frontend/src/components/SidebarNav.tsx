import { NavLink } from "react-router-dom";
import { useState } from "react";

type NavItem = { to: string; label: string; short: string };

/** Product 7 IA — Traditional Chinese primary navigation */
const PRIMARY: NavItem[] = [
  { to: "/overview", label: "總覽", short: "總覽" },
  { to: "/scanner", label: "市場", short: "市場" },
  { to: "/opportunities", label: "機會", short: "機會" },
  { to: "/anomalies", label: "異常", short: "異常" },
  { to: "/intelligence", label: "市場情報", short: "情報" },
  { to: "/trade-plan", label: "交易計畫", short: "計畫" },
  { to: "/performance", label: "績效", short: "績效" },
  { to: "/learning", label: "學習", short: "學習" },
];

const MARKET_DEPTH: NavItem[] = [
  { to: "/crypto/sectors", label: "幣種版塊", short: "版塊" },
  { to: "/crypto/oi", label: "OI 排行", short: "OI" },
  { to: "/crypto/funding", label: "Funding 排行", short: "Funding" },
  { to: "/watchlist", label: "關注清單", short: "關注" },
];

const RESEARCH: NavItem[] = [
  { to: "/paper-lab", label: "PAPER Lab", short: "PAPER" },
  { to: "/global-shadow", label: "全球 Shadow", short: "Shadow" },
  { to: "/ai-reviews", label: "AI 檢討中心", short: "AI" },
  { to: "/anomaly-outcomes", label: "Outcome Research", short: "結果" },
  { to: "/evidence", label: "Evidence", short: "證據" },
  { to: "/membership", label: "Membership", short: "會員" },
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

export function SidebarNav() {
  const [researchOpen, setResearchOpen] = useState(false);
  return (
    <nav className="sidebar-nav sidebar-nav-compact nx-nav-p2 nx-nav-p3 nx-nav-p4 nx-nav-p65" aria-label="Primary">
      <div className="sidebar-brand-block">
        <div className="sidebar-product">NEXUS</div>
        <div className="sidebar-product-sub muted">Market Intelligence</div>
      </div>
      <div className="nav-group">
        <div className="nav-label">產品</div>
        <Links items={PRIMARY} />
      </div>
      <div className="nav-group">
        <div className="nav-label">市場深度</div>
        <Links items={MARKET_DEPTH} />
      </div>
      <div className="nav-group nav-research">
        <button
          type="button"
          className="nav-collapse-btn"
          aria-expanded={researchOpen}
          onClick={() => setResearchOpen((v) => !v)}
        >
          研究 / 營運 {researchOpen ? "▾" : "▸"}
        </button>
        {researchOpen ? <Links items={RESEARCH} /> : null}
      </div>
    </nav>
  );
}
