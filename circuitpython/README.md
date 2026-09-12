# XIAO ESP32S3 CircuitPython app

Wi-Fi provisioning, MQTT over verified TLS, and separate connection/hold
indicators. Targets CircuitPython 10.x; tested on 10.3.0.

| Output | Behavior |
| --- | --- |
| Onboard yellow LED | Blinks during startup and while Wi-Fi or MQTT is unavailable; solid ON when both are connected. |
| D0 / GPIO1 external LED | LOW at boot; blinks four times per second while a hold is active. |
| D10 / GPIO9 transistor control | LOW at boot; HIGH only for the requested hold duration. |

D9 is unused. A hold command raises D10 and D0 together for its duration.
The D0 LED reports the commanded transistor state, not sensed gate position.

Wire **D0 → 1 kΩ resistor → LED anode (+); LED cathode (−) → XIAO GND**.
See the [connection guide](../docs/xiao-breadboard.svg). D0 and D10 are board
labels: **D0 is GPIO1**, and **D10 is GPIO9**. The red charging LED is separate.

The onboard LED is active low and uses 500 ms transitions while disconnected.
D0 uses 125 ms transitions, giving four complete on/off cycles per second.
Both timers are independent of D10. Blocking Wi-Fi/TLS operations can briefly
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
MQTT_PASSWORD='your-device-password'
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
`mqtt_connected` (both Wi-Fi and MQTT ready), `transistor_high`,
`onboard_led_on`, `hold_led_on`, and `hold_edge_count`.
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
D0/D10 allocation and shutdown, legacy-command rejection, MiniMQTT handling,
configuration migration, portal parsing, publisher, and deployment behavior.

The live test requires a provisioned board connected over USB with working
Wi-Fi/MQTT. It waits up to 40 seconds for an online heartbeat, then checks
steady onboard ON and stable session logs. Hold activation should be tested
with `make hold DURATION=3` while watching the console. It fails on session/boot changes,
serial loss, missing heartbeats, or tracebacks. It never sends a command or
resets the board. The full run observes beyond the MQTT keepalive interval;
use it after firmware, timing, network, or library changes.

```sh
make test-hardware TEST_ARGS='--duration 120'
```

Raw logs and a JSON summary are saved to ignored `.artifacts/indicators.*`.
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
The separate D0 LED stays on the XIAO side. The prospective LiftMaster “eyes”
connection has not been established as a compatible gate-control interface.
