import { isMemberSurfaceV1821Enabled } from "./memberSurfaceV1821Flag";

/** Preview-only membership review — never enabled on production default build. */
export const PREVIEW_ENTITLEMENT_REVIEW_ENV = "VITE_PREVIEW_ENTITLEMENT_REVIEW";

export function previewEntitlementOverrideAvailableInProd(): boolean {
  return false;
}

export function previewFounderCapabilityCount(): number {
  return 0;
}

export function isPreviewEntitlementReviewBuildEnabled(): boolean {
  return import.meta.env.VITE_PREVIEW_ENTITLEMENT_REVIEW === "true";
}

/**
 * Runtime gate: preview build flag + member surface v18.2.1 active.
 * No query-string bypass for Research or other plans in production.
 */
export function isPreviewEntitlementReviewAvailable(): boolean {
  if (!isPreviewEntitlementReviewBuildEnabled()) {
    return false;
  }
  if (!isMemberSurfaceV1821Enabled()) {
    return false;
  }
  return true;
}
