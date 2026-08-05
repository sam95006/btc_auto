# NEXUS Public Flutter Mobile Foundation (PUB-J) V1

## Purpose

One Flutter codebase for **iOS + Android** that consumes **public Decision Intelligence DTOs** only.

## Owned paths

- `apps/nexus_public_mobile/`
- `tools/public_mobile/`
- `tests/public_mobile/`
- `artifacts/readiness/immutable/pub_j_flutter_mobile_foundation/`

## Screens

Home, Markets, Decisions, Detail, Evidence, Risks, Alerts, Decision Memory, Outcome Review, NEX AI, Membership, Account, Privacy, Notification Settings.

## Foundations included

| Area | Location |
|------|----------|
| Adaptive themes | `lib/core/theme/` |
| Localization | `lib/core/l10n/` + ARB |
| Accessibility | `lib/core/a11y/` |
| Secure storage / biometric | `lib/core/security/` |
| Offline cache | `lib/core/cache/` |
| Push abstraction | `lib/core/push/` |
| Deep links | `lib/core/deeplink/` |
| Analytics consent | `lib/core/analytics/` |
| Crash abstraction | `lib/core/crash/` |
| Feature flags | `lib/core/flags/` |
| Mock + live modes | `lib/core/mode/` + `lib/data/{mock,live}/` |

## Hard bans

- No exchange SDKs / APIs
- No private-core imports
- No trading / order / wallet controls
- No `*_status.json` lane artifacts

## Platform evidence

| Check | Expected |
|-------|----------|
| Flutter analyze / test / Android debug | Run when toolchain available; else `FLUTTER_SDK_UNAVAILABLE` / `ANDROID_TOOLCHAIN_UNAVAILABLE` |
| iOS project config | `IOS_PROJECT_CONFIG_PASS` |
| iOS signed build | `IOS_SIGNED_BUILD_PLATFORM_BLOCKED` on Windows |

## Verify

```bash
python tools/public_mobile/run_pub_j_passes.py
pytest -q tests/public_mobile
```
