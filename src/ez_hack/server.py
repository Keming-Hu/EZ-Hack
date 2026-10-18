from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl
from starlette.requests import Request
from starlette.responses import JSONResponse

from .db import Database


HOME = Path(os.environ.get("EZ_HACK_HOME", Path.cwd()))
PUBLIC_URL = os.environ.get("EZ_HACK_PUBLIC_URL", "http://127.0.0.1:8000/mcp")
ISSUER_URL = os.environ.get("EZ_HACK_ISSUER_URL", "https://ez-hack.local")
DB = Database(HOME)
DB.ensure_schema()


class DatabaseTokenVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        identity = DB.authenticate(token)
        if not identity:
            return None
        return AccessToken(
            token=token,
            client_id=identity["id"],
            subject=identity["name"],
            scopes=["ez-hack"],
            resource=PUBLIC_URL,
            claims={
                "operator_id": identity["id"],
                "name": identity["name"],
                "role": identity["role"],
                "access_level": identity["access_level"],
            },
        )


mcp = MCPServer(
    "EZ Hack",
    instructions=(
        "A small host/operator collaboration service. Operators submit concise actionable "
        "requests; the host processes them FIFO at cooperative checkpoints. Access level 0 "
        "is read-only, levels 1 through 99 may propose changes, and level 100 is reserved "
        "for the single host."
    ),
    token_verifier=DatabaseTokenVerifier(),
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(ISSUER_URL),
        resource_server_url=AnyHttpUrl(PUBLIC_URL),
        required_scopes=["ez-hack"],
        validate_token_resource=True,
    ),
)


def caller() -> dict[str, Any]:
    access = get_access_token()
    if not access or not access.claims:
        raise PermissionError("Authenticated HTTP access is required.")
    claims = access.claims
    return {
        "id": str(claims["operator_id"]),
        "name": str(claims["name"]),
        "role": str(claims["role"]),
        "access_level": int(claims["access_level"]),
    }


def require_host() -> dict[str, Any]:
    identity = caller()
    if identity["role"] != "host":
        raise ToolError("This tool is available only to the host.")
    return identity


def require_operator() -> dict[str, Any]:
    identity = caller()
    if identity["role"] != "operator":
        raise ToolError("This tool is available only to operators.")
    return identity


@mcp.tool()
def whoami() -> dict[str, Any]:
    """Return the caller's authenticated identity, role, and access level."""
    return caller()


@mcp.tool()
def submit_request(
    summary: str,
    details: str = "",
    kind: str = "change",
    notify: list[str] | None = None,
    expected_result: str = "",
    affected_tasks: list[str] | None = None,
    base_dashboard_revision: int | None = None,
) -> dict[str, Any]:
    """Submit a clarified proposal prepared against a known workflow snapshot."""
    identity = require_operator()
    if identity["access_level"] == 0:
        raise ToolError("Access level 0 is read-only and cannot submit requests.")
    return DB.submit_request(
        identity["id"],
        kind=kind,
        summary=summary,
        details=details,
        notify=notify or [],
        expected_result=expected_result,
        affected_tasks=affected_tasks or [],
        base_dashboard_revision=base_dashboard_revision,
    )


@mcp.tool()
def get_request_status(request_id: str) -> dict[str, Any]:
    """Read the status of your request; the host may read any request."""
    identity = caller()
    try:
        return DB.request_status(identity["id"], identity["role"], request_id)
    except ValueError as exc:
        raise ToolError("Request not found or not accessible.") from exc


@mcp.tool()
def get_dashboard() -> dict[str, Any]:
    """Read the host-maintained project snapshot without waking the host."""
    caller()
    return DB.get_dashboard()


@mcp.tool()
def get_project_context() -> dict[str, Any]:
    """Read stable project background without waking the host."""
    caller()
    return DB.get_project_context()


@mcp.resource("ez-hack://dashboard")
def dashboard_resource() -> str:
    """Read the rendered project dashboard."""
    caller()
    return DB.dashboard_path.read_text(encoding="utf-8")


@mcp.resource("ez-hack://project-context")
def project_context_resource() -> str:
    """Read the stable project background shared with operators."""
    caller()
    return DB.project_context_path.read_text(encoding="utf-8")


@mcp.tool()
def read_notifications(limit: int = 20, mark_read: bool = True) -> list[dict[str, Any]]:
    """Read workflow notifications addressed to the authenticated operator."""
    identity = caller()
    return DB.read_notifications(identity["id"], limit=limit, mark_read=mark_read)


@mcp.tool()
def get_next_request() -> dict[str, Any]:
    """Host only: atomically claim the oldest queued request."""
    identity = require_host()
    return {"request": DB.claim_next_request(identity["id"])}


