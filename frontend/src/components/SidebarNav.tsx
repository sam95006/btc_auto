import { NavLink } from "react-router-dom";
import { useState } from "react";

type NavItem = { to: string; label: string; short: string };

/** Wave 4 Product IA — 7 primary nav items (Traditional Chinese) */
const PRIMARY: NavItem[] = [
  { to: "/overview", label: "總覽", short: "總覽" },
  { to: "/universe", label: "全市場", short: "市場" },
  { to: "/opportunities", label: "機會", short: "機會" },
  { to: "/alerts", label: "警報", short: "警報" },
  { to: "/portfolio", label: "投資組合", short: "組合" },
  { to: "/learning", label: "學習", short: "學習" },
  { to: "/evidence", label: "證據", short: "證據" },
];

const MARKET_DEPTH: NavItem[] = [
  { to: "/crypto/sectors", label: "幣種版塊", short: "版塊" },
  { to: "/crypto/oi", label: "OI 排行", short: "OI" },
  { to: "/crypto/funding", label: "Funding 排行", short: "Funding" },
  { to: "/watchlist", label: "關注清單", short: "關注" },
  { to: "/intelligence", label: "市場情報", short: "情報" },
  { to: "/trade-plan", label: "交易計畫", short: "計畫" },
  { to: "/performance", label: "績效", short: "績效" },
];

const RESEARCH: NavItem[] = [
  { to: "/anomalies", label: "異常中心", short: "異常" },
  { to: "/signals", label: "訊號", short: "訊號" },
  { to: "/scanner", label: "Scanner（舊）", short: "Scan" },
  { to: "/fleets", label: "Fleets（已棄用）", short: "Fleet" },
  { to: "/paper-lab", label: "PAPER Lab", short: "PAPER" },
  { to: "/global-shadow", label: "全球 Shadow", short: "Shadow" },
  { to: "/ai-learning-lab", label: "AI Learning Lab", short: "Lab" },
  { to: "/ai-reviews", label: "AI 檢討中心", short: "AI" },
  { to: "/anomaly-outcomes", label: "Outcome Research", short: "結果" },
  { to: "/founder/runtime", label: "Founder Runtime", short: "Founder" },
  { to: "/membership", label: "Membership", short: "會員" },
  { to: "/assistant", label: "AI 助理頁", short: "助理" },
  { to: "/academy", label: "Academy", short: "學院" },
  { to: "/calculator", label: "Calculator", short: "計算" },
  { to: "/reflection", label: "Reflection", short: "反思" },
  { to: "/provider-shadow", label: "Provider Shadow", short: "Prov" },
  { to: "/risk-evidence", label: "Risk Evidence", short: "Risk" },
  { to: "/equities", label: "Equities", short: "EQ" },
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

export function MobileBottomNav() {
  return (
    <nav className="w4-mobile-bottom-nav" aria-label="Mobile primary">
      {PRIMARY.map((l) => (
        <NavLink key={l.to} to={l.to} className={({ isActive }) => (isActive ? "active" : undefined)}>
          <span>{l.short}</span>
        </NavLink>
      ))}
    </nav>
  );
}

export function SidebarNav() {
  const [expertOpen, setExpertOpen] = useState(false);
  return (
    <>
      <nav className="sidebar-nav sidebar-nav-compact nx-nav-p2 nx-nav-p3 nx-nav-p4 nx-nav-p65 nx-nav-w4" aria-label="Primary">
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
            aria-expanded={expertOpen}
            onClick={() => setExpertOpen((v) => !v)}
          >
            進階 / 研究 {expertOpen ? "▾" : "▸"}
          </button>
          {expertOpen ? <Links items={RESEARCH} /> : null}
        </div>
      </nav>
      <MobileBottomNav />
    </>
  );
}
