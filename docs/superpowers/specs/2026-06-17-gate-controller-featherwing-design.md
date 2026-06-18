# Gate Controller FeatherWing PCB Design

## Overview

A FeatherWing add-on board that replicates the existing Raspberry Pi gate controller circuit on the Adafruit Feather form factor. The board uses an NPN transistor to provide a dry-contact switch for a LiftMaster gate controller's "hold open" input, with a hardwired green LED for gate-active indication and a NeoPixel for firmware-controlled RGB status.

## Board Specifications

- **Form factor**: Adafruit FeatherWing (50.8 x 22.86mm, 2-layer)
- **Base template**: mignon-p/FeatherWing-template-KiCad (KiCad 5, auto-converts to KiCad 8)
- **Feather compatibility**: Board-agnostic; any Feather with GPIO will work. ESP32 HUZZAH recommended for WiFi.
- **Mounting**: 4x M2.5 holes at standard Feather positions
- **Connectors**: Standard 16+12 pin headers (from template) + 2-position screw terminal for gate wires

## Schematic

### Transistor Switch (dry contact output)

Pin A0 drives Q1 (2N3904 NPN) through a 1k base resistor. The collector connects to one screw terminal pin; the emitter and the other screw terminal pin connect to GND. When A0 goes HIGH, the transistor saturates and shorts the two screw terminal pins together, which the LiftMaster reads as "hold open."

```
A0 --+-- R1 (1k) -- Base -- Q1 (2N3904) -- Collector -- J3 pin 1
     |                        Emitter -- GND -- J3 pin 2
     +-- R2 (330) -- LED1 (Green) -- GND
```

### Gate-Active LED

LED1 (green, 0805 SMD) is hardwired to A0 through a 330 ohm resistor. It lights whenever the transistor is driven, providing a firmware-independent gate-active indicator.

### NeoPixel Status LED

A WS2812B on pin A1 provides firmware-controlled RGB status. A 330 ohm resistor on the data line prevents signal ringing. A 100nF bypass capacitor across VDD/VSS stabilizes the NeoPixel's power supply.

```
A1 -- R3 (330) -- DIN -- WS2812B -- DOUT (unused)
                  VDD -- 3V3
                  VSS -- GND
             C1 (100nF) across VDD/VSS
```

## Bill of Materials

| Ref | Part | Value | Package | Purpose |
|-----|------|-------|---------|---------|
| Q1 | 2N3904 | NPN | TO-92 (THT) | Dry-contact switch |
| R1 | Resistor | 1k | 0805 (SMD) | Base current limiter (~2.3mA) |
| R2 | Resistor | 330 | 0805 (SMD) | Gate LED current limiter (~6mA) |
| R3 | Resistor | 330 | 0805 (SMD) | NeoPixel data line resistor |
| C1 | Capacitor | 100nF | 0805 (SMD) | NeoPixel bypass cap |
| LED1 | LED | Green | 0805 (SMD) | Hardwired gate-active indicator |
| LED2 | WS2812B | RGB | 5050 (SMD) | Firmware-controlled RGB status |
| J3 | Screw terminal | 2-pos 5.08mm | THT | LiftMaster connection |

## Pin Assignments

| Feather Pin | Function |
|-------------|----------|
| A0 | Transistor base drive + gate LED |
| A1 | NeoPixel data in |
| 3V3 | NeoPixel power |
| GND | Common ground |

All other Feather pins are unused and available for future expansion.

## PCB Layout Notes

- Screw terminal J3 placed at board edge for easy wire access
- Q1 (TO-92) near the screw terminal to keep high-current traces short
- NeoPixel LED2 placed for top-side visibility
- Gate LED LED1 placed near NeoPixel for a clean indicator cluster
- SMD components (resistors, capacitor, LEDs) on top side
- Through-hole components (Q1, J3, pin headers) require bottom-side soldering

## Design Decisions

- **2N3904 over MOSFET**: Matches the existing working circuit. The dry-contact load is milliamps at low voltage, well within the 2N3904's 200mA/40V rating.
- **Hardwired LED + NeoPixel**: The green LED works without firmware (debug/failsafe). The NeoPixel adds rich status feedback under firmware control.
- **0805 SMD for passives**: Good balance of hand-solderability and board space savings.
- **5.08mm screw terminal**: Standard pitch for field wiring, easy to connect/disconnect without tools beyond a small screwdriver.
- **A0 for transistor**: Easily identifiable pin across all Feather boards.
