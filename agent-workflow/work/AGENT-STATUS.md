# Agent status

Live ownership table for the Demecs Kenu affiliate development.

Rules:

- Read this file before claiming work.
- One Kanban ID may have only one active primary implementation owner.
- Reviewers may coexist with the primary owner when their role is marked `reviewer`.
- Update on claim, material status change, handoff, completion and at least every 30 minutes during long-running work when supported.
- A heartbeat older than 60 minutes is only a stale candidate; the orchestrator must inspect ACTIVITY-LOG.md before reassignment.
- Do not delete historical rows. Close them with `done` or `released`, then append a new row for a new claim.

| Agent / run ID | Role | WORK ID | Kanban IDs | Ownership | Branch / worktree | Status | Started | Last heartbeat | Blocker / next action |
|---|---|---|---|---|---|---|---|---|---|
| codex-root-20261018 | implementation | WORK-0001 | DB-01 | primary | FEATURE-affiliate-module | working | 2026-10-18T14:29:32+02:00 | 2026-10-18T14:29:32+02:00 | Map current schema and write inventory |
