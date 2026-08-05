# NEXUS Public Auth Entitlement & Organization Security V2 (PUB2-F)

**Status:** Non-production foundation (`LOCAL_OR_STAGING_ONLY`)  
**Branch:** `feature/public-v2-auth-entitlement-org-security`  
**Package:** `backend/nexus_public_auth`  
**Base:** `5e93f677ece9f283aeade98657b5e3d5736991b5`  
**Prior foundation:** PUB-H `NEXUS_PUBLIC_AUTH_MEMBERSHIP_FOUNDATION_V1`

## Purpose

Public identity realm security for the member platform:

- public JWT issuer isolated from private / founder / operator secrets
- MFA-ready abstraction (TOTP / WebAuthn / recovery / email OTP types; no live provider)
- member, organization, and team roles
- Free / Pro / Elite / Enterprise entitlements (manual assignment only)
- **entitlements never grant private execution access**
- session creation and revocation
- account deletion and data export
- append-only public audit log
- consent state per purpose
- auth API rate limits

## Hard bans

| Ban | Enforcement |
|-----|-------------|
| No live billing | `LIVE_BILLING_ENABLED=false`, provider `NONE_NON_PRODUCTION`, refuse Stripe/IAP actors |
| No shared private JWT issuer | Public issuer `nexus-public-auth-v1` only; private issuer denylist |
| No private admin session reuse | Tokens must carry `token_use=public_member_session` + public realm |
| No private execution via entitlement | `PRIVATE_EXECUTION_FEATURE_DENYLIST` + fail-closed feature checks on every tier |
| No production customer DB | In-memory staging store only |
| No live public deploy / IAP / custody / copy-trading | Env hard-ban guard |

## Identity boundary

```
Member Web / Mobile
  → Public Auth (realm=nexus.public.identity.v1)
  → Public Decision Cloud
  → Intelligence Publishing Gateway
```

Forbidden:

- reusing founder / operator / demo-autonomous session tokens
- importing private Lesson Memory, checkpoints, or exchange credentials into exports
- charging cards or enabling real IAP in this lane
- unlocking private execution / exchange write / autonomy via Free/Pro/Elite/Enterprise

## Three-pass verification

1. **Pass 1** — env hard-ban guard + tier matrix private-execution exclusion + static owned-path claim scan  
2. **Pass 2** — adversarial probes that must raise `HardBanViolation` (billing, JWT, entitlement execution)  
3. **Pass 3** — independent cross-review probes (Enterprise execution refusal, rate-limit burst, MFA wrong-code, IAP actor)

Runner: `python -m backend.nexus_public_auth.pass_runner`

## Non-goals

- no production customer database
- no live billing / subscriptions / invoices
- no App Store / Play billing products
- no live MFA SMS / IdP providers
- no private-core authorization or execution access
- no merging PR #26 / #27
