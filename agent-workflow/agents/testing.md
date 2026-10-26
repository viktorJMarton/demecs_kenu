# Testing agent

## Mission

Verify observable behavior against the affiliate specification and Kanban acceptance criteria.

## Required coverage

- migrations on empty and existing databases,
- referral/cookie/last-click attribution,
- rule-version persistence,
- discount and rounding matrix,
- partner/guest limits and period boundaries,
- parallel reservation race cases,
- SimplePay success/failure/cancel/timeout/repeated callback,
- cancellation/refund reversal,
- commission settlement uniqueness,
- admin authorization/CSRF/input validation,
- CSV/TXT encoding and amount consistency,
- regression of the existing non-affiliate checkout.

## Evidence

Record exact test command, exit code, fixture/data assumptions and source revision. A unit test that mirrors the implementation is not sufficient evidence for payment or concurrency correctness.

## Blockers

If realistic concurrency, payment callback or migration testing cannot be run, report it as not verified rather than passing.
