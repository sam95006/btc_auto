"""Repository helpers for alpha product services."""
from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.nexus_persistence_pg.pool import PostgresPool


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProductRepository:
    def __init__(self, pool: PostgresPool):
        self.pool = pool

    def create_account(self, email: str, password_hash: str) -> str:
        account_id = f"acct_{uuid.uuid4().hex[:16]}"
        identity_id = f"id_{uuid.uuid4().hex[:16]}"
        self.pool.execute(
            """
            INSERT INTO nexus.accounts (account_id, email, status)
            VALUES (%s, %s, 'active')
            """,
            (account_id, email),
        )
        self.pool.execute(
            """
            INSERT INTO nexus.email_identities (identity_id, account_id, email, verified)
            VALUES (%s, %s, %s, FALSE)
            """,
            (identity_id, account_id, email),
        )
        self.pool.execute(
            """
            INSERT INTO nexus.password_credentials (account_id, password_hash)
            VALUES (%s, %s)
            """,
            (account_id, password_hash),
        )
        return account_id

    def get_account_by_email(self, email: str) -> dict[str, Any] | None:
        rows = self.pool.fetchall(
            """
            SELECT a.account_id, a.email, a.status, pc.password_hash
            FROM nexus.accounts a
            JOIN nexus.email_identities ei ON ei.account_id = a.account_id
            LEFT JOIN nexus.password_credentials pc ON pc.account_id = a.account_id
            WHERE ei.email = %s
            LIMIT 1
            """,
            (email,),
        )
        if not rows:
            return None
        account_id, em, status, password_hash = rows[0]
        return {
            "account_id": account_id,
            "email": em,
            "status": status,
            "password_hash": password_hash,
        }

    def create_session(self, account_id: str, *, ttl_hours: int = 24) -> str:
        session_id = f"sess_{uuid.uuid4().hex}"
        expires = _utcnow() + timedelta(hours=ttl_hours)
        self.pool.execute(
            """
            INSERT INTO nexus.auth_sessions (session_id, account_id, expires_at)
            VALUES (%s, %s, %s)
            """,
            (session_id, account_id, expires),
        )
        return session_id

    def get_active_session(self, session_id: str) -> dict[str, Any] | None:
        rows = self.pool.fetchall(
            """
            SELECT s.session_id, s.account_id, s.expires_at, s.revoked_at, a.email, a.status
            FROM nexus.auth_sessions s
            JOIN nexus.accounts a ON a.account_id = s.account_id
            WHERE s.session_id = %s
            LIMIT 1
            """,
            (session_id,),
        )
        if not rows:
            return None
        sid, account_id, expires_at, revoked_at, email, status = rows[0]
        if revoked_at is not None:
            return None
        if expires_at and expires_at < _utcnow():
            return None
        return {
            "session_id": sid,
            "account_id": account_id,
            "email": email,
            "status": status,
        }

    def revoke_session(self, session_id: str) -> None:
        self.pool.execute(
            "UPDATE nexus.auth_sessions SET revoked_at = NOW() WHERE session_id = %s",
            (session_id,),
        )

    def issue_one_time_token(self, account_id: str, purpose: str, *, ttl_minutes: int = 30) -> str:
        raw = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        token_id = f"tok_{uuid.uuid4().hex[:16]}"
        expires = _utcnow() + timedelta(minutes=ttl_minutes)
        self.pool.execute(
            """
            INSERT INTO nexus.one_time_tokens (token_id, account_id, purpose, token_hash, expires_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (token_id, account_id, purpose, token_hash, expires),
        )
        return raw

    def consume_one_time_token(self, raw: str, purpose: str) -> str | None:
        token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        rows = self.pool.fetchall(
            """
            SELECT token_id, account_id, expires_at, consumed_at
            FROM nexus.one_time_tokens
            WHERE token_hash = %s AND purpose = %s
            LIMIT 1
            """,
            (token_hash, purpose),
        )
        if not rows:
            return None
        token_id, account_id, expires_at, consumed_at = rows[0]
        if consumed_at is not None or (expires_at and expires_at < _utcnow()):
            return None
        self.pool.execute(
            "UPDATE nexus.one_time_tokens SET consumed_at = NOW() WHERE token_id = %s",
            (token_id,),
        )
        return account_id

    def grant_entitlement(self, account_id: str, product_code: str) -> None:
        entitlement_id = f"ent_{uuid.uuid4().hex[:16]}"
        self.pool.execute(
            """
            INSERT INTO nexus.entitlements (entitlement_id, account_id, product_code, active)
            VALUES (%s, %s, %s, TRUE)
            ON CONFLICT DO NOTHING
            """,
            (entitlement_id, account_id, product_code),
        )

    def active_entitlements(self, account_id: str) -> list[str]:
        rows = self.pool.fetchall(
            """
            SELECT product_code FROM nexus.entitlements
            WHERE account_id = %s AND active = TRUE
              AND (expires_at IS NULL OR expires_at > NOW())
            """,
            (account_id,),
        )
        return [r[0] for r in rows]

    def profile(self, account_id: str) -> dict[str, Any]:
        self.pool.execute(
            """
            INSERT INTO nexus.account_profiles (account_id, display_name)
            VALUES (%s, '')
            ON CONFLICT (account_id) DO NOTHING
            """,
            (account_id,),
        )
        row = self.pool.fetchall(
            """
            SELECT a.email, p.display_name, p.locale, p.timezone, p.privacy_preferences, p.version
            FROM nexus.accounts a JOIN nexus.account_profiles p ON p.account_id = a.account_id
            WHERE a.account_id = %s
            """,
            (account_id,),
        )[0]
        return {
            "account_id": account_id, "email": row[0], "display_name": row[1],
            "locale": row[2], "timezone": row[3], "privacy_preferences": row[4], "version": row[5],
        }

    def update_profile(self, account_id: str, payload: dict[str, Any], version: int | None) -> dict[str, Any]:
        current = self.profile(account_id)
        if version is not None and version != current["version"]:
            raise ValueError("profile_version_conflict")
        display_name = str(payload.get("display_name", current["display_name"]))[:120]
        locale = str(payload.get("locale", current["locale"]))[:24]
        timezone_name = str(payload.get("timezone", current["timezone"]))[:64]
        privacy = payload.get("privacy_preferences", current["privacy_preferences"])
        self.pool.execute(
            """
            UPDATE nexus.account_profiles
            SET display_name=%s, locale=%s, timezone=%s, privacy_preferences=%s::jsonb,
                updated_at=NOW(), version=version+1
            WHERE account_id=%s
            """,
            (display_name, locale, timezone_name, json.dumps(privacy), account_id),
        )
        return self.profile(account_id)

    def member_preferences(self, account_id: str) -> dict[str, Any]:
        self.pool.execute(
            "INSERT INTO nexus.member_preferences (account_id) VALUES (%s) ON CONFLICT (account_id) DO NOTHING",
            (account_id,),
        )
        row = self.pool.fetchall(
            "SELECT preferences_json, last_viewed_at, version FROM nexus.member_preferences WHERE account_id=%s",
            (account_id,),
        )[0]
        return {"preferences": row[0], "last_viewed_at": row[1].isoformat() if row[1] else None, "version": row[2]}

    def update_member_preferences(self, account_id: str, preferences: dict[str, Any]) -> dict[str, Any]:
        self.member_preferences(account_id)
        self.pool.execute(
            """
            UPDATE nexus.member_preferences
            SET preferences_json=%s::jsonb, updated_at=NOW(), version=version+1
            WHERE account_id=%s
            """,
            (json.dumps(preferences), account_id),
        )
        return self.member_preferences(account_id)

    def touch_last_viewed(self, account_id: str) -> None:
        self.member_preferences(account_id)
        self.pool.execute("UPDATE nexus.member_preferences SET last_viewed_at=NOW() WHERE account_id=%s", (account_id,))

    def watchlist_symbols(self, account_id: str) -> list[str]:
        rows = self.pool.fetchall(
            """
            SELECT wi.symbol FROM nexus.watchlists w JOIN nexus.watchlist_items wi ON wi.watchlist_id=w.watchlist_id
            WHERE w.account_id=%s AND w.archived_at IS NULL ORDER BY wi.added_at ASC
            """,
            (account_id,),
        )
        return [row[0] for row in rows]

    def add_watchlist_symbol(self, account_id: str, symbol: str, *, limit: int = 30) -> list[str]:
        current = self.watchlist_symbols(account_id)
        if symbol not in current and len(current) >= limit:
            raise ValueError("watchlist_limit_reached")
        rows = self.pool.fetchall(
            "SELECT watchlist_id FROM nexus.watchlists WHERE account_id=%s AND archived_at IS NULL LIMIT 1", (account_id,)
        )
        watchlist_id = rows[0][0] if rows else f"wl_{uuid.uuid4().hex[:16]}"
        if not rows:
            self.pool.execute("INSERT INTO nexus.watchlists (watchlist_id, account_id) VALUES (%s, %s)", (watchlist_id, account_id))
        self.pool.execute(
            "INSERT INTO nexus.watchlist_items (watchlist_id, symbol) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (watchlist_id, symbol),
        )
        return self.watchlist_symbols(account_id)

    def remove_watchlist_symbol(self, account_id: str, symbol: str) -> list[str]:
        self.pool.execute(
            """
            DELETE FROM nexus.watchlist_items wi USING nexus.watchlists w
            WHERE wi.watchlist_id=w.watchlist_id AND w.account_id=%s AND wi.symbol=%s
            """,
            (account_id, symbol),
        )
        return self.watchlist_symbols(account_id)

    def notification_preferences(self, account_id: str) -> dict[str, Any]:
        self.pool.execute(
            "INSERT INTO nexus.notification_preferences (account_id) VALUES (%s) ON CONFLICT (account_id) DO NOTHING",
            (account_id,),
        )
        row = self.pool.fetchall(
            """
            SELECT in_app_enabled, market_alerts_enabled, email_enabled, muted_symbols, version
            FROM nexus.notification_preferences WHERE account_id=%s
            """,
            (account_id,),
        )[0]
        return {
            "in_app_enabled": row[0], "market_alerts_enabled": row[1], "email_enabled": row[2],
            "muted_symbols": row[3], "version": row[4],
        }

    def update_notification_preferences(self, account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.notification_preferences(account_id)
        values = (
            bool(payload.get("in_app_enabled", current["in_app_enabled"])),
            bool(payload.get("market_alerts_enabled", current["market_alerts_enabled"])),
            bool(payload.get("email_enabled", current["email_enabled"])),
            json.dumps(payload.get("muted_symbols", current["muted_symbols"])),
            account_id,
        )
        self.pool.execute(
            """
            UPDATE nexus.notification_preferences
            SET in_app_enabled=%s, market_alerts_enabled=%s, email_enabled=%s, muted_symbols=%s::jsonb,
                updated_at=NOW(), version=version+1 WHERE account_id=%s
            """,
            values,
        )
        return self.notification_preferences(account_id)

    def list_notifications(self, account_id: str) -> list[dict[str, Any]]:
        rows = self.pool.fetchall(
            """
            SELECT notification_id, category, symbol, title, body, read_at, created_at
            FROM nexus.notifications WHERE account_id=%s AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY created_at DESC LIMIT 100
            """,
            (account_id,),
        )
        return [
            {"id": r[0], "category": r[1], "symbol": r[2], "title": r[3], "body": r[4],
             "read": r[5] is not None, "created_at": r[6].isoformat()}
            for r in rows
        ]

    def mark_notification_read(self, account_id: str, notification_id: str) -> None:
        self.pool.execute(
            "UPDATE nexus.notifications SET read_at=COALESCE(read_at, NOW()) WHERE notification_id=%s AND account_id=%s",
            (notification_id, account_id),
        )

    def bind_role(self, account_id: str, role_id: str, org_id: str | None = None) -> None:
        binding_id = f"bind_{uuid.uuid4().hex[:16]}"
        self.pool.execute(
            """
            INSERT INTO nexus.rbac_bindings (binding_id, account_id, role_id, org_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (binding_id, account_id, role_id, org_id),
        )

    def role_permissions(self, account_id: str, org_id: str | None = None) -> set[str]:
        rows = self.pool.fetchall(
            """
            SELECT rp.permission_code
            FROM nexus.rbac_bindings rb
            JOIN nexus.role_permissions rp ON rp.role_id = rb.role_id
            WHERE rb.account_id = %s
              AND (%s::text IS NULL OR rb.org_id IS NULL OR rb.org_id = %s::text)
            """,
            (account_id, org_id, org_id),
        )
        return {r[0] for r in rows}

    def append_product_audit(
        self,
        *,
        actor_account_id: str | None,
        action: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        detail: dict[str, Any] | None = None,
        org_id: str | None = None,
        prev_hash: str | None = None,
    ) -> str:
        event_id = f"paudit_{uuid.uuid4().hex[:16]}"
        detail_json = detail or {}
        content_hash = hashlib.sha256(
            f"{event_id}:{action}:{resource_type}:{resource_id}:{detail_json}".encode("utf-8")
        ).hexdigest()
        self.pool.execute(
            """
            INSERT INTO nexus.product_audit_events
              (event_id, actor_account_id, org_id, action, resource_type, resource_id,
               detail_json, prev_hash, content_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
            """,
            (
                event_id,
                actor_account_id,
                org_id,
                action,
                resource_type,
                resource_id,
                __import__("json").dumps(detail_json),
                prev_hash,
                content_hash,
            ),
        )
        return event_id
