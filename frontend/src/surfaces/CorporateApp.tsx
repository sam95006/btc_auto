/**
 * CORPORATE surface (Surface A) — public company website + admin console.
 *
 * Backend-driven: all business/market content comes from the Corporate API
 * (CMS + safe public market). The frontend renders and animates; it never
 * fabricates business or market values. It never imports the Founder operator,
 * private trading controls, Bybit clients, or the authenticated Personal/
 * Enterprise apps.
 */
import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Chrome } from "../corporate/components/Chrome";
import { MarketProvider } from "../corporate/context/MarketContext";
import { ThemeProvider } from "../corporate/context/ThemeContext";
import { LocaleProvider } from "../corporate/i18n";
import { Home } from "../corporate/pages/Home";
import { ContentPage } from "../corporate/pages/ContentPage";
import { Contact } from "../corporate/pages/Contact";
import "../styles/corporate.css";
import "../styles/corporate-cinematic.css";
import "../styles/corporate-flagship.css";
import "../styles/corporate-theme.css";
import "../styles/corporate-simple.css";

// Admin surfaces are code-split — public visitors never download the console/editors.
const AdminConsole = lazy(() => import("../corporate/admin/AdminConsole").then((m) => ({ default: m.AdminConsole })));
const AdminLogin = lazy(() => import("../corporate/admin/AdminLogin").then((m) => ({ default: m.AdminLogin })));
const OwnerSetup = lazy(() => import("../corporate/admin/OwnerSetup").then((m) => ({ default: m.OwnerSetup })));

function AdminFallback() {
  return <div className="corp-admin-shell"><p className="corp-state corp-state-loading">載入中… / loading…</p></div>;
}

function Site() {
  return (
    <MarketProvider>
      <Chrome>
        <Routes>
          <Route path="/" element={<Home />} />
        <Route path="/products" element={<ContentPage slug="products" />} />
        <Route path="/personal" element={<ContentPage slug="products/personal" />} />
        <Route path="/enterprise" element={<ContentPage slug="products/enterprise" />} />
        <Route path="/pricing" element={<ContentPage slug="pricing" />} />
        <Route path="/security" element={<ContentPage slug="security" />} />
          <Route path="/about" element={<ContentPage slug="about" />} />
          <Route path="/contact" element={<Contact />} />
          <Route path="/*" element={<Navigate to="/" replace />} />
        </Routes>
      </Chrome>
    </MarketProvider>
  );
}

export default function CorporateApp() {
  return (
    <ThemeProvider>
      <LocaleProvider>
        <Suspense fallback={<AdminFallback />}>
          <Routes>
            {/* Owner/admin surfaces are outside the marketing chrome (code-split). */}
            <Route path="/owner/setup" element={<OwnerSetup />} />
            <Route path="/admin/login" element={<AdminLogin />} />
            <Route path="/admin/*" element={<AdminConsole />} />
            <Route path="/*" element={<Site />} />
          </Routes>
        </Suspense>
      </LocaleProvider>
    </ThemeProvider>
  );
}
