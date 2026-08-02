# 12H V3 Cost Gate Forensic Replay

- source: `SYNTHETIC_FIXED_GEOMETRY`
- candidates_replayed: `2407`
- pass: `0` · block: `2407`
- primary_root_cause: `B` — Geometry systematically produced targets too close (fixed ±0.8% ⇒ gross_rr=1.0)
- root_cause_codes: `['B', 'E', 'F']`
- floors: `{'MIN_NET_REWARD_RISK_RATIO': 1.2, 'MIN_NET_REWARD_TO_COST': 1.5}`
- threshold_change_allowed: `False`

## Distributions

```json
{
  "gross_rr": {
    "count": 2407,
    "status": "AVAILABLE",
    "min": 1.0,
    "p25": 1.0,
    "p50": 1.0,
    "p75": 1.0,
    "p95": 1.0,
    "max": 1.0,
    "mean": 1.0
  },
  "net_rr": {
    "count": 2407,
    "status": "AVAILABLE",
    "min": 0.6666666666666657,
    "p25": 0.6666666666666657,
    "p50": 0.6666666666666657,
    "p75": 0.6666666666666657,
    "p95": 0.6666666666666657,
    "max": 0.6666666666666657,
    "mean": 0.6666666666666657
  },
  "reward_to_cost": {
    "count": 2407,
    "status": "AVAILABLE",
    "min": 3.9999999999999822,
    "p25": 3.9999999999999822,
    "p50": 3.9999999999999822,
    "p75": 3.9999999999999822,
    "p95": 3.9999999999999822,
    "max": 3.9999999999999822,
    "mean": 3.999999999999982
  },
  "expected_move": {
    "count": 2407,
    "status": "AVAILABLE",
    "min": 0.007999999999999972,
    "p25": 0.007999999999999972,
    "p50": 0.007999999999999972,
    "p75": 0.007999999999999972,
    "p95": 0.007999999999999972,
    "max": 0.007999999999999972,
    "mean": 0.007999999999999972
  },
  "total_expected_cost": {
    "count": 2407,
    "status": "AVAILABLE",
    "min": 0.8,
    "p25": 0.8,
    "p50": 0.8,
    "p75": 0.8,
    "p95": 0.8,
    "max": 0.8,
    "mean": 0.8
  }
}
```

