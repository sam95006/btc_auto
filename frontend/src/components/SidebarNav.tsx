import { NavLink } from "react-router-dom";

type NavItem = { to: string; label: string; short: string; icon: string };

const PRODUCT: NavItem[] = [
  { to: "/overview", label: "市場總覽", short: "總覽", icon: "▣" },
  { to: "/scanner", label: "市場掃描", short: "掃描", icon: "◎" },
  { to: "/watchlist", label: "關注清單", short: "關注", icon: "★" },
];

const CRYPTO: NavItem[] = [
  { to: "/crypto/sectors", label: "幣種版塊", short: "版塊", icon: "▦" },
  { to: "/crypto/oi", label: "OI 排行", short: "OI", icon: "↕" },
  { to: "/crypto/funding", label: "Funding 排行", short: "Funding", icon: "%" },
  { to: "/crypto/price-oi", label: "Price／OI 結構", short: "結構", icon: "◇" },
  { to: "/anomalies", label: "市場異動", short: "異動", icon: "◉" },
];

const EQUITIES: NavItem[] = [
  { to: "/equities/tokenized", label: "美股代幣", short: "代幣", icon: "▣" },
  { to: "/equities/analysis", label: "美股分析", short: "美股", icon: "▤" },
];

const RESEARCH: NavItem[] = [
  { to: "/anomaly-outcomes", label: "Outcome Research", short: "結果", icon: "◌" },
  { to: "/evidence", label: "Evidence", short: "證據", icon: "▤" },
  { to: "/provider-shadow", label: "Provider Validation", short: "Provider", icon: "◇" },
  { to: "/risk-evidence", label: "Risk Evidence", short: "風險", icon: "◈" },
];

const SYSTEM: NavItem[] = [
  { to: "/evidence#doc-summaries", label: "Research Safety", short: "安全", icon: "☰" },
  { to: "/membership", label: "System Status", short: "系統", icon: "⚙" },
];

function Group({ label, items }: { label: string; items: NavItem[] }) {
  return (
    <div className="nav-group">
      <div className="nav-label">{label}</div>
      {items.map((l) => (
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
  );
}

/**
 * Phase 3 nav — product / crypto / equities / research / system.
 * Forbidden routes absent: /trade, /orders, /arm, /routing-edit
 */
export function SidebarNav() {
  return (
    <nav className="sidebar-nav sidebar-nav-compact nx-nav-p2 nx-nav-p3" aria-label="Primary">
      <div className="sidebar-brand-block">
        <div className="sidebar-product">NEXUS</div>
        <div className="sidebar-product-sub muted">市場情報 · 研究</div>
      </div>
      <Group label="主要產品" items={PRODUCT} />
      <Group label="加密貨幣" items={CRYPTO} />
      <Group label="美股專區" items={EQUITIES} />
      <Group label="研究工具" items={RESEARCH} />
      <Group label="系統資訊" items={SYSTEM} />
    </nav>
  );
}
