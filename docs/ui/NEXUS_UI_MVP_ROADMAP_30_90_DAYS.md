# NEXUS / EATI UI MVP Roadmap (30 / 90 days)

Spec-first. Backend Stage 4.x continues independently. UI must not block backend gates.

---

## Days 0–30 (MVP shell)

**Goal:** Read-only research dashboard shell with demo-safe data.

1. App shell: status bar, sidebar, dark theme, PWA basics  
2. Market Overview + Fleet Center (BTC/ETH first)  
3. Evidence Vault list + decision detail  
4. Risk & Evidence Center (flags only)  
5. AI Assistant stub tabs (explain from local JSON)  
6. Demo data banner + permission gating stubs (Free/Pro)  
7. No trading, no routing, no ARM controls  

**Exit criteria:** Spec pages navigable; demo labeled; zero backend trading mutations.

---

## Days 31–60 (governance surfaces)

1. Provider Shadow Center (read pair-compare / diagnostics)  
2. Paper Trading Lab read-only views  
3. Signal / Anomaly Center + Visual Screener  
4. Reflection Center (patch status display)  
5. Notification Center (event-derived)  
6. Academy Free + Standard content  

**Exit criteria:** Shadow exclusion messaging visible; Stage 4.19 never startable from UI.

---

## Days 61–90 (SaaS readiness)

1. Membership Center UI (plans; billing stub)  
2. Elite exports (PDF/CSV) of evidence summaries  
3. Round Table full layout  
4. Risk Calculator  
5. Team permission stubs (read-only reviewer workflow)  
6. Enterprise checklist page (SSO/audit — design only)  

**Exit criteria:** Clear Free→Elite matrix enforced in UI; still no live trading.

---

## Parallelism with backend

| Track | Owns | Must not touch |
|-------|------|----------------|
| Backend Stage 4.18-P2+ | Routing design / experiments | UI product copy |
| UI Spec / MVP | Docs + read-only frontend | Trading logic, routing, RG, ARM, 4.19 |

---

## Explicit non-roadmap (blocked)

- Live order UI  
- ARM arming  
- Provider routing editors  
- Risk Governor editors  
- Stage 4.19 launch buttons  
- Guaranteed profit marketing  
