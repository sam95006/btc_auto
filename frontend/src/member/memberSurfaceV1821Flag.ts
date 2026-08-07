/** Feature flag: V18.2.1+ member product surface (Actual Panel). */
export const MEMBER_SURFACE_V18_2_1_FLAG = "member_surface_v18_2_1";

/**
 * V18.2.10 Preview deploy: Actual Panel is the DEFAULT surface.
 * LegacyMarketIntelligenceApp (Simple/Pro gold dashboard) must NOT be what Founders see
 * on nexus-member-preview. Opt out only with VITE_MEMBER_SURFACE_V18_2_1=false or ?flag=0.
 */
export function isMemberSurfaceV1821Enabled(): boolean {
  if (import.meta.env.VITE_MEMBER_SURFACE_V18_2_1 === "false") {
    return false;
  }
  if (import.meta.env.VITE_MEMBER_SURFACE_V18_2_1 === "true") {
    return true;
  }
  if (typeof window === "undefined") {
    return true;
  }
  const path = window.location.pathname || "";
  if (path.startsWith("/preview/v18_2_1")) {
    return true;
  }
  try {
    const params = new URLSearchParams(window.location.search);
    if (params.get(MEMBER_SURFACE_V18_2_1_FLAG) === "0") {
      return false;
    }
    if (params.get(MEMBER_SURFACE_V18_2_1_FLAG) === "1") {
      return true;
    }
  } catch {
    /* ignore */
  }
  // Preview branch default: new product surface ON.
  return true;
}

/** Strip preview prefix for in-app routing when using /preview/v18_2_1/* entry. */
export function stripV1821PreviewPrefix(pathname: string): string {
  if (pathname.startsWith("/preview/v18_2_1")) {
    const rest = pathname.slice("/preview/v18_2_1".length);
    return rest || "/";
  }
  return pathname;
}
