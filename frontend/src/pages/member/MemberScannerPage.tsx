import { Link } from "react-router-dom";
import { MemberPageChrome } from "../../member/MemberPageChrome";
import { LiveFunnelMarketPulseScreen, buildLiveFunnelScreen } from "../../member/live_funnel";
import { useRuntimeSnapshot } from "../../member/runtime_snapshot";
import { usePublicEntitlements } from "../../member/public_entitlements_v18_2";
import { UpgradeGate } from "../../member/UpgradeGate";
import { useMemo } from "react";

/** V18.2 scanner — funnel read-only; entitlement-gated full scanner. */
export function MemberScannerPage() {
  const runtime = useRuntimeSnapshot();
  const { dto, hasCapability, loading: entLoading } = usePublicEntitlements("FREE");
  const funnelModel = runtime.model ?? buildLiveFunnelScreen("live_read_only");
  const eligible = runtime.snapshot?.universe_funnel?.display?.eligible;
  const eligibleZero = eligible === "0" || String(eligible ?? "") === "0";

  const denial = useMemo(() => {
    if (entLoading || hasCapability("SCANNER_FULL") || hasCapability("SCANNER_PREVIEW")) {
      return null;
    }
    return {
      ok: false as const,
      error: "ENTITLEMENT_REQUIRED" as const,
      capability_id: "SCANNER_FULL",
      current_plan: dto?.plan || "VISITOR",
      required_plan: "PRO",
      message: "Full market scanner requires upgrade",
      upgrade_display: "PRICE_TBD",
      non_execution_disclaimer: true,
    };
  }, [dto?.plan, entLoading, hasCapability]);

  return (
    <MemberPageChrome titleKey="nav.v182.scanner" subtitleKey="pages.home.subtitle">
      {denial ? (
        <UpgradeGate
          denial={denial}
          featureTitle="Market Scanner"
          featurePurpose="Scan the full universe funnel with honest eligibility counts — analysis only."
        />
      ) : null}
      <section aria-label="Scanner funnel" data-testid="member-scanner-funnel">
        {eligibleZero ? (
          <p className="nx-banner-warn" role="status" data-testid="no-eligible-opportunities">
            No eligible opportunities currently — safety blocks may apply (e.g. liquidity or data
            gaps). We do not fabricate LONG/SHORT signals.
          </p>
        ) : null}
        <LiveFunnelMarketPulseScreen model={funnelModel} />
      </section>
      <p className="muted sm">
        <Link to="/home">Back to overview</Link>
      </p>
    </MemberPageChrome>
  );
}
