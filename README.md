# EZ Hack

EZ Hack connects one host coding agent with several operator coding agents. The host owns the workflow, while operators answer users quickly and submit structured proposals through an authenticated MCP service.

The package provides an `ez-hack` CLI for first-time setup, operator admission, access levels, and broadcast routing.

For the complete team routine, including private GitHub cloning, remote host setup, identity verification, broadcasting, and daily operation, see [HACKATHON_SETUP.md](HACKATHON_SETUP.md).

## Install after cloning

Python 3.11 or newer is required.

```bash
git clone <repository-url>
cd "EZ Hack"
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
```

Use `python -m pip install -e .` instead when developing the package.

## Set up a host

Run these commands from the project directory:

```bash
ez-hack host setup --name "Host name"
ez-hack host start
```

The service starts at `http://127.0.0.1:8000/mcp` by default. Host state and credentials are stored under `.ez-hack/`; credential files are created with owner-only permissions and ignored by Git.

In another terminal, generate the Codex MCP registration commands:

```bash
ez-hack codex-setup --credentials .ez-hack/host-credentials.json
```

## Invite and activate an operator

The host chooses the access level when creating the invitation:

```bash
ez-hack host invite --access-level 10
```

The output contains a join URL, a one-time invitation code, and its assigned level. Send the join URL and code through a trusted channel.

The operator redeems it once:

```bash
ez-hack operator setup \
  --url "https://your-host.example/join" \
  --invite "ezh_invite_l10_..." \
  --name "Operator name"
```

This creates a server-generated UUID and bearer credential and saves them to `ez-hack-credentials.json`. The operator then gives the UUID to the host through the trusted channel. The host compares it with the pending record and activates it:

```bash
ez-hack host operators
ez-hack host approve "operator-uuid"
```

The operator can then generate the Codex MCP registration commands:

```bash
ez-hack codex-setup --credentials ez-hack-credentials.json
```

Invitations expire after 24 hours and allow one redemption by default. Use `--hours` and `--max-uses` to change those limits. Remote joins require HTTPS unless the operator explicitly uses `--allow-http` on a trusted private network.

## Access levels

| Level | Meaning |
| --- | --- |
| `0` | Read project context, dashboard, request results, and notifications. Cannot submit proposals. |
| `1`–`99` | Can submit proposals. The authenticated level accompanies each claimed request so the host can apply project-specific policy. |
| `100` | Reserved for the single host. Host-only tools still require the host role. |

The invitation code visibly includes its assigned level, for example `ezh_invite_l10_...`. The full code is hashed in the host database together with that level. Editing the visible level invalidates the invitation rather than changing its authority.

The host can change an operator later using either its UUID or exact name:

```bash
ez-hack host access "operator-uuid-or-name" --level 25
```

An access-level change takes effect on the next authenticated MCP call. Operator requests remain proposals; the host decides whether and when to integrate them.

## Configure broadcasting

Routes are directed. If Alice's route names Bob and Carol, completing a request submitted by Alice also notifies Bob and Carol.

```bash
ez-hack host route list
ez-hack host route set "Alice" --notify "Bob" "Carol"
ez-hack host route remove "Alice"
```

Only the host CLI and host MCP tools can change the runtime map. The CLI also updates `host/CONTACT_MAP.md`, which remains the readable, user-editable source of truth. If the host edits that file manually, it can call the `sync_contact_map` MCP tool to validate and load it.

## Other host commands

```bash
ez-hack host operators
ez-hack host revoke "operator-uuid"
```

Revoking an operator disables its bearer token immediately and removes its broadcast routes.

## Remote hosting

Put the service behind a TLS reverse proxy or secure tunnel. Set the public endpoint and exact allowed hosts before binding beyond localhost:

```bash
export EZ_HACK_HOME="/path/to/EZ Hack"
export EZ_HACK_HOST="0.0.0.0"
export EZ_HACK_PUBLIC_URL="https://your-host.example/mcp"
export EZ_HACK_ALLOWED_HOSTS="your-host.example,your-host.example:*"
ez-hack host start
```

The `/join` route is public but accepts only a valid invitation. MCP tools require bearer authentication. The database stores hashes of bearer tokens and invitation codes.

## MCP behavior

All active authenticated identities can call `whoami`, `get_project_context`, `get_dashboard`, `read_notifications`, and permitted `get_request_status` operations. Operators at levels 1–99 can call `submit_request`.

Host credentials additionally unlock request processing, dashboard updates, notifications, operator admission and revocation, `set_operator_access_level`, and contact-map management.

Clients never submit a trusted UUID as a tool argument. The server hashes the bearer token, resolves its active database identity, and supplies the UUID, role, and access level as authenticated metadata. A leaked invitation creates only a pending identity and does not grant MCP access without host approval.

## Division of work

Operators answer routine questions using `PROJECT_CONTEXT.md` and the revisioned `DASHBOARD.md`. They clarify requested changes privately and send only concise actionable proposals to the host. Private transcripts are not copied into shared state.

The host processes requests at safe checkpoints between atomic subtasks. It integrates a proposal only when it fits the current plan or a justified plan revision. Requests that cannot yet be integrated are requeued with a reason.

The SQLite queue is the durable proposal record. `DASHBOARD.md` is the operator-facing workflow snapshot. `host/CONTACT_MAP.md` defines notification routing after completed changes.

## Project layout

```text
host/SKILL.md            Host behavior
operator/SKILL.md        Operator behavior
src/ez_hack/server.py    Authenticated MCP service
src/ez_hack/db.py        Identities, queue, notifications, dashboard
src/ez_hack/cli.py       Guided setup and administration CLI
DASHBOARD.md             Human-readable project snapshot
PROJECT_CONTEXT.md       Stable background exposed to operators
CODEX_HANDOFF.md         Original product handoff
HACKATHON_SETUP.md       End-to-end hackathon team routine
```

## Current scope

This version uses one host, a star topology, a durable SQLite FIFO queue, bearer credentials, numeric operator access levels, and directed broadcast routes. It does not include peer messaging, forced interruption, distributed hosting, or a separate dashboard application.
