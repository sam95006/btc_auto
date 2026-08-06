import { MemberPageChrome } from "../../member/MemberPageChrome";
import { usePublicEntitlements } from "../../member/public_entitlements_v18_2";
import { UpgradeGate } from "../../member/UpgradeGate";

/** Enterprise organization shell — team roles; no Founder secrets. */
export function MemberOrganizationPage() {
  const { dto, loading } = usePublicEntitlements("ENTERPRISE");

  if (!loading && dto?.plan !== "ENTERPRISE") {
    return (
      <MemberPageChrome titleKey="nav.v182.organization" subtitleKey="pages.home.subtitle">
        <UpgradeGate
          denial={{
            ok: false,
            error: "ENTITLEMENT_REQUIRED",
            capability_id: "ORG_DASHBOARD",
            current_plan: dto?.plan || "VISITOR",
            required_plan: "ENTERPRISE",
            message: "Organization features require Enterprise",
            upgrade_display: "Contact Sales",
            non_execution_disclaimer: true,
          }}
          featureTitle="Organization"
          featurePurpose="Team roles, audit, and shared watchlists — never exposes Founder private execution."
        />
      </MemberPageChrome>
    );
  }

  return (
    <MemberPageChrome titleKey="nav.v182.organization" subtitleKey="pages.home.subtitle">
      <section className="member-panel" data-testid="member-organization">
        <h2>Organization</h2>
        <p className="muted">
          Roles: ORG_ADMIN, ANALYST, VIEWER — org capabilities only (SSO, audit, team watchlists).
        </p>
        <p className="muted sm">
          Forbidden: Founder portfolio, order IDs, API keys, private strategy parameters.
        </p>
      </section>
    </MemberPageChrome>
  );
}
