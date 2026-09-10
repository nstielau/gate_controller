# XIAO CircuitPython development

- The source of record is `circuitpython/`, never the mounted board. Preserve
  the unrelated Raspberry Pi application and hardware design files.
- Use **uv**: `make setup` creates `.venv` and syncs
  `tools/requirements-dev.lock`. Host tools use `.venv/bin/python`; do not
  depend on packages installed under `/private/tmp` or the system Python.
- Run `make test` before deployment. It includes syntax checks and regressions
  against the actual pinned MiniMQTT Python package. `make deploy` runs it too.
- Third-party CP10 `.mpy` files are committed under `circuitpython/lib/`.
  Keep the host MiniMQTT version and the device version aligned. The local
  `gate_mqtt.py` adapter uses private hooks; test it when updating dependencies.
- `make deploy` preflights credentials and the CA, then copies changed files
  including changed libraries. It does not delete unrelated device files or
  overwrite unrelated settings. Default drive: `/Volumes/CIRCUITPY`; override
  with `CIRCUITPY=/path`. Filesystem writes can cause an intentional Python
  autoreload. No network failure should call `microcontroller.reset()`.
- Keep the CA at ignored `emqxsl-ca.crt`, credentials in ignored `.env`, and
  logs/results in ignored `.artifacts/`. Never print or commit secret values.
  `tools/env_config.py` is the shared literal dotenv parser. Only
  `MQTT_USERNAME` and `MQTT_PASSWORD` are rendered into device `settings.toml`;
  never copy `EMQX_APP_ID` or `EMQX_APP_SECRET` to the board. Settings are
  readable over USB. Do not expose saved Wi-Fi credentials while inspecting NVM.

# Runtime and MQTT

- An open `Gate-Setup-<chip suffix>` AP serves `http://192.168.4.1` when settings
  are missing. With saved settings, the app stays in station mode and retries
  Wi-Fi before recreating MQTT. A failed connection does not reopen the portal.
- NVM `GATE3` uses a two-byte payload length; preserve compatibility with
  `GATE1` and `GATE2`. Wi-Fi settings survive deployment. MQTT credentials in
  `settings.toml` take precedence over NVM.
- The default command/status topics are `gate/v1/devices/<device-id>/command`
  and `/status`. Read `circuitpython/README.md` for the versioned schema.
- Publish with `.venv/bin/python tools/mqtt_blink.py 300 --device-id b3640c`.
  Native MQTT with CA validation is the default; desired settings are retained
  by default and published at QoS 1. A PUBACK proves broker receipt only.
- MiniMQTT 8.1.0 rejects a loop timeout below its socket timeout. Idle polls
  must be short for blinking while TLS handshakes and packet bodies need longer
  deadlines. Do not hide `ValueError` as a network failure. Do not publish from
  inside the message callback or resubscribe twice after reconnecting.
- `board.LED` is active low. Intervals are milliseconds between transitions;
  a full on/off cycle is twice the interval. Network operations introduce jitter.
- Structured `GATE_LOG` records correlate commands, LED writes, heartbeats, and
  boot IDs. Keep logs bounded (four edge samples per new command, ten-second
  heartbeat); excessive output can disturb timing.

# Hardware verification and console

- Test setup: run `make setup` once after checkout. It uses `uv` to create
  `.venv` and install the locked host dependencies. Run `make test` for the
  offline suite; it performs syntax validation and runs the MiniMQTT, command
  schema, NVM/portal, publisher, and deployment regression tests. A code or
  dependency change must leave all tests passing before deployment.
- Test deployment with `make deploy`. This reruns `make test`, validates the
  ignored `.env` and `emqxsl-ca.crt`, and updates only changed files on the
  mounted CIRCUITPY drive. Confirm the board is mounted and stop any other
  serial reader first. `make status` checks the drive and CircuitPython version.
- For behavior or MQTT changes, run `make test-hardware` after deployment.
  Default: three cycles of 2000/300 ms plus a 70-second stability observation.
  It publishes retained commands and leaves the last interval (300 ms) active.
  Override with `TEST_ARGS='--cycles 5 --intervals 2000 300 --soak 120'`.
- Use `make test-hardware-smoke` for quick iteration: one retained 300 ms
  command, four measured edges, and 15 seconds of stability. It is a useful
  smoke check after a publisher/deployment edit, but the full cycle test remains
  required after firmware, timing, MQTT, or library changes.
- The hardware test must be run from the repository root with the board's Wi-Fi
  already provisioned and native MQTT credentials in `.env`. It opens the USB
  console passively, publishes a unique command ID for each interval, waits for
  `command_applied`, then checks four alternating `led_edge` records and their
  measured intervals. It also watches heartbeats during the soak period. A
  successful broker PUBACK alone is insufficient; the device log must confirm
  application. Raw evidence is written to `.artifacts/mqtt-cycles.log` and the
  summary to `.artifacts/mqtt-cycles.json`.
- Require matching command IDs and measured LED write intervals across cycles.
  Quiet logs, successful publish output, or the same visible blink rate alone
  do not prove success. USB serial loss or a new boot ID invalidates a run.
- Use `make console CONSOLE_WAIT=20` for passive, continuously drained logs.
  Reload only explicitly with `CONSOLE_ARGS=--reload`. The default must not
  reset the device or discard buffered logs. Use one serial reader at a time.
- Report actual measurements and the observation window. These tests measure
  software GPIO writes, not light output with external hardware.
