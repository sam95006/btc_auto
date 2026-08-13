import type { MembershipTier } from "../types/dto";
import { TIER_LABELS } from "../lib/entitlements";
import { useAuth } from "../context/AuthContext";

const TIERS: MembershipTier[] = ["starter", "advanced", "professional", "enterprise"];

/** Local Founder preview — not billing. */
export function TierSwitcher() {
  const { tier, previewTier, setPreviewTier } = useAuth();
  return (
    <div>
      <div className="mpv1-tier-switch" role="group" aria-label="會員方案預覽">
        {TIERS.map((t) => (
          <button
            key={t}
            type="button"
            className={tier === t ? "is-on" : undefined}
            onClick={() => setPreviewTier(t)}
          >
            {TIER_LABELS[t]}
          </button>
        ))}
      </div>
      <p className="mpv1-dev-banner" style={{ marginTop: "0.45rem" }}>
        本機預覽切換{previewTier ? `（目前覆寫：${TIER_LABELS[previewTier]}）` : ""} · 非正式扣款
      </p>
    </div>
  );
}
