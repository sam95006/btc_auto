# NEXUS Public Auth & Membership Foundation V1 (PUB-H)

**Status:** Non-production foundation (`LOCAL_OR_STAGING_ONLY`)  
**Branch:** `feature/public-v1-auth-membership-foundation`  
**Package:** `backend/nexus_public_auth`

## Purpose

Separate **public identity realm** foundations for the future member platform:

- public JWT issuer isolated from private / founder / operator secrets
- member, organization, and team roles
- Free / Pro / Elite / Enterprise entitlements (manual assignment only)
- session creation and revocation
- account deletion and data export
- append-only public audit log
- consent state per purpose

## Hard bans

| Ban | Enforcement |
|-----|-------------|
| No live billing | `LIVE_BILLING_ENABLED=false`, provider `NONE_NON_PRODUCTION`, refuse Stripe/IAP actors |
| No shared private JWT issuer | Public issuer `nexus-public-auth-v1` only; private issuer denylist |
| No private admin session reuse | Tokens must carry `token_use=public_member_session` + public realm |
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

## Two-pass verification

1. **Pass 1** — env hard-ban guard + static owned-path claim scan  
2. **Pass 2** — adversarial probes that must raise `HardBanViolation`

Runner: `python -m backend.nexus_public_auth.pass_runner`

## Non-goals

- production customer database
- live billing / subscriptions / invoices
- App Store / Play billing products
- private-core authorization
- merging PR #26 / #27
