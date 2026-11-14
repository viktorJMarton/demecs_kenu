# Reporting and settlement agent

## Mission

Build reproducible admin reporting, commission settlement and exports from authoritative stored snapshots.

## Metrics

Clicks, estimated unique visitors, source/campaign/landing page, payment starts, successful/cancelled bookings, conversion, participants, original value, discount, paid revenue, commission, unsettled and paid commission.

## Rules

Reports must derive financial values from booking snapshots, not current partner rules. Filters must be server-validated and stable in URLs. Monthly aggregation after detailed-retention expiry must preserve totals.

## Exports

CSV and TXT must use deterministic columns/ordering, UTF-8, reproducible totals and safe filenames. UI, print, CSV and TXT totals must match.

## Settlement

Only eligible successful, not-cancelled and not-yet-settled bookings may enter a settlement. Closing freezes items and totals. Paid marking happens once.
