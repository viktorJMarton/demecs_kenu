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
| codex-root-20261026-adm05 | implementation | WORK-0002 | ADM-05 | primary | feature/affiliate-adm-05 | done | 2026-10-26T17:35:57+01:00 | 2026-10-26T17:38:09+01:00 | Dynamic fields complete; 18/18 targeted and 46/46 full DEV Docker tests pass |
| codex-root-20261026-adm06 | implementation | WORK-0002 | ADM-06 | primary | feature/affiliate-adm-06 | done | 2026-10-26T17:40:00+01:00 | 2026-10-26T18:12:41+01:00 | Scope selector complete; 21/21 targeted and 49/49 full DEV Docker tests pass |
| codex-root-20261026-adm07 | implementation | WORK-0002 | ADM-07 | primary | feature/affiliate-adm-07 | done | 2026-10-26T18:13:00+01:00 | 2026-10-26T18:14:30+01:00 | Append-only versioning complete; 22/22 targeted and 50/50 full DEV Docker tests pass |
| codex-root-20261026-adm08 | implementation | WORK-0002 | ADM-08 | primary | feature/affiliate-adm-08 | done | 2026-10-26T18:15:00+01:00 | 2026-10-26T18:16:24+01:00 | Validation and CSRF complete; 29/29 targeted and 57/57 full DEV Docker tests pass |
| codex-root-20261026-adm09 | implementation | WORK-0002 | ADM-09 | primary | feature/affiliate-adm-09 | done | 2026-10-26T18:17:00+01:00 | 2026-10-26T18:19:00+01:00 | Responsive referral link UI complete; 30/30 targeted and 58/58 full DEV Docker tests pass |
| codex-root-20261026-atr01 | implementation | WORK-0003 | ATR-01 | primary | feature/affiliate-atr-01 | done | 2026-10-26T18:19:00+01:00 | 2026-10-26T18:19:36+01:00 | Global ref entry complete; 3/3 targeted and 61/61 full DEV Docker tests pass |
| codex-root-20261026-atr02 | implementation | WORK-0003 | ATR-02 | primary | feature/affiliate-atr-02 | done | 2026-10-26T18:20:00+01:00 | 2026-10-26T18:22:00+01:00 | Click-time rule selection complete; 5/5 targeted and 63/63 full DEV Docker tests pass |
| codex-root-20261026-atr03 | implementation | WORK-0003 | ATR-03 | primary | feature/affiliate-atr-03 | done | 2026-10-26T18:22:00+01:00 | 2026-10-26T18:25:00+01:00 | Secure visitor cookie complete; 7/7 targeted and 65/65 full DEV Docker tests pass |
| codex-root-20261027-atr04 | implementation | WORK-0003 | ATR-04 | primary | feature/affiliate-atr-04 | done | 2026-10-27T00:29:00+01:00 | 2026-10-27T00:32:52+01:00 | Last-click attribution complete; 8/8 targeted and 66/66 full DEV Docker tests pass |
| codex-root-20261027-atr05 | implementation | WORK-0003 | ATR-05 | primary | feature/affiliate-atr-05 | done | 2026-10-27T00:33:00+01:00 | 2026-10-27T00:36:00+01:00 | Tracking metadata complete; 9/9 targeted and 67/67 full DEV Docker tests pass |
| codex-root-20261027-atr06 | implementation | WORK-0003 | ATR-06 | primary | feature/affiliate-atr-06 | done | 2026-10-27T00:36:00+01:00 | 2026-10-27T00:37:00+01:00 | Filtered click-event logging complete; 10/10 targeted and 68/68 full DEV Docker tests pass |
| codex-root-20261027-atr07 | implementation | WORK-0003 | ATR-07 | primary | feature/affiliate-atr-07 | done | 2026-10-27T00:37:00+01:00 | 2026-10-27T00:38:00+01:00 | Safe admin UTM link builder complete; 31/31 targeted and 69/69 full DEV Docker tests pass |
| codex-root-20261027-atr08 | implementation | WORK-0003 | ATR-08 | primary | feature/affiliate-atr-08 | done | 2026-10-27T00:38:00+01:00 | 2026-10-27T00:41:00+01:00 | Attribution integration flow complete; 1/1 targeted and 70/70 full DEV Docker tests pass |
| codex-root-20261027-cal01 | implementation | WORK-0004 | CAL-01 | primary | feature/affiliate-cal-01 | done | 2026-10-27T00:41:00+01:00 | 2026-10-27T00:44:00+01:00 | Pure calculation interface complete; 5/5 targeted and 75/75 full DEV Docker tests pass |
| codex-root-20261027-cal02 | implementation | WORK-0004 | CAL-02 | primary | feature/affiliate-cal-02 | done | 2026-10-27T00:44:00+01:00 | 2026-10-27T00:46:00+01:00 | Percentage and fixed discounts complete; 10/10 targeted and 80/80 full DEV Docker tests pass |
