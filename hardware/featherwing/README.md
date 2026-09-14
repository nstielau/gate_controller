# Drawbridge FeatherWing fabrication package

This is a revision-stamped prototype board for a Feather-compatible host,
including the Unexpected Maker FeatherS3[D] and Adafruit ESP32-S3 Reverse TFT
Feather. It provides the existing, proven 2N3904 transistor output unchanged:
J3 pin 1 is the switched output and J3 pin 2 is the shared ground. The Feather
module is not part of the assembly BOM.

Schematic and PCB signal names use portable Feather header labels:
`WIFI_D5`, `MQTT_D6`, `HOLD_D9`, and `CTRL_D11`. GPIO numbers differ between
Feather models and therefore are not part of these net names.

## PCBWay upload

The generated PCB is `drawbridge-featherwing.kicad_pcb` and the schematic is
`drawbridge-featherwing.kicad_sch`. Generate the fabrication package from the
repository root with:

```sh
make featherwing-fab
```

Every run regenerates the design from `generate.py`, runs ERC/DRC, and replaces
the **entire** `artifacts/featherwing/` directory with a complete release. Do not
keep manual edits or source files in that output directory. Old extracted ZIPs,
previews and reports disappear automatically. Other artifact folders are separate.
If a build fails, the last complete release remains available; its timestamp in
`manifest.json` identifies when it was built. Never upload after a failed build
assuming that the files reflect your latest source changes.

Each build derives its revision from the first three characters of the current
Git `HEAD`. A clean tree produces `<ref>.0`; successful generations from a dirty
tree increment the suffix (`<ref>.1`, `<ref>.2`, and so on). Failed builds do not
consume a number because the previous complete release remains in place. The
same revision is printed below the castle, recorded in `manifest.json`, and
written to `REV_<revision>.txt`. That marker is included in all three ZIP files.

Prerequisites: KiCad 10 in `/Applications/KiCad`, `make setup`, and the repository's
Node/Playwright installation (`make web-setup`, then `npx playwright install chromium`
if Chromium is missing). Incorporate manual KiCad edits into `generate.py` before
rebuilding because the generator is the design source of record.

PCBWay uploads from `artifacts/featherwing/`:

| Upload field | File |
| --- | --- |
| Gerbers | `drawbridge-featherwing-gerbers.zip` |
| Parts list / BOM | `assembly-bom.xlsx` (PCBWay upload) |
| Centroid | `assembly-position.csv` |
| Assembly other files | `drawbridge-featherwing-assembly-other.zip` |
| Complete package for review | `drawbridge-featherwing-pcbway.zip` |

For Seeed Studio Fusion, upload `seeed-assembly-bom.csv`. It uses Seeed's
four-column `Designator`, `Manufacturer Part Number or Seeed SKU`, `Qty`, and
`Link` format and consolidates identical MPNs. All parts except J3 are selected from Seeed's Shenzhen Open Parts Library
(OPL); their links search the live OPL listing. J3 is Phoenix Contact 1725656
and uses its manufacturer link for external sourcing by Seeed (not verified
OPL stock). The BOM includes the two underside Feather headers, five resistors,
Q1, three LEDs, and J3. The Feather host is excluded. Check live availability when requesting a quote because OPL stock
changes independently of this repository.

The selected XKB headers have 2.54 mm pitch, 2.5 mm insulators, 3.0 mm solder
tails, and 6.0 mm mating pins. Seeed must install their bodies on the bottom of
the wing, with the 6.0 mm pins pointing down into the Feather's sockets. The
LEDs are a matching Everlight 3 mm family; observe the KiCad cathode/pad-1
orientation during assembly.

All three ZIPs are generated together and every member is byte-checked against
the corresponding loose file. Gerbers and drills are also available in `gerbers/`
and `drills/`. Each run refreshes `board.png`, `schematic.pdf`, `schematic.svg`,
`schematic.png`, `silkscreen.svg`, logo SVG/PNG, BOM, positions, `netlist.xml`,
`erc.rpt`, `drc.rpt`, and assembly notes. `manifest.json` records the build time
and SHA-256 for every loose file and ZIP (excluding the manifest itself).
The BOM is emitted as both `assembly-bom.xlsx` for PCBWay and `assembly-bom.csv`
for review.

The isometric castle logo uses a 14 × 14 mm SVG canvas with 0.18 mm strokes.
The actual mark occupies about 12 × 12.5 mm on the USB end. The generator imports
`assets/drawbridge-silkscreen.svg` directly into F.Silkscreen. The 840-pixel PNG
is generated from that same SVG as a reference; no separate logo placement by
PCBWay is needed. For a bare-board order, only the Gerbers and drill files are
needed. For assembly, select through-hole assembly and ask PCBWay to
confirm the listed manufacturer part numbers and header availability. J3 is a
top-side screw terminal at the right-hand edge, with wire entry facing outward
away from the USB connector.

Recommended starting options are two layers, FR-4, 1.6 mm thickness, 1 oz
copper, green solder mask, white silkscreen, and lead-free HASL. These are
defaults for quoting, not a manufacturing release.

## Release checks

Run `make featherwing-check` before uploading; it performs the same complete
rebuild as `make featherwing-fab`. Offline package freshness/failure recovery
tests run with `.venv/bin/python -m unittest test_suite.test_featherwing_fab`
and are included in `make test`. Inspect
the Gerbers in PCBWay's viewer, especially the Feather header orientation,
mounting holes, J3 polarity, and the antenna keepout at the FeatherS3[D] end.

The gate-controller interface remains installation-specific. The transistor
stage is retained because it is the known-working circuit. J3 is populated with
[Phoenix Contact MPT 0,5/2-2,54, 1725656](https://www.phoenixcontact.com/us/products/1725656).
Viewed from above with USB left, the upper screw is GND (pin 2) and the lower
screw is OUT_OC (pin 1). Follow these labels when reconnecting existing wires.
The terminal has a 5.54 x 6.2 mm body, 8.5 mm installed height, and 2.54 mm
contact pitch. Use 20–26 AWG wire, strip 4.5 mm, and tighten to 0.12–0.15 N m
while supporting the terminal body. Provide cable strain relief.

The local `Drawbridge:ExitTerminal` footprint retains KiCad's Phoenix footprint
contacts and both 1.1 mm non-plated locating holes from the manufacturer's
drilling drawing, 2.54 mm toward the wire-entry side of the contact pins. It
uses a 0.25 mm body courtyard and omits silkscreen at the wire-entry edge. Do not omit
these holes or substitute a generic 2.54 mm header footprint. J3 is included in
all assembly BOMs and in the top-side position file. The headers remain on the
underside. The board outline is unchanged at 50.8 x 22.86 mm.

Routing uses horizontal, vertical, and 45-degree segments, with chamfers at
right-angle turns. Connected branches may still meet at right angles; these
are electrical junctions, not sharp bends in a continuous route. Copper/holes,
component courtyards, and silkscreen are checked on every fabrication build.
The terminal and cable are near the Feather's antenna end: RF performance and
assembled stack/enclosure clearance need checking with the actual host. DRC
does not establish either of those physical properties.

The Feather-compatible J1 (16-pin) and J2 (12-pin) stacking headers are
bottom-side assembly parts. Their XY pin coordinates are intentionally not
mirrored, preserving the Feather pin order when this board is placed on top of
the Feather host.

## Indicator LEDs

The 3 mm through-hole LEDs in the assembly BOM are assigned as follows:

| Reference | Function | Color |
| --- | --- | --- |
| D1 | Wi-Fi | Cool white |
| D2 | MQTT | Blue |
| D3 | Hold | Green |
