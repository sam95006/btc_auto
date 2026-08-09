import { Navigate, Route, Routes } from "react-router-dom";
import { useEffect, useState } from "react";
import { SkipToContentLabeled } from "../a11y";
import { LiveMarketProvider } from "../market/useLiveMarketFeed";
import { AnomalyOutcomeProvider } from "../market/useAnomalyOutcomes";
import { MarketAnomalyProvider } from "../market/useMarketAnomalies";
import { MarketScannerProvider } from "../market/useMarketScanner";
import { MEMBER_PRODUCT_GENERATION } from "../product_v2/generation";
import { ProductV2TopNav, ProductV2MobileNav } from "../product_v2/ProductV2TopNav";
import { MarketPulseBar } from "../product_v2/MarketPulseBar";
import { ProductV2AiDrawer } from "../product_v2/ProductV2AiDrawer";
import { OverviewPageV2 } from "../product_v2/pages/OverviewPageV2";
import { OpportunitiesPageV2 } from "../product_v2/pages/OpportunitiesPageV2";
import { ScannerPageV2 } from "../product_v2/pages/ScannerPageV2";
import { AlertsPageV2 } from "../product_v2/pages/AlertsPageV2";
import { ResearchPageV2 } from "../product_v2/pages/ResearchPageV2";
import { WatchlistPageV2 } from "../product_v2/pages/WatchlistPageV2";
import { AssistantPageV2 } from "../product_v2/pages/AssistantPageV2";
import { MarketTerminalPageV2 } from "../product_v2/pages/MarketTerminalPageV2";
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
 * NEXUS Member Product V2 — Paid Beta Identity + Retention (V18.2.21).
 * Generation marker = 2. Preserves V18.2.19 analytics; identity + retention completed.
 */
export function NexusMemberProductV2() {
  const [aiOpen, setAiOpen] = useState(false);

  useEffect(() => {
    const onOpen = () => setAiOpen(true);
    window.addEventListener("nexus-open-ai", onOpen);
    return () => window.removeEventListener("nexus-open-ai", onOpen);
  }, []);

  return (
    <LiveMarketProvider>
      <MarketAnomalyProvider>
        <AnomalyOutcomeProvider>
          <MarketScannerProvider>
            <div
              className="mp2-shell"
              data-nexus-product-generation={MEMBER_PRODUCT_GENERATION}
              data-member-surface="v18_2_21"
              data-mp2-theme="dark"
              data-testid="nexus-member-product-v2"
              data-build-marker="PUBLIC_V18_2_21_PAID_BETA_IDENTITY_HEAD"
            >
              <SkipToContentLabeled label="跳至主要內容" />
              <ProductV2TopNav onOpenAi={() => setAiOpen(true)} />
              <MarketPulseBar />
              <main className="mp2-main" id="main-content" tabIndex={-1}>
                <Routes>
                  <Route path="/" element={<Navigate to="/overview" replace />} />
                  <Route path="/overview" element={<OverviewPageV2 />} />
                  <Route path="/review" element={<MembershipReviewEntryGuard />} />
                  <Route path="/opportunities" element={<OpportunitiesPageV2 />} />
                  <Route path="/scanner" element={<ScannerPageV2 />} />
                  <Route path="/alerts" element={<AlertsPageV2 />} />
                  <Route path="/anomalies" element={<Navigate to="/alerts" replace />} />
                  <Route path="/intelligence" element={<ResearchPageV2 />} />
                  <Route path="/research" element={<Navigate to="/intelligence" replace />} />
                  <Route path="/market/:symbol" element={<MarketTerminalPageV2 />} />
                  <Route path="/watchlist" element={<WatchlistPageV2 />} />
                  <Route path="/assistant" element={<AssistantPageV2 />} />
                  <Route path="/nex-ai" element={<Navigate to="/assistant" replace />} />
                  <Route path="/organization" element={<MemberOrganizationPage />} />
                  <Route path="/account" element={<MemberAccountPage />} />
                  <Route path="/privacy" element={<MemberPrivacyPage />} />
                  <Route path="/account-deletion" element={<MemberAccountDeletionPage />} />
                  <Route path="/notification-settings" element={<MemberNotificationSettingsPage />} />
                  <Route path="/notifications" element={<Navigate to="/alerts" replace />} />
                  <Route path="/settings" element={<SettingsRedirect />} />
                  <Route path="/settings/*" element={<SettingsRedirect />} />
                  <Route path="/home" element={<Navigate to="/overview" replace />} />
                  <Route path="/market" element={<Navigate to="/overview" replace />} />
                  <Route path="*" element={<Navigate to="/overview" replace />} />
                </Routes>
              </main>
              <footer className="mp2-footer">
                NEXUS · Live Market Intelligence · READ ONLY · NOT INVESTMENT ADVICE
              </footer>
              <ProductV2MobileNav />
              <ProductV2AiDrawer open={aiOpen} onClose={() => setAiOpen(false)} />
            </div>
          </MarketScannerProvider>
        </AnomalyOutcomeProvider>
      </MarketAnomalyProvider>
    </LiveMarketProvider>
  );
}
