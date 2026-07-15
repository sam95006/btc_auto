import { Navigate, Route, Routes } from "react-router-dom";
import { AICopilotPanel } from "./components/AICopilotPanel";
import { AppFooter } from "./components/AppFooter";
import { SafetyBanner } from "./components/SafetyBanner";
import { SidebarNav } from "./components/SidebarNav";
import { TopStatusBar } from "./components/TopStatusBar";
import { AcademyPage } from "./pages/AcademyPage";
import { AssistantPage } from "./pages/AssistantPage";
import { CalculatorPage } from "./pages/CalculatorPage";
import { EvidencePage } from "./pages/EvidencePage";
import { FleetsPage } from "./pages/FleetsPage";
import { MembershipPage } from "./pages/MembershipPage";
import { OverviewPage } from "./pages/OverviewPage";
import { PaperLabPage } from "./pages/PaperLabPage";
import { ProviderShadowPage } from "./pages/ProviderShadowPage";
import { ReflectionPage } from "./pages/ReflectionPage";
import { RiskEvidencePage } from "./pages/RiskEvidencePage";
import { SignalsPage } from "./pages/SignalsPage";

/**
 * NEXUS / EATI UI MVP-20 Market Intelligence polish (read-only).
 * Explicitly absent (forbidden): /trade, /orders, /arm, /routing-edit
 * Desktop: AI Commander only in right rail. Mobile: bottom dock.
 */
export default function App() {
  return (
    <div className="app-shell mi-shell">
      <SafetyBanner />
      <TopStatusBar />
      <div className="app-body">
        <SidebarNav />
        <div className="main-column">
          <main className="main-content">
            <Routes>
              <Route path="/" element={<Navigate to="/overview" replace />} />
              <Route path="/overview" element={<OverviewPage />} />
              <Route path="/fleets" element={<FleetsPage />} />
              <Route path="/signals" element={<SignalsPage />} />
              <Route path="/risk-evidence" element={<RiskEvidencePage />} />
              <Route path="/evidence" element={<EvidencePage />} />
              <Route path="/reflection" element={<ReflectionPage />} />
              <Route path="/provider-shadow" element={<ProviderShadowPage />} />
              <Route path="/paper-lab" element={<PaperLabPage />} />
              <Route path="/assistant" element={<AssistantPage />} />
              <Route path="/academy" element={<AcademyPage />} />
              <Route path="/calculator" element={<CalculatorPage />} />
              <Route path="/membership" element={<MembershipPage />} />
              <Route path="*" element={<Navigate to="/overview" replace />} />
            </Routes>
          </main>
          <AppFooter />
        </div>
        <aside className="ai-rail desktop-ai-rail" aria-label="AI Commander rail">
          <AICopilotPanel />
        </aside>
      </div>
      <div className="mobile-ai-dock" aria-label="AI Commander mobile">
        <AICopilotPanel compact />
      </div>
    </div>
  );
}
