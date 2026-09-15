# OTA and administrator operations

The implementation is opt-in and currently targets the XIAO ESP32S3 with
CircuitPython 10, board ID `seeed_xiao_esp32_s3_sense` (the installed
Sense firmware build). Its D0/D1/D2/D9/D10 assignments match the documented XIAO
header pins. Initial installation and rollback have passed physical bench
checks; recovery and power-loss qualification is still in progress. Do not
enable a field controller until the checklist below passes. The FeatherWing
PCB's portable headers do not imply that these XIAO firmware pins work on a Feather.

Device `b3640c` is enrolled and opted in (`OTA_ENABLED = 1`). It installed and
confirmed release 1.0.0 over TLS as sequence 2. Deliberate syntax-error,
startup-exception and watchdog-lockup candidates rolled back to that confirmed
copy. Approved release 1.0.0 is now assigned as sequence 6, above the fault-test
sequences. See [the bench validation record](ota-bench-validation.md) for
observed results, local evidence and outstanding checks. GPIO logs establish
software writes, not electrical output or gate position.

The bench probe found three bootstrap issues that host tests missed: CircuitPython
does not support bytearray slice deletion, and its built-in certificate bundle
failed Firebase verification, and CircuitPython 10.1+ returns the OTA enable
setting as a string. Use the corrected USB deployment, including
`certs/google-roots.pem`; the source archive at the initial firmware-v1.0.0 tag
predates these fixes. The release's application file itself is unchanged.

## Administrators

Open the profile dropdown and choose **Administration**. This item appears
only after the server confirms the signed-in Google account is an admin.
Administrators can add/remove administrators and assign/pause firmware updates
for enrolled devices. They do not automatically gain gate-control access;
existing gate UID allowlists and all command checks remain in place.

Add an administrator by their Google email before or after their first login.
Role records are keyed by the SHA-256 of a normalized, verified Google email;
case differences are ignored, but aliases/dots are not rewritten. Every request
still requires verified Google sign-in and App Check. Role checks occur again
inside each write transaction, so revoking a role invalidates subsequent writes.
The owner `nick.stielau@gmail.com` cannot be removed in the UI.

One-time owner initialization, using Nick's project IAM credentials:

```sh
make admin-seed
```

`admins/` stores assignments and `adminAudit/` stores mutations. Normal browser
Firestore access remains denied. Admin actions use request IDs, freshness
checks, and transactional deduplication; retrying the same request cannot
increment a deployment twice. Use Refresh after an uncertain response.

## Firmware boundaries

- `boot.py` chooses USB/device filesystem ownership. USB-managed.
- `code.py` owns provisioning, NVM, Wi-Fi/MQTT, physical output leases, loader,
  watchdog, and update scheduling. USB-managed.
- `lib/gate_ota.py` owns two application slots and checksummed journals.
  `lib/gate_http.py` is a bounded HTTPS client. Both are USB-managed.
- Root `drawbridge.py` is the USB-installed recovery application. It contains
  command policy and the independent indicator timers.
- `certs/google-roots.pem` contains Google's public GTS roots for Firebase TLS,
  loaded explicitly with hostname verification. It is USB-managed; certificate
  sources and update guidance are in `circuitpython/certs/README.md`.
- `/ota/app0.py` and `/ota/app1.py` are OTA slots. Only one verified candidate
  is selected at a time. OTA never overwrites the root recovery copy.
- `/ota/state0.json` and `/ota/state1.json` alternate checksummed generations.
  A torn new journal leaves the earlier complete record available.

The API boundary is a development convention, not a sandbox. Trusted Python
can import other modules. TLS-authenticated Firebase selects the SHA-256 of
trusted release code. Signed manifests and independent signing-key protection
are not implemented.

D10 is initialized LOW before the temporary D0/D1/D2 diagnostic. Bootstrap
validates hold durations and owns the monotonic deadline. OTA starts only while
idle; each download chunk services MQTT/outputs and aborts when a hold arrives.
DNS/TLS/socket calls can still block briefly, as with existing MQTT connection
attempts. Timers are software serviced, not hard real-time electrical limits.

## Initial enrollment and physical recovery

Prepare a disconnected bench board first. Current installation requires one
USB deployment, because old firmware has no updater.

