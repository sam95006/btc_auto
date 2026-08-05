"""Subscription entitlement state machine (billing disabled by default)."""

from __future__ import annotations

from dataclasses import dataclass


class BillingDisabledError(RuntimeError):
    code = "BILLING_DISABLED"


STATES = frozenset(
    {
        "NONE",
        "PENDING_VERIFY",
        "ACTIVE",
        "IN_GRACE",
        "ON_HOLD",
        "CANCELED_ACTIVE_UNTIL_EXPIRY",
        "EXPIRED",
        "REFUNDED",
        "REVOKED",
        "RESTORE_CONFLICT",
    }
)

TRANSITIONS: dict[tuple[str, str], str] = {
    ("NONE", "purchase_started_or_restore"): "PENDING_VERIFY",
    ("PENDING_VERIFY", "verify_success"): "ACTIVE",
    ("PENDING_VERIFY", "verify_failed"): "NONE",
    ("ACTIVE", "billing_retry"): "IN_GRACE",
    ("ACTIVE", "account_hold"): "ON_HOLD",
    ("ACTIVE", "user_canceled_auto_renew"): "CANCELED_ACTIVE_UNTIL_EXPIRY",
    ("CANCELED_ACTIVE_UNTIL_EXPIRY", "period_end"): "EXPIRED",
    ("ACTIVE", "store_refund"): "REFUNDED",
    ("ACTIVE", "store_revoke"): "REVOKED",
    ("EXPIRED", "repurchase_or_restore"): "PENDING_VERIFY",
    ("RESTORE_CONFLICT", "manual_resolution"): "ACTIVE",
    ("IN_GRACE", "verify_success"): "ACTIVE",
    ("IN_GRACE", "period_end"): "EXPIRED",
    ("ON_HOLD", "verify_success"): "ACTIVE",
    ("ON_HOLD", "period_end"): "EXPIRED",
}


@dataclass
class EntitlementRecord:
    user_id: str
    state: str = "NONE"
    product_id: str | None = None
    original_transaction_id: str | None = None


@dataclass
class VerifyResult:
    ok: bool
    state: str
    code: str
    detail: str = ""


class EntitlementService:
    """Server-side entitlement transitions. Live billing is hard-banned unless flags flip."""

    def __init__(
        self,
        *,
        live_billing_enabled: bool = False,
        real_iap_products_enabled: bool = False,
        product_allowlist: set[str] | None = None,
    ) -> None:
        self.live_billing_enabled = live_billing_enabled
        self.real_iap_products_enabled = real_iap_products_enabled
        self.product_allowlist = product_allowlist or set()
        self._records: dict[str, EntitlementRecord] = {}

    def get(self, user_id: str) -> EntitlementRecord:
        if user_id not in self._records:
            self._records[user_id] = EntitlementRecord(user_id=user_id)
        return self._records[user_id]

    def apply_event(self, user_id: str, event: str) -> EntitlementRecord:
        rec = self.get(user_id)
        key = (rec.state, event)
        if key not in TRANSITIONS:
            raise ValueError(f"illegal_transition:{rec.state}:{event}")
        rec.state = TRANSITIONS[key]
        return rec

    def verify_purchase(
        self,
        user_id: str,
        *,
        platform: str,
        product_id: str,
        signed_transaction: str,
        bundle_ok: bool = True,
        signature_ok: bool = True,
    ) -> VerifyResult:
        if not self.live_billing_enabled or not self.real_iap_products_enabled:
            return VerifyResult(False, self.get(user_id).state, "BILLING_DISABLED")
        if not self.product_allowlist:
            return VerifyResult(False, self.get(user_id).state, "PRODUCT_NOT_ALLOWLISTED")
        if product_id not in self.product_allowlist:
            return VerifyResult(False, self.get(user_id).state, "PRODUCT_NOT_ALLOWLISTED")
        if not bundle_ok:
            return VerifyResult(False, self.get(user_id).state, "BUNDLE_MISMATCH")
        if not signature_ok or not signed_transaction:
            return VerifyResult(False, self.get(user_id).state, "SIGNATURE_INVALID")
        if platform not in {"ios", "android"}:
            return VerifyResult(False, self.get(user_id).state, "PLATFORM_UNSUPPORTED")
        self.apply_event(user_id, "purchase_started_or_restore")
        rec = self.apply_event(user_id, "verify_success")
        rec.product_id = product_id
        rec.original_transaction_id = f"{platform}:{signed_transaction[:12]}"
        return VerifyResult(True, rec.state, "OK")

    def restore(self, user_id: str, *, conflict: bool = False) -> VerifyResult:
        if not self.live_billing_enabled:
            return VerifyResult(False, self.get(user_id).state, "BILLING_DISABLED")
        if conflict:
            rec = self.get(user_id)
            rec.state = "RESTORE_CONFLICT"
            return VerifyResult(False, rec.state, "ALREADY_OWNED_OTHER_USER")
        return self.verify_purchase(
            user_id,
            platform="ios",
            product_id=next(iter(self.product_allowlist), "none"),
            signed_transaction="restore-token",
        )

    def cancel(self, user_id: str) -> EntitlementRecord:
        return self.apply_event(user_id, "user_canceled_auto_renew")

    def refund(self, user_id: str) -> EntitlementRecord:
        return self.apply_event(user_id, "store_refund")
