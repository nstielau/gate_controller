# Drawbridge CircuitPython development

# FeatherWing fabrication

- `hardware/featherwing/generate.py` is the design source of record. Incorporate
  manual KiCad edits there before rebuilding. The logo source is
  `hardware/featherwing/assets/drawbridge-silkscreen.svg`; its polylines become
  actual F.Silkscreen geometry. PNG previews come from that same SVG.
- `make featherwing-fab` (also `make featherwing-check`) regenerates the design,
  runs ERC/DRC, and rebuilds **all** ZIPs and loose exports, including board and
  schematic previews, logo, Gerbers, drills, BOM, positions, netlist, and reports.
  Requires installed KiCad 10 plus the repo's Node/Playwright dependencies.
- Fabrication requires a clean repository: reject staged, unstaged, and untracked
  changes anywhere; ignored files are excluded. Commit before building; never
  bypass the check or commit unrelated work just to satisfy it. The revision is
  exactly the first three HEAD characters with no suffix. Every ZIP includes
  `REV_<ref>.txt` containing the short revision and full commit hash; the manifest
  also records the full hash. There is no dirty-build counter.
- Generate from a temporary committed snapshot, leaving tracked files unchanged.
  Fresh native KiCad files are in `artifacts/featherwing/design/` and the combined
  ZIP; tracked native files are reference snapshots. Recheck HEAD and cleanliness
  before publishing output. Tests for this workflow use isolated Git fixtures.
- `artifacts/featherwing/` is disposable build output. Each successful build
  replaces the entire directory, removing old attempts and extracted ZIPs.
  Never store source/manual edits there. Other artifact directories are separate.
  Failed builds preserve the previous complete release; check `manifest.json`
  for its build timestamp and file hashes before uploading.
- All three ZIPs are built together and every member is checked against its
  loose counterpart. Run `.venv/bin/python -m unittest
  test_suite.test_featherwing_fab` for the offline freshness/recovery tests,
  then `make featherwing-fab` and inspect `board.png` and `silkscreen.svg`.

- J3 is now a populated top-side Phoenix 1725656 screw terminal, rotated 90°:
  GND/pin 2 is above OUT_OC/pin 1 with USB left, wires exit right. Preserve its
  two locating holes, top-side BOM/position entry, and underside J1/J2 headers.
  It is externally sourced in the Seeed BOM; do not claim it is verified OPL stock.
- Preserve `route_45` chamfers and run full fabrication checks after routing or
  placement changes. DRC does not validate the assembled host's RF performance.

# Drawbridge Firebase app

- Read `firebase/README.md` for the web app's architecture and operational
  commands. Production project is `drawbridge-45487`, account
  `nick.stielau@gmail.com`, region `us-east1`. Never use AdventureAwaits.
- Browser source is `web/`; backend source is `firebase/functions/`. Build
  with `make web-build`; deploy only generated `web/dist`. Keep both npm
  lockfiles. `make web-setup` installs pinned dependencies and local Node 22.
- Canonical URL is `https://drawbridge-45487.firebaseapp.com`; `drawbridge.stielau.us`
  and the `.web.app` alias redirect there before auth initialization. Google's registered OAuth
  callback is on `.firebaseapp.com`. Firebase authorized domains alone do not
  authorize a new OAuth callback. Run `make web-test-live` after auth/Hosting
  changes: it checks all three entry URLs reach Google and unsigned API calls fail.
- Quick iteration: `make web-test-unit`. Before deployment: `make web-test`
  (unit tests, mobile Chromium/WebKit, actual Firestore emulator). Java 21+
  is needed; the emulator must use `demo-drawbridge` on localhost. Never run
  database tests against production or remove their local-host guard.
- `make web-deploy` runs the full suite then deploys Functions, Hosting, and
  rules. A failed cloud deployment can leave some services updated; inspect
  its output and finish remaining steps, then verify the production URL.
