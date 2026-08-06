import type { PublicPlan } from "./public_entitlements_v18_2/types";
import type { UiDensity } from "./uiDensityPrefs";
import { loadUiDensity, saveUiDensity } from "./uiDensityPrefs";

const PLAN_KEY = "nexus_preview_entitlement_review_plan_v1822";
const DEFAULT_PLAN: PublicPlan = "VISITOR";

export const PREVIEW_PLAN_LABELS: Record<PublicPlan, string> = {
  VISITOR: "訪客",
  FREE: "免費版",
  PRO: "專業版",
  RESEARCH: "研究版",
  ENTERPRISE: "企業版",
};

export const PREVIEW_PLANS: PublicPlan[] = [
  "VISITOR",
  "FREE",
  "PRO",
  "RESEARCH",
  "ENTERPRISE",
];

export function loadPreviewReviewPlan(): PublicPlan {
  try {
    const v = sessionStorage.getItem(PLAN_KEY);
    if (v && PREVIEW_PLANS.includes(v as PublicPlan)) {
      return v as PublicPlan;
    }
  } catch {
    /* ignore */
  }
  return DEFAULT_PLAN;
}

export function savePreviewReviewPlan(plan: PublicPlan): void {
  try {
    sessionStorage.setItem(PLAN_KEY, plan);
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new CustomEvent("nexus-preview-review-plan", { detail: plan }));
}

export function resetPreviewReviewState(): void {
  try {
    sessionStorage.removeItem(PLAN_KEY);
  } catch {
    /* ignore */
  }
  saveUiDensity("SIMPLE");
  window.dispatchEvent(new CustomEvent("nexus-preview-review-reset"));
}

export function loadPreviewReviewDensity(): UiDensity {
  return loadUiDensity();
}

export function savePreviewReviewDensity(d: UiDensity): void {
  saveUiDensity(d);
}
