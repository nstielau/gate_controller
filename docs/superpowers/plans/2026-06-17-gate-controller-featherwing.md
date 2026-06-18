# Gate Controller FeatherWing PCB Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a KiCad FeatherWing PCB that uses an NPN transistor to switch a dry contact for a LiftMaster gate controller, with a hardwired green LED and a NeoPixel for status.

**Architecture:** Edit the existing KiCad 5 schematic to add 8 components (Q1, R1, R2, R3, C1, LED1, LED2/WS2812B, J3) with their footprint assignments. Wiring and PCB layout are done interactively in KiCad 8 (which auto-converts KiCad 5 files on open). The schematic drives the PCB via KiCad's "Update PCB from Schematic" workflow.

**Tech Stack:** KiCad 8 (reading KiCad 5 project files), standard KiCad symbol/footprint libraries

**Spec:** `docs/superpowers/specs/2026-06-17-gate-controller-featherwing-design.md`

---

### Task 1: Add circuit components to schematic

**Files:**
- Modify: `hardware/gate-controller.sch`

This task adds all 8 circuit components plus power symbols to the schematic file. Components are placed in the left half of the schematic sheet (x=1500–6500, y=1200–5500), away from the existing Feather header symbols at x=8350+. No wires are added — wiring is done in Task 3 using KiCad's GUI, which is more reliable than hand-editing wire coordinates.

- [ ] **Step 1: Add component blocks to the schematic**

Insert the following content into `hardware/gate-controller.sch` immediately BEFORE the final `$EndSCHEMATC` line:

