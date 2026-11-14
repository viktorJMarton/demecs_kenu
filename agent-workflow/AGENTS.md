# Demecs Kenu affiliate – agent contract

## Read routing

Start with the current affiliate specification and Kanban in the parent folder. Read only the role file required for the selected work package, then the relevant code and tests. Do not treat planning documents as implemented behavior.

Before starting any work, also read:

- `work/AGENT-STATUS.md` for active ownership,
- `work/ACTIVITY-LOG.md` for recent events,
- `work/TIMESHEET.md` for time accounting.

## Product truth

The affiliate module extends the existing Flask–SQLite–Jinja–SimplePay application. Preserve the current booking and payment flow for non-affiliate customers. The server is authoritative for pricing, eligibility, usage limits, commission and payment amounts.

## Core invariants

- A partner has one stable referral code; rule changes create new versions.
- Attribution is last valid click unless the selected rule says session-only.
- Public UI never exposes partner commission or internal partner metadata.
- Client-supplied price, partner ID, discount or commission is never trusted.
- Payment amount sent to SimplePay must equal the server-calculated booking amount.
- Usage reservation/finalization/release must be idempotent.
- Parallel bookings must not exceed partner or guest limits.
- Successful bookings keep immutable financial and rule snapshots.
- Refund/cancellation reversals may happen once only.
- Existing non-affiliate checkout remains behaviorally unchanged.

## Engineering

Prefer cohesive services with explicit inputs/outputs. Keep request handling, business rules, persistence and payment integration separated. Avoid speculative abstractions. SQLite operations that protect money, limits or state transitions must use explicit transactions and database-enforced uniqueness where possible.

## Security and privacy

Use server-side validation, CSRF protection for admin writes, Secure/HttpOnly/SameSite cookies as applicable, and no PII in logs unless strictly required. Never store bank account data. Treat referral parameters, UTM values, referrers and user input as untrusted.

## Work discipline

Use one WORK ID for each bounded change. Record status against the existing Kanban IDs (DB/ADM/ATR/CAL/PAY/BUD/REP/SET/EXP/TST/REL). Keep evidence concise: changed paths, migration/test commands, exit status, fixtures and blockers. Do not mark work complete solely because documentation exists.

## Mandatory live coordination

Every agent must keep the Drive project journal/timesheet current while working.

Before claiming a task:

1. Read the Kanban and `work/AGENT-STATUS.md`.
2. Verify that the target Kanban ID has no other active primary owner.
3. Register the claim with agent/run ID, role, WORK ID, Kanban IDs, branch/worktree, start timestamp and status=`working`.
4. Append a `task_claimed` event to `work/ACTIVITY-LOG.md`.

While working:

- Update `AGENT-STATUS.md` after every material state change and at least once every 30 minutes during long-running work when the execution environment supports it.
- Append material events to `ACTIVITY-LOG.md`: file/schema changes, decisions, tests, failures, blockers, handoffs and review results.
- Record actual elapsed work in `TIMESHEET.md`; do not substitute estimates for observed time.
- Keep the existing Affiliate Kanban status synchronized with the current task state.
- An agent may be reviewer on another task, but a Kanban ID has only one active primary implementation owner.
- Never overwrite another agent's journal/timesheet entries. Append new entries; the orchestrator reconciles conflicts.

When stopping or handing off:

- Update status to `reviewing`, `blocked`, `done` or `released`.
- Close or checkpoint the timesheet entry with end timestamp and elapsed time.
- Append a handoff/blocker/completion event.
- Release the primary claim when responsibility moves to another agent.

A status entry older than 60 minutes without a heartbeat is only a stale candidate. The orchestrator must inspect the activity log before reassigning it; agents must never steal the task automatically.

## Review

Payment, commission, refund, usage-limit, attribution and migration changes require independent review. Security-sensitive changes require the security agent. Release requires the testing and release roles to verify the latest code revision.

## Definition of done

Acceptance criteria from the existing Kanban are met, regression tests pass, financial invariants are verified, migrations are reversible or have a documented recovery path, release/rollback steps are current, and the status/activity/timesheet records are closed and consistent.
