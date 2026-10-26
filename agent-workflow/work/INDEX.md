# Affiliate work queue

The source of truth for detailed task status is **Affiliate modul – fejlesztési Kanban** in the parent folder. This index groups those IDs into dependency-aware agent work packages.

- **WORK-0001 – Data foundation**: DB-01..DB-05. Dependencies: none.
- **WORK-0002 – Admin partner/rule management**: ADM-01..ADM-09. Dependencies: WORK-0001.
- **WORK-0003 – Attribution and tracking**: ATR-01..ATR-08. Dependencies: WORK-0002.
- **WORK-0004 – Pricing, eligibility and limits**: CAL-01..CAL-10. Dependencies: WORK-0001; selected admin/rule contracts from WORK-0002.
- **WORK-0005 – Booking and SimplePay integration**: PAY-01..PAY-08. Dependencies: WORK-0003, WORK-0004.
- **WORK-0006 – Atomic budget lifecycle**: BUD-01..BUD-07. Dependencies: WORK-0004, WORK-0005.
- **WORK-0007 – Reporting**: REP-01..REP-09. Dependencies: WORK-0003, WORK-0005, WORK-0006.
- **WORK-0008 – Commission, settlement and exports**: SET-01..SET-09, EXP-01..EXP-04. Dependencies: WORK-0005, WORK-0006, WORK-0007.
- **WORK-0009 – System verification and release**: TST-01..TST-09, REL-01..REL-06. Dependencies: WORK-0001..WORK-0008.

## Parallelism

After WORK-0001, selected UI/admin, calculation and attribution subtasks may proceed in parallel only where their contracts are already fixed. Payment, usage-budget and settlement work should not race ahead of those contracts.

## Live coordination files

- `AGENT-STATUS.md` = current agent/task ownership and heartbeat.
- `ACTIVITY-LOG.md` = append-only execution journal.
- `TIMESHEET.md` = observed working time.
- Existing Affiliate Kanban = canonical task status.

Before starting a Kanban ID, an agent must check AGENT-STATUS.md and claim the task. A Kanban ID may have only one active primary implementation owner. Review assignments are tracked separately.

## Status rule

Do not duplicate canonical Kanban state here. This file defines routing/dependencies. Agent ownership, journal events and elapsed work time must be maintained in the live coordination files throughout execution.
