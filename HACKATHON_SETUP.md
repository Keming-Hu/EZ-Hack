# EZ Hack: Hackathon Team Routine

This guide takes a small hackathon team from a private GitHub repository to one running host and several connected operators.

## What the team is setting up

- One teammate runs the **host** service and the main coding-agent workflow.
- Every other teammate runs an **operator** conversation on their own computer.
- Operators answer routine questions, clarify ideas, and submit structured proposals.
- The host reviews proposals at safe workflow checkpoints and broadcasts completed changes according to the contact map.

The host computer must remain online while the team is using EZ Hack.

## 1. Prepare the team

Choose:

1. One host teammate.
2. A short display name for each operator.
3. An operator access level for each teammate.
4. Which teammates should hear about changes proposed by each operator.

Access levels work as follows:

| Level | Capability |
| --- | --- |
| `0` | Read-only access to project context, status, outcomes, and notifications. |
| `1`–`99` | Read access plus the ability to submit proposals. The team decides what the numbers mean in its own hierarchy. |
| `100` | Reserved for the single host. |

All operator changes are proposals. A high level does not bypass host review.

## 2. Install EZ Hack from the private repository

While the repository is private, the repository owner must add every teammate as a GitHub collaborator before they clone it.

Each teammate installs Git, Python 3.11 or newer, and GitHub CLI. Authenticate once:

```bash
gh auth login
```

Then clone and install:

```bash
gh repo clone Keming-Hu/EZ-Hack
cd EZ-Hack
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
```

On Windows PowerShell, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
```

Run EZ Hack commands from the cloned project directory with the virtual environment active.

## 3. Give the host a secure address

Operators on other computers cannot reach `127.0.0.1`. Before host setup, expose port 8000 through an HTTPS tunnel or a TLS reverse proxy.

Assume the resulting public address is:

```text
https://team-host.example
```

The MCP URL is `https://team-host.example/mcp`, and the invitation redemption URL is `https://team-host.example/join`.

Do not expose the service as plain HTTP over the internet. Localhost HTTP is suitable only when every simulated agent runs on the same computer.

## 4. Initialize and start the host

The host runs:

```bash
ez-hack host setup \
  --name "Team Host" \
  --mcp-url "https://team-host.example/mcp"
```

This command generates the only host identity and saves its credential under `.ez-hack/`.

Before starting the service, configure its public address and accepted hostname:

```bash
export EZ_HACK_PUBLIC_URL="https://team-host.example/mcp"
export EZ_HACK_HOST="0.0.0.0"
export EZ_HACK_ALLOWED_HOSTS="team-host.example,team-host.example:*"
ez-hack host start
```

Keep that terminal open. Use another terminal, with the same virtual environment active, for host administration commands.

For a same-computer experiment, skip the public-address environment variables and use:

```bash
ez-hack host setup --name "Team Host"
ez-hack host start
```

## 5. Connect the host coding agent

In a second host terminal:

```bash
ez-hack codex-setup --credentials .ez-hack/host-credentials.json
```

Run the two commands printed by EZ Hack in the terminal that launches Codex. The generated MCP registration follows the Codex CLI pattern documented by OpenAI: `codex mcp add <name> --url <url>`.

Start the host coding-agent conversation in the repository and tell it:

> Read `host/SKILL.md` and follow it as the EZ Hack host for this project.

The MCP configuration is shared by Codex CLI and its IDE extension. Confirm the registration when needed:

```bash
codex mcp list
```

For another MCP-capable agent, register the same MCP URL with the bearer token stored in the host credential file, then give that agent `host/SKILL.md` as its workflow instructions.

## 6. Create one invitation per operator

The host creates a separate invitation for each teammate:

```bash
ez-hack host invite --access-level 10
```

The output resembles:

```json
{
  "join_url": "https://team-host.example/join",
  "invitation_code": "ezh_invite_l10_...",
  "access_level": 10,
  "expires_in_hours": 24,
  "maximum_uses": 1
}
```

Send the join URL and invitation code directly to the intended teammate through a trusted team channel. Invitations are single-use and expire after 24 hours by default.

The level is visible in the invitation for clarity, but it is also bound to the hashed server record. Editing `l10` to another value makes the invitation invalid.

## 7. Let each operator generate an identity

On the operator's computer:

```bash
ez-hack operator setup \
  --url "https://team-host.example/join" \
  --invite "ezh_invite_l10_..." \
  --name "Alice"
```

The command:

