from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal


RequestStatus = Literal["queued", "processing", "completed", "rejected"]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_secret(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


class Database:
    def __init__(self, home: Path):
        self.home = home.resolve()
        self.state_dir = self.home / ".ez-hack"
        self.path = self.state_dir / "ez-hack.sqlite3"
        self.dashboard_path = self.home / "DASHBOARD.md"
        self.project_context_path = self.home / "PROJECT_CONTEXT.md"
        self.contact_map_path = self.home / "host" / "CONTACT_MAP.md"

    def connect(self) -> sqlite3.Connection:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def ensure_schema(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS operators (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL CHECK(role IN ('host', 'operator')),
                    access_level INTEGER NOT NULL DEFAULT 10
                        CHECK(access_level BETWEEN 0 AND 100),
                    token_hash TEXT NOT NULL UNIQUE,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS invites (
                    code_hash TEXT PRIMARY KEY,
                    role TEXT NOT NULL DEFAULT 'operator' CHECK(role = 'operator'),
                    access_level INTEGER NOT NULL DEFAULT 10
                        CHECK(access_level BETWEEN 0 AND 100),
                    created_by TEXT NOT NULL REFERENCES operators(id),
                    expires_at TEXT NOT NULL,
                    max_uses INTEGER NOT NULL CHECK(max_uses > 0),
                    uses INTEGER NOT NULL DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS requests (
                    id TEXT PRIMARY KEY,
                    sender_id TEXT NOT NULL REFERENCES operators(id),
                    kind TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    details TEXT NOT NULL DEFAULT '',
                    notify_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'queued'
                        CHECK(status IN ('queued', 'processing', 'completed', 'rejected')),
                    created_at TEXT NOT NULL,
                    claimed_at TEXT,
                    completed_at TEXT,
                    outcome TEXT
                );

                CREATE INDEX IF NOT EXISTS requests_fifo
                    ON requests(status, created_at, id);

                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recipient_id TEXT NOT NULL REFERENCES operators(id),
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    request_id TEXT REFERENCES requests(id),
                    created_at TEXT NOT NULL,
                    read_at TEXT
                );

                CREATE INDEX IF NOT EXISTS notifications_inbox
                    ON notifications(recipient_id, read_at, created_at, id);

                CREATE TABLE IF NOT EXISTS contact_routes (
                    source_id TEXT NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
                    recipient_id TEXT NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(source_id, recipient_id),
                    CHECK(source_id != recipient_id)
                );

                CREATE INDEX IF NOT EXISTS contact_routes_source
                    ON contact_routes(source_id, recipient_id);

                CREATE TABLE IF NOT EXISTS project_state (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    dashboard_revision INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );

                """
            )
            self._ensure_column(db, "requests", "expected_result", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(
                db, "requests", "affected_tasks_json", "TEXT NOT NULL DEFAULT '[]'"
            )
            self._ensure_column(db, "requests", "base_dashboard_revision", "INTEGER")
            self._ensure_column(db, "requests", "defer_reason", "TEXT")
            self._ensure_column(db, "requests", "recheck_after", "TEXT")
            self._ensure_column(
                db, "requests", "deferral_count", "INTEGER NOT NULL DEFAULT 0"
            )
            self._ensure_column(
                db,
                "operators",
                "access_level",
                "INTEGER NOT NULL DEFAULT 10 CHECK(access_level BETWEEN 0 AND 100)",
            )
            self._ensure_column(
                db,
                "invites",
                "access_level",
                "INTEGER NOT NULL DEFAULT 10 CHECK(access_level BETWEEN 0 AND 100)",
            )
            db.execute("UPDATE operators SET access_level = 100 WHERE role = 'host'")
            db.execute(
                """
                INSERT OR IGNORE INTO project_state(singleton, dashboard_revision, updated_at)
                VALUES (1, 0, ?)
                """,
                (utc_now(),),
            )
        if not self.dashboard_path.exists():
            self.render_dashboard(
                {
                    "current_task": "Not started",
                    "completed": [],
                    "pending": [],
                    "blockers": [],
                    "recent_changes": [],
                    "last_updated": utc_now(),
                }
            )
        if not self.project_context_path.exists():
            self.project_context_path.write_text(
                """# EZ Hack Project Context

## Purpose

Describe the project's stable purpose, scope, architecture, and vocabulary here.
Operators read this file to answer background questions without waking the host.

## Responsibilities

- Operators answer questions, clarify requested modifications, and submit structured proposals.
- The host owns the primary workflow and decides whether proposals fit its plan.

## Current boundaries

- Private operator conversations stay private.
- The dashboard contains changing workflow status.
- This file contains stable project background.
""",
                encoding="utf-8",
            )
        if not self.contact_map_path.exists():
            self.contact_map_path.parent.mkdir(parents=True, exist_ok=True)
            self.contact_map_path.write_text(
                """# EZ Hack Contact Map

This file is the host-owned source of truth for notification routing.

When an operator's proposed change is completed, everyone listed on that
operator's row receives the host's completion message. Names must exactly match
active operator names. Routes are directed and do not imply a reverse route.

## Routes

| Operator | Notify |
| --- | --- |

<!-- Example: | Alice | Bob, Carol | -->
""",
                encoding="utf-8",
            )

    def initialize_host(self, name: str) -> tuple[str, dict[str, Any]]:
        name = self._clean_name(name)
        raw_token = new_secret("ezh_host")
        operator_id = str(uuid.uuid4())
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT id FROM operators LIMIT 1").fetchone()
            if existing:
                db.rollback()
                raise ValueError("This EZ Hack project has already been initialized.")
            db.execute(
                """
                INSERT INTO operators(
                    id, name, role, access_level, token_hash, created_at
                ) VALUES (?, ?, 'host', 100, ?, ?)
                """,
                (operator_id, name, token_hash(raw_token), utc_now()),
            )
            db.commit()
        return raw_token, {
            "id": operator_id,
            "name": name,
            "role": "host",
            "access_level": 100,
        }

    def authenticate(self, raw_token: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                """
                SELECT id, name, role, access_level FROM operators
                WHERE token_hash = ? AND active = 1
                """,
                (token_hash(raw_token),),
            ).fetchone()
        return dict(row) if row else None

    def create_invite(
        self,
        host_id: str,
        *,
        access_level: int = 10,
        expires_in_hours: int = 24,
        max_uses: int = 1,
    ) -> str:
        if expires_in_hours < 1 or max_uses < 1:
            raise ValueError("Invite lifetime and maximum uses must be positive.")
        access_level = self._clean_access_level(access_level)
        code = new_secret(f"ezh_invite_l{access_level}")
        expires_at = (datetime.now(UTC) + timedelta(hours=expires_in_hours)).isoformat(
            timespec="seconds"
        )
        with self.connect() as db:
            self._require_role(db, host_id, "host")
            db.execute(
                """
                INSERT INTO invites(
                    code_hash, access_level, created_by, expires_at, max_uses, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    token_hash(code),
                    access_level,
                    host_id,
                    expires_at,
                    max_uses,
                    utc_now(),
                ),
            )
        return code

    def redeem_invite(self, code: str, name: str) -> tuple[str, dict[str, Any]]:
        name = self._clean_name(name)
        raw_token = new_secret("ezh_operator")
        operator_id = str(uuid.uuid4())
        now = utc_now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            invite = db.execute(
                """
                SELECT code_hash, access_level, expires_at, max_uses, uses, active
                FROM invites WHERE code_hash = ?
                """,
                (token_hash(code),),
            ).fetchone()
            if (
                not invite
                or not invite["active"]
                or invite["uses"] >= invite["max_uses"]
                or invite["expires_at"] <= now
            ):
                db.rollback()
                raise ValueError("Invite is invalid, expired, or already used.")
            try:
                db.execute(
                    """
                    INSERT INTO operators(
                        id, name, role, access_level, token_hash, active, created_at
                    ) VALUES (?, ?, 'operator', ?, ?, 0, ?)
                    """,
                    (
                        operator_id,
                        name,
                        invite["access_level"],
                        token_hash(raw_token),
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                db.rollback()
                raise ValueError("That operator name is already in use.") from exc
            uses = invite["uses"] + 1
            db.execute(
                "UPDATE invites SET uses = ?, active = ? WHERE code_hash = ?",
                (uses, 0 if uses >= invite["max_uses"] else 1, invite["code_hash"]),
            )
            db.commit()
        return raw_token, {
            "id": operator_id,
            "name": name,
            "role": "operator",
            "access_level": invite["access_level"],
            "active": False,
        }

    def list_operators(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT id, name, role, access_level, active, created_at
                FROM operators ORDER BY created_at
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def approve_operator(self, host_id: str, operator_id: str) -> dict[str, Any]:
        with self.connect() as db:
            self._require_role(db, host_id, "host")
            row = db.execute(
                """
                SELECT id, name, role, access_level, active
                FROM operators WHERE id = ?
                """,
                (operator_id,),
            ).fetchone()
            if not row or row["role"] != "operator":
                raise ValueError("The operator UUID is unknown.")
            db.execute("UPDATE operators SET active = 1 WHERE id = ?", (operator_id,))
        return {
            "id": row["id"],
            "name": row["name"],
            "access_level": row["access_level"],
            "active": True,
        }

    def set_operator_access_level(
        self, host_id: str, operator: str, access_level: int
    ) -> dict[str, Any]:
        access_level = self._clean_access_level(access_level)
        with self.connect() as db:
            self._require_role(db, host_id, "host")
            row = db.execute(
                """
                SELECT id, name, role, active FROM operators
                WHERE id = ? OR name = ?
                """,
                (operator, operator),
            ).fetchone()
            if not row or row["role"] != "operator":
                raise ValueError("The operator ID or name is unknown.")
            db.execute(
                "UPDATE operators SET access_level = ? WHERE id = ?",
                (access_level, row["id"]),
            )
        return {
            "id": row["id"],
            "name": row["name"],
            "access_level": access_level,
            "active": bool(row["active"]),
        }

    def revoke_operator(self, host_id: str, operator_id: str) -> dict[str, Any]:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._require_role(db, host_id, "host")
            row = db.execute(
                "SELECT id, name, role FROM operators WHERE id = ?",
                (operator_id,),
            ).fetchone()
            if not row or row["role"] != "operator":
                db.rollback()
                raise ValueError("The operator UUID is unknown.")
            db.execute("UPDATE operators SET active = 0 WHERE id = ?", (operator_id,))
            db.execute(
                "DELETE FROM contact_routes WHERE source_id = ? OR recipient_id = ?",
                (operator_id, operator_id),
            )
            db.commit()
        return {"id": row["id"], "name": row["name"], "active": False}

    def sync_contact_map(self, host_id: str) -> dict[str, Any]:
        routes = self._parse_contact_map(
            self.contact_map_path.read_text(encoding="utf-8")
        )
        mentioned = set(routes)
        for recipients in routes.values():
            mentioned.update(recipients)

        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._require_role(db, host_id, "host")
            operators = db.execute(
                """
                SELECT id, name FROM operators
                WHERE active = 1 AND role = 'operator'
                """
            ).fetchall()
            ids_by_name = {row["name"]: row["id"] for row in operators}
            missing = sorted(mentioned - set(ids_by_name))
            if missing:
                db.rollback()
                raise ValueError(
                    "Unknown or inactive operator names in CONTACT_MAP.md: "
                    + ", ".join(missing)
                )

            edges: list[tuple[str, str, str]] = []
            created_at = utc_now()
            for source_name, recipient_names in routes.items():
                if source_name in recipient_names:
                    db.rollback()
                    raise ValueError(f"{source_name} cannot notify itself.")
                edges.extend(
                    (ids_by_name[source_name], ids_by_name[name], created_at)
                    for name in recipient_names
                )

            db.execute("DELETE FROM contact_routes")
            db.executemany(
                """
                INSERT INTO contact_routes(source_id, recipient_id, created_at)
                VALUES (?, ?, ?)
                """,
                edges,
            )
            db.commit()
        return {
            "path": str(self.contact_map_path),
            "routes": {name: sorted(recipients) for name, recipients in routes.items()},
            "route_count": len(edges),
        }

    def get_contact_map(self, host_id: str) -> dict[str, list[str]]:
        with self.connect() as db:
            self._require_role(db, host_id, "host")
            operators = db.execute(
                """
                SELECT id, name FROM operators
                WHERE active = 1 AND role = 'operator'
                ORDER BY name
                """
            ).fetchall()
            routes = db.execute(
                """
                SELECT cr.source_id, recipient.name AS recipient_name
                FROM contact_routes cr
                JOIN operators recipient ON recipient.id = cr.recipient_id
                WHERE recipient.active = 1
                ORDER BY recipient.name
                """
            ).fetchall()
        names_by_id = {row["id"]: row["name"] for row in operators}
        result = {name: [] for name in names_by_id.values()}
        for route in routes:
            source_name = names_by_id.get(route["source_id"])
            if source_name:
                result[source_name].append(route["recipient_name"])
        return result

    def set_contact_route(
        self, host_id: str, operator: str, recipients: list[str]
    ) -> dict[str, Any]:
        source = self._clean_name(operator)
        cleaned_recipients = set(self._clean_recipients(recipients))
        with self.connect() as db:
            self._require_role(db, host_id, "host")
            active = db.execute(
                """
                SELECT name FROM operators
                WHERE active = 1 AND role = 'operator'
                """
            ).fetchall()
        active_names = {row["name"] for row in active}
        missing = sorted({source, *cleaned_recipients} - active_names)
        if missing:
            raise ValueError(
                "Unknown or inactive operator names: " + ", ".join(missing)
            )
        if source in cleaned_recipients:
            raise ValueError("An operator cannot notify itself.")

        routes = self._parse_contact_map(
            self.contact_map_path.read_text(encoding="utf-8")
        )
        if cleaned_recipients:
            routes[source] = cleaned_recipients
        else:
            routes.pop(source, None)
        self.render_contact_map(routes)
        return self.sync_contact_map(host_id)

    def render_contact_map(self, routes: dict[str, set[str]]) -> None:
        rows = ["| Operator | Notify |", "| --- | --- |"]
        rows.extend(
            f"| {source} | {', '.join(sorted(recipients))} |"
            for source, recipients in sorted(routes.items())
        )
        content = """# EZ Hack Contact Map

This file is the host-owned source of truth for notification routing.

When an operator's proposed change is completed, everyone listed on that
operator's row receives the host's completion message. Names must exactly match
active operator names. Routes are directed and do not imply a reverse route.

## Routes

""" + "\n".join(rows) + "\n"
        self.contact_map_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix="contact-map-", suffix=".md", dir=self.contact_map_path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
            os.replace(temporary, self.contact_map_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def submit_request(
        self,
        sender_id: str,
        *,
        kind: str,
        summary: str,
        details: str,
        notify: list[str],
        expected_result: str = "",
        affected_tasks: list[str] | None = None,
        base_dashboard_revision: int | None = None,
    ) -> dict[str, Any]:
        summary = summary.strip()
        if not summary:
            raise ValueError("Request summary cannot be empty.")
        request_id = str(uuid.uuid4())
        created_at = utc_now()
        with self.connect() as db:
            self._require_active(db, sender_id)
            current_revision = self._dashboard_revision(db)
            if base_dashboard_revision is not None and base_dashboard_revision < 0:
                raise ValueError("Dashboard revision cannot be negative.")
            db.execute(
                """
                INSERT INTO requests(
                    id, sender_id, kind, summary, details, notify_json, created_at,
                    expected_result, affected_tasks_json, base_dashboard_revision
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    sender_id,
                    kind.strip() or "change",
                    summary,
                    details.strip(),
                    json.dumps(self._clean_recipients(notify)),
                    created_at,
                    expected_result.strip(),
                    json.dumps(self._clean_items(affected_tasks or [])),
                    base_dashboard_revision,
                ),
            )
        return {
            "id": request_id,
            "status": "queued",
            "created_at": created_at,
            "summary": summary,
            "base_dashboard_revision": base_dashboard_revision,
            "current_dashboard_revision": current_revision,
        }

    def claim_next_request(self, host_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._require_role(db, host_id, "host")
            row = db.execute(
                """
                SELECT r.*, o.name AS sender_name, o.role AS sender_role,
                       o.access_level AS sender_access_level
                FROM requests r
                JOIN operators o ON o.id = r.sender_id
                WHERE r.status = 'queued'
                ORDER BY (r.defer_reason IS NOT NULL), r.created_at, r.id
                LIMIT 1
                """
            ).fetchone()
            if not row:
                db.commit()
                return None
            claimed_at = utc_now()
            db.execute(
                """
                UPDATE requests
                SET status = 'processing', claimed_at = ?, defer_reason = NULL,
                    recheck_after = NULL
                WHERE id = ?
                """,
                (claimed_at, row["id"]),
            )
            current_revision = self._dashboard_revision(db)
            db.commit()
        item = dict(row)
        item["status"] = "processing"
        item["claimed_at"] = claimed_at
        item["notify"] = json.loads(item.pop("notify_json"))
        item["affected_tasks"] = json.loads(item.pop("affected_tasks_json"))
        item["current_dashboard_revision"] = current_revision
        base_revision = item.get("base_dashboard_revision")
        item["snapshot_is_stale"] = (
            base_revision is not None and base_revision != current_revision
        )
        return item

    def requeue_request(
        self,
        host_id: str,
        request_id: str,
        *,
        reason: str = "",
        recheck_after: str = "",
    ) -> dict[str, Any]:
        reason = reason.strip()
        recheck_after = recheck_after.strip()
        with self.connect() as db:
            self._require_role(db, host_id, "host")
            changed = db.execute(
                """
                UPDATE requests
                SET status = 'queued', claimed_at = NULL, defer_reason = ?,
                    recheck_after = ?, deferral_count = deferral_count + 1
                WHERE id = ? AND status = 'processing'
                """,
                (reason or None, recheck_after or None, request_id),
            ).rowcount
        if not changed:
            raise ValueError("Only a processing request can be returned to the queue.")
        return {
            "id": request_id,
            "status": "queued",
            "defer_reason": reason or None,
            "recheck_after": recheck_after or None,
        }

    def complete_request(
        self,
        host_id: str,
        request_id: str,
        *,
        status: Literal["completed", "rejected"],
        outcome: str,
        extra_notify: list[str],
    ) -> dict[str, Any]:
        outcome = outcome.strip()
        if not outcome:
            raise ValueError("An outcome is required.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._require_role(db, host_id, "host")
            row = db.execute(
                "SELECT sender_id, summary, notify_json, status FROM requests WHERE id = ?",
                (request_id,),
            ).fetchone()
            if not row or row["status"] not in {"queued", "processing"}:
                db.rollback()
                raise ValueError("Request is missing or already resolved.")
            completed_at = utc_now()
            db.execute(
                """
                UPDATE requests
                SET status = ?, outcome = ?, completed_at = ?
                WHERE id = ?
                """,
                (status, outcome, completed_at, request_id),
            )
            names = json.loads(row["notify_json"]) + self._clean_recipients(extra_notify)
            recipients = {row["sender_id"]}
            if names:
                placeholders = ",".join("?" for _ in names)
                found = db.execute(
                    f"SELECT id FROM operators WHERE active = 1 AND name IN ({placeholders})",
                    names,
                ).fetchall()
                recipients.update(item["id"] for item in found)
            if status == "completed":
                routed = db.execute(
                    """
                    SELECT cr.recipient_id
                    FROM contact_routes cr
                    JOIN operators recipient ON recipient.id = cr.recipient_id
                    WHERE cr.source_id = ? AND recipient.active = 1
                    """,
                    (row["sender_id"],),
                ).fetchall()
                recipients.update(item["recipient_id"] for item in routed)
            delivered = db.execute(
                f"SELECT id, name FROM operators WHERE id IN ({','.join('?' for _ in recipients)})",
                list(recipients),
            ).fetchall()
            delivered_names = sorted(
                item["name"] for item in delivered if item["id"] != host_id
            )
            message = outcome
            if status == "completed":
                message = f"Completed change: {row['summary']}\nOutcome: {outcome}"
            for recipient_id in recipients:
                if recipient_id == host_id:
                    continue
                db.execute(
                    """
                    INSERT INTO notifications(
                        recipient_id, event_type, message, request_id, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (recipient_id, f"request_{status}", message, request_id, completed_at),
                )
            db.commit()
        return {
            "id": request_id,
            "status": status,
            "completed_at": completed_at,
            "notified": delivered_names,
        }

    def request_status(self, caller_id: str, role: str, request_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute(
                """
                SELECT r.id, r.sender_id, r.kind, r.summary, r.status,
                       r.created_at, r.claimed_at, r.completed_at, r.outcome,
                       r.expected_result, r.affected_tasks_json,
                       r.base_dashboard_revision, r.defer_reason,
                       r.recheck_after, r.deferral_count,
                       o.name AS sender_name
                FROM requests r JOIN operators o ON o.id = r.sender_id
                WHERE r.id = ?
                """,
                (request_id,),
            ).fetchone()
        if not row or (role != "host" and row["sender_id"] != caller_id):
            raise ValueError("Request not found.")
        result = dict(row)
        result["affected_tasks"] = json.loads(result.pop("affected_tasks_json"))
        return result

    def add_notification(
        self,
        host_id: str,
        recipients: list[str],
        *,
        event_type: str,
        message: str,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        names = self._clean_recipients(recipients)
        if not names:
            raise ValueError("At least one recipient is required.")
        with self.connect() as db:
            self._require_role(db, host_id, "host")
            placeholders = ",".join("?" for _ in names)
            found = db.execute(
                f"SELECT id, name FROM operators WHERE active = 1 AND name IN ({placeholders})",
                names,
            ).fetchall()
            found_names = {row["name"] for row in found}
            missing = sorted(set(names) - found_names)
            created_at = utc_now()
            for row in found:
                if row["id"] != host_id:
                    db.execute(
                        """
                        INSERT INTO notifications(
                            recipient_id, event_type, message, request_id, created_at
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (row["id"], event_type, message.strip(), request_id, created_at),
                    )
        return {"delivered_to": sorted(found_names), "unknown_recipients": missing}

    def read_notifications(
        self, operator_id: str, *, limit: int, mark_read: bool
    ) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 100))
        marked_at: str | None = None
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT id, event_type, message, request_id, created_at, read_at
                FROM notifications
                WHERE recipient_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (operator_id, limit),
            ).fetchall()
            if mark_read:
                unread_ids = [row["id"] for row in rows if row["read_at"] is None]
                if unread_ids:
                    marked_at = utc_now()
                    placeholders = ",".join("?" for _ in unread_ids)
                    db.execute(
                        f"UPDATE notifications SET read_at = ? WHERE id IN ({placeholders})",
                        [marked_at, *unread_ids],
                    )
        result = [dict(row) for row in rows]
        if marked_at is not None:
            for item in result:
                if item["read_at"] is None:
                    item["read_at"] = marked_at
        return result

    def get_dashboard(self) -> dict[str, Any]:
        with self.connect() as db:
            revision = self._dashboard_revision(db)
        return {
            "path": str(self.dashboard_path),
            "revision": revision,
            "markdown": self.dashboard_path.read_text(encoding="utf-8"),
        }

    def get_project_context(self) -> dict[str, Any]:
        return {
            "path": str(self.project_context_path),
            "markdown": self.project_context_path.read_text(encoding="utf-8"),
        }

    def update_dashboard(
        self,
        host_id: str,
        *,
        current_task: str,
        completed: list[str],
        pending: list[str],
        blockers: list[str],
        recent_changes: list[str],
    ) -> dict[str, Any]:
        payload = {
            "current_task": current_task.strip() or "No active task",
            "completed": self._clean_items(completed),
            "pending": self._clean_items(pending),
            "blockers": self._clean_items(blockers),
            "recent_changes": self._clean_items(recent_changes),
            "last_updated": utc_now(),
        }
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._require_role(db, host_id, "host")
            revision = self._dashboard_revision(db) + 1
            db.execute(
                """
                UPDATE project_state
                SET dashboard_revision = ?, updated_at = ?
                WHERE singleton = 1
                """,
                (revision, payload["last_updated"]),
            )
            db.commit()
        payload["revision"] = revision
        self.render_dashboard(payload)
        return payload

    def render_dashboard(self, payload: dict[str, Any]) -> None:
        data = payload

        def section(title: str, items: list[str]) -> str:
            lines = "\n".join(f"- {item}" for item in items) if items else "- None"
            return f"## {title}\n\n{lines}"

        content = "\n\n".join(
            [
                "# EZ Hack Dashboard",
                f"**Revision:** {data.get('revision', 0)}",
                f"**Last updated:** {data['last_updated']}",
                f"## Current task\n\n{data['current_task']}",
                section("Completed", data["completed"]),
                section("Pending", data["pending"]),
                section("Blockers", data["blockers"]),
                section("Recent changes", data["recent_changes"]),
            ]
        ) + "\n"
        self.home.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix="dashboard-", suffix=".md", dir=self.home)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
            os.replace(temporary, self.dashboard_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def _clean_name(name: str) -> str:
        value = " ".join(name.split())
        if not 1 <= len(value) <= 80:
            raise ValueError("Name must contain 1 to 80 characters.")
        return value

    @staticmethod
    def _clean_recipients(values: list[str]) -> list[str]:
        return sorted({" ".join(value.split()) for value in values if value.strip()})

    @staticmethod
    def _clean_items(values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]

    @staticmethod
    def _clean_access_level(value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Operator access level must be an integer from 0 to 99.")
        if not 0 <= value <= 99:
            raise ValueError(
                "Operator access level must be between 0 and 99; level 100 is reserved for the host."
            )
        return value

    @staticmethod
    def _ensure_column(
        db: sqlite3.Connection, table: str, column: str, definition: str
    ) -> None:
        columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _dashboard_revision(db: sqlite3.Connection) -> int:
        row = db.execute(
            "SELECT dashboard_revision FROM project_state WHERE singleton = 1"
        ).fetchone()
        return int(row["dashboard_revision"]) if row else 0

    @classmethod
    def _parse_contact_map(cls, markdown: str) -> dict[str, set[str]]:
        routes: dict[str, set[str]] = {}
        in_routes = False
        for line_number, line in enumerate(markdown.splitlines(), start=1):
            stripped = line.strip()
            if stripped.lower() == "## routes":
                in_routes = True
                continue
            if in_routes and stripped.startswith("## "):
                break
            if not in_routes or not stripped.startswith("|"):
                continue
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if len(cells) != 2:
                raise ValueError(
                    f"CONTACT_MAP.md line {line_number} must have exactly two columns."
                )
            source, raw_recipients = cells
            if source.lower() == "operator" or set(source) <= {"-", ":", " "}:
                continue
            source = cls._clean_name(source)
            recipients = {
                cls._clean_name(name)
                for name in raw_recipients.split(",")
                if name.strip()
            }
            routes.setdefault(source, set()).update(recipients)
        return routes

    @staticmethod
    def _require_active(db: sqlite3.Connection, operator_id: str) -> None:
        row = db.execute(
            "SELECT active FROM operators WHERE id = ?", (operator_id,)
        ).fetchone()
        if not row or not row["active"]:
            raise PermissionError("Operator is inactive or unknown.")

    @staticmethod
    def _require_role(db: sqlite3.Connection, operator_id: str, role: str) -> None:
        row = db.execute(
            "SELECT role, active FROM operators WHERE id = ?", (operator_id,)
        ).fetchone()
        if not row or not row["active"] or row["role"] != role:
            raise PermissionError(f"This action requires the {role} role.")
