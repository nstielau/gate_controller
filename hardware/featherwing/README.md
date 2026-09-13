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
pair of hand-solder pads at the right-hand edge so the output wires leave away
from the USB connector.

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
stage is retained because it is the known-working circuit; J3 is two large
plated-through solder pads, with pad 1 = OUT_OC and pad 2 = GND. No connector
component is populated; hand-solder the field wires and add strain relief.
J3 is omitted from both the assembly BOM and centroid position file.

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
