# Codex handoff — Lightweight host/operator collaboration extension

## Mission

Implement an MVP of a **plug-and-play, model-agnostic collaboration extension** for small teams (roughly 2–5 people), especially hackathon teams and AI-native small businesses. Multiple people should be able to contribute to **one shared AI-driven project workflow** through their own private coding-agent conversations. Do not turn this into a broad multi-agent orchestration platform.

The intended experience:

- Host: install extension, create a project, share connection/invitation details.
- Teammate: install extension in an existing coding agent (Claude Code, Codex, etc.), join, and continue conversing privately.
- Operators send **occasional actionable requests** to the host. Routine discussions remain local. Users can ask for progress without waking the host.

## Agreed architecture

**Star topology:** one host and N operators. Operators do not communicate with each other. Human teammates can communicate through their ordinary channels. The host alone owns and executes the primary project workflow.

1. **Host agent**: any existing coding agent, with `host/SKILL.md`. Owns project changes, processes incoming requests, maintains workflow status, and issues relevant notifications.
2. **Operator**: a user's *existing* coding agent with `operator/SKILL.md`, not an always-running separate daemon/agent. Maintains a private user conversation and submits structured, actionable conclusions to the host when appropriate.
3. **Host-local MCP server**: runs as a separate process on the host's machine. Provides communication tools to heterogeneous MCP-capable agents on different computers. Persists authenticated messages in a queue and exposes read-only status. Use secure remote access; localhost alone cannot serve remote teammates.
4. **Persistent FIFO queue**: operators submit concurrently; the host handles requests sequentially at cooperative checkpoints. Do **not** implement priority-queue scheduling or forced mid-turn interruption for MVP. Retain identity/role/priority metadata for future use.
5. **`DASHBOARD.md`**: host-maintained snapshot of current task, completed/pending work, blockers, recent changes, and update timestamp. MCP server exposes it read-only, so operators can answer frequent progress questions without asking the host to reason. A lightweight web rendering of this same data is desirable, not a separate source of truth.

### Message directions

- Operator → host: structured modification requests, proposals, contextual advice.
- Host → operator: acceptance/rejection/completion outcomes and selective project notifications.
- No operator ↔ operator messaging. No host-facilitated human chat.

Each operator request may include a **notify list** identifying other operators who should receive a status update if the request changes the workflow. Host skill may add affected recipients and may broadcast truly project-wide changes. Notifications are brief workflow events, not conversational negotiations.

## Roles and trust

- Each joined operator has an authenticated identity/token associated with a user and role/permission level. Credentials should be verified by the server and not placed inside the model-readable natural-language prompt.
- Host receives authenticated sender metadata and applies authority/priority rules defined in its skill codebook. Policy decisions can be skill-guided, but basic credential verification and tool access boundaries must be enforced by trusted code.
- Separate authorization (may this operator request this modification?) from scheduling priority (when to consider it?). Start with FIFO even across roles.
- Keep each user's private chat private. Forward only selected actionable content, not the whole transcript.

## Skills vs. server

Skills govern behavior: what qualifies as an actionable request; how to summarize it; when host checks inbox; how host treats roles, responds, updates dashboard, and notifies affected operators.

MCP tools provide capabilities; server code implements actual message transport, durable queue, authentication, and dashboard reads. Skill Markdown itself is not a secure transport or an always-running scheduler.

Suggested conceptual tools (names not fixed): `join_project`, `submit_request`, `get_next_request`, `complete_request`, `get_dashboard`, `read_notifications`, and `notify`. Minimize interfaces for MVP.

## Constraints / user preferences

- **Keep the MVP small.** Avoid premature features such as peer-to-peer agent messaging, broad organizational management, complex priority scheduling, dynamic agent spawning, sophisticated conflict arbitration, distributed hosting, elaborate dashboard frameworks.
- **Implementation first, verification afterward**; the user explicitly objected to an elaborate testing experiment before implementation. Once built, verify safely.
- Build an *extension* for existing coding agents, not a new IDE, chatbot, or proprietary agent runtime.
- Portability matters: Claude Code host with Codex operator (and vice versa) should be an intended configuration, subject to actual MCP/skills support.
- Avoid too many implementation steps in one response. Discuss decisions incrementally when necessary.
- Host should only refresh `DASHBOARD.md` at meaningful milestones (task start/completion, blockers, decisions); include `last_updated`. Never invent progress.
- Host is often busy with long tasks. Queued requests need not interrupt it. Cooperative checkpoints suffice for MVP; acknowledge the latency tradeoff.

## Relevant open-source references (investigate, don't assume their code meets our requirements)

- [vkolotov/mcp-agent-collaboration](https://github.com/vkolotov/mcp-agent-collaboration): coordinator/secondary identities, join tokens, MCP messages, broadcast, check-ins/long polling; closest communication model.
- [tkellogg/postal-mcp](https://github.com/tkellogg/postal-mcp): very minimal SQLite-backed HTTP MCP mailbox/queue.
- [oxiaom/collab-mcp](https://github.com/oxiaom/collab-mcp): TrustBase Collab MCP; API keys/JWT, join policies, roles, broadcast, shared tasks, SQLite. More peer-oriented than our star hierarchy.
- [Dymyt-ry/warren](https://github.com/Dymyt-ry/warren): multi-computer agent rooms, scoped identity, MCP and cross-vendor delivery adapters.
- [multiagentcognition/macp](https://github.com/multiagentcognition/macp): draft protocol on top of MCP, not an established standard.

No exact mature implementation of our private-human-operator → single-host-workflow product was verified. Prefer borrowing a small communication component if licensing/architecture suits, but do not assume it is production ready.

## What to do in Codex

Treat the architecture above as the current product specification. First inspect the new project/workspace and propose a **minimal file layout and implementation scope**, then implement the extension and communication service. Ask only for blocking decisions (for example, deployment/network exposure and language/runtime if they materially affect build). Keep the product's simplicity and the user's original hackathon pain point central.
