# NEXUS 6H V2 Readiness Report

**FOUNDER_GATE=`DEMO_AUTONOMOUS_6H_V2_BOUNDED_VALIDATION`**  
**APPROVED=false** (not requesting approval yet)

## Why V2 (not 24H)

Round-1 6H never entered real cost math (`FEE_RATE_UNKNOWN` 1221/1221).  
It is **not** valid trading-behavior evidence. After fee honesty + structure geometry land on the single service, re-run **6H V2**, then consider 24H.

## Fixed V2 envelope (when Founder later approves)

- duration=6H  
- max_positions=1  
- max_pending=1  
- max_entries≤6  
- margin_cap=20U  
- fixed_leverage=25  
- isolated_only=true  
- automatic_extension=false  
- `MIN_NET_REWARD_RISK_RATIO=1.2` unchanged unless Founder separately approves geometry policy change  

## Blockers before proposing V2

1. Live Demo fee capability classified  
2. Conservative fee Founder-approved **if** unsupported  
3. Structure geometry inputs captured on candidates  
4. Single-service cutover + retire old two services  
5. Read-only T+0/60/180 PASS  

**6h_v2_gate_ready=false**
