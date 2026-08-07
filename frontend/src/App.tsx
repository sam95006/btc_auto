/**
 * NEXUS Member Platform shell — React (not Flutter).
 * Public Decision Integrity pages. No private trading controls.
 * Forbidden routes: /trade, /orders, /arm, /routing-edit
 *
 * PUB-E: Founder private operator mounts in a separate shell (never inside member SidebarNav).
 * V18.2.11 Preview: Member Product V2 is default. No silent fallback to Legacy / ActualPanel.
 */
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { FounderDiagnosticsPage } from "./founder/FounderDiagnosticsPage";
import { FounderLiveOpsPage } from "./founder/FounderLiveOpsPage";
import { FounderOperatorShell } from "./founder/FounderOperatorShell";
import { FounderOperatorPage } from "./founder/FounderOperatorPage";
import { FounderRuntimePage } from "./pages/FounderRuntimePage";
import { NexusMemberProductV2 } from "./app/NexusMemberProductV2";
import { MemberPlatformApp } from "./app/MemberPlatformApp";
import { MEMBER_SURFACE_V18_2_1_FLAG } from "./member/memberSurfaceV1821Flag";

function ActualPanelPreviewRedirect() {
  const loc = useLocation();
  const rest = loc.pathname.replace(/^\/preview\/v18_2_1\/?/, "") || "opportunities";
  if (rest === "review" || rest === "/review") {
    const params = new URLSearchParams(loc.search);
    params.set(MEMBER_SURFACE_V18_2_1_FLAG, "1");
    return <Navigate to={`/review?${params.toString()}${loc.hash}`} replace />;
  }
  const path = rest.startsWith("/") ? rest : `/${rest}`;
  const params = new URLSearchParams(loc.search);
  params.set(MEMBER_SURFACE_V18_2_1_FLAG, "1");
  return <Navigate to={`${path}?${params.toString()}${loc.hash}`} replace />;
}

/**
 * Member Platform (PUB-D) + Founder Private Operator (PUB-E).
 * Founder operator never mounts inside member nav.
 * Default Preview surface = Product V2 only.
 */
export default function App() {
  return (
    <Routes>
      <Route path="/founder/operator" element={<FounderOperatorShell />}>
        <Route index element={<FounderOperatorPage />} />
      </Route>
      <Route path="/founder/diagnostics" element={<FounderOperatorShell />}>
        <Route index element={<FounderDiagnosticsPage />} />
      </Route>
      <Route path="/founder/live-ops" element={<FounderOperatorShell />}>
        <Route index element={<FounderLiveOpsPage />} />
      </Route>
      <Route path="/founder/runtime" element={<FounderRuntimePage />} />
      <Route path="/preview/v18_2_1/*" element={<ActualPanelPreviewRedirect />} />
      <Route path="/member-platform/*" element={<MemberPlatformApp />} />
      <Route path="/*" element={<NexusMemberProductV2 />} />
    </Routes>
  );
}
