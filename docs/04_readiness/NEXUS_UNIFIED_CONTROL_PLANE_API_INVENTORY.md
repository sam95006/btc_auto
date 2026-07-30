# NEXUS Unified Control Plane — API Inventory

Inventory of routes that exist in-repo. Control Plane may federate **GET** only from allowlisted hosts. Status reflects code presence, not live deployment of Control Plane.

| `/api/nexus/control-plane/why-no-trade` | control_plane | GET | none/local | gate breakdown | source_timestamp | demo_execution | yes | no | IMPLEMENTED |
| `/api/nexus/control-plane/federation-counters` | control_plane | GET | none/local | counters | n/a | control_plane | yes | no | IMPLEMENTED |
| `/api/nexus/control-plane/ownership` | control_plane | GET | none/local | ownership contract | n/a | control_plane | yes | no | IMPLEMENTED |

## Control Plane (new)

| route | service | method | auth | schema | freshness | data owner | safe for frontend | contains secret | status |
|-------|---------|--------|------|--------|-----------|------------|-------------------|-----------------|--------|
| `/api/nexus/control-plane/overview` | control_plane | GET | none/local | envelope map | source_timestamp | aggregator | yes | no | IMPLEMENTED |
| `/api/nexus/control-plane/services` | control_plane | GET | none/local | service registry | n/a | control_plane | yes | no | IMPLEMENTED |
| `/api/nexus/control-plane/market` | control_plane | GET | none/local | envelope map | source_timestamp | market_intelligence | yes | no | IMPLEMENTED |
| `/api/nexus/control-plane/demo-session` | control_plane | GET | none/local | envelope map | source_timestamp | demo_execution | yes | no | IMPLEMENTED |
| `/api/nexus/control-plane/positions` | control_plane | GET | none/local | envelope map | source_timestamp | demo_execution | yes | no | IMPLEMENTED |
| `/api/nexus/control-plane/performance` | control_plane | GET | none/local | envelope map | source_timestamp | demo_execution | yes | no | IMPLEMENTED |
| `/api/nexus/control-plane/learning` | control_plane | GET | none/local | envelope map | source_timestamp | demo_execution | yes | no | IMPLEMENTED |
| `/api/nexus/control-plane/runtime-identity` | control_plane | GET | none/local | envelope map | source_timestamp | demo_execution | yes | no | IMPLEMENTED |
| `/api/nexus/control-plane/orders` | control_plane | POST/PUT/PATCH/DELETE | n/a | reject | n/a | n/a | n/a | no | BLOCKED_405 |
| `/api/nexus/control-plane/session/start` | control_plane | write methods | n/a | reject | n/a | n/a | n/a | no | BLOCKED_405 |
| `/api/nexus/control-plane/session/stop` | control_plane | write methods | n/a | reject | n/a | n/a | n/a | no | BLOCKED_405 |
| `/api/nexus/control-plane/position/close` | control_plane | write methods | n/a | reject | n/a | n/a | n/a | no | BLOCKED_405 |

## Demo Validation (execution owner) — federation sources

| route | service | method | auth | schema | freshness | data owner | safe for frontend | contains secret | status |
|-------|---------|--------|------|--------|-----------|------------|-------------------|-----------------|--------|
| `/api/nexus/demo-execution/status` | demo_execution | GET | none | status json | fetched_at | demo_execution | yes | no | EXISTS |
| `/api/nexus/demo-execution/account` | demo_execution | GET | none | account snapshot | fetched_at | demo_execution | yes | no | EXISTS |
| `/api/nexus/demo-execution/gate` | demo_execution | GET | none | gate | fetched_at | demo_execution | yes | no | EXISTS |
| `/api/nexus/demo-execution/epoch` | demo_execution | GET | none | epoch | fetched_at | demo_execution | yes | no | EXISTS |
| `/api/nexus/demo-execution/kill-switch` | demo_execution | GET | none | kill switch | fetched_at | demo_execution | yes | no | EXISTS |
| `/api/nexus/demo-execution/bounded-6h/status` | demo_execution | GET | none | bounded session | fetched_at | demo_execution | yes | no | EXISTS |
| `/api/nexus/demo-execution/founder-smoke/latest` | demo_execution | GET | none | smoke report | fetched_at | demo_execution | yes | no | EXISTS |
| `/api/nexus/demo-execution/bounded-6h/start` | demo_execution | POST | founder gate | mutate | n/a | demo_execution | **no** | no | EXISTS — **DO NOT PROXY** |
| `/api/nexus/demo-execution/bounded-6h/stop` | demo_execution | POST | founder gate | mutate | n/a | demo_execution | **no** | no | EXISTS — **DO NOT PROXY** |
| `/api/nexus/demo-execution/founder-smoke/execute` | demo_execution | POST | founder gate | mutate | n/a | demo_execution | **no** | no | EXISTS — **DO NOT PROXY** |

## Stage3 / Market Intelligence — federation sources

| route | service | method | auth | schema | freshness | data owner | safe for frontend | contains secret | status |
|-------|---------|--------|------|--------|-----------|------------|-------------------|-----------------|--------|
| `/api/nexus/stage3/status` | market_intelligence | GET | none | status | fetched_at | stage3 | yes | no | EXISTS |
| `/api/nexus/stage3/summary` | market_intelligence | GET | none | summary | fetched_at | stage3 | yes | no | EXISTS |
| `/api/nexus/stage3/account` | market_intelligence | GET | none | **legacy account** | fetched_at | stage3 | **display forbidden as demo wallet** | no | EXISTS — KEEP_AS_MARKET only / not Demo SoT |
| `/api/nexus/stage3/trades` | market_intelligence | GET | none | **legacy trades** | fetched_at | stage3 | **must not masquerade as validation trades** | no | EXISTS — DEPRECATE plan |
| `/api/nexus/stage3/learning` | market_intelligence | GET | none | learning | fetched_at | stage3 | caution | no | EXISTS |
| `/api/nexus/stage3/log-tail` | market_intelligence | GET | none | logs | fetched_at | stage3 | operator only | maybe | EXISTS |

## Stage3 legacy autonomous (must not own Demo Validation UI)

| route | service | method | notes | status |
|-------|---------|--------|-------|--------|
| `/api/nexus/demo/autonomous/status` | stage3 legacy | GET | Old session ACTIVE can conflict with Validation NONE | EXISTS — DEPRECATE_AFTER_* |
| `/api/nexus/demo/autonomous/account` | stage3 legacy | GET | Must not feed Control Plane demo_account | EXISTS |
| `/api/nexus/demo/autonomous/recent-trades` | stage3 legacy | GET | Must not feed Control Plane performance | EXISTS |
| `/api/nexus/demo/autonomous/session/*` | stage3 legacy | POST | Mutating — never via Control Plane | EXISTS — DO_NOT_PROXY |
| `/api/nexus/demo/autonomous/close` | stage3 legacy | POST | Mutating | EXISTS — DO_NOT_PROXY |

## Federation policy

Allowed methods via Control Plane client: **GET** only.  
Forbidden via Control Plane proxy: POST, PUT, PATCH, DELETE, order create/cancel, position close, trading stop, leverage/margin change, session start/stop.