```
Wire Notes Line
	1500 1200 6500 1200
Wire Notes Line
	6500 1200 6500 5500
Wire Notes Line
	6500 5500 1500 5500
Wire Notes Line
	1500 5500 1500 1200
Text Notes 1600 1400 0    100  ~ 20
Gate Controller Circuit
$Comp
L Device:R R1
U 1 1 6651A002
P 3200 2000
F 0 "R1" V 3100 2000 50  0000 C CNN
F 1 "1k" V 3300 2000 50  0000 C CNN
F 2 "Resistor_SMD:R_0805_2012Metric" H 3200 2000 50  0001 C CNN
F 3 "~" H 3200 2000 50  0001 C CNN
	1    3200 2000
	0    1    1    0   
$EndComp
$Comp
L Transistor_BJT:2N3904 Q1
U 1 1 6651A001
P 4200 2000
F 0 "Q1" H 4391 2046 50  0000 L CNN
F 1 "2N3904" H 4391 1955 50  0000 L CNN
F 2 "Package_TO_SOT_THT:TO-92_Inline" H 4400 1925 50  0001 L CIN
F 3 "~" H 4200 2000 50  0001 L CNN
	1    4200 2000
	1    0    0    -1  
$EndComp
$Comp
L Connector:Screw_Terminal_01x02 J3
U 1 1 6651A008
P 5800 1700
F 0 "J3" H 5880 1692 50  0000 L CNN
F 1 "Gate_Output" H 5880 1601 50  0000 L CNN
F 2 "TerminalBlock:TerminalBlock_bornier-2_P5.08mm" H 5800 1700 50  0001 C CNN
F 3 "~" H 5800 1700 50  0001 C CNN
	1    5800 1700
	1    0    0    -1  
$EndComp
$Comp
L Device:R R2
U 1 1 6651A003
P 2200 3200
F 0 "R2" H 2270 3246 50  0000 L CNN
F 1 "330" H 2270 3155 50  0000 L CNN
F 2 "Resistor_SMD:R_0805_2012Metric" H 2200 3200 50  0001 C CNN
F 3 "~" H 2200 3200 50  0001 C CNN
	1    2200 3200
	1    0    0    -1  
$EndComp
$Comp
L Device:LED LED1
U 1 1 6651A006
P 2200 3800
F 0 "LED1" H 2193 4017 50  0000 C CNN
F 1 "Green" H 2193 3926 50  0000 C CNN
F 2 "LED_SMD:LED_0805_2012Metric" H 2200 3800 50  0001 C CNN
F 3 "~" H 2200 3800 50  0001 C CNN
	1    2200 3800
	-1   0    0    1   
$EndComp
$Comp
L Device:R R3
U 1 1 6651A004
P 3200 4600
F 0 "R3" V 3100 4600 50  0000 C CNN
F 1 "330" V 3300 4600 50  0000 C CNN
F 2 "Resistor_SMD:R_0805_2012Metric" H 3200 4600 50  0001 C CNN
F 3 "~" H 3200 4600 50  0001 C CNN
	1    3200 4600
	0    1    1    0   
$EndComp
$Comp
L LED:WS2812B LED2
U 1 1 6651A007
P 4500 4600
F 0 "LED2" H 4844 4646 50  0000 L CNN
F 1 "WS2812B" H 4844 4555 50  0000 L CNN
F 2 "LED_SMD:LED_WS2812B_PLCC4_5.0x5.0mm_P3.2mm" H 4550 4300 50  0001 L TNN
F 3 "~" H 4600 4225 50  0001 L TNN
	1    4500 4600
	1    0    0    -1  
$EndComp
$Comp
L Device:C C1
U 1 1 6651A005
P 5500 4600
F 0 "C1" H 5615 4646 50  0000 L CNN
F 1 "100nF" H 5615 4555 50  0000 L CNN
F 2 "Capacitor_SMD:C_0805_2012Metric" H 5538 4450 50  0001 C CNN
F 3 "~" H 5500 4600 50  0001 C CNN
	1    5500 4600
	1    0    0    -1  
$EndComp
$Comp
L power:GND #PWR03
U 1 1 6651A009
P 4300 2400
F 0 "#PWR03" H 4300 2150 50  0001 C CNN
F 1 "GND" H 4305 2227 50  0000 C CNN
F 2 "" H 4300 2400 50  0001 C CNN
F 3 "" H 4300 2400 50  0001 C CNN
	1    4300 2400
	1    0    0    -1  
$EndComp
$Comp
L power:GND #PWR04
U 1 1 6651A00A
P 5600 1900
F 0 "#PWR04" H 5600 1650 50  0001 C CNN
F 1 "GND" H 5605 1727 50  0000 C CNN
F 2 "" H 5600 1900 50  0001 C CNN
F 3 "" H 5600 1900 50  0001 C CNN
	1    5600 1900
	1    0    0    -1  
$EndComp
$Comp
L power:GND #PWR05
U 1 1 6651A00B
P 2200 4100
F 0 "#PWR05" H 2200 3850 50  0001 C CNN
F 1 "GND" H 2205 3927 50  0000 C CNN
F 2 "" H 2200 4100 50  0001 C CNN
F 3 "" H 2200 4100 50  0001 C CNN
	1    2200 4100
	1    0    0    -1  
$EndComp
$Comp
L power:GND #PWR06
U 1 1 6651A00C
P 4500 5100
F 0 "#PWR06" H 4500 4850 50  0001 C CNN
F 1 "GND" H 4505 4927 50  0000 C CNN
F 2 "" H 4500 5100 50  0001 C CNN
F 3 "" H 4500 5100 50  0001 C CNN
	1    4500 5100
	1    0    0    -1  
$EndComp
$Comp
L power:+3.3V #PWR07
U 1 1 6651A00D
P 4500 4200
F 0 "#PWR07" H 4500 4050 50  0001 C CNN
F 1 "+3.3V" H 4515 4373 50  0000 C CNN
F 2 "" H 4500 4200 50  0001 C CNN
F 3 "" H 4500 4200 50  0001 C CNN
	1    4500 4200
	1    0    0    -1  
$EndComp
$Comp
L power:GND #PWR08
U 1 1 6651A00E
P 5500 4900
F 0 "#PWR08" H 5500 4650 50  0001 C CNN
F 1 "GND" H 5505 4727 50  0000 C CNN
F 2 "" H 5500 4900 50  0001 C CNN
F 3 "" H 5500 4900 50  0001 C CNN
	1    5500 4900
	1    0    0    -1  
$EndComp
$Comp
L power:+3.3V #PWR09
U 1 1 6651A00F
P 5500 4300
F 0 "#PWR09" H 5500 4150 50  0001 C CNN
F 1 "+3.3V" H 5515 4473 50  0000 C CNN
F 2 "" H 5500 4300 50  0001 C CNN
F 3 "" H 5500 4300 50  0001 C CNN
	1    5500 4300
	1    0    0    -1  
$EndComp
```

- [ ] **Step 2: Verify the file is valid**

Run: `grep -c '\$Comp' hardware/gate-controller.sch && grep -c '\$EndComp' hardware/gate-controller.sch`

