# NEXUS Single-Service Cutover Report (in progress)

**Branch:** `feature/nexus-single-service-consolidation`  
**Keep service:** `nexus-bybit-demo-learning-validation`  
**new_service_created:** false  
**target:** `final_zeabur_service_count=1`  
**24H:** closed · next trade gate after cutover: **6H V2 only**

## Done this wave

| Item | Status |
|------|--------|
| Demo fee capability probe tooling + CI mode | landed |
| `DEMO_FEE_ENDPOINT_UNSUPPORTED` honesty | landed |
| `trade_geometry.py` (structure + sensitivity) | landed |
| 1221 geometry replay | complete (inputs missing on frozen evidence) |
| R:R gate 1.2 left unchanged | confirmed |
| Tests | 30 passed |

## Not yet complete (blockers)

| Item | Status |
|------|--------|
| Live fee probe artifact on Validation container | pending CI |
| Internalize Stage3 market modules | pending |
| Internalize Control Plane UI on Validation | pending |
| Deploy read-only to Validation service | pending |
| T+0/60/180 | pending |
| Scale-to-zero Stage3 + Control Plane | pending |
| `final_zeabur_service_count=1` | **still 3** |

## Recommendation

`NEXUS_SINGLE_SERVICE_PARTIAL_WITH_BLOCKERS`
