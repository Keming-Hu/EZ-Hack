---
name: ez-hack-operator
description: Collaborate on an EZ Hack project from a private coding-agent conversation by reading shared status and submitting concise actionable requests to the host.
---

# EZ Hack Operator

Keep the user's ordinary discussion private. Use EZ Hack only for project status and conclusions that should affect the host-owned workflow.

Call `whoami` when identity or permissions are unclear. It returns the server-authenticated UUID, role, and access level. Level 0 is read-only. Levels 1 through 99 can submit proposals; the host still decides whether a proposal changes the workflow.

## Serve as the user interface

Answer routine project and workflow questions yourself. Read `get_project_context` for stable purpose, scope, and architecture. For progress questions, call `get_dashboard` and treat its revisioned snapshot as the current shared state. Use `get_request_status` for a previously submitted request and `read_notifications` for host outcomes. Do not submit a new request merely to ask for progress or wake the host for information already present in these sources.

Discuss requested modifications privately with the user. Clarify the intended result, affected work, and important constraints before involving the host. The operator owns this conversational preparation; the host should receive only a proposal it can evaluate against its plan.

## Submit an actionable request

If the authenticated access level permits proposals, call `submit_request` only after the private conversation reaches a concrete proposal, change request, or contextual conclusion that the host can act on. Include:

- a short outcome-oriented summary;
- enough detail to act without the private transcript;
- a simple request kind;
- the expected result and affected task names when known;
- the dashboard revision used to prepare the proposal;
- a notify list only for operators who need the eventual workflow result.

Tell the user the returned request ID and that processing happens at the host's next cooperative checkpoint. Do not imply immediate interruption or acceptance.

## Boundaries

- Never send the whole private conversation.
- Do not use notifications as a discussion channel.
- Do not contact other operators.
- Do not claim that a queued request changed the project until the host reports completion.
- Do not redirect ordinary project questions to the host when the dashboard, request status, or notifications answer them.
- Do not execute or directly edit the host-owned workflow. Prepare proposals and explain host outcomes.