Expected: Both counts should be 18 (2 original connectors + 2 original power + 8 new components + 6 new power = 18).

- [ ] **Step 3: Commit**

```bash
git add hardware/gate-controller.sch
git commit -m "Add gate controller circuit components to schematic"
```

---

### Task 2: Add .gitignore for KiCad files

**Files:**
- Create: `hardware/.gitignore`

KiCad generates many temporary/backup files. These should not be committed.

- [ ] **Step 1: Create the .gitignore**

Write `hardware/.gitignore`:

```
# KiCad backup and temp files
*.bak
*.bck
*-backups/
*.kicad_pcb-bak
*.sch-bak
*~
\#*
_autosave-*
*.tmp
fp-info-cache
*.dsn
*.ses
*.kicad_prl

# KiCad 8 auto-generated
*.kicad_dru

# Gerber outputs (regenerate from source)
gerbers/
```

- [ ] **Step 2: Commit**

```bash
git add hardware/.gitignore
git commit -m "Add .gitignore for KiCad temp files"
```

---

### Task 3: Wire schematic in KiCad (MANUAL — requires KiCad GUI)

**Files:**
- Modify: `hardware/gate-controller.sch` (via KiCad GUI)

This task must be done interactively in KiCad. An agent cannot perform these steps.

- [ ] **Step 1: Open the project in KiCad 8**

Open `hardware/gate-controller.pro` in KiCad 8. It will prompt to auto-convert from KiCad 5 format — accept. This creates `.kicad_sch`, `.kicad_pro`, and `.kicad_pcb` files in KiCad 8 format.

- [ ] **Step 2: Verify component placement**

Open the schematic editor. You should see:
- **Right side:** Feather pin headers (J1, J2) with labeled pins — this is from the template
- **Left side (boxed area):** All new components (R1, Q1, J3, R2, LED1, R3, LED2, C1) with power symbols

If any components overlap or are hard to read, drag them to better positions. The exact positions don't matter as long as the wiring is clear.

- [ ] **Step 3: Wire the transistor switch subcircuit**

Draw wires for this circuit:

```
A0 --+-- R1 (1k) -- Q1 base
     |                Q1 collector -- J3 pin 1
     |                Q1 emitter -- GND
     |                J3 pin 2 -- GND
     +-- (branches to LED subcircuit, step 4)
```

Specific connections:
1. Place a net label `A0` on a wire stub attached to R1 pin 1 (left end of horizontal R1)
2. Draw a wire from R1 pin 2 (right end) to Q1 base (left pin)
3. Draw a wire from Q1 collector (top pin) to J3 pin 1 (top pin of screw terminal)
4. Connect Q1 emitter (bottom pin) to the GND symbol below it
5. Connect J3 pin 2 (bottom pin of screw terminal) to its GND symbol

- [ ] **Step 4: Wire the gate LED subcircuit**

```
A0 -- R2 (330) -- LED1 anode
                   LED1 cathode -- GND
```

Connections:
1. Place a net label `A0` on a wire stub attached to R2 pin 1 (top of vertical R2)
2. Draw a wire from R2 pin 2 (bottom) to LED1 anode (top pin)
3. Connect LED1 cathode (bottom pin) to the GND symbol below it

- [ ] **Step 5: Wire the NeoPixel subcircuit**

```
A1 -- R3 (330) -- WS2812B DIN
                   WS2812B VDD -- +3.3V
                   WS2812B VSS -- GND
                   WS2812B DOUT -- (no connect)
```

Connections:
1. Place a net label `A1` on a wire stub attached to R3 pin 1 (left end of horizontal R3)
2. Draw a wire from R3 pin 2 (right end) to WS2812B DIN pin
3. Connect WS2812B VDD to the +3.3V symbol above it
4. Connect WS2812B VSS to the GND symbol below it
5. Place a "No Connect" flag (X) on WS2812B DOUT pin

- [ ] **Step 6: Wire the bypass capacitor**

```
C1 pin 1 -- +3.3V
C1 pin 2 -- GND
```

1. Connect C1 pin 1 (top) to its +3.3V symbol
2. Connect C1 pin 2 (bottom) to its GND symbol

- [ ] **Step 7: Run ERC (Electrical Rules Check)**

In KiCad's schematic editor: **Inspect → Electrical Rules Checker → Run ERC**