1. Redeems the invitation once.
2. Generates a unique operator UUID and bearer credential.
3. Saves them in `ez-hack-credentials.json` with owner-only permissions.
4. Prints the UUID and assigned access level.

The operator sends only the displayed UUID back to the host through the trusted team channel. The bearer credential remains private on the operator's computer.

## 8. Verify and approve the operator

The host lists pending identities:

```bash
ez-hack host operators
```

The host compares the pending UUID with the UUID sent by the teammate. If they match:

```bash
ez-hack host approve "operator-uuid"
```

If an unfamiliar identity appears, leave it inactive. If an active identity must be removed:

```bash
ez-hack host revoke "operator-uuid"
```

The host can change an operator's level at any time:

```bash
ez-hack host access "operator-uuid-or-exact-name" --level 25
```

## 9. Connect each operator coding agent

Each approved operator runs:

```bash
ez-hack codex-setup --credentials ez-hack-credentials.json
```

Run the printed commands in the terminal that launches that operator's Codex session. Then start a conversation in the repository and tell it:

> Read `operator/SKILL.md` and follow it as an EZ Hack operator for this project.

The operator can call `whoami` to confirm its UUID, role, and current access level.

## 10. Configure completion broadcasts

After the relevant operators are active, the host defines directed routes:

```bash
ez-hack host route set "Alice" --notify "Bob" "Carol"
ez-hack host route list
```

This means that when the host completes a request submitted by Alice, Bob and Carol also receive the completion notification. It does not create reverse routes.

Change or remove routes with:

```bash
ez-hack host route set "Alice" --notify "Bob"
ez-hack host route remove "Alice"
```

The CLI updates both the runtime database and the readable `host/CONTACT_MAP.md` file.

## 11. Run the hackathon workflow

### Operator routine

1. Discuss the teammate's idea privately.
2. Read `PROJECT_CONTEXT.md` through MCP for stable project background.
3. Read `DASHBOARD.md` through MCP for current progress.
4. Turn a settled change into a concise proposal.
5. Submit it with the expected result, affected tasks, and current dashboard revision.
6. Give the teammate the returned request ID.
7. Check request status and notifications for the host's decision.

Operators should answer progress questions from shared status instead of sending routine questions to the host.

### Host routine

1. Keep working on the main project task.
2. Finish the current atomic subtask before checking incoming work.
3. At a safe checkpoint, claim one queued proposal.
4. Review its authenticated sender, access level, expected result, affected tasks, and dashboard revision.
5. Complete, reject, or defer it.
6. Record the outcome and resume the saved main-workflow continuation point.
7. Update the dashboard only at meaningful milestones.

## 12. Start-of-day checklist

The host:

```bash
cd EZ-Hack
. .venv/bin/activate
ez-hack host start
```

Then:

- confirm the HTTPS tunnel or reverse proxy still uses the configured address;
- confirm the host agent sees the EZ Hack MCP server;
- run `ez-hack host operators` to inspect active identities;
- run `ez-hack host route list` to inspect broadcasting.

Each operator activates its environment, starts its agent with the saved bearer-token environment variable, and confirms `whoami`.

## 13. End-of-day checklist

1. Stop accepting new work.
2. Let the host process or deliberately defer queued proposals.
3. Update `DASHBOARD.md` with the actual stopping point.
4. Commit and push project source changes.
5. Stop the host service with Ctrl+C.
6. Stop the HTTPS tunnel if the team no longer needs remote access.

Do not commit `.ez-hack/` or `ez-hack-credentials.json`. Both are excluded by this repository's `.gitignore`.

## Common problems

### A browser shows `invalid_token`

The `/mcp` URL is an authenticated machine endpoint. Opening it as a normal web page does not send the bearer credential. Register it in the coding agent using the generated setup command.

### The operator is registered but tools are rejected

The identity is probably still pending. The host must verify the UUID and run `ez-hack host approve`.

### The operator cannot submit a proposal

Call `whoami`. Access level 0 is read-only. The host can assign a proposal-capable level with `ez-hack host access`.

### Another computer cannot connect

Confirm that the host uses a public HTTPS address, the tunnel reaches port 8000, `EZ_HACK_PUBLIC_URL` ends in `/mcp`, and `EZ_HACK_ALLOWED_HOSTS` contains the public hostname.

### A route command rejects a name

Broadcast routes require exact names of active operators and cannot point an operator to itself. Run `ez-hack host operators` and copy the displayed names.

### An invitation no longer works

It may be expired, already redeemed, or edited. Generate a new single-use invitation for that teammate.
