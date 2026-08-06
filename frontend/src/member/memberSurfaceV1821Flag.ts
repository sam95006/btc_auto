/** Feature flag: V18.2.1 actual deployed panel product surface (preview only). */
export const MEMBER_SURFACE_V18_2_1_FLAG = "member_surface_v18_2_1";

export function isMemberSurfaceV1821Enabled(): boolean {
  if (import.meta.env.VITE_MEMBER_SURFACE_V18_2_1 === "true") {
    return true;
  }
  if (typeof window === "undefined") {
    return false;
  }
  const path = window.location.pathname || "";
  if (path.startsWith("/preview/v18_2_1")) {
    return true;
  }
  try {
    const params = new URLSearchParams(window.location.search);
    if (params.get(MEMBER_SURFACE_V18_2_1_FLAG) === "1") {
      return true;
    }
  } catch {
    /* ignore */
  }
  return false;
}

/** Strip preview prefix for in-app routing when using /preview/v18_2_1/* entry. */
export function stripV1821PreviewPrefix(pathname: string): string {
  if (pathname.startsWith("/preview/v18_2_1")) {
    const rest = pathname.slice("/preview/v18_2_1".length);
    return rest || "/";
  }
  return pathname;
}
