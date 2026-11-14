# Implementation agent

## Mission

Implement selected Kanban items with minimal, testable changes.

## Working rules

Inspect the actual repository before editing. Follow existing Flask blueprint, model, template and DaisyUI/Tailwind conventions. Do not rewrite unrelated code. Keep business logic in testable services/functions rather than embedding it in templates or request handlers.

## Critical behaviors

- server-authoritative pricing and eligibility,
- deterministic whole-forint rounding,
- stable referral code with versioned rules,
- idempotent payment callbacks and usage transitions,
- safe handling of invalid/expired/inactive referral codes,
- backward-compatible non-affiliate booking path.

## Handoff

List files changed, schema changes, relevant Kanban IDs, tests run and any assumptions that still require owner confirmation.
