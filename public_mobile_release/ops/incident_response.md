# Incident response — public mobile release

**Status:** RUNBOOK_DRAFT · NON_SUBMISSION  
**Scope:** Public member mobile/web surfaces only (not private trading core)

## Severity

| Sev | Examples | Response target (draft) |
|-----|----------|-------------------------|
| SEV1 | Auth outage, mass data exposure, billing charge errors (when enabled) | Immediate bridge |
| SEV2 | Stale market data without indicators, deletion pipeline failure | Same day |
| SEV3 | Cosmetic / single-region flag issues | Backlog |

## First actions

1. Declare incident channel + incident commander
2. Freeze store uploads (`publish_to_stores=false` already for PUB-L)
3. Disable feature flags regionally if needed (`regional/feature_flags.yaml` remote config counterpart)
4. If credential leak: rotate public auth secrets; never rotate via committing secrets
5. If private-core boundary breach suspected: cut public gateway routes; escalate Founder

## Communication

- External: factual, no profitability claims, no legal conclusions
- Internal: timeline, impact, blast radius, ban checklist

## Evidence

- Preserve gateway logs, deletion request IDs, entitlement audit events
- Do not rewrite raw evidence
- Do not fabricate participant counts

## Ban checklist during incidents

- [ ] No emergency App Store submission from this lane
- [ ] No exchange write
- [ ] No private-core direct exposure as “fix”
- [ ] No silent customer data purge without audit trail
