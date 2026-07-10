# NEXUS / EATI UI Data Source Mapping v1

UI is **read-only**. Prefer summaries and reports. Never write trading state.

| UI surface | Primary sources | Notes |
|------------|-----------------|-------|
| Top Status / Stage Readiness | `docs/stage4_ai_decision_layer_plan.md`, stage summary JSON, gate reports | Show current gate; never mutate |
| Market Overview | `stage4_ai_decision_summary.json`, latest `ai_decisions.jsonl` rows | Status taxonomy only |
| AI Fleet Center | `ai_decisions.jsonl`, fleet fields in summary | Per-symbol intent/provider |
| AI Round Table | decision reason fields + reflection summaries | Consensus / disagreement |
| Signal / Anomaly | `ai_decisions.jsonl`, system events | No buy/sell labels |
| Visual Screener | confidence + risk score from decisions | Four-quadrant mapping |
| Risk & Evidence | summary flags, validator/calibration/graduation JSON | `order_allowed`, ARM, mock |
| Evidence Vault | `ai_decisions.jsonl`, report markdown links | Stage markers |
| Reflection Center | reflection / learning patch summaries | Applied vs not |
| Provider Shadow | shadow diagnostics + pair compare summaries | Shadow excluded from graduation |
| Paper Lab | paper logger outputs, calibration, graduation | Read-only would_* states |
| AI Assistant | same read sources + report excerpts | Explain-only |
| Academy | static curriculum markdown | No live trading tips as advice |
| Notifications | `stage4_system_events.jsonl` + derived alerts | Severity tiers |
| Membership | product config (static) | SaaS future |

## Allowed file patterns

- `stage4_ai_decision_summary.json`  
- `ai_decisions.jsonl`  
- `stage4_system_events.jsonl`  
- paper logger outputs  
- calibration outputs  
- shadow / provider diagnostics summaries  
- `docs/reports/*.md`  
- plan status markdown  

## Demo fallback

If a source is missing:

```
DEMO DATA · READ-ONLY · NOT INVESTMENT ADVICE
```

## Forbidden UI writes

- Provider routing env / chain  
- Risk Governor thresholds / MAE / confidence floor  
- ARM / radar / production / btc-auto  
- Order or paper execution APIs  
- Stage 4.19 start triggers  
