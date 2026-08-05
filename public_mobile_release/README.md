# Public V1 Mobile Store Compliance & Release Pipeline

**Lane:** PUB-L (`feature/public-v1-mobile-release-readiness`)  
**Status:** NON_SUBMISSION_PACKAGE  
**Legal:** NOT_LEGAL_ADVICE · NO_LEGAL_APPROVAL_CLAIMED  
**Stores:** DO_NOT_SUBMIT

This package prepares iOS/Android **build configuration, compliance drafts, deletion flows, subscription state machines, review demo mode, incident/rollback runbooks, and CI gates**. It does **not** authorize App Store / Google Play submission, live billing, real IAP products, production customer databases, or legal approval.

## Package map

| Area | Path |
|------|------|
| Identifiers | `identifiers/app_ids.yaml` |
| iOS build | `build/ios/` |
| Android build | `build/android/` |
| Signing abstraction | `signing/` |
| Environment separation | `env/` (`env.public.*.example`) |
| Privacy / Data Safety drafts | `privacy/` |
| Account + web deletion | `deletion/` |
| Subscription architecture | `subscriptions/` |
| Regional feature flags | `regional/feature_flags.yaml` |
| Review demo mode | `review/` |
| Incident + rollback | `ops/` |
| CI pipeline spec | `ci/pipeline_spec.yaml` |

## Machine gate

```text
python tools/public_mobile_release/verify_store_readiness_package.py
pytest tests/public_mobile_release -q
```

## Hard bans (summary)

- No App Store / Play submission
- No live billing / real IAP SKUs
- No production customer DB
- No custodial wallet / copy trading / automated customer trading
- No private-core route embedding
- No legal-approval claims
- No `*_status.json` artifacts from this lane
