# NEXUS Public Mobile (PUB-J)

Single Flutter codebase for **iOS + Android** consuming **public Decision Intelligence DTOs** only.

## Hard bans

- No exchange APIs or SDKs
- No private-core imports
- No trading / order / position / wallet controls
- No fabricated live values (mock mode must label `DEMO_DATA`)

## Modes

| Mode | Purpose |
|------|---------|
| `mock` | Fixture DTOs + offline cache demos |
| `live` | HTTP client against public Decision Cloud (staging/local) |

## Screens

Home · Markets · Decisions · Detail · Evidence · Risks · Alerts · Decision Memory · Outcome Review · NEX AI · Membership · Account · Privacy · Notification Settings

## Platform status (Windows host)

| Check | Result |
|-------|--------|
| Flutter analyze/test | Run when SDK present (`flutter analyze`, `flutter test`) |
| Android debug | Run when Android toolchain present |
| iOS project config | `IOS_PROJECT_CONFIG_PASS` |
| iOS signed build | `IOS_SIGNED_BUILD_PLATFORM_BLOCKED` (non-macOS) |

## Verify without Flutter SDK

```bash
python tools/public_mobile/run_pub_j_passes.py
```
