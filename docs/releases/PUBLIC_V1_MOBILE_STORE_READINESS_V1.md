# Public V1 Mobile Store Compliance & Release Readiness (PUB-L)

**Branch:** `feature/public-v1-mobile-release-readiness`  
**Package:** `public_mobile_release/`  
**Status:** NON_SUBMISSION_PACKAGE  
**Legal:** NOT_LEGAL_ADVICE · legal_approval_claimed=false  
**Stores:** Do not submit to App Store or Google Play from this lane.

## What this delivers

Machine-gated readiness package covering:

- iOS / Android build configuration and identifiers
- Signing abstraction (secrets out of git)
- Environment separation (dev / staging / prod)
- Privacy manifest + data inventory
- Data Safety / financial disclosure / age rating **drafts**
- Account deletion + web deletion request architecture
- Subscription entitlement / verify / restore / cancel / refund state machine (billing disabled)
- Regional feature flags
- App Review demo mode
- Incident response + release rollback runbooks
- CI pipeline that refuses store upload

## Verify

```bash
python tools/public_mobile_release/verify_store_readiness_package.py
pytest tests/public_mobile_release -q
```

## Explicit non-claims

This package does **not** claim legal approval, regulatory clearance, or store acceptance. Live billing and real IAP products remain disabled. No production customer database is enabled.
