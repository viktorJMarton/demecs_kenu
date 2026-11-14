# Release agent

## Mission

Prepare a controlled deployment of the affiliate module without breaking the existing booking flow.

## Preconditions

- All P0 Kanban acceptance criteria verified.
- Database backup and restore procedure tested.
- Migration tested on a production-like copy and rerun safely.
- Existing non-affiliate checkout regression is green.
- Affiliate functionality can be enabled gradually via feature flag.
- Rollback steps are documented.

## Go/no-go

Run an internal test-partner E2E path: referral click -> attribution -> booking -> SimplePay -> callback -> reporting -> settlement. Check amounts and state transitions in both UI and database.

## Handoff

Record deployed revision, migration result, enabled flags, smoke-test evidence, rollback point and unresolved risks.
