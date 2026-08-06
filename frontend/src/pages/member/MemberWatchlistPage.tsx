import { MemberPageChrome } from "../../member/MemberPageChrome";
import { usePublicEntitlements } from "../../member/public_entitlements_v18_2";
import { UpgradeGate } from "../../member/UpgradeGate";

export function MemberWatchlistPage() {
  const { dto, hasCapability, loading } = usePublicEntitlements("FREE");
  const max = dto?.limits?.watchlist_max;
  const limitLabel = typeof max === "number" ? max : "policy";

  if (!loading && !hasCapability("WATCHLIST")) {
    return (
      <MemberPageChrome titleKey="nav.v182.watchlist" subtitleKey="pages.home.subtitle">
        <UpgradeGate
          denial={{
            ok: false,
            error: "ENTITLEMENT_REQUIRED",
            capability_id: "WATCHLIST",
            current_plan: dto?.plan || "VISITOR",
            required_plan: "FREE",
            message: "Watchlist requires a free account",
            upgrade_display: "PRICE_TBD",
            non_execution_disclaimer: true,
          }}
          featureTitle="Watchlist"
          featurePurpose="Track symbols for read-only alerts — no orders or execution."
        />
      </MemberPageChrome>
    );
  }

  return (
    <MemberPageChrome titleKey="nav.v182.watchlist" subtitleKey="pages.home.subtitle">
      <section className="member-panel" data-testid="member-watchlist">
        <p className="muted">
          Watchlist (read-only). Policy limit: {limitLabel} symbols — configured server-side, not
          hardcoded in UI.
        </p>
        <p className="muted sm">No portfolio connection or trade actions on this surface.</p>
      </section>
    </MemberPageChrome>
  );
}
