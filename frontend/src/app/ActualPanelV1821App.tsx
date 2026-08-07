import { Navigate, Route, Routes } from "react-router-dom";

import { SkipToContentLabeled } from "../a11y";

import { AppFooter } from "../components/AppFooter";

import { ActualPanelSidebarNav } from "../components/ActualPanelSidebarNav";

import { AiCommander } from "../components/AiCommander";

import { MarketTopTicker } from "../components/MarketTopTicker";

import { LiveMarketProvider } from "../market/useLiveMarketFeed";

import { AnomalyOutcomeProvider } from "../market/useAnomalyOutcomes";

import { MarketAnomalyProvider } from "../market/useMarketAnomalies";

import { MarketScannerProvider } from "../market/useMarketScanner";

import { useT } from "../i18n";

import { AlertsPage } from "../pages/AlertsPage";

import { AssistantPage } from "../pages/AssistantPage";

import { IntelligencePage } from "../pages/IntelligencePage";

import { MarketSymbolPage } from "../pages/MarketSymbolPage";

import { ScannerPage } from "../pages/ScannerPage";

import { WatchlistPage } from "../pages/WatchlistPage";

import { ActualPanelOverviewPage } from "../pages/actual_panel/ActualPanelOverviewPage";

import { OpportunitiesPageV1821 } from "../pages/actual_panel/OpportunitiesPageV1821";

import { MembershipReviewEntryGuard } from "../pages/actual_panel/MembershipEntitlementReviewPage";

import {

  MemberAccountDeletionPage,

  MemberAccountPage,

  MemberNotificationSettingsPage,

  MemberOrganizationPage,

  MemberPrivacyPage,

} from "../pages/member";



function SettingsRedirect() {

  return <Navigate to="/account" replace />;

}



/**

 * V18.2.9 UX — distinct page personalities under shared warm graphite + cobalt shell.

 * Editorial overview · master/detail opps · scanner workstation · alert stream · research reading · analyst drawer.

 */

export function ActualPanelV1821App() {

  const t = useT();

  return (

    <LiveMarketProvider>

      <MarketAnomalyProvider>

        <AnomalyOutcomeProvider>

          <MarketScannerProvider>

            <div

              className="v1828-shell v1829-shell nx-actual-panel-v1821"

              data-member-surface="v18_2_1"

              data-product-gen="v18_2_9"

            >

              <SkipToContentLabeled label={t("a11y.skipToContent")} />

              <MarketTopTicker />

              <div className="v1828-body">

                <ActualPanelSidebarNav />

                <div className="v1828-main-column">

                  <main className="v1828-main" id="main-content" tabIndex={-1}>

                    <div className="v1828-grid">

                      <Routes>

                        <Route path="/" element={<Navigate to="/overview" replace />} />

                        <Route path="/overview" element={<ActualPanelOverviewPage />} />

                        <Route path="/review" element={<MembershipReviewEntryGuard />} />

                        <Route path="/opportunities" element={<OpportunitiesPageV1821 />} />

                        <Route path="/scanner" element={<ScannerPage />} />

                        <Route path="/alerts" element={<AlertsPage />} />

                        <Route path="/anomalies" element={<Navigate to="/alerts" replace />} />

                        <Route path="/intelligence" element={<IntelligencePage />} />

                        <Route path="/market/:symbol" element={<MarketSymbolPage />} />

                        <Route path="/watchlist" element={<WatchlistPage />} />

                        <Route path="/assistant" element={<AssistantPage />} />

                        <Route path="/nex-ai" element={<Navigate to="/assistant" replace />} />

                        <Route path="/organization" element={<MemberOrganizationPage />} />

                        <Route path="/account" element={<MemberAccountPage />} />

                        <Route path="/privacy" element={<MemberPrivacyPage />} />

                        <Route path="/account-deletion" element={<MemberAccountDeletionPage />} />

                        <Route

                          path="/notification-settings"

                          element={<MemberNotificationSettingsPage />}

                        />

                        <Route

                          path="/notifications"

                          element={<Navigate to="/notification-settings" replace />}

                        />

                        <Route path="/settings" element={<SettingsRedirect />} />

                        <Route path="/settings/*" element={<SettingsRedirect />} />

                        <Route path="/home" element={<Navigate to="/overview" replace />} />

                        <Route path="/market" element={<Navigate to="/overview" replace />} />

                        <Route path="*" element={<Navigate to="/overview" replace />} />

                      </Routes>

                    </div>

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

