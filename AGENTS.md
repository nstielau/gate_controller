# XIAO CircuitPython development

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
  only in `.artifacts/web-test`; `tools/build_web.mjs --test` creates it.
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
- Keep credentials in ignored `.env`, the CA in ignored `emqxsl-ca.crt`, and
  logs/results in ignored `.artifacts/`. Never print or commit secrets.
  `tools/env_config.py` is the shared literal dotenv parser. Only
  `MQTT_USERNAME` and `MQTT_PASSWORD` go into device `settings.toml`;
  never copy REST API credentials. Settings are readable over USB.
  Do not expose saved Wi-Fi credentials while inspecting NVM.

# Runtime and pins

- Current firmware initializes transistor control `board.D10` (**GPIO9**) LOW.
  A valid timed MQTT hold raises D10 steadily until monotonic expiry or exit.
  D9 is unused. Indicator servicing must never toggle D10.
- The onboard `board.LED` is **active low**: a 100 ms pulse every two seconds
  shows the loop is running, independent of connectivity and hold state.
- External LEDs are active HIGH: D0/GPIO1 is Wi-Fi (500 ms transitions until
  connected, then ON); D1/GPIO2 is MQTT (OFF without Wi-Fi, 500 ms transitions
  until subscribed, then ON); D2/GPIO3 is hold (OFF unless D10 is HIGH,
  four full cycles/second with 125 ms transitions).
  Each LED needs its own 1 kΩ series resistor to its anode and cathode to GND.
- Keep the commented temporary three-flash D0/D1/D2 startup diagnostic until
  requested to remove it. It releases pins before runtime initialization.
  Runtime outputs return LOW and the active-low onboard LED turns OFF on exit.
- `gate_indicators.py` owns the independent LED timers. Network operations
  can temporarily delay servicing, particularly initial Wi-Fi/TLS connection.
  No network failure should call `microcontroller.reset()`.
- Missing settings start an open `Gate-Setup-<chip suffix>` AP and portal at
  `http://192.168.4.1`. Saved settings use station mode with retry, not an
  automatic fallback portal. Preserve NVM GATE1/GATE2/GATE3 compatibility.
  Deploy-time MQTT credentials override NVM.
- Default topics: `gate/v1/devices/<device-id>/command` and `/status`.
  Hold payloads are `{"version":1,"type":"hold_gate",
  "duration_seconds":5,"command_id":"..."}` and are never retained;
  retained deliveries are rejected, including stale messages from old tools.
  `make hold DURATION=5` uses the TLS-verified publisher; zero cancels.
- MiniMQTT 8.1.0 rejects a loop timeout below its socket timeout. Idle polls
  must remain short; TLS and packet bodies need longer deadlines. Do not
  hide ValueError as a connection failure, publish inside callbacks, or
  subscribe twice after reconnecting.
- Bounded GATE_LOG records include boot IDs, indicator modes, four D2 edge
  samples per mode change/heartbeat, and ten-second online heartbeats with
  independent Wi-Fi/MQTT states and an onboard `alive_edge_count`.

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
  Evidence: `.artifacts/indicators.log` and `.artifacts/indicators.json`.
  The old `tools/test_mqtt_cycles.py` publisher test is obsolete for this
  firmware (its passive log reader is reused).
- Hardware checks measure software GPIO writes, not optical/electrical output.
  Offline and inactive-hold behavior use host tests; the passive live test
  does not disconnect Wi-Fi or activate the gate. Report those limits accurately.
- `make console CONSOLE_WAIT=20` reads passively; use `CONSOLE_ARGS=--reload`
  only for an intentional Ctrl-C/Ctrl-D reload. Use one serial reader at a time.
  `make status` checks the mounted CircuitPython version.

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
