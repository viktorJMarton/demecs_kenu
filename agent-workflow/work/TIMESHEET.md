# Agent timesheet

Record actual observed work time, not estimates. Start an entry when a task is claimed; close or checkpoint it on handoff, blocking, review, completion or session end.

Use Europe/Budapest timestamps unless the execution environment requires UTC; be consistent within an entry.

| Agent / run ID | Role | WORK ID | Kanban IDs | Activity | Start | End / checkpoint | Elapsed | Branch / worktree | Notes |
|---|---|---|---|---|---|---|---|---|---|
| codex-root-20261018 | implementation | WORK-0001 | DB-01 | Existing schema and write-path inventory | 2026-10-18T14:29:32+02:00 | open | open | FEATURE-affiliate-module | Primary implementation claim |
| codex-root-20261026-adm05 | implementation | WORK-0002 | ADM-05 | Dynamic affiliate rule form | 2026-10-26T17:35:57+01:00 | 2026-10-26T17:38:09+01:00 | 00:02:12 | feature/affiliate-adm-05 | Implemented and tested; ready for commit |
| codex-root-20261026-adm06 | implementation | WORK-0002 | ADM-06 | Tour and location scope selector | 2026-10-26T17:40:00+01:00 | 2026-10-26T18:12:41+01:00 | 00:32:41 | feature/affiliate-adm-06 | Implemented and tested; ready for commit |
| codex-root-20261026-adm07 | implementation | WORK-0002 | ADM-07 | Append-only rule versioning | 2026-10-26T18:13:00+01:00 | 2026-10-26T18:14:30+01:00 | 00:01:30 | feature/affiliate-adm-07 | Implemented and tested; ready for commit |
| codex-root-20261026-adm08 | implementation | WORK-0002 | ADM-08 | Server-side rule validation and CSRF | 2026-10-26T18:15:00+01:00 | 2026-10-26T18:16:24+01:00 | 00:01:24 | feature/affiliate-adm-08 | Implemented and tested; ready for commit |
| codex-root-20261026-adm09 | implementation | WORK-0002 | ADM-09 | Responsive referral link UI | 2026-10-26T18:17:00+01:00 | 2026-10-26T18:19:00+01:00 | 00:02:00 | feature/affiliate-adm-09 | Implemented and tested; ready for commit |
| codex-root-20261026-atr01 | implementation | WORK-0003 | ATR-01 | Global referral parameter entry | 2026-10-26T18:19:00+01:00 | 2026-10-26T18:19:36+01:00 | 00:00:36 | feature/affiliate-atr-01 | Implemented and tested; ready for commit |
| codex-root-20261026-atr02 | implementation | WORK-0003 | ATR-02 | Click-time eligible rule selection | 2026-10-26T18:20:00+01:00 | 2026-10-26T18:22:00+01:00 | 00:02:00 | feature/affiliate-atr-02 | Implemented and tested; ready for commit |
| codex-root-20261026-atr03 | implementation | WORK-0003 | ATR-03 | Secure visitor cookie lifecycle | 2026-10-26T18:22:00+01:00 | 2026-10-26T18:25:00+01:00 | 00:03:00 | feature/affiliate-atr-03 | Implemented and tested; ready for commit |
| codex-root-20261027-atr04 | implementation | WORK-0003 | ATR-04 | Atomic last-click attribution | 2026-10-27T00:29:00+01:00 | 2026-10-27T00:32:52+01:00 | 00:03:52 | feature/affiliate-atr-04 | Implemented and tested; ready for commit |
| codex-root-20261027-atr05 | implementation | WORK-0003 | ATR-05 | Bounded click metadata persistence | 2026-10-27T00:33:00+01:00 | 2026-10-27T00:36:00+01:00 | 00:03:00 | feature/affiliate-atr-05 | Implemented and tested; ready for commit |
| codex-root-20261027-atr06 | implementation | WORK-0003 | ATR-06 | Click-event filtering signals | 2026-10-27T00:36:00+01:00 | 2026-10-27T00:37:00+01:00 | 00:01:00 | feature/affiliate-atr-06 | Implemented and tested; ready for commit |
| codex-root-20261027-atr07 | implementation | WORK-0003 | ATR-07 | Safe admin UTM link builder | 2026-10-27T00:37:00+01:00 | 2026-10-27T00:38:00+01:00 | 00:01:00 | feature/affiliate-atr-07 | Implemented and tested; ready for commit |
| codex-root-20261027-atr08 | implementation | WORK-0003 | ATR-08 | Attribution integration test matrix | 2026-10-27T00:38:00+01:00 | 2026-10-27T00:41:00+01:00 | 00:03:00 | feature/affiliate-atr-08 | Implemented and tested; ready for commit |
| codex-root-20261027-cal01 | implementation | WORK-0004 | CAL-01 | Pure calculation service interface | 2026-10-27T00:41:00+01:00 | 2026-10-27T00:44:00+01:00 | 00:03:00 | feature/affiliate-cal-01 | Implemented and tested; ready for commit |
| codex-root-20261027-cal02 | implementation | WORK-0004 | CAL-02 | Percentage and fixed discounts | 2026-10-27T00:44:00+01:00 | 2026-10-27T00:46:00+01:00 | 00:02:00 | feature/affiliate-cal-02 | Implemented and tested; ready for commit |
| codex-root-20261027-cal03 | implementation | WORK-0004 | CAL-03 | Free-participant discounts | 2026-10-27T00:46:00+01:00 | 2026-10-27T00:48:00+01:00 | 00:02:00 | feature/affiliate-cal-03 | Implemented and tested; ready for commit |
| codex-root-20261027-cal04 | implementation | WORK-0004 | CAL-04 | Tracking-only calculation | 2026-10-27T00:48:00+01:00 | 2026-10-27T00:50:00+01:00 | 00:02:00 | feature/affiliate-cal-04 | Implemented and tested; ready for commit |
| codex-root-20261027-cal05 | implementation | WORK-0004 | CAL-05 | Scope and validity eligibility | 2026-10-27T00:50:00+01:00 | 2026-10-27T00:54:00+01:00 | 00:04:00 | feature/affiliate-cal-05 | Implemented and tested; ready for commit |
| codex-root-20261027-cal06 | implementation | WORK-0004 | CAL-06 | Discount cap and rounding | 2026-10-27T00:54:00+01:00 | 2026-10-27T00:56:00+01:00 | 00:02:00 | feature/affiliate-cal-06 | Implemented and tested; ready for commit |
| codex-root-20261027-cal07 | implementation | WORK-0004 | CAL-07 | Total and per-guest limits | 2026-10-27T00:56:00+01:00 | 2026-10-27T00:59:00+01:00 | 00:03:00 | feature/affiliate-cal-07 | Implemented and tested; ready for commit |
| codex-root-20261027-cal08 | implementation | WORK-0004 | CAL-08 | Booking and participant quantities | 2026-10-27T00:59:00+01:00 | 2026-10-27T01:01:00+01:00 | 00:02:00 | feature/affiliate-cal-08 | Implemented and tested; ready for commit |
| codex-root-20261027-cal09 | implementation | WORK-0004 | CAL-09 | Budget-period resolution | 2026-10-27T01:01:00+01:00 | 2026-10-27T01:04:00+01:00 | 00:03:00 | feature/affiliate-cal-09 | Implemented and tested; ready for commit |
