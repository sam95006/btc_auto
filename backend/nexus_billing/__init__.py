"""NEXUS Billing foundation (BILLING-1).

Plan catalog + subscription lifecycle model. Infrastructure only: no payment
provider, no checkout, no real-money path. The backend subscription model is the
sole source of truth for a member's plan/subscription state.
"""
