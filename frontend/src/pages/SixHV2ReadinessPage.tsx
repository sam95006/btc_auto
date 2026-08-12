/**
 * 6H V2 Readiness page stub — must NOT be deployed to frozen Validation runtime.
 * Start button stays disabled until FOUNDER_GATE=DEMO_AUTONOMOUS_6H_V2_BOUNDED_VALIDATION.
 */
export default function SixHV2ReadinessPage() {
  const approved = false;
  return (
    <main style={{ padding: "2rem", maxWidth: 880, margin: "0 auto", fontFamily: "Georgia, serif" }}>
      <h1>6H V2 Readiness</h1>
      <p>FOUNDER APPROVAL REQUIRED — live Validation remains frozen / read-only.</p>
      <ul>
        <li>Operational Observation (24h GET-only)</li>
        <li>Single Service Count = 1 HTTP-200</li>
        <li>Execution Owner = 1</li>
        <li>Fee Policy = FOUNDER_APPROVED_CONFIG (conservative)</li>
        <li>Fee Expiry = 2026-08-31</li>
        <li>Geometry Completeness / Cost Gate Readiness</li>
        <li>Demo Account / Positions / Orders</li>
        <li>Exchange Write = false</li>
        <li>6H V2 Approval Gate = not approved</li>
      </ul>
      <p>
        Runtime deployment_commit SoT: <code>598a5e1…</code> (docs tip must never replace this)
      </p>
      <button type="button" disabled={!approved} aria-disabled="true">
        START 6H V2 (disabled)
      </button>
    </main>
  );
}
