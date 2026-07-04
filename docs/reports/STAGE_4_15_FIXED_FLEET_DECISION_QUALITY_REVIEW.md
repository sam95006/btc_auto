# Stage 4.15 — Fixed Fleet Decision-Quality Review

**Generated:** 2026-07-04T17:44:30Z  
**Verdict:** `NEEDS_RISK_GOVERNOR_RULES`  
**Final:** `STAGE_4_15_QUALITY_GATE_COMPLETE`

---

## 1. Executive summary

- Analyzed **718** effective AI decisions across **4** read-only datasets.
- Shadow compared: **664** rows (3 shadow sessions × 4 symbols).
- Parse errors after 414f repairs: **0**; mock_ai_used=**0**; order_sent=**0**.
- Provider dependency: Cerebras **0.7916** (high risk).
- **bad_watch** concentrated in alts (SOL/PEPE); majors BTC/ETH relatively stable.
- Recommended next gate: **Stage 4.16_paper_trading_design_gate**.

## 2. Dataset coverage

- `/data/stage4_ai_decisions_413d_fixed_fleet_180m`
- `/data/stage4_ai_decisions_414b_fixed_fleet_6h`
- `/data/stage4_ai_decisions_414d_fixed_fleet_6h_clean`
- `/data/stage4_ai_decisions_414f_schema_repair_30m_regression`

## 3. Per-symbol decision quality

| Symbol | Decisions | bad_watch_rate | missed_opp_rate | good_skip_rate | reasonable_watch_rate |
|--------|-----------|----------------|-----------------|----------------|----------------------|
| BTCUSDT | 182 | 0.1124 | 0.0592 | 0.0828 | 0.1834 |
| ETHUSDT | 175 | 0.0556 | 0.142 | 0.2469 | 0.1235 |
| SOLUSDT | 180 | 0.259 | 0.1084 | 0.0542 | 0.2229 |
| PEPEUSDT | 181 | 0.2515 | 0.2335 | 0.0419 | 0.1976 |

## 4. Per-intent quality

```json
{
  "watch": 531,
  "soft_skip": 80,
  "hard_skip": 74,
  "enter_candidate": 33
}
```

Label-by-intent (shadow fleet):

```json
{
  "BTCUSDT": {
    "symbol": "BTCUSDT",
    "decision_count": 177,
    "shadow_compared_count": 169,
    "shadow_label_distribution": {
      "missed_opportunity": 10,
      "neutral": 95,
      "reasonable_watch": 31,
      "good_skip": 14,
      "bad_watch": 19,
      "insufficient_future_data": 8
    },
    "decision_intent_distribution": {
      "watch": 139,
      "soft_skip": 34,
      "hard_skip": 1,
      "enter_candidate": 2,
      "unknown": 1
    },
    "bad_watch_count": 19,
    "missed_opportunity_count": 10,
    "bad_watch_rate": 0.1124,
    "missed_opportunity_rate": 0.0592,
    "bad_watch_concentrated_in_watch_intent": true,
    "missed_opportunity_concentrated_in_skip_intent": false,
    "label_by_intent": {
      "watch": {
        "missed_opportunity": 8,
        "neutral": 75,
        "reasonable_watch": 31,
        "bad_watch": 19
      },
      "soft_skip": {
        "neutral": 18,
        "good_skip": 13,
        "missed_opportunity": 2
      },
      "hard_skip": {
        "good_skip": 1
      },
      "enter_candidate": {
        "neutral": 2
      }
    },
    "watch_intent_count": 139,
    "skip_intent_count": 35,
    "bad_watch_in_watch_count": 19,
    "missed_in_watch_count": 8,
    "missed_in_skip_count": 2,
    "reasonable_watch_count": 31,
    "good_skip_count": 14,
    "neutral_count": 95,
    "alias_used": false
  },
  "ETHUSDT": {
    "symbol": "ETHUSDT",
    "decision_count": 170,
    "shadow_compared_count": 162,
    "shadow_label_distribution": {
      "missed_opportunity": 23,
      "good_skip": 40,
      "neutral": 70,
      "bad_watch": 9,
      "reasonable_watch": 20,
      "insufficient_future_data": 8
    },
    "decision_intent_distribution": {
      "watch": 86,
      "hard_skip": 67,
      "soft_skip": 14,
      "enter_candidate": 2,
      "unknown": 1
    },
    "bad_watch_count": 9,
    "missed_opportunity_count": 23,
    "bad_watch_rate": 0.0556,
    "missed_opportunity_rate": 0.142,
    "bad_watch_concentrated_in_watch_intent": true,
    "missed_opportunity_concentrated_in_skip_intent": true,
    "label_by_intent": {
      "watch": {
        "missed_opportunity": 10,
        "neutral": 41,
        "bad_watch": 9,
        "reasonable_watch": 20
      },
      "hard_skip": {
        "missed_opportunity": 13,
        "good_skip": 33,
        "neutral": 19
      },
      "soft_skip": {
        "good_skip": 7,
        "neutral": 7
      },
      "enter_candidate": {
        "neutral": 2
      },
      "unknown": {
        "neutral": 1
      }
    },
    "watch_intent_count": 86,
    "skip_intent_count": 81,
    "bad_watch_in_watch_count": 9,
    "missed_in_watch_count": 10,
    "missed_in_skip_count": 13,
    "reasonable_watch_count": 20,
    "good_skip_count": 40,
    "neutral_count": 70,
    "alias_used": false
  },
  "SOLUSDT": {
    "symbol": "SOLUSDT",
    "decision_count": 174,
    "shadow_compared_count": 166,
    "shadow_label_distribution": {
      "missed_opportunity": 18,
      "reasonable_watch": 37,
      "neutral": 59,
      "bad_watch": 43,
      "good_skip": 9,
      "insufficient_future_data": 8
    },
    "decision_intent_distribution": {
      "watch": 141,
      "soft_skip": 12,
      "enter_candidate": 21
    },
    "bad_watch_count": 43,
    "missed_opportunity_count": 18,
    "bad_watch_rate": 0.259,
    "missed_opportunity_rate": 0.1084,
    "bad_watch_concentrated_in_watch_intent": true,
    "missed_opportunity_concentrated_in_skip_intent": false,
    "label_by_intent": {
      "watch": {
        "missed_opportunity": 15,
        "reasonable_watch": 37,
        "neutral": 44,
        "bad_watch": 43
      },
      "soft_skip": {
        "neutral": 2,
        "good_skip": 9,
        "missed_opportunity": 1
      },
      "enter_candidate": {
        "neutral": 13,
        "missed_opportunity": 2
      }
    },
    "watch_intent_count": 141,
    "skip_intent_count": 12,
    "bad_watch_in_watch_count": 43,
    "missed_in_watch_count": 15,
    "missed_in_skip
```

