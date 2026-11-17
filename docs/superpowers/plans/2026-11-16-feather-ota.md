# Feather OTA and app-owned UI

Approved: make Reverse TFT Feather the forward platform for OTA, with existing
TLS/digest/two-slot rollback and protected physical leases. Enrollment/opt-in and
explicit per-device approved release assignment only. Publishing never advances
fleet targets. Connected bench device 37cc02 only; leave b3640c/990 unchanged.

## Shared contract

- USB BASE_VERSION 1.0.15, compatibility BOOTSTRAP_VERSION 1.1.0. Application
  APP_VERSION 1.1.0, APP_API_VERSION 2. New base supports legacy API1 and new API2.
- Known boards: seeed_xiao_esp32_s3_sense and
  adafruit_feather_esp32s3_reverse_tft. Legacy API1 manifests remain exactly
  XIAO-only/minimum_bootstrap_version 1.0.0 and unchanged immutable bytes.
  API2 manifests use minimum_bootstrap_version 1.1.0 and a unique nonempty list
  of known boards, including the board receiving it. New 1.1.0 release initially
  Feather-only, keeping legacy assignments undisturbed. No arbitrary board IDs.
- App2 is self-contained in drawbridge.py: normal/setup/QR renderers and website
  view/timeout/button policy move there. Base samples/debounces/releases pins,
  persists next-reboot intent through a narrow Platform method, routes protected
  onboarding/network state, and owns all output writes/lease deadlines.
  device_display.py becomes a thin compatibility import of the USB recovery
  app helpers; no duplicated renderer implementation remains in the base.
- Feather boot: OTA opt-in, sample D1 active HIGH/Pull.DOWN; D1 held at hard reset
  keeps USB writable and disables loader. D9 remains Hold LED and is never used
  for Feather recovery. XIAO recovery stays D9 active LOW/Pull.UP.
- Runtime only loads OTA while boot.py gave device filesystem write ownership;
  unknown boards/USB maintenance/unprovisioned setup cannot start a trial.
  No concurrent-write bypass. New UI exceptions participate in rollback.
- maintenance and OTA report carry optional board_id. Persist only known board
  IDs in public reports; expose via existing observation as boardId. Existing
  old reports remain valid without this field.
- OTA IAM enrollment for Feather requires BOARD_ID parameter, saved as otaBoardId
  with token hash, plus BOARD_ID in ignored local credential file. Existing
  XIAO enrollment is legacy-compatible. No silent token replacement.
- Server API2 target assignment requires enrolled otaBoardId in manifest and a
  reported base >=1.0.15, plus normal enabled/admin/freshness/transaction checks.
  Legacy API1 targets continue to accept legacy XIAO enrollment without board
  metadata. API2 manifest serving repeats compatibility checks, preventing stale
  or manually mismatched targets from reaching an incompatible device.
- USB provisioner accepts supported boot_out board IDs, validates enrollment
  BOARD_ID matches actual board (legacy missing BOARD_ID only XIAO), preserves
  other settings and prints correct recovery instructions, never token values.
- Release builder reads app API/version, emits API2 Feather-only/minbootstrap
  1.1.0 for new release; preserves legacy support for tests/API1 source. Build
  from clean tagged committed snapshot; never alter/recreate existing releases.

## Ownership

Root: boot.py/code.py/drawbridge.py, gate_ota.py, device_enrollment payload and
firmware host tests/UI tests; USB/base bump/docs, integration, bench, release.
Backend worker: firebase/functions/* and corresponding server/unit/emulator
checks for compatibility/board metadata/target guards. No web edits except
coordination when necessary; no deploy/production changes.
Tooling worker: tools/ota_provision.py, firmware_release.py, firmware_admin.cjs,
Makefile and relevant host/tool tests. No firmware/backend edits or production.
Reviewer: static cross-boundary review, no edits or hardware.

## Verification and rollout

Use failing regressions before code. Full make test/precommit/web-test before
deployment. Native USB install only when idle; preserve NVM and unrelated files.
Enroll/enable only 37cc02. Hard reset and inspect actual GATE_BOOT mode. Verify
real recovery button with user assistance; leave field opt-in unqualified until
physical recovery is confirmed. Publish/import an immutable 1.1.0 release from a
clean tagged checkout, explicitly assign only bench Feather, observe TLS install,
trial and confirmed version. Local fault candidates are never public releases.
Test syntax/startup/watchdog rollback and corrupt/truncated journal recovery with
outputs disconnected/LOW; do not automatically issue gate commands. Physical
power-loss and live-hold qualification require separate evidence; a reset or
simulated torn write must never be called a power-cut test. Record actual limits.
