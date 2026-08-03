# NEXUS Private / Public Separation Design V1

## Zones

### Private Zone
Founder Private Autonomous Trading Core: research, risk, execution, reflection, Lesson Memory.

### Publishing Gateway
Sanitizes and transforms Private Intelligence into Decision Intelligence artifacts allowed in public cloud.

### Public Decision Cloud
Multi-tenant Decision Integrity Platform for ICP users.

## Must be separate

| Dimension | Private | Public |
|---|---|---|
| Services | Founder runtime only | Multi-tenant app services |
| Secrets | Founder exchange/AI keys | Tenant auth + public vendor keys |
| Databases | Private ledgers / lessons | Decision Objects / Graph |
| Permissions | Founder sole operator | User ownership + least privilege |
| Deployments | Isolated, non-commercial | Commercial product deploys |
| Audit logs | Private security audit | Tenant-visible activity + admin audit |
| Data classifications | Secret / strategy / account | Decision Intelligence / public market |
| Withdrawal & correction | N/A (no public custody) | User correction events; no silent rewrite |

## Withdrawal and correction flow (public)

1. User requests correction/withdrawal of a Decision record field
2. Append correction event; prior version remains replayable
3. Gateway never pulls private Lesson Memory to “fix” public history

## Forbidden crossings

- Private strategies → public docs/UI
- Private fills → public Outcome without sanitization policy
- Public tenants → private execution controls