- `make web-test-mqtt` runs three real TLS publish/receive cycles using the
  backend publisher on a unique synthetic topic. It never actuates the gate.
  Real gate holds need the same deliberate hardware-testing judgment as
  firmware work. PUBACK is broker acceptance, not hardware confirmation.
- One WebKit cached-offline-launch test is skipped for Playwright's Chromium
  service-worker limitation. Both browsers test offline controls. Do not
  represent this as validated iPhone offline installation/launch. Google
  login and real hardware behavior still need an interactive production check.
- Preserve verified Google sign-in, UID allowlists, enabled-device checks,
  exact topic checks, App Check enforcement, deny-all Firestore client rules,
  request freshness, transactional deduplication, and per-device cooldown.
  Never add a production debug-token/test-gateway bypass. Browser mocks belong
  only in `artifacts/web-test`; `tools/build_web.mjs --test` creates it.
- Keep MQTT credentials/CA in Secret Manager. `make web-secrets` imports the
  ignored local files without printing them; redeploy after rotating secrets.
  Public Firebase and App Check configs are ignored in `web/`. Never put
  Google OAuth secrets or MQTT connection parameters into the browser URL.
- `make web-grant EMAIL=... DEVICE_ID=...` and `make web-revoke` use project IAM.
  Runtime uses the dedicated `drawbridge-functions` service account with
  database access and secret-level Secret Accessor, not project Editor.
- Do not queue or automatically retry uncertain gate commands. Preserve
  `pending`/`unknown` audit records so a replay cannot publish again. MQTT
  QoS 1 is not a guarantee of exactly-once physical action.
- `devices/<id>.activeHold` holds only the last broker-accepted web command's
  expected start/duration. It drives the UI countdown and progress sweep, not
  a claim that the board/gate state is confirmed. Update it transactionally
  only when its matching pending command finishes; clear it on end-hold or
  uncertain delivery. Never expose command IDs in device lists.
- Hash/cache only public app assets, never auth helpers, API responses, or
  command POSTs. Keep zero minimum function instances and bounded timeouts.
- Gate nicknames are shared `devices/<id>.name` values. `renameGate` requires
  verified Google auth/App Check and checks current device access inside the
  write transaction. Update only `name`, validate 1–80 trimmed characters,
  and render as text. Renaming must never publish MQTT or modify routing.
- Usage counts represent broker-accepted nonzero holds, not physical openings.
  Preserve `devices/<id>.holdCount`; private `usagePeople/<sha256(uid)>` and
  `devices/<id>/usagePeople/<sha256(uid)>` documents store UID/holdCount for
  person and person/gate totals. All increments share the pending-to-accepted
  command transaction; derive identity/duration from its reserved audit record.
  Never count End hold, unknown/pending/rejected commands or replayed finishes.
  Person counters begin at deployment with no historical backfill. Keep them
  server-only and covered by deny-all client rules.

# QR device registration

- A public device ID alone is not proof of ownership. First enroll a physically
  attached board with `make device-pairing-enroll PORT=/dev/cu.usbmodem...` using
  project IAM. This creates `devicePairingBindings/<id>` with the derived public
  hash and refuses replacement by a different identity. Public endpoints must
  never create this binding or fall back to accepting an unbound ID.
- Preserve the random private pairing proof in NVM. Only its SHA-256 derived
  code belongs in the QR fragment; the private proof travels only in verified
  TLS device POST bodies. Never print the proof, credentials, or full NVM.
  Browser claims/status require verified Google auth and App Check.
- Preserve QR query/fragment across the canonical-origin redirect, capture the
  fragment before auth initialization, remove it from the address bar, and keep
  the pairing intent through OAuth. Existing gate owners must still see the
  scanned device's registration flow. Keep manual code entry unnecessary.
- Retry provisioning with the same encrypted credential envelope and broker
  identity. Enable controls only after the device persists credentials,
  subscribes to its exact MQTT topic, and acknowledges completion. Browser
  responses never contain MQTT credentials. Registration never actuates a gate.
  See `firebase/README.md` and `docs/superpowers/plans/2026-11-16-qr-pairing.md`.

