# Gate Controller

Alexa-enabled driveway gate controller with custom FeatherWing PCB.

The XIAO ESP32S3 CircuitPython app provides Wi-Fi provisioning, MQTT, and
connection/hold indicators. See [circuitpython/README.md](circuitpython/README.md)
for setup, deployment, and hardware verification. Host dependencies are
managed with `uv`; use `make setup`, `make test`, and `make deploy` from the
repository root.

The current bench firmware holds D10/GPIO9 LOW at startup. A hold message raises
D10 and the separate D0/GPIO1 LED for the requested duration; the D0 LED blinks
four times per second while active and is otherwise off. Wire D0 through 1 kΩ
to the LED anode, cathode to GND. D9 is unused.
See the [connection guide](docs/xiao-breadboard.svg) and the
[170-hole mini breadboard layout](docs/xiao-breadboard.md), including the
Fritzing project and exact hole assignments. The transistor collector
LED is a disconnected bench load; the prospective LiftMaster eyes interface
has not been validated. Current firmware ignores legacy MQTT blink commands.

## Software

Python server running on a Raspberry Pi (or Feather with WiFi) that controls
the gate via GPIO. Supports Alexa voice commands and HTTP API.

### API

- `POST /hold` — hold gate open (body: seconds, default 1)
- `POST /hold/cancel` — release gate
- `GET /hold` — check if gate is held

### Running

```bash
docker build -t gate_controller .
docker run -p 80:80 --privileged gate_controller
```

## Hardware

FeatherWing PCB in `hardware/` — designed in KiCad.

### Circuit

- **NPN switch**: GPIO A0 → 1kΩ → 2N3904 base; collector/emitter across
  LiftMaster dry-contact input via screw terminal
- **Gate LED**: Green 0805 LED on A0 — lights when gate is held open
- **NeoPixel**: WS2812B on A1 — firmware-controlled RGB status
- **Bypass cap**: 100nF across WS2812B power rails

### BOM

| Ref | Part | Value | Package |
|-----|------|-------|---------|
| Q1 | 2N3904 | NPN | TO-92 |
| R1 | Resistor | 1kΩ | 0805 |
| R2 | Resistor | 330Ω | 0805 |
| R3 | Resistor | 330Ω | 0805 |
| C1 | Capacitor | 100nF | 0805 |
| LED1 | LED | Green | 0805 |
| LED2 | WS2812B | RGB | 5050 |
| J3 | Screw terminal | 2-pos | 5.08mm |

### Fabrication

Generate Gerber files from KiCad: File → Fabrication Outputs → Gerbers.
Upload to JLCPCB, OSH Park, or PCBWay.
