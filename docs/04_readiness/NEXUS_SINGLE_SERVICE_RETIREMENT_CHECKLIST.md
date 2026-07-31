# NEXUS Single-Service Retirement Checklist

Do **not** delete services until cutover smoke passes.

## Pre-retire (required)

- [x] `NEXUS_SINGLE_SERVICE=true` on Validation
- [x] `stage3_dependency_required=false`
- [x] `external_control_plane_dependency_required=false`
- [x] health T+0/60/180 PASS
- [x] position_count=0, open_order_count=0
- [x] exchange_write=false
- [x] fee_rate_status explainable (`FEE_RATE_CONFIGURED_CONSERVATIVE`)

## Scale-to-zero (not delete)

1. [x] `nexus-stage3-bybit-demo-learning` → suspended / non-200 (`502`) — run 30606087614  
2. [x] `nexus-unified-control-plane` → suspended / non-200 (`502`) — run 30606087614  

Observe ≥24h **operational** (not trading validation) — **in progress** until `2026-08-01T05:11:30Z`.

- market still works on Validation
- UI still works
- demo account still works
- no hidden HTTP dependency

Then delete/remove.

## Final

- [ ] `final_zeabur_service_count=1`
- [ ] display name may become `NEXUS`
- [ ] sole execution owner = Validation service itself