# CircuitPython workflow

- Source of record: `circuitpython/`, never the mounted board. The former
  Balena/Raspberry Pi GPIO runtime was removed; do not reintroduce it.
- Use **uv**: `make setup` creates `.venv` and syncs
  `tools/requirements-dev.lock`. Host tools use `.venv/bin/python`.
- Run `make test` before deployment; `make deploy` also runs it.
  Keep the pinned host MiniMQTT and device CP10 library versions aligned.
  The local `gate_mqtt.py` adapter uses private hooks; test dependency updates.
- Install hooks once with `make precommit-install`. Run `make precommit` for
  the complete all-files check or `make lint` for Ruff only. Hooks scan for
  private keys and likely secrets, reject malformed JSON/XML and merge
  conflicts, enforce whitespace, and run Ruff formatting/linting. Hooks use
  `uvx`; no global Python installation is required.
- Deployment preflights credentials and the CA, copies changed files including
  libraries, and preserves unrelated device files/settings. Default destination
  is `/Volumes/CIRCUITPY`; override with `CIRCUITPY=/path`.
- Identify the actual board using `boot_out.txt` and `board.board_id` before
  choosing firmware, polarity or pins. Trace physical FeatherWing header nets
  in `hardware/featherwing/generate.py`; XIAO pin aliases are not portable.
  If a starter app runs instead, inspect competing root startup files and verify
  the interpreter is executing the deployed `code.py` loader.
- Use `tools/xiao_console.py`/`open_console` for USB access (DTR asserted, RTS
  deasserted), with one serial reader at a time. Await command completion and
  confirm the REPL is ready before disabling autoreload and copying a bundle.
  Restart deliberately afterward and verify the reported app/base pair; a
  successful copy alone does not establish that the new firmware is running.
- Probe new helpers on actual CircuitPython before deployment. Host Python
  tests miss interpreter differences: use `hashlib.new("sha256")` and encode
  digest bytes explicitly; do not assume `hashlib.sha256`, `hexdigest`, or the
  two-argument `next(iterator, default)` is available on the target.
- Keep credentials in ignored `.env`, the CA in ignored `emqxsl-ca.crt`, and
  logs/results in ignored `artifacts/`. Never print or commit secrets.
  `tools/env_config.py` is the shared literal dotenv parser. Only
  `MQTT_USERNAME` and `MQTT_PASSWORD` go into device `settings.toml`;
  never copy REST API credentials. Settings are readable over USB.
  Do not expose saved Wi-Fi credentials while inspecting NVM.

# Captive Wi-Fi setup

- Store up to five networks in NVM; adding/updating/forgetting Wi-Fi must preserve
  the pairing proof, registration acknowledgment and per-device MQTT identity.
  A blank password keeps an existing password; Open network explicitly clears
  it. Keep GATE1/GATE2/GATE3 migration support and never prefill saved passwords.
- Reverse TFT normal operation: D0 (active LOW) or D1 (active HIGH) toggles
  the ordinary website QR, returning after 20 seconds. Never include pairing
  parameters in that shortcut. Keep the dark header and center its QR below;
  omit hold/reboot controls from the QR view while preserving the normal status
  screen. D2 (active HIGH) selects the one-shot next-reboot
  Normal/Wi-Fi setup action shown on the bottom TFT row. Persist before showing
  success, consume the flag before setup, and debounce all inputs. Onboarding
  consumes button state without triggering normal shortcuts. Buttons never
  change a hold lease or reboot immediately.
- Administration's Restart setup is private-proof authenticated on the device,
  generation-fenced and idle-only. Preserve trusted identity, access and broker
  envelope. Clear local credentials only after matching server ACK; retain old
  Wi-Fi and pending marker on failure, and resume before MQTT on boot. Require a
  fresh authorized same-generation QR claim. Never run a production reset just
  for automated validation. See the base 1.0.13 note and restart-setup plan.
