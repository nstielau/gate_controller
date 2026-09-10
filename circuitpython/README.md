# XIAO ESP32S3 CircuitPython app

This app provisions Wi-Fi, connects to EMQX with verified TLS, and controls
the onboard active-low `board.LED` from MQTT commands. It targets CircuitPython
10.x; this setup was tested on 10.3.0. The red charging indicator is separate.

## Setup and deployment

From the repository root, use **uv** for the host environment (Python 3.11+):

```sh
make setup
make test
make deploy
```

`make setup` creates `.venv` and uses `uv pip sync` with
`tools/requirements-dev.lock`. To refresh that lock after changing dependencies:

```sh
uv pip compile tools/requirements-dev.txt -o tools/requirements-dev.lock
```

Put the downloaded CA at `emqxsl-ca.crt` and MQTT login credentials in `.env`:

```dotenv
MQTT_USERNAME=your-device-username
MQTT_PASSWORD='your-device-password'
```

Both files are gitignored. Deployment copies the CA to `/certs/emqxsl-ca.crt`
and renders **only** the MQTT username/password into `/settings.toml` on the
XIAO. REST API credentials stay on the host. Values may be unquoted or enclosed
in matching quotes; values are literal, the last duplicate wins, and process
environment variables take precedence. Publishing and deployment share this
parser. Device `settings.toml` is readable over USB.

`make deploy` runs host tests, preflights the inputs, and copies changed app
and library files to `/Volumes/CIRCUITPY`. Existing libraries are updated;
unrelated device files and settings are preserved. Override the destination
with `make deploy CIRCUITPY=/path/to/CIRCUITPY`. CircuitPython normally reloads
after filesystem writes; there is no hard board reset in the application.

When Wi-Fi or MQTT settings are missing, join the open `Gate-Setup-<chip suffix>`
network and visit `http://192.168.4.1`. The portal stores settings in board NVM;
deploy-time MQTT credentials override saved MQTT credentials. With settings
present, the app uses station mode and retries connectivity every five seconds
after failures. Bad saved settings do not automatically reopen the portal.

## Publish a blink command

```sh
.venv/bin/python tools/mqtt_blink.py 300 --device-id b3640c
.venv/bin/python tools/mqtt_blink.py 2000 --device-id b3640c
```

The utility uses native MQTT over TLS at
`jd3a6164.ala.us-east-1.emqxsl.com:8883`, validates the server using
`emqxsl-ca.crt`, and waits for the broker's QoS 1 acknowledgment. This confirms
broker receipt; use the hardware test below to confirm device application.

Commands are **retained by default**: the broker stores the latest command on
each topic and delivers it when a device subscribes again. This suits a desired
blink setting. `--no-retain` sends a temporary change but does not erase any
previously retained command. `--transport api` remains available for the older
Deployment API workflow with `EMQX_API_URL`, `EMQX_APP_ID`, and
`EMQX_APP_SECRET` in `.env`.

The interval is the time **between LED transitions**, so 300 ms means about
300 ms on, then 300 ms off. Accepted values are integer milliseconds from 25
through 60000. Network activity adds scheduling jitter; this is not a precision
timer. While provisioning or waiting between connection attempts, the LED uses
750 ms transitions. Network connection attempts can temporarily pause blinking.
Online, it defaults to 150 ms until it receives a command.

## Topics and schema

One broker can serve many devices, each with separate topics:

| Purpose | Default topic |
| --- | --- |
| Commands | `gate/v1/devices/<device-id>/command` |
| Status | `gate/v1/devices/<device-id>/status` |

The device ID is its lowercase chip suffix (`b3640c` for this XIAO). Use
`--topic` for a custom command topic configured in the portal.

```json
{"version":1,"type":"set_blink_interval","blink_interval_ms":300,"command_id":"unique-request-id"}
```

The publisher generates a unique `command_id`. It is optional for older
clients; if present it must be a string of 1–64 characters. Version and type
allow future commands without changing the topic layout. Duplicate deliveries
of the current command ID and value do not restart the blink timer.

The device publishes retained `device_status` at connection, after commands,
and every ten seconds. Online status includes the applied `command_id`,
`blink_interval_ms`, `boot_id`, `uptime_ms`, and `edge_count`; its last will
publishes `state: "offline"` if the broker loses the connection. These are
status reports, not commands.

## Repeatable verification

```sh
make test
make test-hardware-smoke
make test-hardware
```

Host tests cover the actual pinned MiniMQTT library's timeout behavior,
fragmented QoS 1 packets, command validation and scheduling, broker
acknowledgments, configuration migration, fragmented portal requests, and
deployment updates.

The hardware test requires the configured XIAO on USB, its working Wi-Fi,
the CA, and `.env` credentials. It opens serial once without interrupting the
app, then publishes **2000 → 300 ms three times**, retaining each setting.
For every unique command ID it requires a matching `command_applied` event
and four alternating GPIO transitions within ±max(75 ms, 15%) of the interval.
It then observes 70 seconds of heartbeats with increasing edge counts. Any
session loss, new boot ID, traceback, serial loss, or missing confirmation
fails the test. It leaves the final **300 ms** setting retained.

```sh
make test-hardware TEST_ARGS='--cycles 5 --intervals 2000 300 --soak 120'
```

Raw logs and a JSON result are saved in ignored `.artifacts/`. The log evidence
is generated immediately after writes to the LED GPIO; it does not replace
an optical sensor or oscilloscope measurement. Timing guarantees apply only
to the tested intervals and observation window.

Use `make test-hardware-smoke` for a quick one-command, 300 ms check with a
15-second stability window while iterating. It is useful after a routine
publisher or deployment change. Use the full `make test-hardware` run after
firmware, MQTT, timing, or library changes; the smoke test does not replace it.

## Serial console

```sh
make console CONSOLE_WAIT=20
make console CONSOLE_WAIT=20 CONSOLE_ARGS=--reload
```

The default streams continuously without resetting the board. `--reload`
explicitly sends Ctrl-C then Ctrl-D to restart Python. Stop other console
readers before running the hardware test; two readers can consume each other's
logs. Pass `CONSOLE_ARGS='--port /dev/cu.usbmodem...'` if multiple boards are
connected. Normal MQTT recovery does not disconnect USB.

See [AUDIT.md](AUDIT.md) for the reproduced failure and verification results.
