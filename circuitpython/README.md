# XIAO ESP32S3 CircuitPython app

Wi-Fi provisioning, MQTT over verified TLS, and separate connection/hold
indicators. Targets CircuitPython 10.x; tested on 10.3.0.

| Output | Behavior |
| --- | --- |
| Onboard yellow LED | Running heartbeat: two 100 ms flashes, starting 250 ms apart, every 2 seconds (1.0.1). |
| D0 / GPIO1 external LED | Wi-Fi: 500 ms transitions while connecting; steady ON when connected. |
| D1 / GPIO2 external LED | MQTT: OFF without Wi-Fi; 500 ms transitions while connecting; steady ON after subscription. |
| D2 / GPIO3 external LED | Hold: OFF normally; four full blinks per second while D10 is HIGH. |
| D10 / GPIO9 transistor control | LOW at boot; HIGH only for the requested hold duration. |

D9 is reserved for optional OTA maintenance recovery. A hold command raises D10 steadily for its duration.
The D2 LED reports the commanded transistor state, not sensed gate position.
The temporary startup diagnostic flashes D0/D1/D2 together three times,
then releases the pins before normal operation. Its function and call are
marked for later removal.

Wire each of **D0, D1, D2 → its own 1 kΩ resistor → LED anode (+);
LED cathode (−) → XIAO GND**. D2/GPIO3 is a strapping pin; do not add a
pull-up or externally drive it during reset.
The [connection guide](../docs/xiao-breadboard.svg) predates this four-LED assignment.
D0 and D10 are board
labels: **D0 is GPIO1**, and **D10 is GPIO9**. The red charging LED is separate.

The onboard LED is active low; external LEDs are active high.
D2 uses 125 ms transitions, giving four complete on/off cycles per second.
All LED timers are independent of D10. Blocking Wi-Fi/TLS operations can briefly
pause blinking, especially during connection attempts.

## Setup and deployment

From the repository root, use **uv** (Python 3.11+):

```sh
make setup
make test
make deploy
```

Host dependencies are locked in `tools/requirements-dev.lock`. Refresh after
changing dependencies with:

```sh
uv pip compile tools/requirements-dev.txt -o tools/requirements-dev.lock
```

Put the downloaded CA at ignored `emqxsl-ca.crt` and credentials in ignored
`.env`:

```dotenv
MQTT_USERNAME=your-device-username
MQTT_PASSWORD='your-device-password'  # pragma: allowlist secret
```

Deployment copies the CA to `/certs/emqxsl-ca.crt` and renders only MQTT
username/password into device `settings.toml`, readable over USB. REST API
credentials stay on the host. The dotenv parser accepts literal quoted or
unquoted values; the last duplicate wins and process environment overrides
the file.

`make deploy` runs tests, preflights inputs, then copies changed app/library
files to `/Volumes/CIRCUITPY`, preserving unrelated files and settings.
Override with `CIRCUITPY=/path`. Filesystem writes normally trigger Python
autoreload; network recovery never deliberately hard-resets the board.

With missing settings, join the open `Gate-Setup-<chip suffix>` network and
visit `http://192.168.4.1`. The portal stores settings in NVM; deploy-time MQTT
credentials override saved credentials. Provisioned devices retry in station
mode after connection failures instead of reopening the portal.

## MQTT status

Default topics are `gate/v1/devices/<device-id>/command` and `/status`.
The ID is the lowercase chip suffix (`b3640c` for this board). The portal
can configure custom topics.

The device publishes retained `device_status` at connection and every ten
seconds with `boot_id`, `uptime_ms`, IP, and an `indicators` object containing
`wifi_connected`, `mqtt_connected` (both Wi-Fi and MQTT ready), `transistor_high`,
`wifi_led_on`, `mqtt_led_on`, `onboard_led_on`, `alive_edge_count`,
`hold_led_on`, and `hold_edge_count`.
Its last will reports `state: "offline"`.

The command schema is `{"version":1,"type":"hold_gate","duration_seconds":5,
"command_id":"unique-id"}`. Duration is 0–86400 seconds; zero cancels.
Commands are never retained, so a reboot cannot replay a timed gate action.
The firmware also rejects retained hold deliveries, including stale retained
messages left by older publishers.
Use `make hold DURATION=5` or `tools/mqtt_hold.py`. Invalid legacy blink
commands are rejected and cannot change either output.

## Verification

```sh
make test                   # offline regression suite
make test-hardware-smoke    # passive 20-second observation
make test-hardware          # passive 70-second observation
```

Host tests cover connection/hold LED independence, timed hold expiry, active-low polarity,
D0/D1/D2/D10 allocation and shutdown, legacy-command rejection, MiniMQTT handling,
configuration migration, portal parsing, publisher, and deployment behavior.

The live test requires a provisioned board connected over USB with working
Wi-Fi/MQTT. It waits up to 40 seconds for an online heartbeat, then checks
steady D0/D1 ON, advancing onboard heartbeat edge counts, and stable session logs. Hold activation should be tested
with `make hold DURATION=3` while watching the console. It fails on session/boot changes,
serial loss, missing heartbeats, or tracebacks. It never sends a command or
resets the board. The full run observes beyond the MQTT keepalive interval;
use it after firmware, timing, network, or library changes.

```sh
make test-hardware TEST_ARGS='--duration 120'
```

Raw logs and a JSON summary are saved to ignored `artifacts/indicators.*`.
These are software GPIO measurements; confirm physical light output visually.
Inactive-hold and disconnected behavior are covered by host tests; the live
indicator check does not activate the gate by itself.
The former MQTT command-cycle test does not apply to these automatic LEDs.

## Console

```sh
make console CONSOLE_WAIT=20
make console CONSOLE_WAIT=20 CONSOLE_ARGS=--reload
```

Default monitoring is passive; `--reload` intentionally restarts Python.
Use one serial reader at a time. With multiple boards, supply
`CONSOLE_ARGS='--port /dev/cu.usbmodem...'` or the live test's `--port` option.

The collector-powered LED in the diagram is a disconnected bench load.
The separate signal LEDs stay on the XIAO side. The prospective LiftMaster “eyes”
connection has not been established as a compatible gate-control interface.

## Opt-in OTA application updates

`drawbridge.py` contains the versioned application policy; `code.py` retains
networking and physical output leases. `boot.py`, the loader, libraries, and
the root recovery app are deployed over USB. OTA writes verified application
slots under `/ota/` and uses a trial boot before confirmation. Updates are
initially disabled. Two installations, hold deferral, and failure rollback have
passed on the bench; [the validation record](../docs/ota-bench-validation.md)
tracks remaining recovery and power-loss checks.
See [OTA operations](../docs/ota-operations.md) before enabling a device.
D9/GPIO8 is reserved as the active-low maintenance input during reset when
OTA is enabled on the XIAO. All other current pin roles are preserved.

The base and OTA app have independent versions. `lib/gate_base.py` defines the
USB bundle's `BASE_VERSION`; the selected application's `APP_VERSION` can move
forward independently. MQTT/Firebase report both, and Administration displays
the pair. Older boards show “Base not reported” until deliberately updated by
USB. Protected base commits require a version bump and change note; see the
OTA editing boundary in [AGENTS.md](../AGENTS.md).
