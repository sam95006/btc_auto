# NEXUS / EATI UI Sitemap v1

Research-only / read-only product map. No order execution routes.

```
/
├── /overview                    # Market Overview
├── /fleets
│   ├── /fleets/btc
│   ├── /fleets/eth
│   ├── /fleets/sol
│   └── /fleets/pepe
├── /round-table                 # AI Round Table
├── /signals                     # Signal / Anomaly Center
├── /screener                    # Visual Screener (4Q)
├── /risk-evidence               # Risk & Evidence Center
├── /evidence
│   ├── /evidence/vault
│   └── /evidence/:decisionId
├── /reflection                  # Reflection Center
├── /provider-shadow             # Provider Shadow Center
├── /paper-lab                   # Paper Trading Lab (read-only)
├── /assistant                   # AI Assistant (or right-rail)
├── /academy
│   ├── /academy/free
│   ├── /academy/standard
│   └── /academy/pro
├── /calculator                  # Risk Calculator
├── /notifications
├── /membership
│   ├── /membership/plans
│   └── /membership/billing      # future SaaS; stub in MVP
└── /settings
    ├── /settings/profile
    ├── /settings/safety-banner  # always show research-only
    └── /settings/data-sources   # read-only mapping view
```

## Sidebar order (desktop)

1. Overview  
2. Fleets  
3. Round Table  
4. Signals  
5. Screener  
6. Risk & Evidence  
7. Evidence Vault  
8. Reflection  
9. Provider Shadow  
10. Paper Lab  
11. Academy  
12. Calculator  
13. Notifications  
14. Membership  

## Mobile PWA tabs (primary)

Overview · Signals · Fleets · Evidence · More (rest)

## Explicitly absent routes

- `/trade`, `/orders`, `/arm`, `/production`, `/btc-auto`, `/routing-edit`