- On Reverse TFT Feather, hold D1 while pressing/releasing RESET, then release
  D1 when setup appears. D1 is active HIGH. Join `Gate-Setup-<suffix>` and open
  `http://192.168.4.1`. Failed saved networks keep retrying station mode; opening
  an AP is an explicit setup action unless there are no saved networks.
- Keep a visible Save and connect button on mobile. Selecting an SSID hides
  and disables manual entry; choosing the default option restores it. Preserve
  the Drawbridge branding and escape displayed SSIDs and messages.
- Send complete HTTP bodies with tracked short writes and bounded EAGAIN retries.
  Never retry an entire partially sent response. Close the successful response
  before waiting ten seconds and restarting. Show the saved SSID, countdown and
  phone reconnection instructions so success does not look like a broken page.

# Runtime and pins

- Reverse TFT Feather + FeatherWing USB firmware uses transistor control
  D11/GPIO11, Wi-Fi D5/GPIO5, MQTT D6/GPIO6 and Hold D9/GPIO9. These match
  J2 pins 6/10/9/8 in `hardware/featherwing/generate.py`. D0/D1/D2 are buttons;
  never drive them as indicator outputs. Feather onboard LED is active HIGH.
  The following D10/D0/D1/D2 mapping applies to XIAO. Feather OTA requires
  explicit enrollment/opt-in and uses D1 held at hard reset for USB recovery. J3 is open collector: active control sinks OUT_OC to GND and
  does not provide a HIGH output voltage. Use `TEST_ARGS='--hold-pin D9'` with
  passive hardware checks on Feather.

- XIAO firmware initializes transistor control `board.D10` (**GPIO9**) LOW.
  A valid timed MQTT hold raises D10 steadily until monotonic expiry or exit.
  D9 is the optional OTA maintenance input. Indicator servicing must never toggle D10.
- XIAO's onboard `board.LED` is **active low**: two 100 ms pulses, starting 250 ms
  apart, every two seconds show the loop is running, independent of connectivity
  and hold state.
- XIAO external LEDs are active HIGH: D0/GPIO1 is Wi-Fi (500 ms transitions until
  connected, then ON); D1/GPIO2 is MQTT (OFF without Wi-Fi, 500 ms transitions
  until subscribed, then ON); D2/GPIO3 is hold (OFF unless D10 is HIGH,
  four full cycles/second with 125 ms transitions).
  Each LED needs its own 1 kΩ series resistor to its anode and cathode to GND.
- Keep the commented temporary three-flash D0/D1/D2 startup diagnostic until
  requested to remove it. It releases pins before runtime initialization.
  Runtime outputs return LOW and the active-low onboard LED turns OFF on exit.
- `drawbridge.py` owns the independent LED timers (`gate_indicators.py` is a compatibility import). Network operations
  can temporarily delay servicing, particularly initial Wi-Fi/TLS connection.
  No network failure should call `microcontroller.reset()`.
- Missing settings start an open `Gate-Setup-<chip suffix>` AP and portal at
  `http://192.168.4.1`. Saved settings use station mode with retry, not an
  automatic fallback portal. Preserve NVM GATE1/GATE2/GATE3 compatibility.
  Deploy-time MQTT credentials apply only to legacy configurations that are
  neither awaiting registration nor already registered; preserve per-device
  NVM credentials once registration is pending or complete.
- Default topics: `gate/v1/devices/<device-id>/command` and `/status`.
  Hold payloads are `{"version":1,"type":"hold_gate",
  "duration_seconds":5,"command_id":"..."}` and are never retained;
  retained deliveries are rejected, including stale messages from old tools.
  `make hold DURATION=5` uses the TLS-verified publisher; zero cancels.
- MiniMQTT 8.1.0 rejects a loop timeout below its socket timeout. Idle polls
  must remain short; TLS and packet bodies need longer deadlines. Do not
  hide ValueError as a connection failure, publish inside callbacks, or
  subscribe twice after reconnecting.
