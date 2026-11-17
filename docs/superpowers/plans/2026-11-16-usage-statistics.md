# Server usage statistics

Goal: retain accepted nonzero hold-command totals per gate, person, and person
on each gate. These count broker-accepted commands, not physical gate openings.
The existing gate `holdCount` remains authoritative and is not reset/backfilled.
New person counters begin with this deployment. No new browser/UI/API access.

Architecture: extend the existing pending-to-accepted command transaction in
`firebase/functions/store.cjs`. Obtain UID and duration from the reserved command,
not caller-supplied identity. Hash the UID for a fixed-length document key.
Increment `usagePeople/<sha256(uid)>.holdCount` and
`devices/<id>/usagePeople/<sha256(uid)>.holdCount`, storing UID for IAM analysis.
Use Firestore increment transforms in the transaction to preserve concurrent
cross-gate counts. The command's pending check supplies idempotency. End hold,
unknown, denied, replayed and still-pending commands do not count. Deny-all
client rules already cover both paths; public device lists stay unchanged.

1. Add real emulator regressions in `test-emulator/store.test.cjs` for counts
   across people/gates, duplicate finish/request races, unknown/end-hold/pending
   exclusions, private response shape and direct-client rule denial.
2. Run `make web-test-emulator`; require new missing-counter failures.
3. Add `FieldValue.increment(1)` merged writes to both private paths before the
   existing transaction writes; only after confirming a pending accepted hold.
   Derive keys/UID from `command.data()`. Keep existing gate count and active hold
   behavior. Never publish extra commands or retry uncertain delivery.
4. Run `make web-test` and `make precommit`. Update Firebase/AGENTS documentation
   with exact schema, semantics and forward-only person counting.
5. Commit/push and deploy Functions after successful checks. Deployment must not
   actuate a real gate or modify device OTA assignments. Verify live API denial
   and production function deployment; no synthetic production usage writes.
