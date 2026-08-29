/**
 * CORPORATE surface (Surface A) — public company / product marketing site.
 *
 * Built only into the corporate build. It never imports the authenticated
 * Billing center, the Founder operator, or private trading controls. Copy is
 * neutral placeholder — no final branding/domain is hardcoded.
 */
import { Link, Navigate, Route, Routes } from "react-router-dom";

function Shell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="corp-shell" style={{ maxWidth: "60rem", margin: "0 auto", padding: "1.5rem" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "1rem" }}>
        <Link to="/" style={{ fontWeight: 700, fontSize: "1.15rem" }}>
          NEXUS
        </Link>
        <nav aria-label="corporate" style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
          <Link to="/products">產品</Link>
          <Link to="/personal">個人版</Link>
          <Link to="/enterprise">企業版</Link>
          <Link to="/security">安全</Link>
          <Link to="/about">關於</Link>
          <Link to="/contact">聯絡</Link>
          {/* Login entry points into the personal / enterprise apps. */}
          <a href="/personal.html" data-testid="login-personal">個人登入</a>
          <a href="/enterprise.html" data-testid="login-enterprise">企業登入</a>
        </nav>
      </header>
      <main>
        <h1>{title}</h1>
        {children}
      </main>
      <footer style={{ marginTop: "2rem", opacity: 0.7, fontSize: "0.85rem" }}>
        READ-ONLY · research platform · not investment advice
      </footer>
    </div>
  );
}

function HomePage() {
  return (
    <Shell title="市場情報平台">
      <p>公開的公司與產品介紹網站。個人與企業產品皆由此進入。</p>
      <ul>
        <li><Link to="/personal" data-testid="link-personal">個人 Market Intelligence</Link></li>
        <li><Link to="/enterprise" data-testid="link-enterprise">企業 Intelligence Workspace</Link></li>
      </ul>
    </Shell>
  );
}

export default function CorporateApp() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/products" element={<Shell title="產品"><p>個人版與企業版產品總覽（placeholder）。</p></Shell>} />
      <Route path="/personal" element={<Shell title="個人版"><p>個人 Market Intelligence SaaS 介紹。<a href="/personal.html">前往個人 App</a></p></Shell>} />
      <Route path="/enterprise" element={<Shell title="企業版"><p>企業 Intelligence Workspace 介紹。<a href="/enterprise.html">前往企業 App</a></p></Shell>} />
      <Route path="/security" element={<Shell title="安全與信任"><p>安全性與資料保護（placeholder）。</p></Shell>} />
      <Route path="/about" element={<Shell title="關於"><p>公司介紹（placeholder）。</p></Shell>} />
      <Route path="/contact" element={<Shell title="聯絡"><p>聯絡方式即將開放。</p></Shell>} />
      <Route path="/*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
