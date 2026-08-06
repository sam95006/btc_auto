import { Navigate, Route, Routes } from "react-router-dom";
import { SkipToContentLabeled } from "../a11y";
import { AppFooter } from "../components/AppFooter";
import { SafetyBanner } from "../components/SafetyBanner";
import { SidebarNav } from "../components/SidebarNav";
import { useT } from "../i18n";
import {
  MemberAccountDeletionPage,
  MemberAccountPage,
  MemberAlertsPage,
  MemberCounterEvidencePage,
  MemberDecisionDetailPage,
  MemberDecisionFeedPage,
  MemberDecisionMemoryPage,
  MemberEvidencePage,
  MemberHomePage,
  MemberIntelligencePage,
  MemberMarketOverviewPage,
  MemberMembershipPage,
  MemberNexAiPage,
  MemberNotificationSettingsPage,
  MemberOrganizationPage,
  MemberOutcomeReviewPage,
  MemberPrivacyPage,
  MemberRiskConditionsPage,
  MemberScannerPage,
  MemberThesisMonitorPage,
  MemberWatchlistPage,
} from "../pages/member";

/** V18.2 member platform shell (deep links preserved; not default Zeabur surface). */
export function MemberPlatformApp() {
  const t = useT();
  return (
    <div className="app-shell member-shell nx-member-platform">
      <SkipToContentLabeled label={t("a11y.skipToContent")} />
      <SafetyBanner />
      <div className="app-body app-body-no-rail">
        <SidebarNav />
        <div className="main-column">
          <main className="main-content" id="main-content" tabIndex={-1}>
            <Routes>
              <Route path="/" element={<Navigate to="/home" replace />} />
              <Route path="/home" element={<MemberHomePage />} />
              <Route path="/scanner" element={<MemberScannerPage />} />
              <Route path="/watchlist" element={<MemberWatchlistPage />} />
              <Route path="/organization" element={<MemberOrganizationPage />} />
              <Route path="/market" element={<MemberMarketOverviewPage />} />
              <Route path="/overview" element={<Navigate to="/market" replace />} />
              <Route path="/intelligence" element={<MemberIntelligencePage />} />
              <Route path="/decisions" element={<MemberDecisionFeedPage />} />
              <Route path="/decisions/:decisionId" element={<MemberDecisionDetailPage />} />
              <Route path="/evidence" element={<MemberEvidencePage />} />
              <Route path="/counter-evidence" element={<MemberCounterEvidencePage />} />
              <Route path="/risk-conditions" element={<MemberRiskConditionsPage />} />
              <Route path="/thesis-monitor" element={<MemberThesisMonitorPage />} />
              <Route path="/alerts" element={<MemberAlertsPage />} />
              <Route path="/decision-memory" element={<MemberDecisionMemoryPage />} />
              <Route path="/outcome-review" element={<MemberOutcomeReviewPage />} />
              <Route path="/nex-ai" element={<MemberNexAiPage />} />
              <Route path="/assistant" element={<Navigate to="/nex-ai" replace />} />
              <Route path="/membership" element={<MemberMembershipPage />} />
              <Route path="/account" element={<MemberAccountPage />} />
              <Route path="/privacy" element={<MemberPrivacyPage />} />
              <Route path="/account-deletion" element={<MemberAccountDeletionPage />} />
              <Route path="/notification-settings" element={<MemberNotificationSettingsPage />} />
              <Route path="/notifications" element={<Navigate to="/notification-settings" replace />} />
              <Route path="*" element={<Navigate to="/home" replace />} />
            </Routes>
          </main>
          <AppFooter />
        </div>
      </div>
    </div>
  );
}