- Bounded GATE_LOG records include boot IDs, indicator modes, four hold-LED edge
  samples per mode change/heartbeat, and ten-second online heartbeats with
  independent Wi-Fi/MQTT states and an onboard `alive_edge_count`.
- Reverse TFT normal status uses a Drawbridge header with separate Wi-Fi, MQTT
  and Hold rows. Keep QR registration/progress and the D2 next-reboot footer readable
  on 240×135 pixels, with a four-module QR quiet zone. `device_display.py` is
  USB-managed base firmware and requires the normal version bump/change note.

# Verification

- `make test`: offline regressions for LED timers, active-low polarity,
  pin allocation, cleanup, separation from D10, ignored legacy commands,
  MiniMQTT packets/deadlines, NVM/portal, publisher, and deployment.
- `make deploy`: test, then update the mounted board. Filesystem writes may
  trigger an intentional autoreload. Stop other serial readers first.
- After firmware/timing/MQTT/library changes, run `make test-hardware`.
  It passively watches an already provisioned USB board for an online
  heartbeat, then observes 70 seconds. It checks steady D0/D1 ON, increasing
  onboard heartbeat edge counts and stable session logs; use
  `make hold DURATION=3` to exercise D10/D2 activation,
  increasing D2 edge counts, alternating sampled writes at 125–200 ms,
  and stable boot/session. It never publishes, resets, or toggles the gate.
- `make test-hardware-smoke` uses a 20-second observation for quick iteration.
  Customize with `TEST_ARGS='--duration 120 --port /dev/cu.usbmodem...'`.
  Evidence: `artifacts/indicators.log` and `artifacts/indicators.json`.
  The old `tools/test_mqtt_cycles.py` publisher test is obsolete for this
  firmware (its passive log reader is reused).
- Hardware checks measure software GPIO writes, not optical/electrical output.
  Offline and inactive-hold behavior use host tests; the passive live test
  does not disconnect Wi-Fi or activate the gate. Report those limits accurately.
- A TFT Hold ON message, broker PUBACK or GPIO log does not verify the green LED,
  transistor circuit or gate. Confirm these separately when physical testing is
  intended. An idle passive check with zero hold samples proves no hold timing.
- `make console CONSOLE_WAIT=20` reads passively; use `CONSOLE_ARGS=--reload`
  only for an intentional Ctrl-C/Ctrl-D reload. Use one serial reader at a time.
  `make status` checks the mounted CircuitPython version.
- Session summary and remaining physical checks:
  `docs/session-notes/2026-11-16-feather-onboarding.md`.

# Wiring

- Connection guide: `docs/xiao-breadboard.svg`. The current physical layout
  is `docs/xiao-breadboard.fzz`, for a 170-hole mini breadboard without rails;
  exact holes and jumpers are documented in `docs/xiao-breadboard.md`.
  Preview: `docs/xiao-mini-breadboard.svg`. Older KiCad artifacts retain prior
  pin assignments. Keep firmware unchanged when editing the layout.
- `make fritzing` uses uv and the bundled XIAO contribution plus installed
  Fritzing core parts. It checks eight separate nets, all header alignments,
  unused GPIO isolation, and unique hole occupancy. `make fritzing-preview`
  exports through the installed macOS app. Inspect that real export after
  generator changes; graph checks alone do not prove visible parts/wires.
- Breadboard wires use `wireFlags="64"`, not PCB trace flag 4. Keep SVG's
  default namespace, explicit layer IDs, and valid connector IDs. Preserve
  upstream parts; normalized/rotated clones live inside the generated FZZ.
- XIAO occupies C1–C7 and G1–G7 with USB left. D0 is the XIAO pin name;
  breadboard hole D0 is a different label; the signal LED uses the XIAO D0 at
  G1 in this layout.
- D10 -> 1 kΩ -> 2N3904 base; emitter -> GND; 100 kΩ base-emitter pulldown.
  Verify the transistor datasheet pin order. The collector LED + resistor
  powered by 3V3 is a bench load with the gate disconnected.
