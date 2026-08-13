import { Link } from "react-router-dom";
import type { MembershipTier } from "../types/dto";
import { TIER_LABELS } from "../lib/entitlements";
import { IconLock } from "./Icons";

export function LockedPanel({
  featureLabel,
  requiredTier,
}: {
  featureLabel: string;
  requiredTier: MembershipTier;
}) {
  return (
    <div className="mpv1-locked">
      <IconLock size={18} />
      <h4>{featureLabel}</h4>
      <p className="mpv1-muted">{TIER_LABELS[requiredTier]} 以上可解鎖</p>
      <Link className="mpv1-btn mpv1-btn-primary mpv1-btn-sm" style={{ marginTop: "0.75rem" }} to="/app/membership">
        查看方案
      </Link>
    </div>
  );
}