@mcp.tool()
def requeue_request(
    request_id: str,
    reason: str = "",
    recheck_after: str = "",
) -> dict[str, Any]:
    """Host only: defer a request that cannot yet fit the current plan."""
    identity = require_host()
    return DB.requeue_request(
        identity["id"], request_id, reason=reason, recheck_after=recheck_after
    )


@mcp.tool()
def complete_request(
    request_id: str,
    outcome: str,
    status: Literal["completed", "rejected"] = "completed",
    notify: list[str] | None = None,
) -> dict[str, Any]:
    """Host only: resolve a request and notify its sender and selected operators."""
    identity = require_host()
    return DB.complete_request(
        identity["id"],
        request_id,
        status=status,
        outcome=outcome,
        extra_notify=notify or [],
    )


@mcp.tool()
def update_dashboard(
    current_task: str,
    completed: list[str],
    pending: list[str],
    blockers: list[str],
    recent_changes: list[str],
) -> dict[str, Any]:
    """Host only: replace the dashboard at a meaningful workflow milestone."""
    identity = require_host()
    return DB.update_dashboard(
        identity["id"],
        current_task=current_task,
        completed=completed,
        pending=pending,
        blockers=blockers,
        recent_changes=recent_changes,
    )


@mcp.tool()
def notify(
    recipients: list[str],
    event_type: str,
    message: str,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Host only: send a brief workflow event to named operators."""
    identity = require_host()
    return DB.add_notification(
        identity["id"],
        recipients,
        event_type=event_type,
        message=message,
        request_id=request_id,
    )


@mcp.tool()
def list_operators() -> list[dict[str, Any]]:
    """Host only: list joined identities and their active flag without credentials."""
    require_host()
    return DB.list_operators()


@mcp.tool()
def approve_operator(operator_id: str) -> dict[str, Any]:
    """Host only: activate a joined operator after verifying its UUID."""
    identity = require_host()
    return DB.approve_operator(identity["id"], operator_id)


@mcp.tool()
def revoke_operator(operator_id: str) -> dict[str, Any]:
    """Host only: disable an operator token and remove its contact routes."""
    identity = require_host()
    return DB.revoke_operator(identity["id"], operator_id)


@mcp.tool()
def set_operator_access_level(operator: str, access_level: int) -> dict[str, Any]:
    """Host only: assign an operator access level from 0 to 99."""
    identity = require_host()
    try:
        return DB.set_operator_access_level(identity["id"], operator, access_level)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
def get_contact_map() -> dict[str, list[str]]:
    """Host only: inspect the current operator-to-recipient notification map."""
    identity = require_host()
    return DB.get_contact_map(identity["id"])


@mcp.tool()
def sync_contact_map() -> dict[str, Any]:
    """Host only: validate CONTACT_MAP.md and replace the runtime routing map."""
    identity = require_host()
    return DB.sync_contact_map(identity["id"])


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "ez-hack"})


@mcp.custom_route("/join", methods=["POST"])
async def join(request: Request) -> JSONResponse:
    try:
        content_length = int(request.headers.get("content-length", "0"))
    except ValueError:
        return JSONResponse({"error": "invalid_content_length"}, status_code=400)
    if content_length > 8192:
        return JSONResponse({"error": "request_too_large"}, status_code=413)
    try:
        payload = await request.json()
        code = str(payload.get("invite", ""))
        name = str(payload.get("name", ""))
        token, identity = DB.redeem_invite(code, name)
    except (ValueError, TypeError):
        return JSONResponse({"error": "invalid_invite_or_name"}, status_code=400)
    return JSONResponse({"token": token, "identity": identity, "mcp_url": PUBLIC_URL})


def transport_security(host: str) -> TransportSecuritySettings | None:
    allowed_hosts = [
        item.strip()
        for item in os.environ.get("EZ_HACK_ALLOWED_HOSTS", "").split(",")
        if item.strip()
    ]
    allowed_origins = [
        item.strip()
        for item in os.environ.get("EZ_HACK_ALLOWED_ORIGINS", "").split(",")
        if item.strip()
    ]
    if host in {"127.0.0.1", "localhost", "::1"} and not allowed_hosts:
        return None
    if not allowed_hosts:
        raise RuntimeError(
            "Set EZ_HACK_ALLOWED_HOSTS before binding the server to a non-local address."
        )
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


def main() -> None:
    host = os.environ.get("EZ_HACK_HOST", "127.0.0.1")
    port = int(os.environ.get("EZ_HACK_PORT", "8000"))
    try:
        mcp.run(
            transport="streamable-http",
            host=host,
            port=port,
            stateless_http=True,
            json_response=True,
            transport_security=transport_security(host),
        )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
