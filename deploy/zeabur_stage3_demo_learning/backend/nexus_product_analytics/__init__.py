"""Minimal server-safe product analytics foundation (no external platform)."""
from backend.nexus_product_analytics.events import (
    PRODUCT_EVENT_NAMES,
    ProductAnalyticsStore,
    get_analytics_store,
    record_event,
)

__all__ = [
    "PRODUCT_EVENT_NAMES",
    "ProductAnalyticsStore",
    "get_analytics_store",
    "record_event",
]