Expected: 0 errors. Warnings about unconnected Feather pins (A2–A5, SCK, MOSI, etc.) are OK — those are unused. Add "No Connect" flags to unused pins to silence warnings if desired.

If ERC shows errors for missing connections, fix the wiring. Common issues:
- Wire doesn't quite touch a pin — extend it to snap to the pin endpoint
- Missing power flag — add a `PWR_FLAG` symbol to the GND or +3.3V net

- [ ] **Step 8: Save and commit**

```bash
git add hardware/
git commit -m "Wire gate controller schematic and pass ERC"
```

---

### Task 4: PCB layout — import, place, route (MANUAL — requires KiCad GUI)

**Files:**
- Modify: `hardware/gate-controller.kicad_pcb` (via KiCad GUI)

- [ ] **Step 1: Update PCB from schematic**

In KiCad's PCB editor: **Tools → Update PCB from Schematic**

This imports all new components as footprints. They'll appear as a cluster near the board — you need to place them.

- [ ] **Step 2: Place components on the PCB**

The board is 50.8 x 22.86mm. Headers run along the top and bottom edges. Available space is the interior rectangle between the pin rows, roughly 40mm x 12mm.

Placement guidelines (coordinates in mm from the board's top-left corner at 25.4, 25.4):

| Component | Suggested position | Notes |
|-----------|-------------------|-------|
| J3 (screw terminal) | Right edge, between mounting holes | Place at board edge for easy wire access. The 5.08mm terminal is ~10mm wide. |
| Q1 (TO-92) | Near J3, slightly left | Keep collector trace to J3 short |
| R1 (0805) | Between pin header (A0 pad) and Q1 | Route A0 → R1 → Q1 base |
| LED1 (0805) | Center of board, visible from top | Hardwired gate indicator |
| R2 (0805) | Between A0 pad and LED1 | |
| LED2 (WS2812B, 5050) | Center of board, near LED1 | RGB status — place for visibility |
| R3 (0805) | Between A1 pad and LED2 | |
| C1 (0805) | Adjacent to LED2 | Bypass cap — keep close to WS2812B |

Key constraints:
- J3 must be at a board edge (right or top) so wires can exit
- Q1 (TO-92) is the largest component at ~5mm wide — ensure it clears mounting holes
- Keep bypass cap C1 within 5mm of WS2812B
- All SMD parts on the top (F.Cu) side

- [ ] **Step 3: Route traces**

Trace widths:
- Signal traces (A0→R1, A1→R3, R1→Q1 base, etc.): **0.25mm** (default)
- Power traces (3.3V to WS2812B, GND): **0.4mm** minimum
- Q1 collector→J3: **0.5mm** (carries the dry-contact current)

Routing order (easiest first):
1. GND connections — consider a small GND copper pour in unused areas
2. +3.3V to WS2812B VDD and C1
3. A0 → R1 → Q1 base
4. Q1 collector → J3 pin 1
5. Q1 emitter → GND, J3 pin 2 → GND
6. A0 → R2 → LED1 → GND
7. A1 → R3 → WS2812B DIN

All traces can be routed on the front copper layer (F.Cu). Use the back layer (B.Cu) only if you need to cross traces.

- [ ] **Step 4: Add silkscreen labels**

Add text labels on F.SilkS:
- "GATE" near J3
- "+" and "-" near J3 pins (or "GATE" and "GND")
- "LED" near LED1
- Board name: "Gate Controller Wing v1.0"

- [ ] **Step 5: Run DRC (Design Rules Check)**

**Inspect → Design Rules Checker → Run DRC**

Expected: 0 errors, 0 unconnected nets. Fix any violations (usually clearance issues — move components apart slightly).

- [ ] **Step 6: Save and commit**

```bash
git add hardware/
git commit -m "Place and route gate controller PCB"
```

---

### Task 5: Update README and final commit

**Files:**
- Modify: `README`

- [ ] **Step 1: Update README with hardware section**

Replace the contents of the `README` file with:

```
# Gate Controller

Alexa-enabled driveway gate controller with custom FeatherWing PCB.

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
```

- [ ] **Step 2: Rename README to README.md**

```bash
cd ~/depot/github.com/nstielau/gate_controller
git mv README README.md
```

- [ ] **Step 3: Commit and push**

```bash
git add README.md
git commit -m "Update README with hardware docs and BOM"
git push
```
