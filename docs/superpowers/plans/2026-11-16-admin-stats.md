# Administration Stats tab

Approved design: third admin tab, devices with total holds, expandable people
sorted by count, name/email identity, shared refresh button. Counts mean
broker-accepted nonzero holds. Person tracking began November 16, 2026; older
device totals may exceed the person breakdown. No gate commands or firmware edits.

## Read API

Create `firebase/functions/statistics.cjs`, `createStatistics({db, auth})`, read
method behind a new `adminStats` callable using existing Google/App Check/runtime
options. No deviceId returns up to 200 device summaries. deviceId returns the
highest 200 person counters for that device, resolving Firebase Auth identities
in batches of 100. Queries read 201 items and return explicit truncation flags.
Reject invalid input and missing devices; verify current admin inside a read
transaction before data access. Recheck role after external identity lookups.
Return only device id/name/count and opaque person id/name/email/count. No UID,
credentials, command IDs, raw Auth profiles or global user totals leave the API.
A deleted account remains an identifiable unavailable-account row. Auth failures
fail the request. Reading never creates/updates counts or publishes anything.

## UI

Add third accessible tab/panel in `web/index.html`; wire `adminStats` in real
and test gateways. `web/admin.js` owns lazy device/person loading, native details
expansion, retained expansion across refresh, empty/loading/error/limited states.
Text rendering only. Epoch checks discard late responses after refresh/logout/
offline and clear private stats on close/offline/errors. Existing tabs, keyboard
navigation, reset polling and mutation handling stay intact. CSS handles narrow
screens, long identities and readable count columns. Refresh reads current data.

## Execution

1. Add mobile Chromium/WebKit regression first; run it and observe missing Stats
   tab failure. Add backend unit/emulator tests for auth, fresh revocation,
   sorting/limits, deleted identities, response allowlisting and read-only state.
2. Implement read API/index/gateway, then safe UI and test gateway fixtures.
3. Run targeted tests, then full `make web-test` and `make precommit`. Inspect
   mobile screenshots and fix layout. Request code review; fix any blockers.
4. Update Firebase README/AGENTS. Commit/push. Build and deploy generated Hosting
   plus adminStats Function using the production project/account; verify deployed
   UI asset and live auth/unsigned API denial. Never issue physical gate commands.
