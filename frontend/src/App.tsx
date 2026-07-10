import { Navigate, Route, Routes } from "react-router-dom";
import { SafetyBanner } from "./components/SafetyBanner";
import { TopStatusBar } from "./components/TopStatusBar";
import { SidebarNav } from "./components/SidebarNav";
import { AICommanderPanel } from "./components/AICommanderPanel";
import { OverviewPage } from "./pages/OverviewPage";
import { FleetsPage } from "./pages/FleetsPage";
import { SignalsPage } from "./pages/SignalsPage";
import { RiskEvidencePage } from "./pages/RiskEvidencePage";
import { EvidencePage } from "./pages/EvidencePage";
import { ReflectionPage } from "./pages/ReflectionPage";
import { ProviderShadowPage } from "./pages/ProviderShadowPage";
import { PaperLabPage } from "./pages/PaperLabPage";
import { AssistantPage } from "./pages/AssistantPage";
import { AcademyPage } from "./pages/AcademyPage";
import { CalculatorPage } from "./pages/CalculatorPage";
import { MembershipPage } from "./pages/MembershipPage";

/**
 * NEXUS / EATI UI MVP-0 shell.
 * Explicitly absent: /trade, /orders, /arm, /routing-edit
 */
export default function App() {
  return (
    <div className="app-shell">
      <SafetyBanner />
      <TopStatusBar />
      <div className="app-body">
        <SidebarNav />
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
        <AICommanderPanel />
      </div>
    </div>
  );
}