```sh
make setup
make test
make deploy
make ota-bucket-setup
make ota-enroll DEVICE_ID=b3640c
make ota-provision DEVICE_ID=b3640c
```

Use the board's actual lowercase chip suffix from its boot log. Enrollment
creates a random per-device credential in ignored `artifacts/ota/<id>.env`
with owner-only file permissions. Only its SHA-256 goes to Firestore. The
provisioner writes it to USB-readable `settings.toml`. It also writes
`OTA_DEVICE_ID`; runtime refuses network updates if this does not match the chip.
Enrollment and provisioning leave OTA disabled. Re-enrollment refuses to
silently replace an existing credential or local enrollment file.

After completing the bench checks, explicitly opt in:

```sh
make ota-provision DEVICE_ID=b3640c OTA_ARGS=--enable
```

Then hard-reset or power-cycle the board: changing `boot.py` or filesystem
ownership requires a full boot. With `OTA_ENABLED = 1`, `boot.py` samples D9
(GPIO8 on this XIAO only) using its internal pull-up. **Hold D9 to GND during
reset to enter USB-writable maintenance mode.** D9 must otherwise remain unused.
Normal field mode gives CircuitPython write ownership of CIRCUITPY; do not
bypass concurrent-write protection. Maintenance mode disables OTA even if the
setting is enabled. To disable OTA persistently, set `OTA_ENABLED = 0` via USB
and hard-reset. An unsupported board remains in USB mode.
Missing saved Wi-Fi/MQTT configuration runs the recovery application and portal
without starting an OTA trial or watchdog.

When repairing an OTA-installed application by USB, enter maintenance mode,
run `make deploy`, and remove the two `/ota/state*.json` records before returning
to field mode. This selects the new root recovery file; otherwise a confirmed
OTA slot remains selected. Keep a copy of journals/logs before repair.
To revoke a lost OTA credential, delete `otaCredentialHash` from that device
using project IAM and pause its target. Rotate the device and the ignored local
credential deliberately; it is independent of its MQTT identity.

## Base and application versions

Normal OTA development edits only `circuitpython/drawbridge.py`. The USB-managed
base is `boot.py`, `code.py`, libraries and public certificates. The pre-commit
guard rejects staged base changes unless they include an increased
`BASE_VERSION` in `lib/gate_base.py` and a change note in
`docs/base-firmware/<version>.md`. It checks the index, so an unstaged bump does
not approve a staged edit. It also catches removed/renamed files and MPY changes.
This is an accident-prevention guard, not a security boundary against an actor
who can change hooks; do not bypass it with SKIP or --no-verify.

The device reports two independent versions: `version` is the selected app,
`base_version` is the installed USB bundle. MQTT also preserves the `bootstrap`
alias. Administration shows, for example, “App 1.0.9 · Base 1.0.1”. These are
separate release histories, not numbers to subtract. The timestamp still means
last report, not current reachability. Older reports show “Base not reported”.
The CircuitPython interpreter and app compatibility API are separate again.

Future GitHub releases bundle `base-firmware.zip` and `base-manifest.json`
alongside the single-file OTA app and its manifest. The base manifest records
its semantic version, full release commit and file hashes. Its aggregate hash
excludes the bundled root recovery app, whose hash is recorded separately.
Two app releases may therefore carry the same base version/digest. The ZIP is
for deliberate USB maintenance and excludes device settings, credentials and
the CircuitPython interpreter. Firebase continues to mirror only drawbridge.py.
The existing 1.0.0/1.0.1 releases are unchanged.

Base 1.0.1 adds reporting and incorporates the previously tested USB fixes.
It has not been installed on the board yet. Install through the existing D9
maintenance workflow and run hardware verification before claiming the new base
is in use. An OTA-only upgrade cannot add reporting to an older bootstrap.

## Releasing and selecting firmware

Release assets come from a clean, tagged Git commit. Update `APP_VERSION` in
`circuitpython/drawbridge.py`, run tests, commit, and push a matching tag such as
`firmware-v1.0.1` before publishing. No tool automatically commits or pushes code.

```sh
make firmware-build VERSION=1.0.1
make firmware-release VERSION=1.0.1
make firmware-import VERSION=1.0.1
```

