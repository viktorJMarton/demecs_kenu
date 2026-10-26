# Affiliate agent workflow

This folder adapts the P2P/Homework agent-document pattern to the Demecs Kenu affiliate module.

## Structure

- `AGENTS.md` – repository-level agent contract for this feature.
- `agents/` – role-specific operating instructions.
- `work/INDEX.md` – dependency-aware work routing mapped to the existing Kanban IDs.
- `work/AGENT-STATUS.md` – live ownership/heartbeat table showing which agent is on which task.
- `work/ACTIVITY-LOG.md` – append-only project journal of material agent events.
- `work/TIMESHEET.md` – actual observed agent work time by WORK/Kanban ID.
- `templates/handoff.md` – standard handoff format.

## Intended use

An orchestrator selects one executable work package, checks current ownership, loads only the relevant role documents and source files, assigns implementation/review responsibilities, and records evidence. Roles are instructions, not proof that an autonomous agent is currently running.

The Drive coordination files are part of the work protocol, not optional documentation. Agents must update them at task claim, meaningful progress, testing, blocking, handoff and completion. Long-running work should heartbeat at least every 30 minutes when the execution environment supports it.

The canonical business requirements remain the parent-folder documents:

- **Feladatbontás és becslés**
- **Affiliate modul – fejlesztési Kanban**

The Kanban remains the task-status authority; the status/activity/timesheet files provide live agent ownership, audit trail and actual work-time evidence.

If this agent workflow conflicts with the product requirements, the product requirements win unless the owner explicitly approves a change.
