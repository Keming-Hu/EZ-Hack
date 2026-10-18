from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .db import Database


def project_home(value: str | None) -> Path:
    return Path(value or os.environ.get("EZ_HACK_HOME", Path.cwd())).resolve()


def write_secret(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def read_credentials(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Could not read credentials from {path}: {exc}") from exc


def host_context(home: Path) -> tuple[Database, dict[str, Any], dict[str, Any]]:
    database = Database(home)
    database.ensure_schema()
    credential_path = home / ".ez-hack" / "host-credentials.json"
    credentials = read_credentials(credential_path)
    identity = database.authenticate(credentials["token"])
    if not identity or identity["role"] != "host":
        raise SystemExit("The stored host credentials are invalid.")
    return database, credentials, identity


def init_command(args: argparse.Namespace) -> None:
    home = project_home(args.home)
    database = Database(home)
    database.ensure_schema()
    token, identity = database.initialize_host(args.name)
    credential_path = home / ".ez-hack" / "host-credentials.json"
    write_secret(
        credential_path,
        {"token": token, "identity": identity, "mcp_url": args.mcp_url},
    )
    print(f"Initialized EZ Hack at {home}")
    print(f"Host credentials saved with owner-only permissions: {credential_path}")
    print("Next: run `ez-hack host start`, then create an invitation with `ez-hack host invite --access-level 10`.")


def invite_command(args: argparse.Namespace) -> None:
    home = project_home(args.home)
    database, credentials, identity = host_context(home)
    invite = database.create_invite(
        identity["id"],
        access_level=args.access_level,
        expires_in_hours=args.hours,
        max_uses=args.max_uses,
    )
    join_url = args.join_url or credentials["mcp_url"].removesuffix("/mcp") + "/join"
    print(
        json.dumps(
            {
                "join_url": join_url,
                "invitation_code": invite,
                "access_level": args.access_level,
                "expires_in_hours": args.hours,
                "maximum_uses": args.max_uses,
            },
            indent=2,
        )
    )


def join_command(args: argparse.Namespace) -> None:
    parsed = urllib.parse.urlparse(args.url)
    if parsed.scheme not in {"http", "https"}:
        raise SystemExit("Join URL must use http or https.")
    if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        if not args.allow_http:
            raise SystemExit("Remote joins require HTTPS. Use --allow-http only on a trusted private network.")
    request = urllib.request.Request(
        args.url,
        data=json.dumps({"invite": args.invite, "name": args.name}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Could not join EZ Hack: {exc}") from exc
    output = Path(args.output or "ez-hack-credentials.json").resolve()
    write_secret(output, payload)
    print(f"Registered as {payload['identity']['name']} ({payload['identity']['role']}).")
    print(f"Operator ID: {payload['identity']['id']}")
    print(f"Assigned access level: {payload['identity']['access_level']}")
    if not payload["identity"].get("active", True):
        print("This identity is pending host approval and cannot use MCP tools yet.")
    print(f"Credentials saved with owner-only permissions: {output}")


def host_start_command(args: argparse.Namespace) -> None:
    home = project_home(args.home)
    host_context(home)
    os.environ["EZ_HACK_HOME"] = str(home)
    from .server import main as server_main

    server_main()


def host_operators_command(args: argparse.Namespace) -> None:
    database, _, _ = host_context(project_home(args.home))
    print(json.dumps(database.list_operators(), indent=2))


def host_approve_command(args: argparse.Namespace) -> None:
    database, _, identity = host_context(project_home(args.home))
    result = database.approve_operator(identity["id"], args.operator_id)
    print(json.dumps(result, indent=2))


def host_revoke_command(args: argparse.Namespace) -> None:
    database, _, identity = host_context(project_home(args.home))
    result = database.revoke_operator(identity["id"], args.operator_id)
    print(json.dumps(result, indent=2))


def host_access_command(args: argparse.Namespace) -> None:
    database, _, identity = host_context(project_home(args.home))
    result = database.set_operator_access_level(
        identity["id"], args.operator, args.level
    )
    print(json.dumps(result, indent=2))


def host_route_list_command(args: argparse.Namespace) -> None:
    database, _, identity = host_context(project_home(args.home))
    print(json.dumps(database.get_contact_map(identity["id"]), indent=2))


def host_route_set_command(args: argparse.Namespace) -> None:
    database, _, identity = host_context(project_home(args.home))
    result = database.set_contact_route(identity["id"], args.operator, args.notify)
    print(json.dumps(result, indent=2))


def host_route_remove_command(args: argparse.Namespace) -> None:
    database, _, identity = host_context(project_home(args.home))
    result = database.set_contact_route(identity["id"], args.operator, [])
    print(json.dumps(result, indent=2))


def codex_command(args: argparse.Namespace) -> None:
    credentials = read_credentials(Path(args.credentials).resolve())
    print("Run these commands in the terminal that launches Codex:")
    print(f"export EZ_HACK_TOKEN='{credentials['token']}'")
    print(
        "codex mcp add ez-hack "
        f"--url '{credentials['mcp_url']}' "
        "--bearer-token-env-var EZ_HACK_TOKEN"
    )


def dashboard_command(args: argparse.Namespace) -> None:
    database = Database(project_home(args.home))
    database.ensure_schema()
    print(database.dashboard_path.read_text(encoding="utf-8"), end="")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ez-hack")
    parser.add_argument("--home", help="Project root; defaults to EZ_HACK_HOME or the current directory")
    subcommands = parser.add_subparsers(dest="command", required=True)

    host = subcommands.add_parser("host", help="Set up and operate an EZ Hack host")
    host_commands = host.add_subparsers(dest="host_command", required=True)

    host_setup = host_commands.add_parser("setup", help="Create the host identity")
    host_setup.add_argument("--name", required=True, help="Host display name")
    host_setup.add_argument("--mcp-url", default="http://127.0.0.1:8000/mcp")
    host_setup.set_defaults(handler=init_command)

    host_start = host_commands.add_parser("start", help="Run the local MCP service")
    host_start.set_defaults(handler=host_start_command)

    host_invite = host_commands.add_parser(
        "invite", help="Create an access-level-bound operator invitation"
    )
    host_invite.add_argument("--access-level", type=int, default=10)
    host_invite.add_argument("--hours", type=int, default=24)
    host_invite.add_argument("--max-uses", type=int, default=1)
    host_invite.add_argument("--join-url")
    host_invite.set_defaults(handler=invite_command)

    host_operators = host_commands.add_parser(
        "operators", help="List host and operator identities"
    )
    host_operators.set_defaults(handler=host_operators_command)

    host_approve = host_commands.add_parser(
        "approve", help="Activate a pending operator after verifying its ID"
    )
    host_approve.add_argument("operator_id")
    host_approve.set_defaults(handler=host_approve_command)

    host_revoke = host_commands.add_parser(
        "revoke", help="Disable an operator and remove its broadcast routes"
    )
    host_revoke.add_argument("operator_id")
    host_revoke.set_defaults(handler=host_revoke_command)

    host_access = host_commands.add_parser(
        "access", help="Assign an operator access level from 0 to 99"
    )
    host_access.add_argument("operator", help="Operator UUID or exact name")
    host_access.add_argument("--level", required=True, type=int)
    host_access.set_defaults(handler=host_access_command)

    host_route = host_commands.add_parser(
        "route", help="Manage directed completion broadcasts"
    )
    route_commands = host_route.add_subparsers(dest="route_command", required=True)

    route_list = route_commands.add_parser("list", help="Show active routes")
    route_list.set_defaults(handler=host_route_list_command)

    route_set = route_commands.add_parser("set", help="Replace one operator's route")
    route_set.add_argument("operator", help="Exact active operator name")
    route_set.add_argument(
        "--notify", nargs="+", required=True, help="Recipient operator names"
    )
    route_set.set_defaults(handler=host_route_set_command)

    route_remove = route_commands.add_parser("remove", help="Remove one route")
    route_remove.add_argument("operator", help="Exact active operator name")
    route_remove.set_defaults(handler=host_route_remove_command)

    operator = subcommands.add_parser(
        "operator", help="Join an EZ Hack host as an operator"
    )
    operator_commands = operator.add_subparsers(dest="operator_command", required=True)
    operator_setup = operator_commands.add_parser(
        "setup", help="Redeem an invitation and generate one operator ID"
    )
    operator_setup.add_argument("--url", required=True, help="Host /join URL")
    operator_setup.add_argument("--invite", required=True, help="Invitation code")
    operator_setup.add_argument("--name", required=True, help="Operator display name")
    operator_setup.add_argument("--output")
    operator_setup.add_argument("--allow-http", action="store_true")
    operator_setup.set_defaults(handler=join_command)

    init = subcommands.add_parser("init", help="Initialize a project and host identity")
    init.add_argument("--name", required=True, help="Host display name")
    init.add_argument("--mcp-url", default="http://127.0.0.1:8000/mcp")
    init.set_defaults(handler=init_command)

    invite = subcommands.add_parser("invite", help="Create a time-limited operator invite")
    invite.add_argument("--access-level", type=int, default=10)
    invite.add_argument("--hours", type=int, default=24)
    invite.add_argument("--max-uses", type=int, default=1)
    invite.add_argument("--join-url")
    invite.set_defaults(handler=invite_command)

    join = subcommands.add_parser("join", help="Redeem an invite and save operator credentials")
    join.add_argument("--url", required=True, help="The host's /join URL")
    join.add_argument("--invite", required=True)
    join.add_argument("--name", required=True)
    join.add_argument("--output")
    join.add_argument("--allow-http", action="store_true")
    join.set_defaults(handler=join_command)

    codex = subcommands.add_parser("codex-setup", help="Print Codex MCP setup commands")
    codex.add_argument("--credentials", required=True)
    codex.set_defaults(handler=codex_command)

    dashboard = subcommands.add_parser("dashboard", help="Print the current dashboard")
    dashboard.set_defaults(handler=dashboard_command)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.handler(args)
    except (ValueError, PermissionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