- The intended controller may be a LiftMaster LA500UL. Its “eyes” terminals
  are monitored safety-sensor inputs, not an established dry-contact interface.
  Do not extend the bench LED supply circuit to those terminals or describe
  it as a validated gate connection. The D0 indicator stays on the XIAO side.
- The diagrams predate the four-LED firmware assignment. D2/GPIO3 is now the
  requested hold LED; it is a strapping pin, so do not pull it HIGH or externally
  drive it during reset. Keep USB GPIO19/20 unused; preserve D6/D7 for serial.

# OTA editing boundary and versions

- Default firmware work belongs in `circuitpython/drawbridge.py` and its tests.
  That is the only file delivered OTA. Do not change USB-managed files as an
  incidental part of an application change. Base edits require a task that
  explicitly calls for networking, loader, pin, library, certificate, or base
  behavior changes; the independent version-reporting work is one such change.
- Protected base: all Python/MPY/certificate files under `circuitpython/` except
  root `drawbridge.py`. This includes `boot.py`, `code.py`, `lib/` and public
  roots. OTA never modifies these or the root recovery app. Device credentials,
  settings and NVM are separate and never belong in a release.
- `APP_VERSION` identifies the running application. `BASE_VERSION` in
  `circuitpython/lib/gate_base.py` identifies the installed USB bundle, independent
  of the CircuitPython interpreter version and application compatibility API.
  An app-only update does not bump BASE_VERSION. App and base version numbers
  need not match; report the actual pair rather than calculating a numeric gap.
- The installed pre-commit configuration runs `tools/check_base_firmware.py`.
  It examines staged bytes, including deletions/renames and binary libraries.
  Base changes require a strictly increased staged BASE_VERSION and a staged
  `docs/base-firmware/<version>.md` explaining the change and USB validation.
  Stage all intended base files together with the bump/note. Do not use SKIP or
  --no-verify to bypass this guard. It guards commits, not editor saves; review
  the diff before deployment. All-files hook runs still inspect the index.
- `make firmware-build VERSION=x.y.z` requires a clean tagged commit and tests.
  Future releases contain `drawbridge.py`, OTA `manifest.json`, `base-firmware.zip`
  and `base-manifest.json`. The latter records base version, full release commit,
  per-file SHA-256 and an aggregate base digest. The ZIP also includes the root
  recovery app; its hash is separate, so app-only updates preserve base identity.
  Existing releases remain immutable. Firebase imports only the OTA application.
- MQTT status and Firebase reports include the running app and base versions;
  Administration displays both. Legacy boards omit base_version and must show
  “not reported”, never an inferred base from the assigned release. A one-time
  USB update is needed for this new reporting; publishing an OTA app cannot
  retrofit the base. Do not describe a locally edited base as installed.
- Base 1.0.1 includes the prior bench fixes and dual-version reporting. It has
  host validation only until an intentional USB install and hardware checks.
  Before release/deploy run `make test`, `make precommit`; for server/UI changes
  also run `make web-test`. Follow the physical checks in `docs/ota-operations.md`.

# OTA and application administrators

- Read `docs/ota-operations.md` for actual behavior; `docs/ota-upgrades.md` is
  the earlier proposal. OTA is disabled until USB enrollment and explicit opt-in.
  Supported opt-in platforms are XIAO ESP32S3 and Reverse TFT Feather on CP10
  after USB base 1.0.15. API2 releases require loader 1.1.0, matching enrolled/
  reported board and latest reported base >=1.0.15. Legacy API1 stays XIAO-only.
- `drawbridge.py` owns application policy; `code.py` owns physical hold leases,
  networking and loader. OTA must never replace root `drawbridge.py`, `boot.py`,
  `code.py`, libraries, or certificates. `/ota/app0.py` and `app1.py` plus two
  checksummed journals preserve trial/confirmed state. This is not a sandbox.
- D9/GPIO8 becomes maintenance recovery in OTA mode: ground it at hard reset
  for host write access. Never disable concurrent filesystem-write protection.
