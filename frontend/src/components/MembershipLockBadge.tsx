import type { MembershipTier } from "../types/nexus";

const UPGRADE_HINT: Partial<Record<MembershipTier, string>> = {
  Free: "Upgrade to Pro",
  Standard: "Upgrade to Pro",
  Pro: "Upgrade to Elite",
  Elite: "Upgrade to Team",
  Team: "Upgrade to Enterprise",
};

/**
 * UI-only membership lock stub. Does not call any write APIs.
 */
export function MembershipLockBadge({
  requiredTier = "Pro",
  currentTier = "Free",
}: {
  requiredTier?: MembershipTier;
  currentTier?: MembershipTier;
}) {
  const locked = tierRank(currentTier) < tierRank(requiredTier);
  if (!locked) return null;

  const hint =
    UPGRADE_HINT[currentTier] ??
    (requiredTier === "Elite"
      ? "Upgrade to Elite"
      : requiredTier === "Team"
        ? "Upgrade to Team"
        : "Upgrade to Pro");

  return (
    <span className="lock-badge">
      Locked · requires {requiredTier}
      <button type="button" onClick={() => undefined}>
        {hint}
      </button>
    </span>
  );
}

function tierRank(t: MembershipTier): number {
  const order: MembershipTier[] = [
    "Free",
    "Standard",
    "Pro",
    "Elite",
    "Team",
    "Enterprise",
  ];
  return order.indexOf(t);
}