Build runs offline tests and checks that the application's version/API matches
the tag at HEAD. Publish creates a GitHub Release containing `drawbridge.py`,
`manifest.json`, `base-firmware.zip`, and `base-manifest.json`. Import verifies the published tag, source commit, bytes, size,
and SHA-256, then mirrors the file to a create-only object in the private
`drawbridge-45487-firmware` bucket. It creates an approved, immutable manifest in
`firmwareReleases/<version>`. Only local IAM tooling can import releases; the
browser cannot upload code or choose arbitrary URLs.

`make ota-bucket-setup` creates the private bucket in `us-east1` and grants the
runtime service account bucket-scoped Object Viewer. Device downloads pass
through the authenticated Firebase `firmwareDevice` HTTP function; devices do
not receive Storage credentials or signed URLs. The endpoint is
`https://drawbridge-45487.firebaseapp.com/device-api/v1/`. Requests use
`X-Device-ID` and a bearer token, with no redirects allowed. Endpoint response
bodies, credentials, and firmware API responses are never service-worker cached.

In Administration, select an imported release for an enrolled, enabled device
and choose **Assign release**. Every assignment gets a newer deployment
sequence, including assigning an older app version as a deliberate rollback.
**Pause updates** stops future checks from receiving a target; it does not
interrupt a download already admitted by the server or undo installed firmware.
Assigning firmware never sends an MQTT hold or changes device access.

Checks start 60–315 seconds after startup, then every six hours plus jitter.
Failed checks back off from one minute to 24 hours. Active holds defer checks.
The client bounds manifests to 4 KiB, artifacts to 64 KiB, socket waits to five
seconds, and each HTTP transfer to 45 seconds plus bounded DNS/TLS setup.
It supports fragmented Content-Length and chunked responses and rejects
compression, redirects, malformed framing, incompatible boards/APIs, short
reads, and digest mismatches.

A candidate is journaled before reload. It must import with matching version
and API, run its loop, and maintain a subscribed MQTT connection for 60 seconds
before confirmation. Failure to become healthy within five minutes rolls back.
A subsequent boot that finds an already-started, unconfirmed trial also rolls
back. A 60-second watchdog in OTA field mode catches loop lockups; it is fed by
the main loop and download servicing, not by a background task. Ordinary network
errors do not explicitly hard-reset the board. Hardware watchdog resets and
filesystem persistence across actual power loss still need bench validation.

The last confirmed slot is retained during the next download. If that slot
fails validation, bootstrap falls back to the USB recovery file. A runtime
exception in an OTA-selected app drives outputs LOW and selects recovery. Filesystem
corruption affecting both journals or the root files still requires USB repair.
No application-level scheme can promise recovery from all FAT/media failures.

Administration displays the last device-reported version/state and timestamp,
separately from the assigned target. Reporting is periodic and best effort;
it does not confirm gate position. MQTT `device_status.firmware` and `GATE_LOG`
also expose the app version and update state without secrets.

## Verification before first field rollout

Automated checks:

```sh
make test
make web-test
make precommit
make test-hardware  # requires a provisioned USB board; observes only
```

Host tests cover candidate verification, two-slot selection, checksummed journal
recovery, trial rollback, transfer failures, size/space limits, replay rejection,
lease separation, and HTTP framing. Firestore emulator tests cover admin grants,
revocation, deduplication, owner protection, device enrollment/target guards,
token scope/revocation, throttling, and deny-all rules. Mobile Chromium/WebKit
exercise admin visibility, role changes, targeting, offline controls, and signout.

On a disconnected bench controller, verify all of these before targeting the
installed gate:

1. Normal USB deploy and unchanged Wi-Fi/MQTT/LED behavior.
2. D9 maintenance recovery after enabling OTA, including after a bad candidate.
3. A real TLS download, app version report, trial confirmation, and later update.
4. Hold deferral and download abort when an explicit short hold arrives.
5. Syntax error, startup exception, loop lockup, and no-MQTT trial rollback.
6. Power removal during slot write and each journal transition; inspect the
   selected bytes and actual D10 state on restart.
7. Full storage, damaged journal/slot, disabled token/device, and paused target.
8. Reassignment to the previous app under a newer deployment sequence.

Use a short explicit bench hold and optical/electrical checks in addition to
logs. Do not treat host filesystem fault simulation as physical flash testing.
After bench validation, target one canary device and observe it for a week
before expanding. Channel-wide promotion and signed manifests remain future
work; this implementation provides explicit per-device assignments.