- Preserve hold deferral, size/digest/API/board validation, trial confirmation,
  failed-sequence suppression, and USB fallback. Run `make test`, then real bench
  power-loss/TLS/recovery checks before enabling field OTA. USB baseline was
  deployed to b3640c on CircuitPython 10.3.0 (board ID
  `seeed_xiao_esp32_s3_sense`); application 1.0.0 reconnects to Wi-Fi/MQTT.
  The board installed and confirmed release 1.0.0 (sequence 2) via TLS, then
  recovered from local syntax-error, startup-exception and watchdog-loop trials.
  Sequence 6 also installed and confirmed after a successful hold-deferral test.
  See `docs/ota-bench-validation.md` for current
  evidence and pending tests. D9 recovery must be repeated with the boot setting
  fix; power-loss qualification remains outstanding.
- CircuitPython bytearrays do not support item deletion; use slicing in the
  bounded HTTP parser. Firebase needs the explicit public Google roots deployed
  from `circuitpython/certs/google-roots.pem`. Never disable TLS verification.
- CircuitPython 10.1+ getenv returns strings even for TOML integers. Both boot.py
  and code.py must accept the string "1" for OTA opt-in. GATE_BOOT records the
  actual USB/maintenance/OTA mode; check it when testing the recovery jumper.
- Admin roles use verified Google emails in server-owned `admins/` records.
  Nick is seeded via `make admin-seed`; owner removal is blocked. Browser roles
  require App Check and a fresh transactional check on every admin mutation.
  Gate-control UID allowlists remain separate; admin access is not gate access.
- Device OTA bearer tokens are random and per-device, hashed in Firestore,
  stored locally only in ignored `artifacts/ota/`. Never print them or expose
  them in admin responses, URLs, web assets, or logs. Device HTTP auth is
  separate from browser auth. Keep deny-all Firestore rules for new collections.
- Release tools require a clean tagged commit and verified GitHub release
  bytes; mirrors are create-only in a private bucket. Target only approved
  manifests. Reassigning an older app must use a newer deployment sequence.


# Feather OTA and thin base (1.0.15 / app API2)

- `drawbridge.py` owns TFT renderers and button/view policy as well as command
  policy/indicators. `device_display.py` is only the root recovery app import
  shim; future UI edits belong in the app. Base owns all pin sampling/writes,
  physical leases, credentials, network/provisioning and loader/rollback.
- Opt-in/enrollment/approved release assignment are per board. Publishing a
  release never advances the fleet. API2 needs matching otaBoardId and newest
  observation.boardId/baseVersion >=1.0.15; never infer missing metadata. Existing
  990 Butterfield/XIAO assignments remain unchanged unless explicitly requested.
- Feather recovery is D1 active HIGH/Pull.DOWN at hard reset; XIAO remains D9
  active LOW/Pull.UP. Never sample Feather D9 as recovery or bypass filesystem
  ownership. Normal OTA mode makes host CIRCUITPY read-only.
- Rendering/button app errors must reach rollback handling; handle expected NVM
  save errors inside the protected Platform operation. Trial timeout cannot
  deliberately restart an active hold. Defer Restart setup during trials and
  suppress OTA/watchdog on a durable pending setup-reset boot. Preserve OTA
  settings, confirmed slot, journals and sequence floor across setup restart.
- Build releases from a clean tagged committed checkout. A separate clean
  snapshot/worktree avoids unrelated scratch files; never delete or commit user
  scratch to satisfy the release guard. Physical power-loss/recovery qualification
  must be reported separately from simulated torn writes or watchdog resets.

- Feather 37cc02 has USB base 1.0.15/app 1.1.0 installed, with approved OTA
  release 1.1.0 confirmed at sequence 6. Physical D1 recovery and local
  syntax/UI/watchdog rollback passed; see `docs/feather-ota-bench-validation.md`.
  Physical power-loss and real Feather hold/update qualification remain pending.
