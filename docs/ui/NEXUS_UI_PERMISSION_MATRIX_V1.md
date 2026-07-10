# NEXUS / EATI UI Permission Matrix v1

Legend: `R` = read · `-` = hidden/denied · `L` = limited · `W` = write (non-trading only)

| Surface | Free | Standard | Pro | Elite | Team | Enterprise |
|---------|------|----------|-----|-------|------|------------|
| Market Overview (BTC/ETH basic) | R | R | R | R | R | R |
| Multi-symbol radar cards | - | R | R | R | R | R |
| AI Fleet Center | - | L | R | R | R | R |
| AI Round Table (full) | - | - | R | R | R | R |
| Signal / Anomaly Center | L | R | R | R | R | R |
| Visual Screener | - | R | R | R | R | R |
| Risk & Evidence Center | L | L | R | R | R | R |
| Evidence Vault (basic) | - | - | R | R | R | R |
| Evidence Vault (full) | - | - | - | R | R | R |
| Reflection Center | - | - | R | R | R | R |
| Provider Shadow Center | - | - | - | R | R | R |
| Paper Trading Lab | - | - | R | R | R | R |
| AI Assistant (basic) | L | R | R | R | R | R |
| AI Assistant (full tabs) | - | L | R | R | R | R |
| Academy Free | R | R | R | R | R | R |
| Academy Standard | - | R | R | R | R | R |
| Academy Pro | - | - | R | R | R | R |
| Risk Calculator | L | R | R | R | R | R |
| Notifications (browser) | - | R | R | R | R | R |
| PDF/CSV export | - | - | - | R | R | R |
| Team permissions / journal | - | - | - | - | R/W | R/W |
| SSO / audit / API ACL | - | - | - | - | - | R/W |
| Order / ARM / live trade | - | - | - | - | - | - |
| Edit provider routing | - | - | - | - | - | - |
| Edit Risk Governor | - | - | - | - | - | - |
| Start Stage 4.19 | - | - | - | - | - | - |

## Safety invariants (all tiers)

- UI cannot enable ARM, production, or btc-auto.  
- UI cannot change provider routing or Risk Governor thresholds.  
- UI cannot place orders or paper-execute.  
- Demo data must be labeled DEMO DATA / READ-ONLY / NOT INVESTMENT ADVICE.
