import { useCallback, useEffect, useState } from "react";
import type { PublicPlan } from "./public_entitlements_v18_2/types";
import {
  isPreviewEntitlementReviewAvailable,
} from "./previewEntitlementReview";
import { loadPreviewReviewPlan, savePreviewReviewPlan } from "./previewMembershipReviewState";

/** Preview-only plan override for entitlement UI (sessionStorage, no DB). */
export function usePreviewReviewPlan(fallback: PublicPlan = "FREE"): PublicPlan {
  const reviewOn = isPreviewEntitlementReviewAvailable();
  const [plan, setPlan] = useState<PublicPlan>(() =>
    reviewOn ? loadPreviewReviewPlan() : fallback,
  );

  useEffect(() => {
    if (!reviewOn) return;
    const onPlan = (e: Event) => {
      const detail = (e as CustomEvent<PublicPlan>).detail;
      if (detail) setPlan(detail);
    };
    const onReset = () => setPlan(loadPreviewReviewPlan());
    window.addEventListener("nexus-preview-review-plan", onPlan);
    window.addEventListener("nexus-preview-review-reset", onReset);
    return () => {
      window.removeEventListener("nexus-preview-review-plan", onPlan);
      window.removeEventListener("nexus-preview-review-reset", onReset);
    };
  }, [reviewOn]);

  const effective = reviewOn ? plan : fallback;
  return effective;
}

export function useSetPreviewReviewPlan(): (p: PublicPlan) => void {
  return useCallback((p: PublicPlan) => {
    if (!isPreviewEntitlementReviewAvailable()) return;
    savePreviewReviewPlan(p);
  }, []);
}
