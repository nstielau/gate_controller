# Drawbridge FeatherWing fabrication package

This is a revision-A prototype board for a FeatherS3[D]-compatible host. It
provides the existing, proven 2N3904 transistor output unchanged: J3 pin 1 is
the switched output and J3 pin 2 is the shared ground. The Feather module is
not part of the assembly BOM.

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

Prerequisites: KiCad 10 in `/Applications/KiCad`, `make setup`, and the repository's
Node/Playwright installation (`make web-setup`, then `npx playwright install chromium`
if Chromium is missing). Incorporate manual KiCad edits into `generate.py` before
rebuilding because the generator is the design source of record.

PCBWay uploads from `artifacts/featherwing/`:

| Upload field | File |
| --- | --- |
| Gerbers | `drawbridge-featherwing-gerbers.zip` |
| Parts list / BOM | `assembly-bom.csv` |
| Centroid | `assembly-position.csv` |
| Assembly other files | `drawbridge-featherwing-assembly-other.zip` |
| Complete package for review | `drawbridge-featherwing-pcbway.zip` |

All three ZIPs are generated together and every member is byte-checked against
the corresponding loose file. Gerbers and drills are also available in `gerbers/`
and `drills/`. Each run refreshes `board.png`, `schematic.pdf`, `schematic.svg`,
`schematic.png`, `silkscreen.svg`, logo SVG/PNG, BOM, positions, `netlist.xml`,
`erc.rpt`, `drc.rpt`, and assembly notes. `manifest.json` records the build time
and SHA-256 for every loose file and ZIP (excluding the manifest itself).

The isometric castle logo uses a 14 × 14 mm SVG canvas with 0.18 mm strokes.
The actual mark occupies about 12 × 12.5 mm on the USB end. The generator imports
`assets/drawbridge-silkscreen.svg` directly into F.Silkscreen. The 840-pixel PNG
is generated from that same SVG as a reference; no separate logo placement by
PCBWay is needed. For a bare-board order, only the Gerbers and drill files are
needed. For assembly, select through-hole assembly and ask PCBWay to
confirm the listed manufacturer part numbers and header availability. J3 is a
compact two-pin solder header so the output wires can leave from the right-hand
edge, away from the USB connector.

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
stage is retained because it is the known-working circuit; do not change J3
wiring or apply the board to a different controller without electrical review.
