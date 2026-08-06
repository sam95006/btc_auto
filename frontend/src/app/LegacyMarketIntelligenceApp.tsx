import { Navigate, Route, Routes } from "react-router-dom";
import { AppFooter } from "../components/AppFooter";
import { AiCommander } from "../components/AiCommander";
import { MarketTopTicker } from "../components/MarketTopTicker";
import { SafetyBanner } from "../components/SafetyBanner";
import { LegacyWave4SidebarNav } from "../components/LegacyWave4SidebarNav";
import { LiveMarketProvider } from "../market/useLiveMarketFeed";
import { AnomalyOutcomeProvider } from "../market/useAnomalyOutcomes";
import { MarketAnomalyProvider } from "../market/useMarketAnomalies";
import { MarketScannerProvider } from "../market/useMarketScanner";
import { AnomaliesPage } from "../pages/AnomaliesPage";
import { AnomalyOutcomesPage } from "../pages/AnomalyOutcomesPage";
import { AcademyPage } from "../pages/AcademyPage";
import { AssistantPage } from "../pages/AssistantPage";
import { CalculatorPage } from "../pages/CalculatorPage";
import { EvidencePage } from "../pages/EvidencePage";
import { GlobalMarketShadowPage } from "../pages/GlobalMarketShadowPage";
import { AiLearningLabPage } from "../pages/AiLearningLabPage";
import { MembershipPage } from "../pages/MembershipPage";
import { OverviewPage } from "../pages/OverviewPage";
import { PaperLabPage } from "../pages/PaperLabPage";
import { ProviderShadowPage } from "../pages/ProviderShadowPage";
import { ReflectionPage } from "../pages/ReflectionPage";
import { RiskEvidencePage } from "../pages/RiskEvidencePage";
import { UniversePage } from "../pages/UniversePage";
import { AlertsPage } from "../pages/AlertsPage";
import { PortfolioWorkspacePage } from "../pages/PortfolioWorkspacePage";
import { MarketSymbolPage } from "../pages/MarketSymbolPage";
import { WatchlistPage } from "../pages/WatchlistPage";
import { SignalsPage } from "../pages/SignalsPage";
import { AiReviewsPage } from "../pages/AiReviewsPage";
import { ResearchPerformancePage } from "../pages/ResearchPerformancePage";
import { CryptoSectorsPage } from "../pages/crypto/CryptoSectorsPage";
import { CryptoSectorDetailPage } from "../pages/crypto/CryptoSectorDetailPage";
import { CryptoFundingPage, CryptoOiPage, CryptoPriceOiPage } from "../pages/crypto/CryptoRankPages";
import {
  EquitiesAnalysisPage,
  EquitiesIndexRedirect,
  EquitiesTokenizedPage,
} from "../pages/equities/EquitiesPages";
import { OpportunitiesPage } from "../pages/OpportunitiesPage";
import { IntelligencePage } from "../pages/IntelligencePage";
import { TradePlanPage } from "../pages/TradePlanPage";
import { LearningPage } from "../pages/LearningPage";

function FleetsDeprecatedRedirect() {
  return (
    <div className="page-stack">
      <p className="tag tag-warn">/fleets 已棄用 — 重新導向至 /universe</p>
      <Navigate to="/universe" replace />
    </div>
  );
}

/** Stable production shell (flag off) — matches deployed Zeabur panel IA. */
export function LegacyMarketIntelligenceApp() {
  return (
    <LiveMarketProvider>
      <MarketAnomalyProvider>
        <AnomalyOutcomeProvider>
          <MarketScannerProvider>
            <div className="app-shell mi-shell mvp22-shell nx-phase2-shell nx-phase3-shell nx-phase4-shell nx-wave4-shell">
              <SafetyBanner />
              <MarketTopTicker />
              <div className="app-body app-body-no-rail">
                <LegacyWave4SidebarNav />
                <div className="main-column">
                  <main className="main-content" id="main-content" tabIndex={-1}>
                    <Routes>
                      <Route path="/" element={<Navigate to="/overview" replace />} />
                      <Route path="/overview" element={<OverviewPage />} />
                      <Route path="/control-plane" element={<Navigate to="/overview" replace />} />
                      <Route path="/universe" element={<UniversePage />} />
                      <Route path="/opportunities" element={<OpportunitiesPage />} />
                      <Route path="/alerts" element={<AlertsPage />} />
                      <Route path="/portfolio" element={<PortfolioWorkspacePage />} />
                      <Route path="/intelligence" element={<IntelligencePage />} />
                      <Route path="/trade-plan" element={<TradePlanPage />} />
                      <Route path="/learning" element={<LearningPage />} />
                      <Route path="/performance" element={<ResearchPerformancePage />} />
                      <Route path="/scanner" element={<UniversePage />} />
                      <Route path="/market/:symbol" element={<MarketSymbolPage />} />
                      <Route path="/watchlist" element={<WatchlistPage />} />
                      <Route path="/crypto/sectors" element={<CryptoSectorsPage />} />
                      <Route path="/crypto/sectors/:sectorSlug" element={<CryptoSectorDetailPage />} />
                      <Route path="/crypto/oi" element={<CryptoOiPage />} />
                      <Route path="/crypto/funding" element={<CryptoFundingPage />} />
                      <Route path="/crypto/price-oi" element={<CryptoPriceOiPage />} />
                      <Route path="/equities" element={<EquitiesIndexRedirect />} />
                      <Route path="/equities/tokenized" element={<EquitiesTokenizedPage />} />
                      <Route path="/equities/analysis" element={<EquitiesAnalysisPage />} />
                      <Route path="/anomalies" element={<AnomaliesPage />} />
                      <Route path="/anomaly-outcomes" element={<AnomalyOutcomesPage />} />
                      <Route path="/global-shadow" element={<GlobalMarketShadowPage />} />
                      <Route path="/ai-learning-lab" element={<AiLearningLabPage />} />
                      <Route path="/fleets" element={<FleetsDeprecatedRedirect />} />
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
                      <Route path="/ai-reviews" element={<AiReviewsPage />} />
                      <Route path="/research-performance" element={<Navigate to="/performance" replace />} />
                      <Route path="*" element={<Navigate to="/overview" replace />} />
                    </Routes>
                  </main>
                  <AppFooter />
                </div>
              </div>
              <AiCommander />
            </div>
          </MarketScannerProvider>
        </AnomalyOutcomeProvider>
      </MarketAnomalyProvider>
    </LiveMarketProvider>
  );
}
