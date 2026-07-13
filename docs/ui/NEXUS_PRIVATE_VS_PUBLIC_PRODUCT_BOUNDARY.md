# NEXUS / EATI — Private Operator UI vs Future Public SaaS

**Status:** Architecture labels only (no product launch claim)  
**Date:** 2026-07-13  
**Audience:** Operators, UI implementers  

This document draws a hard product boundary between the **Private Operator Dashboard** (now) and a **Future Public SaaS** surface (not implemented). It does not authorize billing, customer accounts, live trading, or managed products.

---

## 1. Private Operator UI (now)

| Label | Meaning |
|-------|---------|
| Product surface | Read-only research / governance / evidence dashboard |
| Audience | Internal operators and researchers |
| Mode | Private Operator Mode ON |
| Data | DEMO DATA or operator-local read-only fixtures (`frontend/src/demo/`) |
| Capabilities | Stage gate status, provider/shadow summaries, paper-lab graduation counts, risk flags, evidence vault list |
| Mutations | None — no order, ARM, routing, or Risk Governor editors |

**In scope now**

- Overview with Stage Gate + Safety Status cards  
- Risk & Evidence Center (flags only)  
- Provider Shadow Center (compare + exclusion messaging)  
- Paper Trading Lab (read-only counts)  
- Evidence / Reflection / Signals / Fleets (observe language)  
- Membership page as **Future Public SaaS labels only**  

**Explicitly out of scope now**

- Live trade routes (`/trade`, `/orders`, …)  
- Order / ARM / production APIs  
- Provider routing editors  
- Risk Governor editors  
- Stage 4.19 start controls  

---

## 2. Future Public SaaS (architecture label only)

| Label | Meaning |
|-------|---------|
| Product surface | Future member-facing research SaaS (design placeholder) |
| Audience | Hypothetical Free → Enterprise members |
| Status | **Future only · Not implemented · No billing** |
| Capabilities (planned labels) | Tiered read access, academy content, export stubs, team reviewer stubs |

Membership tiers shown in the UI are **architecture placeholders**. They must not imply:

- Active billing or payments  
- Customer account signup / auth product  
- Copy trading  
- Managed accounts  
- Guaranteed profit or investment advice  

---

## 3. Boundary matrix

| Concern | Private Operator (now) | Future Public SaaS |
|---------|------------------------|--------------------|
| Read-only dashboard | Yes | Future design |
| DEMO DATA labeling | Required | Required if demo |
| Stage / graduation / safety flags | Yes | Future (read-only) |
| Billing | No | No (not implemented) |
| Customer accounts | No | No (not implemented) |
| API key collection UI | No | No |
| Copy trading | No | No |
| Managed accounts | No | No |
| Guaranteed profit marketing | No | No |
| Live orders / ARM / routing edit | No | No |

---

## 4. Safety banner contract

Private Operator UI must keep a global SafetyBanner:

`READ-ONLY · RESEARCH MODE · NOT INVESTMENT ADVICE · NO LIVE TRADING`

Plus Private Operator Mode messaging on Overview (and related chrome) so operators never confuse this shell with a public trading product.

---

## 5. Related docs

- `docs/ui/NEXUS_UI_PRODUCT_SPEC_V1.md`  
- `docs/ui/NEXUS_UI_MVP_ROADMAP_30_90_DAYS.md`  
- `docs/ui/NEXUS_UI_MVP1_PRIVATE_OPERATOR_DASHBOARD_REPORT.md`  
