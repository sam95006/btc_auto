"""Personal Market Intelligence product access (PERSONAL-1).

Wires the existing membership / entitlement / quota foundation to real,
member-safe personal product actions. Backend is authoritative: every paid
product API is gated by Authentication AND Entitlement AND (when metered) Quota.
Frontend feature locking is UX only, never authorization.

This surface contains no private trading execution, no Founder controls, no
Enterprise organization logic, and no AI-agent product.
"""
