/**
 * CORPORATE surface (Surface A) — public company website + admin console.
 *
 * Backend-driven: all business/market content comes from the Corporate API
 * (CMS + safe public market). The frontend renders and animates; it never
 * fabricates business or market values. It never imports the Founder operator,
 * private trading controls, Bybit clients, or the authenticated Personal/
 * Enterprise apps.
 */
import { Navigate, Route, Routes } from "react-router-dom";
import { Chrome } from "../corporate/components/Chrome";
import { Home } from "../corporate/pages/Home";
import { ContentPage } from "../corporate/pages/ContentPage";
import { Contact } from "../corporate/pages/Contact";
import { AdminConsole } from "../corporate/admin/AdminConsole";
import { AdminLogin } from "../corporate/admin/AdminLogin";
import { OwnerSetup } from "../corporate/admin/OwnerSetup";
import "../styles/corporate.css";

function Site() {
  return (
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
  );
}

export default function CorporateApp() {
  return (
    <Routes>
      {/* Owner/admin surfaces are outside the marketing chrome. */}
      <Route path="/owner/setup" element={<OwnerSetup />} />
      <Route path="/admin/login" element={<AdminLogin />} />
      <Route path="/admin/*" element={<AdminConsole />} />
      <Route path="/*" element={<Site />} />
    </Routes>
  );
}
