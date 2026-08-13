import { Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { WatchlistProvider } from "./context/WatchlistContext";
import { AppShell, PublicShell } from "./layout/Shells";
import {
  AccountPage,
  AlertsPage,
  DashboardPage,
  MarketDetailPage,
  MarketsPage,
  MembershipPage,
  WatchlistPage,
} from "./pages/AppPages";
import {
  ForgotPasswordPage,
  LandingPage,
  LoginPage,
  PlansPage,
  RegisterPage,
} from "./pages/PublicPages";
import "./styles/memberPlatformV1.css";

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
            <Route path="/plans" element={<PlansPage />} />
          </Route>
          <Route path="/app" element={<AppShell />}>
            <Route index element={<DashboardPage />} />
            <Route path="markets" element={<MarketsPage />} />
            <Route path="market/:symbol" element={<MarketDetailPage />} />
            <Route path="watchlist" element={<WatchlistPage />} />
            <Route path="alerts" element={<AlertsPage />} />
            <Route path="membership" element={<MembershipPage />} />
            <Route path="account" element={<AccountPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </WatchlistProvider>
    </AuthProvider>
  );
}