## 5. Bad watch analysis

- Total bad_watch: **113**
- Average confidence: **0.513**
- By symbol: `{"BTCUSDT": 19, "ETHUSDT": 9, "SOLUSDT": 43, "PEPEUSDT": 42}`
- By intent: `{"watch": 113}`
- By provider: `{"cerebras": 81, "groq": 32}`
- Regime distribution: `{"trend": 65, "range": 6, "volatile": 42}`

**Answers:**

1. **SOL/PEPE concentration?** Yes — alt symbols dominate bad_watch counts.
2. **Mainly watch intent?** Yes — bad_watch applies to watch intent under adverse excursion.
3. **Confidence elevated?** Moderate — average confidence 0.513; not uniformly high.
4. **High vol / down / range?** See regime distribution above; alts in trending/down regimes show elevation.
5. **Risk Governor watch-quality guard?** Recommended — see section 8.

Top reason keywords:

```json
[
  {
    "keyword": "adverse",
    "count": 113
  },
  {
    "keyword": "excursion",
    "count": 113
  },
  {
    "keyword": "dominated",
    "count": 113
  }
]
```

## 6. Missed opportunity analysis

- Total missed_opportunity: **90**
- Average confidence: **0.4726**
- By symbol: `{"BTCUSDT": 10, "ETHUSDT": 23, "SOLUSDT": 18, "PEPEUSDT": 39}`
- By intent: `{"watch": 65, "hard_skip": 13, "soft_skip": 8, "enter_candidate": 4}`
- Regime distribution: `{"trend": 56, "range": 6, "volatile": 28}`

**Answers:**

1. **Concentrated in hard_skip/soft_skip?** Also present under watch intent.
2. **Symbol most prone:** PEPE and ETH historically; see by-symbol counts.
3. **AI overly conservative?** Partial — high skip/watch ratio with selective missed moves; not uniform enter suppression.
4. **Watchlist follow-up vs enter?** Yes — paper-trading design should tier watchlist follow-up before hypothetical enter.

## 7. Provider dependency and quality

- Success distribution: `{"groq": 149, "cerebras": 566}`
- Truncation retry successes: **7**
- Schema repairs: **0**
- Budget guard needed: **True**

## 8. Risk Governor implications

- `watch_quality_guard_sol_high_volatility`
- `watch_quality_guard_meme_adverse_excursion`
- `elevated_mae_watch_downgrade_or_soft_skip`
- `regime_aware_watch_cap:trend`

bad_watch is shadow-labeled adverse excursion under watch intent; Risk Governor should cap watch exposure in high-volatility alts before paper execution.

Consider watchlist follow-up tier instead of immediate enter when skip intent faces directional moves (missed=90).

## 9. Paper-trading readiness assessment

- Infrastructure stable: **True**
- Ready for Stage 4.16 design gate: **True**
- Requires RG rules first: **True**
- Recommended mode: **watchlist_follow_up_and_hypothetical_entry_log**

## 10. Recommended Stage 4.16 next gate

Proceed to **Stage 4.16 paper-trading design gate** (design only — no execution):

- Hypothetical entry/exit log from AI decisions
- Watchlist follow-up tier before enter_candidate
- Risk Governor watch-quality guards for SOL/PEPE high-vol regimes
- Explicit stakeholder approval before any demo order path

---

**Prohibitions remain:** no demo order, ARM, radar, real money, production, btc-auto, mock fallback, new long soaks.

**decision_quality_verdict=`NEEDS_RISK_GOVERNOR_RULES`**
