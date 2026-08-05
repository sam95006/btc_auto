/**
 * NEXUS Member Platform shell — React (not Flutter).
 * Public Decision Integrity pages. No private trading controls.
 * Forbidden routes: /trade, /orders, /arm, /routing-edit
 * No external reference embed; no runtime dependency on reference URL.
 *
 * PUB-E: Founder private operator mounts in a separate shell (never inside member SidebarNav).
 */
import { Navigate, Route, Routes } from "react-router-dom";
import { SkipToContentLabeled } from "./a11y";
import { AppFooter } from "./components/AppFooter";
import { SafetyBanner } from "./components/SafetyBanner";
import { SidebarNav } from "./components/SidebarNav";
import { FounderOperatorShell } from "./founder/FounderOperatorShell";
import { FounderOperatorPage } from "./founder/FounderOperatorPage";
import { useT } from "./i18n";
import { FounderRuntimePage } from "./pages/FounderRuntimePage";
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
  MemberOutcomeReviewPage,
  MemberPrivacyPage,
  MemberRiskConditionsPage,
  MemberThesisMonitorPage,
} from "./pages/member";

function MemberShell() {
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

/**
 * Member Platform (PUB-D) + Founder Private Operator (PUB-E).
 * Founder operator never mounts inside member SidebarNav.
 */
export default function App() {
  return (
    <Routes>
      <Route path="/founder/operator" element={<FounderOperatorShell />}>
        <Route index element={<FounderOperatorPage />} />
      </Route>
      <Route path="/founder/runtime" element={<FounderRuntimePage />} />
      <Route path="/*" element={<MemberShell />} />
    </Routes>
  );
}
