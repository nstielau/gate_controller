# XIAO on a 170-hole mini breadboard

Open [the Fritzing project](xiao-breadboard.fzz) in **Breadboard** view.
[Rendered preview](xiao-mini-breadboard.svg) · [Circuit connection guide](xiao-breadboard.svg).

This layout assumes a standard **170-hole, 17 × 10 mini breadboard without
power rails**, with 2.54 mm hole spacing. USB faces left, the XIAO straddles the
center gap, and both LEDs and the transistor sit to its right. It uses nine
insulated jumpers. No separate screw-terminal block is needed for this bench circuit.

The drawing is rotated relative to some breadboards: numbers 1–17 run left
to right; A–E are above the center gap, F–J below. Each numbered group A–E
is connected internally, as is F–J. The two halves are separate.
If your board is unmarked, count from the left/top in the preview.
**Hole D0 is not the XIAO pin named D0.**

## Seat the components

Fit the resistors and short jumpers before seating the XIAO. Its headers must
be soldered. Leave USB pointing off the left edge so the cable stays accessible.
Bend component leads to the listed hole spacing; insert one lead per hole.

| Part | Holes | Notes |
| --- | --- | --- |
| XIAO upper header | C1–C7 | Left → right: 5V, GND, 3V3, D10, D9, D8, D7 |
| XIAO lower header | G1–G7 | Left → right: D0, D1, D2, D3, D4, D5, D6 |
| R1, 1 kΩ | A4 → A9 | D10 to transistor base; 12.7 mm lead spacing |
| Q1, 2N3904 | E10 / E11 / E12 | Emitter / base / collector; verify your actual part's datasheet |
| R3, 100 kΩ | D9 → H9 | Base pulldown; 15.24 mm lead spacing |
| R2, 1 kΩ | D14 → H14 | Red bench LED current limit; 15.24 mm lead spacing |
| Red LED1 | Cathode E13; anode E14 | Steady when the transistor conducts |
| R4, 1 kΩ | D17 → H17 | Green hold LED current limit; 15.24 mm lead spacing |
| Green LED2 | Cathode E16; anode E17 | Blinks while D10 is HIGH; otherwise off |

The cathode is usually the shorter LED lead and the flat side of the lens.
Check polarity before cutting leads. The transistor illustration uses E–B–C
from left to right; do not assume that order for a different transistor.

## Add the nine jumpers

| Color | From | To | Connection |
| --- | --- | --- | --- |
| Orange | B9 | A11 | R1 output / pulldown to Q1 base |
| Black | B2 | A10 | XIAO GND to Q1 emitter row |
| Black | D10 | F10 | Carry ground across the center gap |
| Black | I9 | I10 | Pulldown return to ground |
| Black | J10 | J16 | Ground to hold LED return row |
| Black | F16 | D16 | Ground across the gap to the green LED cathode |
| Orange | A12 | A13 | Q1 collector to red LED cathode |
| Red | B3 | I14 | 3V3 to the red LED's resistor |
| Green | G1 | I17 | XIAO D0 to the green LED's resistor |

Use insulated jumper wire for routes that cross other leads. Crossings in
the drawing are not junctions; only the endpoint holes and breadboard's
internal strips connect. All power and ground connections use terminal rows.

## What to expect

Current firmware keeps **D10/GPIO9** and the green **D0/GPIO1** indicator LOW
until a hold command arrives. During the hold, D10 is HIGH and the green
indicator blinks four times per second; the red bench LED is on.
The onboard LED blinks until Wi-Fi and MQTT connect, then stays ON. D9 is unused.
The green LED reports the transistor output command, not sensed gate position.
Pin mapping: [Seeed's XIAO ESP32-S3 reference](https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/).

The red LED and 3V3 branch are a bench load with the gate disconnected.
This drawing does not specify wiring to the LiftMaster monitored “eyes” input.

## Regenerate and verify

From the repository root, with Fritzing installed at `/Applications/Fritzing.app`:

```sh
make fritzing          # generate FZZ and validate connections/placement
make fritzing-preview  # also render the actual Fritzing breadboard view
```

The generator uses uv with pinned `svgelements`. The FZZ embeds its required
custom parts; there is no separate part-install step. It uses the bundled
GOKUX XIAO contribution, corrects its header spacing for seating, and normalizes
the core mini-board artwork to 2.54 mm pitch. The original FZPZ stays intact.
The schematic and PCB views are not laid out.

Validation checks eight distinct nets, used and unused XIAO pins, all fourteen
header positions, component lead alignment, and no duplicate occupied holes.
The preview is exported by Fritzing itself to catch asset and wire-rendering
errors. This is drawing validation, not an electrical measurement of an
assembled breadboard. Export diagnostics are in ignored
`artifacts/fritzing-mini/export.log`.
