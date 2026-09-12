# XIAO CircuitPython development

- Source of record: `circuitpython/`, never the mounted board. Preserve the
  unrelated Raspberry Pi application and hardware design files.
- Use **uv**: `make setup` creates `.venv` and syncs
  `tools/requirements-dev.lock`. Host tools use `.venv/bin/python`.
- Run `make test` before deployment; `make deploy` also runs it.
  Keep the pinned host MiniMQTT and device CP10 library versions aligned.
  The local `gate_mqtt.py` adapter uses private hooks; test dependency updates.
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

- Current firmware initializes transistor control `board.D10` (**GPIO9**) and
  signal LED `board.D0` (**GPIO1**) LOW. A valid timed MQTT hold raises both;
  D10 and D0 return LOW at monotonic expiry or on Python exit. D9 is unused.
- The onboard `board.LED` is **active low**: blink with 500 ms transitions
  while Wi-Fi/MQTT are unavailable, then stay ON when both are connected.
  Transistor activity must not change the onboard connectivity indication.
- The separate hold indicator is `board.D0` (**GPIO1**), active HIGH.
  Wire D0 through its own 1 kΩ resistor to LED anode, cathode to XIAO GND.
  Keep it OFF when D10 is LOW; blink at four full cycles/second (125 ms
  transitions) when D10 is HIGH. Indicator servicing must never toggle D10.
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
- Bounded GATE_LOG records include boot IDs, indicator modes, four D0 edge
  samples per mode change/heartbeat, and ten-second online heartbeats.

# Verification

- `make test`: offline regressions for LED timers, active-low polarity,
  pin allocation, cleanup, separation from D10, ignored legacy commands,
  MiniMQTT packets/deadlines, NVM/portal, publisher, and deployment.
- `make deploy`: test, then update the mounted board. Filesystem writes may
  trigger an intentional autoreload. Stop other serial readers first.
- After firmware/timing/MQTT/library changes, run `make test-hardware`.
  It passively watches an already provisioned USB board for an online
  heartbeat, then observes 70 seconds. It checks steady onboard ON and stable
  session logs; use `make hold DURATION=3` to exercise D10/D0 activation,
  increasing D0 edge counts, alternating sampled writes at 125–200 ms,
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
- Keep D2/GPIO3 (strapping) and USB GPIO19/20 out of this circuit; preserve
  D6/D7 for serial diagnostics.
