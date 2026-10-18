# EZ Hack Project Context

## Purpose

EZ Hack connects one host coding agent with several operator coding agents. The operators give users a responsive, project-aware interface while the host remains focused on executing the primary workflow.

## Responsibilities

### Operators

- Answer questions about the project and current workflow.
- Discuss and clarify requested modifications with their users.
- Turn settled requests into concise structured proposals.
- Track submitted proposals and explain host outcomes.
- Keep private conversation out of the shared service.

### Host

- Own and execute the primary project workflow.
- Publish meaningful workflow milestones through the dashboard.
- Evaluate authenticated proposals at safe checkpoints.
- Integrate a proposal only when it fits the current plan or a justified plan revision.
- Defer, complete, or reject proposals and report the result.

## Shared state

- `PROJECT_CONTEXT.md` contains stable background for operator explanations.
- `DASHBOARD.md` contains the current revisioned workflow snapshot.
- The SQLite request queue durably stores structured proposals and outcomes.
- `host/CONTACT_MAP.md` defines notification routing after completed changes.

## Identity and access

- The host is the single level-100 identity and owns admission, access assignment, and broadcast routing.
- Operator identities use server-generated UUIDs and bearer credentials.
- An invitation binds a new operator to an access level. The identity stays inactive until the host verifies and approves its UUID.
- Level 0 is read-only. Levels 1 through 99 can submit proposals, with the authenticated level included for the host's user-defined policy.
- An operator's access level never bypasses host review or directly changes the workflow.

## Communication boundary

Operators do not modify the host workflow directly and do not communicate with one another through EZ Hack. The host receives actionable proposals instead of private transcripts or routine questions. The host alone decides whether and when a proposal becomes part of the workflow plan.
