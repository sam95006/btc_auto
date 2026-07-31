# NEXUS Single-Service Retirement Checklist

Do **not** delete services until cutover smoke passes.

## Pre-retire (required)

- [ ] `NEXUS_SINGLE_SERVICE=true` on Validation
- [ ] `stage3_dependency_required=false`
- [ ] `external_control_plane_dependency_required=false`
- [ ] health T+0/60/180 PASS
- [ ] position_count=0, open_order_count=0
- [ ] exchange_write=false
- [ ] fee_rate_status explainable (LIVE or Founder-approved conservative)

## Scale-to-zero (not delete)

1. `nexus-stage3-bybit-demo-learning` → DISABLED / SCALED_TO_ZERO  
2. `nexus-unified-control-plane` → DISABLED / SCALED_TO_ZERO  

Observe ≥24h **operational** (not trading validation):

- market still works on Validation
- UI still works
- demo account still works
- no hidden HTTP dependency

Then delete/remove.

## Final

- [ ] `final_zeabur_service_count=1`
- [ ] display name may become `NEXUS`
- [ ] sole execution owner = Validation service itself
