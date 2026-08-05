"""Exceptions for the Intelligence Publishing Gateway."""
from __future__ import annotations


class PublishingGatewayError(Exception):
    """Base gateway error (fail-closed)."""


class DenyTrapError(PublishingGatewayError):
    """Denied private field detected in publish path."""


class SchemaVersionError(PublishingGatewayError):
    """Schema version mismatch or missing."""


class AggregationThresholdError(PublishingGatewayError):
    """Payload failed aggregation / k-anonymity threshold."""


class EnvironmentGuardError(PublishingGatewayError):
    """Gateway invoked outside LOCAL/STAGING."""


class PrivateImportError(PublishingGatewayError):
    """Forbidden private-core / trading import detected."""
