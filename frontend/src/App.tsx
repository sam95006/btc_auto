import { Navigate, Route, Routes } from "react-router-dom";
import { AppFooter } from "./components/AppFooter";
import { FloatingAIAssistant } from "./components/FloatingAIAssistant";
import { MarketTopTicker } from "./components/MarketTopTicker";
import { SafetyBanner } from "./components/SafetyBanner";
import { SidebarNav } from "./components/SidebarNav";
import { LiveMarketProvider } from "./market/useLiveMarketFeed";
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
 * NEXUS / EATI UI MVP-22A — Live Market Data Truth Layer (read-only).
 * Forbidden: /trade, /orders, /arm, /routing-edit
 * Market: Bybit Mainnet public lastPrice only · no private API
 * AI: floating panel (no permanent right rail).
 */
export default function App() {
  return (
    <LiveMarketProvider>
      <div className="app-shell mi-shell mvp22-shell">
        <SafetyBanner />
        <MarketTopTicker />
        <div className="app-body app-body-no-rail">
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
        </div>
        <FloatingAIAssistant />
      </div>
    </LiveMarketProvider>
  );
}
