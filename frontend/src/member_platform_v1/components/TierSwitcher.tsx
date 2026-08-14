import type { MembershipTier } from "../types/dto";
import { TIER_LABELS } from "../lib/entitlements";
import { useAuth } from "../context/AuthContext";

const TIERS: MembershipTier[] = ["starter", "advanced", "professional", "enterprise"];

/** Single Founder-only tier preview control. Not billing. DEV-only via VITE_MEMBER_TIER_PREVIEW. */
export function TierSwitcher() {
  const enabled = import.meta.env.VITE_MEMBER_TIER_PREVIEW === "true";
  const { tier, setPreviewTier } = useAuth();
  if (!enabled) return null;

  return (
    <div className="mpv1-tier-preview" title="開發預覽：切換會員解鎖深度（非正式扣款）">
      <label htmlFor="mpv1-tier-preview">Preview</label>
      <select
        id="mpv1-tier-preview"
        value={tier}
        onChange={(e) => setPreviewTier(e.target.value as MembershipTier)}
        aria-label="會員方案預覽"
      >
        {TIERS.map((t) => (
          <option key={t} value={t}>
            {TIER_LABELS[t]}
          </option>
        ))}
      </select>
    </div>
  );
}
