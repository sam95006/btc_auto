"""PostgreSQL-backed Corporate platform repository.

Owns owner bootstrap, admin/RBAC, sessions, audit, the CMS (draft/publish/
versioning), settings, and leads. Reuses the shared PostgresPool. It never
touches trading/execution/credential tables.
"""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from backend.nexus_corporate.content import DEFAULT_CONTENT
from backend.nexus_corporate.passwords import hash_password, verify_password
from backend.nexus_persistence_pg.pool import PostgresPool

SESSION_TTL_HOURS = 12
MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 15
BOOTSTRAP_SETTING = "owner_bootstrap"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


class CorporateRepository:
    def __init__(self, pool: PostgresPool):
        self.pool = pool

    # ----- owner bootstrap -----
    def owner_count(self) -> int:
        return int(self.pool.fetchval(
            "SELECT COUNT(*) FROM nexus.corporate_admins WHERE role='OWNER' AND disabled_at IS NULL") or 0)

    def bootstrap_closed(self) -> bool:
        row = self.pool.fetchval("SELECT value FROM nexus.corporate_settings WHERE key=%s", (BOOTSTRAP_SETTING,))
        if row:
            val = row if isinstance(row, dict) else json.loads(row)
            if val.get("closed"):
                return True
        return self.owner_count() > 0

    def create_owner(self, *, email: str, password: str, display_name: str = "", ip: str = "") -> dict[str, Any]:
        # Server-authoritative one-time bootstrap.
        if self.bootstrap_closed():
            raise PermissionError("owner_bootstrap_closed")
        admin = self._create_admin(email=email, password=password, display_name=display_name, role="OWNER")
        self.set_setting(BOOTSTRAP_SETTING, {"closed": True, "closed_at": _now().isoformat()})
        self.add_audit(admin_id=admin["admin_id"], action="owner.bootstrap", target=email, ip=ip)
        return admin

    # ----- admins -----
    def _create_admin(self, *, email: str, password: str, display_name: str, role: str) -> dict[str, Any]:
        email = (email or "").strip().lower()
        if "@" not in email:
            raise ValueError("invalid_email")
        algo, salt, digest = hash_password(password)
        admin_id = _id("adm")
        self.pool.execute(
            "INSERT INTO nexus.corporate_admins (admin_id,email,display_name,password_hash,password_salt,"
            "password_algo,role) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (admin_id, email, display_name or "", digest, salt, algo, role),
        )
        return {"admin_id": admin_id, "email": email, "display_name": display_name or "", "role": role}

    def create_admin(self, *, email: str, password: str, display_name: str, role: str, actor_id: str) -> dict[str, Any]:
        if not self.pool.fetchval("SELECT 1 FROM nexus.corporate_roles WHERE role=%s", (role,)):
            raise ValueError("unknown_role")
        admin = self._create_admin(email=email, password=password, display_name=display_name, role=role)
        self.add_audit(admin_id=actor_id, action="admin.create", target=admin["email"], meta={"role": role})
        return admin

    def get_admin_by_email(self, email: str) -> Optional[dict[str, Any]]:
        rows = self.pool.fetchall(
            "SELECT admin_id,email,display_name,password_hash,password_salt,role,failed_logins,locked_until,disabled_at"
            " FROM nexus.corporate_admins WHERE email=%s", ((email or "").strip().lower(),))
        if not rows:
            return None
        r = rows[0]
        return {"admin_id": r[0], "email": r[1], "display_name": r[2], "password_hash": r[3], "password_salt": r[4],
                "role": r[5], "failed_logins": r[6], "locked_until": r[7], "disabled_at": r[8]}

    def role_permissions(self, role: str) -> set[str]:
        val = self.pool.fetchval("SELECT permissions FROM nexus.corporate_roles WHERE role=%s", (role,))
        if not val:
            return set()
        perms = val if isinstance(val, list) else json.loads(val)
        return set(perms)

    # ----- login / sessions -----
    def login(self, *, email: str, password: str, ip: str = "") -> dict[str, Any]:
        admin = self.get_admin_by_email(email)
        if not admin or admin["disabled_at"] is not None:
            raise PermissionError("invalid_credentials")
        if admin["locked_until"] and admin["locked_until"] > _now():
            raise PermissionError("account_locked")
        if not verify_password(password, admin["password_salt"], admin["password_hash"]):
            self._register_failed_login(admin["admin_id"])
            self.add_audit(admin_id=admin["admin_id"], action="admin.login_failed", target=admin["email"], ip=ip)
            raise PermissionError("invalid_credentials")
        self.pool.execute("UPDATE nexus.corporate_admins SET failed_logins=0, locked_until=NULL WHERE admin_id=%s",
                          (admin["admin_id"],))
        session = self._create_session(admin["admin_id"], ip)
        self.add_audit(admin_id=admin["admin_id"], action="admin.login", target=admin["email"], ip=ip)
        return {"session_id": session["session_id"], "csrf_token": session["csrf_token"],
                "admin": {"admin_id": admin["admin_id"], "email": admin["email"],
                          "display_name": admin["display_name"], "role": admin["role"]}}

    def _register_failed_login(self, admin_id: str) -> None:
        fails = int(self.pool.fetchval(
            "UPDATE nexus.corporate_admins SET failed_logins=failed_logins+1 WHERE admin_id=%s RETURNING failed_logins",
            (admin_id,)) or 0)
        if fails >= MAX_FAILED_LOGINS:
            self.pool.execute("UPDATE nexus.corporate_admins SET locked_until=%s WHERE admin_id=%s",
                              (_now() + timedelta(minutes=LOCK_MINUTES), admin_id))

    def _create_session(self, admin_id: str, ip: str) -> dict[str, Any]:
        session_id = _id("sess")
        csrf = secrets.token_urlsafe(24)
        self.pool.execute(
            "INSERT INTO nexus.corporate_sessions (session_id,admin_id,expires_at,ip,csrf_token) VALUES (%s,%s,%s,%s,%s)",
            (session_id, admin_id, _now() + timedelta(hours=SESSION_TTL_HOURS), ip, csrf))
        return {"session_id": session_id, "csrf_token": csrf}

    def resolve_session(self, session_id: str) -> Optional[dict[str, Any]]:
        if not session_id:
            return None
        rows = self.pool.fetchall(
            "SELECT s.admin_id,s.expires_at,s.revoked_at,s.csrf_token,a.email,a.display_name,a.role,a.disabled_at"
            " FROM nexus.corporate_sessions s JOIN nexus.corporate_admins a ON a.admin_id=s.admin_id"
            " WHERE s.session_id=%s", (session_id,))
        if not rows:
            return None
        r = rows[0]
        if r[2] is not None or r[7] is not None or r[1] <= _now():
            return None
        return {"admin_id": r[0], "csrf_token": r[3], "email": r[4], "display_name": r[5], "role": r[6],
                "permissions": self.role_permissions(r[6])}

    def revoke_session(self, session_id: str) -> None:
        self.pool.execute("UPDATE nexus.corporate_sessions SET revoked_at=NOW() WHERE session_id=%s AND revoked_at IS NULL",
                          (session_id,))

    def revoke_all(self, admin_id: str) -> None:
        self.pool.execute("UPDATE nexus.corporate_sessions SET revoked_at=NOW() WHERE admin_id=%s AND revoked_at IS NULL",
                          (admin_id,))

    # ----- audit -----
    def add_audit(self, *, admin_id: str | None, action: str, target: str = "", meta: dict | None = None, ip: str = "") -> None:
        self.pool.execute(
            "INSERT INTO nexus.corporate_audit (audit_id,admin_id,action,target,meta,ip) VALUES (%s,%s,%s,%s,%s,%s)",
            (_id("aud"), admin_id, action, target, json.dumps(meta or {}), ip))

    def list_audit(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.pool.fetchall(
            "SELECT audit_id,admin_id,action,target,created_at FROM nexus.corporate_audit ORDER BY created_at DESC LIMIT %s",
            (max(1, min(limit, 500)),))
        return [{"audit_id": r[0], "admin_id": r[1], "action": r[2], "target": r[3],
                 "created_at": r[4].isoformat() if r[4] else None} for r in rows]

    # ----- CMS -----
    def get_published(self, slug: str) -> Optional[dict[str, Any]]:
        val = self.pool.fetchval("SELECT published_json FROM nexus.corporate_content WHERE slug=%s", (slug,))
        if val:
            return val if isinstance(val, dict) else json.loads(val)
        # Seed default: the site ships with backend-owned published defaults.
        return DEFAULT_CONTENT.get(slug)

    def get_content(self, slug: str) -> Optional[dict[str, Any]]:
        rows = self.pool.fetchall(
            "SELECT slug,kind,status,draft_json,published_json,published_version,updated_at,published_at"
            " FROM nexus.corporate_content WHERE slug=%s", (slug,))
        if not rows:
            default = DEFAULT_CONTENT.get(slug)
            if default is None:
                return None
            return {"slug": slug, "kind": "section", "status": "PUBLISHED", "draft": default,
                    "published": default, "published_version": 1, "seeded": True}
        r = rows[0]
        return {"slug": r[0], "kind": r[1], "status": r[2],
                "draft": r[3] if isinstance(r[3], dict) else json.loads(r[3] or "{}"),
                "published": (r[4] if isinstance(r[4], dict) else json.loads(r[4])) if r[4] else None,
                "published_version": r[5], "updated_at": r[6].isoformat() if r[6] else None,
                "published_at": r[7].isoformat() if r[7] else None, "seeded": False}

    def save_draft(self, *, slug: str, body: dict[str, Any], actor_id: str) -> None:
        self.pool.execute(
            "INSERT INTO nexus.corporate_content (slug,kind,status,draft_json,updated_at) VALUES (%s,'section','DRAFT',%s,NOW())"
            " ON CONFLICT (slug) DO UPDATE SET draft_json=EXCLUDED.draft_json, status='DRAFT', updated_at=NOW()",
            (slug, json.dumps(body)))
        self.add_audit(admin_id=actor_id, action="content.draft", target=slug)

    def publish(self, *, slug: str, actor_id: str) -> dict[str, Any]:
        content = self.get_content(slug)
        if content is None:
            raise ValueError("unknown_slug")
        body = content["draft"]
        version = int(content.get("published_version") or 0) + 1
        self.pool.execute(
            "INSERT INTO nexus.corporate_content (slug,kind,status,draft_json,published_json,published_version,updated_at,published_at)"
            " VALUES (%s,'section','PUBLISHED',%s,%s,%s,NOW(),NOW())"
            " ON CONFLICT (slug) DO UPDATE SET published_json=EXCLUDED.published_json, status='PUBLISHED',"
            " published_version=EXCLUDED.published_version, updated_at=NOW(), published_at=NOW()",
            (slug, json.dumps(body), json.dumps(body), version))
        self.pool.execute(
            "INSERT INTO nexus.corporate_content_versions (version_id,slug,version,json,created_by) VALUES (%s,%s,%s,%s,%s)",
            (_id("ver"), slug, version, json.dumps(body), actor_id))
        self.add_audit(admin_id=actor_id, action="content.publish", target=slug, meta={"version": version})
        return {"slug": slug, "published_version": version}

    def list_content(self) -> list[dict[str, Any]]:
        rows = self.pool.fetchall("SELECT slug,status,published_version,updated_at FROM nexus.corporate_content ORDER BY slug")
        db = {r[0]: {"slug": r[0], "status": r[1], "published_version": r[2],
                     "updated_at": r[3].isoformat() if r[3] else None} for r in rows}
        for slug in DEFAULT_CONTENT:
            db.setdefault(slug, {"slug": slug, "status": "PUBLISHED", "published_version": 1, "seeded": True})
        return sorted(db.values(), key=lambda x: x["slug"])

    # ----- settings -----
    def get_setting(self, key: str) -> Optional[dict[str, Any]]:
        val = self.pool.fetchval("SELECT value FROM nexus.corporate_settings WHERE key=%s", (key,))
        if val is None:
            return None
        return val if isinstance(val, dict) else json.loads(val)

    def set_setting(self, key: str, value: dict[str, Any]) -> None:
        self.pool.execute(
            "INSERT INTO nexus.corporate_settings (key,value,updated_at) VALUES (%s,%s,NOW())"
            " ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()",
            (key, json.dumps(value)))

    # ----- leads -----
    def add_lead(self, *, name: str, email: str, company: str = "", message: str = "", kind: str = "contact") -> str:
        lead_id = _id("lead")
        self.pool.execute(
            "INSERT INTO nexus.corporate_leads (lead_id,name,email,company,message,kind) VALUES (%s,%s,%s,%s,%s,%s)",
            (lead_id, name or "", (email or "").strip().lower(), company or "", message or "", kind))
        return lead_id

    def list_leads(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.pool.fetchall(
            "SELECT lead_id,name,email,company,kind,status,created_at FROM nexus.corporate_leads ORDER BY created_at DESC LIMIT %s",
            (max(1, min(limit, 500)),))
        return [{"lead_id": r[0], "name": r[1], "email": r[2], "company": r[3], "kind": r[4], "status": r[5],
                 "created_at": r[6].isoformat() if r[6] else None} for r in rows]
