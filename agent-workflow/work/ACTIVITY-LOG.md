# Activity log

Append-only project journal. Every material agent event gets one row. Do not rewrite another agent's entries.

Recommended event types: `task_claimed`, `heartbeat`, `change`, `decision`, `test`, `blocked`, `handoff`, `review`, `completed`, `claim_released`.

| Timestamp | Agent / run ID | Role | WORK ID | Kanban IDs | Event | Summary | Evidence / path / command |
|---|---|---|---|---|---|---|---|
| 2026-10-18T14:29:32+02:00 | codex-root-20261018 | implementation | WORK-0001 | DB-01 | task_claimed | Claimed current-schema inventory as the first dependency-free task. | Branch `FEATURE-affiliate-module`; `flaskr/schema.sql`, `flaskr/db.py`, booking/payment write paths |
| 2026-10-26T17:35:57+01:00 | codex-root-20261026-adm05 | implementation | WORK-0002 | ADM-05 | task_claimed | Claimed dynamic affiliate rule form after verifying no active ADM-05 owner. | Branch `feature/affiliate-adm-05`; Kanban status `Folyamatban` |
| 2026-10-26T17:37:30+01:00 | codex-root-20261026-adm05 | implementation | WORK-0002 | ADM-05 | change | Added mode-dependent discount, commission, limit, period and validity controls with server-side irrelevant-field filtering. | `flaskr/admin/admin_affiliates.py`; `flaskr/templates/admin/affiliates/rule_form.html` |
| 2026-10-26T17:38:09+01:00 | codex-root-20261026-adm05 | implementation | WORK-0002 | ADM-05 | test | Targeted and full regression suites pass locally and in the networkless DEV container. | `18 passed`; `46 passed`; `scripts/dev-compose.sh run --rm --build test` |
| 2026-10-26T17:38:09+01:00 | codex-root-20261026-adm05 | implementation | WORK-0002 | ADM-05 | completed | Dynamic rule-field contract complete; persistence remains explicitly assigned to ADM-07 and strict validation to ADM-08. | Branch `feature/affiliate-adm-05` ready for commit |
| 2026-10-26T17:40:00+01:00 | codex-root-20261026-adm06 | implementation | WORK-0002 | ADM-06 | task_claimed | Claimed tour/location scope selector after verifying no active ADM-06 owner. | Branch `feature/affiliate-adm-06`; Kanban status `Folyamatban` |
| 2026-10-26T18:12:41+01:00 | codex-root-20261026-adm06 | implementation | WORK-0002 | ADM-06 | test | Scope UI, normalization and database round-trip pass targeted and full regression tests. | `21 passed`; `49 passed`; networkless DEV Docker `49 passed` |
| 2026-10-26T18:12:41+01:00 | codex-root-20261026-adm06 | implementation | WORK-0002 | ADM-06 | completed | All/tour/location scope selection and lossless persistence helpers complete. | `flaskr/admin/admin_affiliates.py`; `rule_form.html` |
| 2026-10-26T18:13:00+01:00 | codex-root-20261026-adm07 | implementation | WORK-0002 | ADM-07 | task_claimed | Claimed append-only rule versioning after ADM-05 and ADM-06 completion. | Branch `feature/affiliate-adm-07`; Kanban status `Folyamatban` |
| 2026-10-26T18:14:30+01:00 | codex-root-20261026-adm07 | implementation | WORK-0002 | ADM-07 | test | Version creation, active-version handoff and immutable prior configuration pass targeted and full suites. | `22 passed`; local and networkless DEV Docker `50 passed` |
| 2026-10-26T18:14:30+01:00 | codex-root-20261026-adm07 | implementation | WORK-0002 | ADM-07 | completed | Atomic append-only versions and one-active-version lifecycle complete. | `save_rule_version`; partial unique active index |
| 2026-10-26T18:15:00+01:00 | codex-root-20261026-adm08 | implementation | WORK-0002 | ADM-08 | task_claimed | Claimed server-side validation and CSRF hardening. | Branch `feature/affiliate-adm-08`; Kanban status `Folyamatban` |
| 2026-10-26T18:16:24+01:00 | codex-root-20261026-adm08 | implementation | WORK-0002 | ADM-08 | test | Manipulated types, ranges, dates, limit combinations, scope IDs and missing CSRF are rejected. | `29 passed`; local and networkless DEV Docker `57 passed` |
| 2026-10-26T18:16:24+01:00 | codex-root-20261026-adm08 | implementation | WORK-0002 | ADM-08 | completed | Server-authoritative rule validation and production CSRF gate complete. | `_rule_form_errors`; endpoint regression tests |
| 2026-10-26T18:17:00+01:00 | codex-root-20261026-adm09 | implementation | WORK-0002 | ADM-09 | task_claimed | Claimed responsive admin polish and referral URL copy. | Branch `feature/affiliate-adm-09` |
| 2026-10-26T18:19:00+01:00 | codex-root-20261026-adm09 | implementation | WORK-0002 | ADM-09 | completed | Full server-built referral URL and responsive clipboard control complete. | Targeted `30 passed`; full DEV Docker `58 passed` |
| 2026-10-26T18:19:00+01:00 | codex-root-20261026-atr01 | implementation | WORK-0003 | ATR-01 | task_claimed | Claimed global referral parameter entry point. | Branch `feature/affiliate-atr-01` |
| 2026-10-26T18:19:36+01:00 | codex-root-20261026-atr01 | implementation | WORK-0003 | ATR-01 | completed | Bounded normalization and silent stateless rejection for invalid, unknown and inactive refs complete. | Targeted `3 passed`; full DEV Docker `61 passed` |
| 2026-10-26T18:20:00+01:00 | codex-root-20261026-atr02 | implementation | WORK-0003 | ATR-02 | task_claimed | Claimed click-time eligible rule selection. | Branch `feature/affiliate-atr-02` |
| 2026-10-26T18:22:00+01:00 | codex-root-20261026-atr02 | implementation | WORK-0003 | ATR-02 | completed | Exact active, date-valid and capacity-eligible rule version is pinned at click time. | Targeted `5 passed`; full DEV Docker `63 passed` |
| 2026-10-26T18:22:00+01:00 | codex-root-20261026-atr03 | implementation | WORK-0003 | ATR-03 | task_claimed | Claimed secure visitor cookie lifecycle. | Branch `feature/affiliate-atr-03` |
| 2026-10-26T18:25:00+01:00 | codex-root-20261026-atr03 | implementation | WORK-0003 | ATR-03 | completed | Random PII-free visitor cookie follows rule lifetime with HttpOnly, SameSite and environment Secure. | Targeted `7 passed`; full DEV Docker `65 passed` |
| 2026-10-27T00:29:00+01:00 | codex-root-20261027-atr04 | implementation | WORK-0003 | ATR-04 | task_claimed | Claimed atomic last-click attribution. | Branch `feature/affiliate-atr-04` |
| 2026-10-27T00:32:52+01:00 | codex-root-20261027-atr04 | implementation | WORK-0003 | ATR-04 | completed | Eligible clicks atomically insert or replace one attribution per visitor and pin the click-time rule. | Targeted `8 passed`; full DEV Docker `66 passed` |
