# Coordinated restart setup and next-reboot selector

Approved objective: repeat Wi-Fi + QR onboarding without losing the device's
trusted identity or existing access. Keep one normal device screen. Add an
explicit one-shot next-boot Wi-Fi choice instead of requiring a startup chord.
User chose D2 as the dedicated next-boot toggle, with its action displayed on
the bottom TFT row. D0/D1 in normal operation show the ordinary website QR,
press again to return, with a short auto-return timeout. Keep the current hold
countdown and D2 reboot choice visible on the QR screen. This website QR never
contains the pairing proof. Retain D1-at-startup as recovery.

## Shared implementation contract

- Web uses existing `adminChange` with action `restartSetup`, deviceId, fresh
  issuedAtMs and requestId. Verified Google + App Check and a fresh transactional
  admin role remain mandatory. Deduplicate by existing admin audit key.
- Only enabled, registered devices with a trusted binding and advertised
  `maintenance.supportsRestartSetup === true` qualify. Reject known active
  `activeHold` (startedAtMs + durationSeconds*1000 > now), pending command IDs,
  incompatible devices, and overlapping resets. The actual board also checks
  its local hold lease and defers all reset work until idle.
- Store `devices/<id>.setupReset` with a stable 64-hex id (audit hash), state,
  requestedAtMs and actor internally. States: `pending`, `awaiting_setup`,
  `provisioning`, `complete`. Request creation sets enabled false, blocking new
  commands transactionally, while preserving allowedUsers, name, counters,
  command audit, firmware fields and trusted pairing binding.
- Extend existing deviceRegister POST with private-proof-authenticated actions
  `maintenance` and `restart_setup_complete`. No new public identity/bootstrap
  mechanism. Keep generic errors/no-store and never return credentials to web.
- `maintenance` body includes app_version and base_version. It advertises
  restart-setup capability and updates `device.maintenance` with public version
  metadata, lastSeenAtMs and supportsRestartSetup true. It returns
  `{deviceId, restartSetup: null | {id, state}}`. Validate supported firmware
  (base >=1.0.13) and private proof against the trusted binding/envelope.
- Firmware polls while idle, initially then approximately every 20 seconds;
  skip HTTPS maintenance while holding. If pending, drain MQTT once, check idle
  again, durably save setup_reset_id plus setup_reset_pending true, then close
  MQTT before acknowledging. On boot, resume a pending reset before reconnecting
  MQTT. Keep Wi-Fi credentials until server acknowledgment is confirmed.
- `restart_setup_complete` body includes setup_reset_id. It is idempotent for
  the matching pending/awaiting_setup reset and rejects stale IDs or completed
  generations. Reply `{deviceId,state:"awaiting_setup",setup_reset_id}`. Change
  enrollment state to awaiting_setup; invalidate the former claim's pending
  status. Preserve the encrypted credential envelope (retest/recovery, not a
  credential-rotation or ownership-transfer operation).
- After a confirmed matching acknowledgment, board saves only pairing_secret,
  setup_reset_id, registration_pending true and empty wifi_networks. Remove
  operational Wi-Fi/MQTT settings and pending-reset/boot-mode markers, then
  deliberately reload into the portal. Network errors only retry; no reset.
- Browser claim/status for awaiting_setup require the existing allowedUsers;
  strangers cannot take over. Fresh owner claim carries current reset generation
  in its server record and returns pending. Default device provision includes
  setup_reset_id and may replay preserved encrypted credentials ONLY after
  that fresh nonexpired same-generation claim. Move to ready/provisioning;
  preserve all device access/name/counters/firmware fields.
- Final `complete` acknowledgment also includes setup_reset_id for reset
  generations. Require it to prevent delayed pre-reset ACK/provision requests
  from skipping the new flow. Complete only the matching generation, restore
  enabled controls and mark setupReset complete. Repeated/stale messages cannot
  reset or reenable an independently disabled registered device.
- Admin overview exposes only allowlisted maintenance fields (lastSeenAtMs,
  supportsRestartSetup, appVersion, baseVersion) and setupReset state/timestamps;
  never the private proof, credential envelope, broker settings or reset id.
- Admin UI: Restart setup button on supported registered devices, independently
  of OTA support. Explicit confirm explains clearing Wi-Fi/MQTT and preserving
  identity/access. Show queued/offline, awaiting on-device Wi-Fi/QR, provisioning
  and complete states. Refresh pending status while open, never retry mutations
  automatically. Unsupported boards explain USB update needed. Error/cancel,
  offline, sign-out and stale refreshes must behave safely.

## Root firmware work

- New host-safe `gate_setup.py`: next-boot config toggle/consume, debounced
  rising-edge selection, and reset-config cleanup preserving the private proof.
- Next-boot flag lives in NVM and is consumed before setup starts. D2 press in
  normal operation changes selection only, never resets immediately or changes
  an active hold. Holding a button never toggles repeatedly. Keep XIAO pins and
  D9 OTA recovery unchanged; input lifecycle/cleanup is Feather-only.
- Normal screen footer shows `Reboot: Normal` / `Reboot: Wi-Fi setup` on the
  bottom row aligned with D2; during a hold also indicate reset ends the hold.
  Update cached labels without rebuilding the bitmap. Continue local countdown.
- Extend device_enrollment.registration_payload to supported maintenance actions,
  optional setup_reset_id, and maintenance version fields. registration_request
  validates device/reset IDs and response states before any local cleanup.
- USB base 1.0.13; detailed version/change note. This is explicitly networking,
  device UI and base behavior work. No Feather OTA enablement.

## Work allocation and verification

1. Backend owner: enrollment/administration services, their unit + actual local
   Firestore emulator regressions, necessary gate transaction guard/race checks.
2. Web owner: admin UI and test gateway/browser regressions only, matching the
   shared contract above. No credentials or device proof in browser tooling.
3. Root: firmware, NVM/button/network/display host regressions, docs and USB.
4. Integrate and security-review ownership, stale requests, lost ACK recovery,
   command/reset races, private-proof handling and native CircuitPython APIs.
   Run make test, make precommit (stage base bump/note), make web-test.
5. Deploy full Functions/Hosting/rules and verify all entry/auth/API paths.
   Intentionally USB install only when board idle, confirm actual app/base,
   preserve current Wi-Fi and registration during installation, then run passive
   70-second hardware checks with --hold-pin D9. Do not issue a production
   Restart setup, wipe saved networks, toggle boot intent or actuate the gate
   merely to validate installation; leave destructive end-to-end testing to user.
6. Commit and push integrated verified changes. Record pending interactive checks.
