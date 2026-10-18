# EZ Hack: Play With a Friend

This is the practical first-run guide for you and a friend. One of you runs the **host**; the other joins as an **operator**. The host does the main project work. The operator talks with their user, checks shared progress, and sends clear proposals to the host.

The project is currently in a private GitHub repository, so both people need access to it. You can follow these steps on separate computers. At the end there is a same-computer option for a quick local experiment.

## What the team is setting up

- One teammate runs the **host** service and the main coding-agent workflow.
- Every other teammate runs an **operator** conversation on their own computer.
- Operators answer routine questions, clarify ideas, and submit structured proposals.
- The host reviews proposals at safe workflow checkpoints and broadcasts completed changes according to the contact map.

The host computer must remain online while the team is using EZ Hack.

## 1. Give your friend GitHub access

The repository owner adds the friend as a collaborator:

1. Open [EZ Hack on GitHub](https://github.com/Keming-Hu/EZ-Hack).
2. Open **Settings → Collaborators**.
3. Add your friend's GitHub username and have them accept the invitation.

The repository is private, so a friend cannot clone it until access is accepted.

## 2. Install EZ Hack on both computers

Both people need Git and Python 3.11 or newer. The friend also needs GitHub CLI (`gh`) and a GitHub login that can access this private repository.

Each person runs:

```bash
gh auth login
gh repo clone Keming-Hu/EZ-Hack
cd EZ-Hack
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
```

On Windows PowerShell:

```powershell
gh auth login
gh repo clone Keming-Hu/EZ-Hack
cd EZ-Hack
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install .
```

Keep the terminal open or activate `.venv` again whenever opening a new terminal. Run the `ez-hack` commands below from this cloned project directory.

## 3. Pick who does what

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

## 4. Choose local or two-computer play

For the quickest experiment, keep the host and operator on the same computer. Use `http://127.0.0.1:8000`; no tunnel is needed.

For two computers, `127.0.0.1` points to each person's own computer, so it cannot connect the operator to the host. The host must expose port 8000 through an HTTPS tunnel or TLS reverse proxy. Use a tunnel service your team trusts and keep it running during the session. Assume its public address is:

```text
https://team-host.example
```

The MCP URL is `https://team-host.example/mcp`, and the invitation redemption URL is `https://team-host.example/join`. Use your actual tunnel hostname everywhere in this guide.

Do not expose the service as plain HTTP over the internet. Localhost HTTP is suitable only when every simulated agent runs on the same computer.

## 5. Initialize and start the host

Choose one setup command. For two computers, the host runs:

```bash
ez-hack host setup \
  --name "Team Host" \
  --mcp-url "https://team-host.example/mcp"
```

This command generates the only host identity and saves its credential under `.ez-hack/`.

Before starting the service, set its public address and accepted hostname. These values must match the HTTPS tunnel hostname:

```bash
export EZ_HACK_PUBLIC_URL="https://team-host.example/mcp"
export EZ_HACK_HOST="0.0.0.0"
export EZ_HACK_ALLOWED_HOSTS="team-host.example,team-host.example:*"
ez-hack host start
```

Keep that terminal open. Use another terminal, with the same virtual environment active, for host administration commands.

For a same-computer experiment, use this setup command instead and skip the public-address variables:

```bash
ez-hack host setup --name "Team Host"
ez-hack host start
```

## 6. Connect the host coding agent

In a second host terminal:

```bash
ez-hack codex-setup --credentials .ez-hack/host-credentials.json
```

Run the two commands printed by EZ Hack in the terminal that launches Codex. The generated MCP registration follows the Codex CLI pattern documented by OpenAI: `codex mcp add <name> --url <url>`.

Restart Codex after adding the MCP server if it was already running. Start the host coding-agent conversation in the repository and tell it:

> Read `host/SKILL.md` and follow it as the EZ Hack host for this project.

The MCP configuration is shared by Codex CLI and its IDE extension. Confirm the registration when needed:

```bash
codex mcp list
```

For another MCP-capable agent, register the same MCP URL with the bearer token stored in the host credential file, then give that agent `host/SKILL.md` as its workflow instructions. Keep the host credential private; only share invitation codes with operators.

## 7. Create an invitation for your friend

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

## 8. Your friend generates their operator identity

On the operator's computer (use the local URL instead if both agents are on one computer):

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

## 9. Verify and approve your friend

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

## 10. Connect the operator coding agent

Each approved operator runs:

```bash
ez-hack codex-setup --credentials ez-hack-credentials.json
```

Run the printed commands in the terminal that launches that operator's Codex session. Then start a conversation in the repository and tell it:

> Read `operator/SKILL.md` and follow it as an EZ Hack operator for this project.

Restart the operator's agent after registering MCP if it was already running. The operator can call `whoami` to confirm its UUID, role, and current access level.

## 11. Set who should receive completion broadcasts

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

## 12. Try a first proposal together

### Operator routine

Start the operator conversation with:

> Read `operator/SKILL.md` and act as the operator for this project. Check the shared project context and dashboard, then help me prepare a small, concrete proposal for the host: [describe the change]. Submit it when the request is clear, and give me the request ID.

Choose a change that fits the host's agreed task. Save the request ID and check its status and notifications for the host's decision.

Operators should answer progress questions from shared status instead of sending routine questions to the host.

### Host routine

Start the host conversation with:

> Read `host/SKILL.md`. Work on this small project task: [describe the task]. Keep the work in clear atomic steps, update the dashboard at meaningful milestones, and check the EZ Hack request queue at safe checkpoints.

When a request arrives, the host reviews it against the task, completes, rejects, or defers it, then reports the outcome through MCP. Confirm the operator receives the notification.

The host decides when to act. Submitting a proposal does not interrupt an atomic step or guarantee acceptance.

## 13. Start the service again later

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

## 14. End the session safely

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
