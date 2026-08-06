import type { EntitlementDenialBody } from "./public_entitlements_v18_2";

type Props = {
  denial: EntitlementDenialBody;
  featureTitle: string;
  featurePurpose: string;
};

/** Upgrade gate — PRICE_TBD or Contact Sales; no fake urgency. */
export function UpgradeGate({ denial, featureTitle, featurePurpose }: Props) {
  return (
    <section
      className="member-panel member-upgrade-gate"
      role="region"
      aria-labelledby="upgrade-gate-title"
      data-testid="upgrade-gate"
      data-denial-code={denial.error}
    >
      <h2 id="upgrade-gate-title">{featureTitle}</h2>
      <p>{featurePurpose}</p>
      <ul className="member-upgrade-meta">
        <li>
          <span className="muted">Current plan</span> <strong>{denial.current_plan}</strong>
        </li>
        <li>
          <span className="muted">Required plan</span>{" "}
          <strong>{denial.required_plan || "Upgrade"}</strong>
        </li>
        <li>
          <span className="muted">Pricing</span>{" "}
          <strong data-testid="upgrade-price-display">{denial.upgrade_display}</strong>
        </li>
      </ul>
      <p className="muted sm" data-testid="non-execution-disclaimer">
        Intelligence and analysis only — no trade execution, orders, or exchange controls.
      </p>
    </section>
  );
}
