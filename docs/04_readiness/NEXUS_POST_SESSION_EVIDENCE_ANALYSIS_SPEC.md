# Post-Session Evidence Analysis Spec

Offline only. Input = export directory or ZIP. Never mount Zeabur `/data` directly from the analyzer.

## Tool

```bash
python tools/analysis/analyze_nexus_demo_session.py \
  --input <export_dir_or.zip> \
  --session-id NEXUS-DEMO-6H-... \
  --output <out_dir> \
  [--strict]
```

## Outputs

- `analysis_summary.json`
- `trade_cost_analysis.csv`
- `outcome_analysis.csv`
- `reflection_analysis.json`
- `similar_case_analysis.json`
- `decision_delta_analysis.json`
- `error_recurrence_analysis.json`
- `session_quality_report.md`

## Required metrics

Candidates, Risk Critic / Mistake Guard / Cost Gate blocks, Entries, Completed Trades, Wins/Losses, Gross PnL, Entry/Exit/Total Fees, Funding, Net PnL, Profit Factor, Expectancy, Max Drawdown, Good/Bad Process Win/Loss, Reflection / Similar Case coverage, Decision Delta count, Repeated errors, Cost-dominated entries, Direction-correct-but-net-loss, Fee churn, Protection / Duplicate / Reconciliation incidents, Worker stalls, Kill switch events.

## Honesty rules

- Missing Funding → `UNAVAILABLE` (never coerce to `0`)
- Insufficient sample → `INSUFFICIENT_SAMPLE` (do not invent precise expectancy)
- Zero trades is **not** automatic Fail; emit zero-trade analysis + optional `DEMO_AUTONOMOUS_6H_BLOCKED_NO_VALID_CANDIDATES`
- 6H must not label: `PROVEN`, `PRODUCTION_READY`, `PROFITABLE`

## Reflection evidence chain

Trade Case → Outcome → Process Quality → Reflection → Similar Case Search → Guard Action → Subsequent Candidate → Decision Delta

Minimum success evidence fields:

`source_trade_case_id`, `similar_candidate_id`, `similarity_score`, `before_verdict`, `after_verdict`, `before_score`, `after_score`, `guard_action`, `policy_version`

Learning effectiveness:

| Condition | Label |
|-----------|-------|
| Reflection only, no similar candidate | `NOT_YET_OBSERVABLE` |
| Similar candidate, decision unchanged | `NOT_PROVEN` |
| Error recurrence down + decision delta | `PRELIMINARY_EVIDENCE` |

## After 6H deadline (not early)

1. Confirm write window closed  
2. Confirm 0 position / 0 orders / MATCH recon  
3. Export  
4. Run this analyzer  
5. Final 6H report  
6. **Do not** start 24H  
7. **Do not** deploy Control Plane  
8. Stop at two separate Founder gates
