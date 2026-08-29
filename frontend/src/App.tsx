/**
 * PERSONAL surface — the individual Market Intelligence member SaaS.
 * React (not Flutter). Public Decision Integrity pages. No private trading controls.
 * Forbidden routes: /trade, /orders, /arm, /routing-edit.
 *
 * PLATFORM-1 boundary: this personal entry does NOT import or mount the Founder
 * private operator tree. Founder surfaces live only in the founder-private build
 * (src/surfaces/FounderApp.tsx via src/entries/founderMain.tsx). Corporate and
 * Enterprise are separate build surfaces too.
 */
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { NexusMemberProductV2 } from "./app/NexusMemberProductV2";
import { MemberPlatformApp } from "./app/MemberPlatformApp";
import { MemberPlatformV1App } from "./member_platform_v1";
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
 * Personal Member Platform. Default member surface = Member Platform UI V1.
 * Founder operator is intentionally absent from this surface.
 */
export default function App() {
  return (
    <Routes>
      <Route path="/preview/v18_2_1/*" element={<ActualPanelPreviewRedirect />} />
      <Route path="/member-platform/*" element={<MemberPlatformApp />} />
      <Route path="/product-v2/*" element={<NexusMemberProductV2 />} />
      <Route path="/*" element={<MemberPlatformV1App />} />
    </Routes>
  );
}
