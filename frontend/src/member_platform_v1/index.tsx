import { Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { WatchlistProvider } from "./context/WatchlistContext";
import { AppShell, PublicShell } from "./layout/Shells";
import {
  AccountPage as RealAccountPage,
  AlertsPage as RealAlertsPage,
  DashboardPage as RealDashboardPage,
  MarketDetailPage as RealMarketDetailPage,
  MarketsPage as RealMarketsPage,
  WatchlistPage as RealWatchlistPage,
} from "./pages/RealAppPages";
import { BillingCancelPage, BillingCenterPage, BillingSuccessPage } from "./pages/BillingPages";
import { IntelligencePage } from "./pages/IntelligencePages";
import {
  ForgotPasswordPage,
  LandingPage,
  LoginPage,
  PendingVerificationPage,
  PlansPage,
  RegisterPage,
  ResetPasswordPage,
  VerifyEmailPage,
} from "./pages/PublicPages";
import "./styles/memberPlatformV1.css";
import "./styles/memberPlatformMobile.css";

export function MemberPlatformV1App() {
  return (
    <AuthProvider>
      <WatchlistProvider>
        <Routes>
          <Route element={<PublicShell />}>
            <Route path="/" element={<LandingPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />
            <Route path="/verify-email" element={<VerifyEmailPage />} />
            <Route path="/check-email" element={<PendingVerificationPage />} />
            <Route path="/plans" element={<PlansPage />} />
            <Route path="/billing/success" element={<BillingSuccessPage />} />
            <Route path="/billing/cancel" element={<BillingCancelPage />} />
          </Route>
          <Route path="/app" element={<AppShell />}>
            <Route index element={<RealDashboardPage />} />
            <Route path="markets" element={<RealMarketsPage />} />
            <Route path="intelligence" element={<IntelligencePage />} />
            <Route path="market/:symbol" element={<RealMarketDetailPage />} />
            <Route path="watchlist" element={<RealWatchlistPage />} />
            <Route path="alerts" element={<RealAlertsPage />} />
            <Route path="membership" element={<BillingCenterPage />} />
            <Route path="account" element={<RealAccountPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </WatchlistProvider>
    </AuthProvider>
  );
}
