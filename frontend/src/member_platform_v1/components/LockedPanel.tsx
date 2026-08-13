import { Link } from "react-router-dom";
import type { MembershipTier } from "../types/dto";
import { TIER_LABELS } from "../lib/entitlements";

export function LockedPanel({
  featureLabel,
  requiredTier,
  preview,
}: {
  featureLabel: string;
  requiredTier: MembershipTier;
  preview?: string;
}) {
  return (
    <div className="mpv1-locked">
      <div className="mpv1-locked-body" aria-hidden>
        <p className="mpv1-muted">{preview || "進階市場細節已準備好，升級後即可展開。"}</p>
        <ul className="mpv1-list">
          <li>支持證據與反證</li>
          <li>衍生品與流動性摘要</li>
          <li>歷史訊號脈絡</li>
        </ul>
      </div>
      <div className="mpv1-locked-cta">
        <strong>{featureLabel}</strong>
        <p className="mpv1-muted">需要 {TIER_LABELS[requiredTier]} 或以上</p>
        <Link className="mpv1-btn mpv1-btn-primary" to="/app/membership">
          查看方案
        </Link>
      </div>
    </div>
  );
}
