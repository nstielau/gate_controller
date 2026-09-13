"""Generate the revision-stamped review design with KiCad 10's bundled Python.

Source of truth for this revision is this script; generated files remain editable
in KiCad. Do not regenerate after manual edits without incorporating them here.
"""

import csv
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import uuid
import xml.etree.ElementTree as ET

import pcbnew as pcb
import wx

HERE = Path(__file__).resolve().parent
SUPPORT = Path(
    os.environ.get("KICAD_SUPPORT", "/Applications/KiCad/KiCad.app/Contents/SharedSupport")
)
NAME = "drawbridge-featherwing"
ROOT_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, NAME))
REVISION = os.environ.get("DRAWBRIDGE_REV", "dev.0")
if not re.fullmatch(r"[0-9a-z]{3}\.\d+", REVISION):
    raise RuntimeError(f"Invalid DRAWBRIDGE_REV: {REVISION!r}")


def uid(name):
    return str(uuid.uuid5(uuid.UUID(ROOT_ID), name))


def expr(text):
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', text)
    stack = []
    for token in tokens:
        if token == "(":
            stack.append([])
        elif token == ")":
            item = stack.pop()
            if not stack:
                return item
            stack[-1].append(item)
        else:
            stack[-1].append(token)
    raise ValueError("Unbalanced s-expression")


def dump(node):
    return "(" + " ".join(dump(x) if isinstance(x, list) else x for x in node) + ")"


def sub(node, name):
    return [x for x in node if isinstance(x, list) and x[0] == name]


def field(node, name):
    return sub(node, name)[0]


def quoted(s):
    # KiCad strings must escape newlines and quotes, including multiline notes.
    # Literal newlines inside a quoted note cause "Unterminated delimited string".
    return json.dumps(s)


def symbol(lib, name):
    source = expr((SUPPORT / "symbols" / (lib + ".kicad_sym")).read_text())
    item = next(s for s in sub(source, "symbol") if s[1] == quoted(name))
    if sub(item, "extends"):
        raise ValueError("Use a fully defined symbol")
    item[1] = quoted(lib + ":" + name)
    return item


def connector_symbol(name, names):
    # Names refer to FeatherS3[D] GPIOs, not generic Feather D-number aliases.
    size = len(names)
    pins = "".join(
        f"(pin passive line (at -7.62 {-i * 2.54:.2f} 0) (length 2.54) "
        f"(name {quoted(label)} (effects (font (size 1 1)))) "
        f'(number "{i + 1}" (effects (font (size 1 1)))))'
        for i, label in enumerate(names)
    )
    return expr(f'''(symbol "Drawbridge:{name}" (pin_names (offset 1.016))
      (in_bom yes) (on_board yes)
      (property "Reference" "J" (at 0 4 0) (effects (font (size 1.27 1.27))))
      (property "Value" "{name}" (at 0 2 0) (effects (font (size 1.27 1.27))))
      (symbol "{name}_0_1" (rectangle (start -5.08 1.27) (end 10.16 {-size * 2.54 + 1.27})
        (stroke (width 0.254) (type default)) (fill (type background))))
      (symbol "{name}_1_1" {pins}))''')


R_FP = "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal"
LED_FP = "LED_THT:LED_D3.0mm"
BOARD_CENTER_Y = 22.86 / 2
TRANSISTOR_STACK_SPACING = 4.75
INDICATOR_STACK_SPACING = (16.5 - (5.5 + 3.81)) / 2
INDICATOR_RESISTOR_Y = BOARD_CENTER_Y - INDICATOR_STACK_SPACING - 3.81
INDICATOR_LED_Y = BOARD_CENTER_Y + INDICATOR_STACK_SPACING
# Center the castle between the board's left edge and R1's left pad edge.
R1_LEFT_EDGE_X = 21.59 - 0.8
CASTLE_CENTER_X = R1_LEFT_EDGE_X / 2
CASTLE_SOURCE_CENTER_X = (11 + 130) / 2
CASTLE_X = CASTLE_CENTER_X - CASTLE_SOURCE_CENTER_X * 0.1
PARTS = [
    # ref, value, library symbol, footprint, pad nets, schematic position, pcb x/y/angle
    (
        "J1",
        "Feather 16",
        "Drawbridge:Feather16",
        "Drawbridge:FeatherHeader16",
        {"4": "GND"},
        (45, 55),
        (6.35, 21.59, 90),
    ),
    (
        "J2",
        "Feather 12",
        "Drawbridge:Feather12",
        "Drawbridge:FeatherHeader12",
        {"6": "CTRL_D11", "8": "HOLD_D9", "9": "MQTT_D6", "10": "WIFI_D5"},
        (95, 55),
        (16.51, 1.27, 90),
    ),
    # The 7.62 mm resistor bodies share the board's 25.4 mm horizontal
    # centerline. Their pad-1 origins are therefore 3.81 mm left of center.
    (
        "R1",
        "1k",
        "Device:R",
        R_FP,
        {"1": "CTRL_D11", "2": "BASE"},
        (135, 50),
        (21.59, BOARD_CENTER_Y - TRANSISTOR_STACK_SPACING, 0),
    ),
    (
        "R2",
        "100k",
        "Device:R",
        R_FP,
        {"1": "BASE", "2": "GND"},
        (135, 80),
        (21.59, BOARD_CENTER_Y + TRANSISTOR_STACK_SPACING, 0),
    ),
    (
        "Q1",
        "2N3904",
        "Transistor_BJT:Q_NPN_EBC",
        "Package_TO_SOT_THT:TO-92_Inline",
        {"1": "GND", "2": "BASE", "3": "OUT_OC"},
        (170, 58),
        # The TO-92 origin is its left pad; subtract its 1.27 mm body-center
        # offset so the body is centered between the two resistors.
        (24.13, BOARD_CENTER_Y, 0),
    ),
    # Keep the exit pins in a vertical row at the far end of the wing, clear
    # of the Feather USB connector. Pin 1 is the upper square pad (OUT_OC);
    # pin 2 directly below it is GND.
    (
        "J3",
        "OUT / GND",
        "Connector_Generic:Conn_01x02",
        "Drawbridge:GateOutputPads",
        {"1": "OUT_OC", "2": "GND"},
        (220, 58),
        (48, 8, 0),
    ),
]
for i, (role, signal, x) in enumerate(
    [("WIFI", "WIFI_D5", 32), ("MQTT", "MQTT_D6", 38), ("HOLD", "HOLD_D9", 43)]
):
    PARTS.extend(
        [
            (
                f"R{i + 3}",
                "1k",
                "Device:R",
                "Drawbridge:GateHoldResistor" if role == "HOLD" else R_FP,
                {"1": signal, "2": role + "_A"},
                (120 + i * 45, 120),
                # The axial body's centre is 1.27 mm right of pad 1 after
                # its -90° rotation. Offset pad 1 by 1.27 mm so the body is
                # centered directly above the LED below it.
                (x + 1.27, INDICATOR_RESISTOR_Y, -90),
            ),
            (
                f"D{i + 1}",
                role,
                "Device:LED",
                LED_FP,
                {"1": "GND", "2": role + "_A"},
                (120 + i * 45, 140),
                (x, INDICATOR_LED_Y, 0),
            ),
        ]
    )


def schematic():
    libs = {
        lib: symbol(*lib.split(":"))
        for lib in {p[2] for p in PARTS}
        if not lib.startswith("Drawbridge:")
    }
    libs["Drawbridge:Feather16"] = connector_symbol(
        "Feather16",
        [
            "RST",
            "3V3",
            "IO0_BOOT",
            "GND",
            "IO17",
            "IO18",
            "IO14",
            "IO12",
            "IO6",
            "IO5",
            "SCK_IO36",
            "MOSI_IO35",
            "MISO_IO37",
            "RX_IO44",
            "TX_IO43",
            "LDO2_OUT",
        ],
    )
    libs["Drawbridge:Feather12"] = connector_symbol(
        "Feather12",
        [
            "VBAT",
            "EN",
            "VBUS",
            "IO11_D13",
            "IO10_D12",
            "IO7_D11",
            "IO3_D10_BOOT",
            "IO1_D9",
            "IO38_D6",
            "IO33_D5",
            "SCL_IO9",
            "SDA_IO8",
        ],
    )
    out = [
        f'(kicad_sch (version 20250114) (generator "eeschema") (uuid {ROOT_ID}) (paper "A4")',
        f'(title_block (title "Drawbridge FeatherWing - FeatherS3[D]") (rev "{REVISION}") (comment 1 "USB-powered host; no Feather module in assembly BOM") (comment 2 "Prototype open-collector output; gate interface not released"))',
        "(lib_symbols " + "\n".join(dump(s) for s in libs.values()) + ")",
    ]
    for ref, value, lib, footprint, nets, (x, y), _ in PARTS:
        x, y = round(round(x / 1.27) * 1.27, 2), round(round(y / 1.27) * 1.27, 2)
        out.append(
            f'(symbol (lib_id "{lib}") (at {x} {y} 0) (unit 1) (in_bom yes) (on_board yes) (dnp no) (uuid {uid(ref)})'
        )
        for label, val, dy, hidden in [
            ("Reference", ref, -8, False),
            ("Value", value, -5.5, False),
            ("Footprint", footprint, 0, True),
        ]:
            out.append(
                f'(property "{label}" {quoted(val)} (at {x + 7} {y + dy} 0) (effects (font (size 1.27 1.27)) {"hide" if hidden else ""}))'
            )
        out.append(
            f'(instances (project "{NAME}" (path "/{ROOT_ID}" (reference "{ref}") (unit 1)))))'
        )
        for unit in sub(libs[lib], "symbol"):
            for pin in sub(unit, "pin"):
                number = json.loads(field(pin, "number")[1])
                at = field(pin, "at")
                px, py, angle = float(at[1]) + x, y - float(at[2]), float(at[3])
                if number not in nets:
                    out.append(f"(no_connect (at {px} {py}) (uuid {uid(ref + number + 'nc')}))")
                    continue
                # Short wire extends outward, away from the symbol pin body.
                ex = round(px - 5.08 * math.cos(math.radians(angle)), 4)
                ey = round(py + 5.08 * math.sin(math.radians(angle)), 4)
                out.append(
                    f"(wire (pts (xy {px} {py}) (xy {ex} {ey})) (stroke (width 0) (type default)) (uuid {uid(ref + number + 'wire')}))"
                )
                out.append(
                    f'(label "{nets[number]}" (at {ex} {ey} 0) (effects (font (size 1 1)) (justify left bottom)) (uuid {uid(ref + number + "label")}))'
                )
    notes = "Feather D5: Wi-Fi   D6: MQTT   D9: Hold\nFeather D11: transistor control\nQ1: onsemi 2N3904, pads 1=E, 2=B, 3=C\nJ3: open collector and common GND; NOT an isolated contact\nNo connection to VBUS, VBAT, EN, LDO2, USB or strapping pins."
    headings = [
        ("FEATHERS3[D] HEADER", 35, 43),
        ("OPEN-COLLECTOR OUTPUT", 145, 43),
        ("STATUS INDICATORS (ACTIVE HIGH)", 105, 108),
    ]
    for label, x, y in headings:
        out.append(
            f"(text {quoted(label)} (at {x} {y} 0) (effects (font (size 1.1 1.1)) (justify left)) (uuid {uid('heading-' + label)}))"
        )
    out.append(
        f"(text {quoted(notes)} (at 45 145 0) (effects (font (size 0.9 0.9)) (justify left)) (uuid {uid('notes')}))"
    )
    out.append("(embedded_fonts no))")
    (HERE / (NAME + ".kicad_sch")).write_text("\n".join(out) + "\n")
    (HERE / "Drawbridge.kicad_sym").write_text(
        '(kicad_symbol_lib (version 20250114) (generator "kicad_symbol_editor") '
        + "\n".join(
            dump(s).replace('"Drawbridge:', '"', 1)
            for k, s in libs.items()
            if k.startswith("Drawbridge:")
        )
        + ")\n"
    )
    (HERE / "sym-lib-table").write_text(
        '(sym_lib_table (lib (name "Drawbridge") (type "KiCad") (uri "${KIPRJMOD}/Drawbridge.kicad_sym") (options "") (descr "FeatherS3D header mapping")))\n'
    )


def board(netlist):
    app = wx.App(False)  # KiCad path resolution requires wx initialization.
    b = pcb.BOARD()
    local_library = HERE / "Drawbridge.pretty"
    local_library.mkdir(exist_ok=True)
    for count in (12, 16):
        fp = expr(
            (
                SUPPORT
                / "footprints/Connector_PinHeader_2.54mm.pretty"
                / f"PinHeader_1x{count}_P2.54mm_Vertical.kicad_mod"
            ).read_text()
        )
        fp[1] = quoted(f"FeatherHeader{count}")
        # These stacking headers are installed on the underside of the wing.
        field(fp, "layer")[1] = '"B.Cu"'
        for graphic in list(fp):
            if not isinstance(graphic, list) or not graphic[0].startswith("fp_"):
                continue
            if sub(graphic, "layer") and field(graphic, "layer")[1] == '"F.SilkS"':
                fp.remove(graphic)
            elif sub(graphic, "layer") and field(graphic, "layer")[1] == '"F.CrtYd"':
                field(graphic, "start")[1:] = ["-1.52", "-1.52"]
                field(graphic, "end")[1:] = ["1.52", str((count - 1) * 2.54 + 1.52)]
        (local_library / f"FeatherHeader{count}.kicad_mod").write_text(dump(fp) + "\n")
    # J3 is intentionally only two large plated-through solder pads. No
    # connector is populated; the field wires are hand-soldered to OUT/GND.
    output_fp = expr(
        '(footprint "GateOutputPads" (version 20260206) (generator "drawbridge") '
        '(layer "F.Cu") (attr through_hole) '
        '(pad "1" thru_hole rect (at 0 0) (size 2.2 2.2) (drill 1.2) (layers "*.Cu" "*.Mask")) '
        '(pad "2" thru_hole circle (at 0 2.54) (size 2.2 2.2) (drill 1.2) (layers "*.Cu" "*.Mask")))'
    )
    (local_library / "GateOutputPads.kicad_mod").write_text(dump(output_fp) + "\n")
    hold_fp = expr(
        (
            SUPPORT
            / "footprints/Resistor_THT.pretty/R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal.kicad_mod"
        ).read_text()
    )
    hold_fp[1] = '"GateHoldResistor"'
    for graphic in list(hold_fp):
        if isinstance(graphic, list) and graphic[0].startswith("fp_") and sub(graphic, "layer"):
            if field(graphic, "layer")[1] == '"F.CrtYd"':
                hold_fp.remove(graphic)
            elif graphic[0] == "fp_line" and field(graphic, "layer")[1] == '"F.SilkS"':
                # Preserve R5's normal body outline. Only its right-hand edge
                # crosses J3 pad 1; leave a mask/clearance gap at that pad.
                # Local x maps to PCB y = 6.5 + x at R5's -90 degree rotation.
                if field(graphic, "start")[1:] == ["0.54", "-1.37"] and field(graphic, "end")[
                    1:
                ] == ["7.08", "-1.37"]:
                    lower = expr(dump(graphic))
                    field(graphic, "end")[1:] = ["2.2", "-1.37"]
                    field(lower, "start")[1:] = ["4.8", "-1.37"]
                    hold_fp.append(lower)
    (local_library / "GateHoldResistor.kicad_mod").write_text(dump(hold_fp) + "\n")
    mount = expr(
        (SUPPORT / "footprints/MountingHole.pretty/MountingHole_2.5mm.kicad_mod").read_text()
    )
    mount[1] = '"FeatherMount"'
    for graphic in sub(mount, "fp_circle"):
        if field(graphic, "layer")[1] == '"F.CrtYd"':
            field(graphic, "end")[1:] = ["2.25", "0"]
    for p in sub(mount, "pad"):
        field(p, "drill")[1:] = ["2.54"]
        field(p, "size")[1:] = ["2.54", "2.54"]
    (local_library / "FeatherMount.kicad_mod").write_text(dump(mount) + "\n")
    (HERE / "fp-lib-table").write_text(
        '(fp_lib_table (lib (name "Drawbridge") (type "KiCad") (uri "${KIPRJMOD}/Drawbridge.pretty") (options "") (descr "Feather outline header and mounting adaptations")))\n'
    )
    b.GetDesignSettings().SetBoardThickness(pcb.FromMM(1.6))
    nets = {}
    xml = ET.parse(netlist)
    pad_nets = {}
    for item in xml.findall("nets/net"):
        name = item.attrib["name"]
        net = pcb.NETINFO_ITEM(b, name)
        b.Add(net)
        nets[name.removeprefix("/")] = net
        for node in item.findall("node"):
            pad_nets[node.attrib["ref"] + "." + node.attrib["pin"]] = net

    def pos(x, y):
        return pcb.VECTOR2I(pcb.FromMM(x + 50), pcb.FromMM(y + 50))

    def text(label, x, y, size=0.85, layer=pcb.F_SilkS, angle=0):
        t = pcb.PCB_TEXT(b)
        t.SetText(label)
        t.SetPosition(pos(x, y))
        t.SetTextAngle(pcb.EDA_ANGLE(angle, pcb.DEGREES_T))
        size = max(size, 0.8)
        t.SetTextSize(pcb.VECTOR2I(pcb.FromMM(size), pcb.FromMM(size)))
        t.SetTextThickness(pcb.FromMM(0.15))
        t.SetLayer(layer)
        if layer == pcb.B_SilkS:
            t.SetMirrored(True)
        b.Add(t)

    def line(a, z, layer=pcb.Edge_Cuts):
        shape = pcb.PCB_SHAPE(b)
        shape.SetShape(pcb.SHAPE_T_SEGMENT)
        shape.SetStart(pos(*a))
        shape.SetEnd(pos(*z))
        shape.SetLayer(layer)
        shape.SetWidth(pcb.FromMM(0.1))
        b.Add(shape)
        return shape

    # One vector source for the actual Gerber mark and its SVG/PNG previews.
    # 14 mm canvas, 0.18 mm strokes, in the open area at the USB end.
    logo = ET.parse(HERE / "assets/drawbridge-silkscreen.svg")
    for path in logo.findall(".//{http://www.w3.org/2000/svg}polyline"):
        points = [tuple(float(v) for v in p.split(",")) for p in path.attrib["points"].split()]
        for a, z in zip(points, points[1:]):
            shape = line(
                (CASTLE_X + a[0] * 0.1, 4 + a[1] * 0.1),
                (CASTLE_X + z[0] * 0.1, 4 + z[1] * 0.1),
                pcb.F_SilkS,
            )
            shape.SetWidth(pcb.FromMM(0.18))
    # Standard 50.8 x 22.86 outline with 2.54 mm corner radii.
    for a, z in [
        ((2.54, 0), (48.26, 0)),
        ((50.8, 2.54), (50.8, 20.32)),
        ((48.26, 22.86), (2.54, 22.86)),
        ((0, 20.32), (0, 2.54)),
    ]:
        line(a, z)
    for cx, cy, angles in [
        (2.54, 2.54, (180, 225, 270)),
        (48.26, 2.54, (270, 315, 360)),
        (48.26, 20.32, (0, 45, 90)),
        (2.54, 20.32, (90, 135, 180)),
    ]:
        points = [
            pos(cx + 2.54 * math.cos(math.radians(a)), cy + 2.54 * math.sin(math.radians(a)))
            for a in angles
        ]
        shape = pcb.PCB_SHAPE(b)
        shape.SetShape(pcb.SHAPE_T_ARC)
        shape.SetArcGeometry(*points)
        shape.SetLayer(pcb.Edge_Cuts)
        shape.SetWidth(pcb.FromMM(0.1))
        b.Add(shape)
    for i, (x, y) in enumerate([(2.54, 2.54), (48.26, 2.54), (2.54, 20.32), (48.26, 20.32)]):
        fp = pcb.FootprintLoad(str(local_library), "FeatherMount")
        fp.SetReference(f"H{i + 1}")
        fp.Reference().SetVisible(False)
        fp.Value().SetVisible(False)
        fp.SetFPID(pcb.LIB_ID("Drawbridge", "FeatherMount"))
        fp.SetAttributes(fp.GetAttributes() | pcb.FP_BOARD_ONLY)
        fp.SetPosition(pos(x, y))
        b.Add(fp)
    pads = {}
    for ref, value, lib, footprint, connections, _, (x, y, angle) in PARTS:
        libname, fpname = footprint.split(":")
        library = (
            local_library
            if libname == "Drawbridge"
            else SUPPORT / "footprints" / (libname + ".pretty")
        )
        fp = pcb.FootprintLoad(str(library), fpname)
        fp.SetReference(ref)
        fp.SetValue(value)
        fp.SetFPID(pcb.LIB_ID(libname, fpname))
        path = pcb.KIID_PATH()
        path.push_back(pcb.KIID(ROOT_ID))
        path.push_back(pcb.KIID(uid(ref)))
        fp.SetPath(path)
        fp.SetPosition(pos(x, y))
        fp.SetOrientationDegrees(angle)
        if ref == "J3":
            # Pads remain in the board design but must not be sent to an
            # assembly house as a connector component.
            fp.SetAttributes(fp.GetAttributes() | pcb.FP_BOARD_ONLY)
        if ref in ("J1", "J2"):
            # The FeatherWing mounts over the Feather, so its stacking
            # headers are assembled on the underside. Set only the side;
            # mirroring the footprint would reverse the Feather pin order.
            fp.SetLayer(pcb.B_Cu)
            for graphic in list(fp.GraphicalItems()):
                if graphic.GetLayer() == pcb.F_SilkS:
                    fp.Remove(graphic)
        fp.Value().SetVisible(False)
        fp.Reference().SetVisible(False)
        for p in fp.Pads():
            if ref + "." + p.GetNumber() in pad_nets:
                p.SetNet(pad_nets[ref + "." + p.GetNumber()])
            pads[ref + "." + p.GetNumber()] = p
        b.Add(fp)

    # Routes are explicit and reviewable. Coordinates are millimetres from top-left.
    def xy(key):
        p = pads[key].GetPosition()
        return (pcb.ToMM(p.x) - 50, pcb.ToMM(p.y) - 50)

    def track(net, points, layer=pcb.F_Cu, width=0.3):
        points = [xy(p) if isinstance(p, str) else p for p in points]
        for a, z in zip(points, points[1:]):
            t = pcb.PCB_TRACK(b)
            t.SetStart(pos(*a))
            t.SetEnd(pos(*z))
            t.SetLayer(layer)
            t.SetWidth(pcb.FromMM(width))
            t.SetNet(nets[net])
            b.Add(t)

    track("CTRL_D11", ["J2.6", (27.94, 2.54), (27.94, 3.3), (21.59, 3.3), "R1.1"])
    # Enter Q1's centre base pad from above and leave below; a horizontal
    # trace through this TO-92 footprint would cross its emitter/collector.
    track("BASE", ["R1.2", (25.4, BOARD_CENTER_Y - 2), "Q1.2"])
    track("BASE", ["Q1.2", (25.4, BOARD_CENTER_Y + 2), "R2.1"])
    track("OUT_OC", ["Q1.3", (26.67, 8.79), (35, 8.79), "J3.1"], pcb.B_Cu, 0.5)
    track(
        "GND",
        [
            "J3.2",
            (48, 11.5),
            (46, 11.5),
            (46, 9.5),
            (30, 9.5),
            (30, 13),
            (22, 13),
            (22, BOARD_CENTER_Y),
            "Q1.1",
        ],
        pcb.B_Cu,
        0.5,
    )
    track(
        "GND",
        ["Q1.1", (20, BOARD_CENTER_Y), (20, 18.3), (13.97, 19.33), "J1.4"],
        pcb.B_Cu,
        0.5,
    )
    track("GND", ["J1.4", (13.97, 19.4), (43, 19.4)], pcb.B_Cu, 0.5)
    track("GND", ["R2.2", (29.21, 19.4)], pcb.B_Cu, 0.5)
    for i, x in enumerate([32, 38, 43]):
        track("GND", [f"D{i + 1}.1", (x, 19.4)], pcb.B_Cu, 0.5)
        track(["WIFI_A", "MQTT_A", "HOLD_A"][i], [f"R{i + 3}.2", f"D{i + 1}.2"])
    track("WIFI_D5", ["J2.10", (40.8, 3.8)], pcb.B_Cu)
    via = pcb.PCB_VIA(b)
    via.SetPosition(pos(40.8, 3.8))
    via.SetWidth(pcb.FromMM(0.7))
    via.SetDrill(pcb.FromMM(0.3))
    via.SetLayerPair(pcb.F_Cu, pcb.B_Cu)
    via.SetNet(nets["WIFI_D5"])
    b.Add(via)
    track("WIFI_D5", [(40.8, 3.8), (40.8, 5.5), (34.5, 5.5), "R3.1"])
    track("MQTT_D6", ["J2.9", (36.83, 4.79), "R4.1"], pcb.B_Cu)
    track("HOLD_D9", ["J2.8", (34.29, 2.8), (44.54, 2.8), "R5.1"])
    # Frame the castle with the product name above and revision below while
    # staying clear of the mounting holes and Feather header pads.
    text("DRAWBRIDGE", CASTLE_CENTER_X + 0.75, 3.7, 0.9)
    text(f"rev {REVISION}", CASTLE_CENTER_X + 0.75, 19, 0.7)
    text("WIFI", 33.27, INDICATOR_LED_Y + 3.2, 0.7)
    text("MQTT", 39.27, INDICATOR_LED_Y + 3.2, 0.7)
    text("HOLD", 44.27, INDICATOR_LED_Y + 3.2, 0.7)
    # Transistor pin order is documented in the schematic note; keep the
    # crowded TO-92 body clear on the PCB silkscreen.
    text("R1 1k", 25.4, BOARD_CENTER_Y - TRANSISTOR_STACK_SPACING - 2.3, 0.7)
    text("R2 100k", 25.4, BOARD_CENTER_Y + TRANSISTOR_STACK_SPACING + 2.1, 0.7)
    text("R3", 33.27, BOARD_CENTER_Y - INDICATOR_STACK_SPACING + 0.19, 0.7)
    text("1k", 33.27, BOARD_CENTER_Y - INDICATOR_STACK_SPACING + 1.69, 0.7)
    text("R4", 39.27, BOARD_CENTER_Y - INDICATOR_STACK_SPACING + 0.19, 0.7)
    text("1k", 39.27, BOARD_CENTER_Y - INDICATOR_STACK_SPACING + 1.69, 0.7)
    text("R5", 44.27, BOARD_CENTER_Y - INDICATOR_STACK_SPACING + 0.19, 0.7)
    text("1k", 44.27, BOARD_CENTER_Y - INDICATOR_STACK_SPACING + 1.69, 0.7)
    # Keep the destination label vertical beside the matching output pads.
    text("(To EXIT)", 49.85, 9.27, 0.7, angle=90)
    text("PROTOTYPE", 32, 10, 0.85, pcb.B_SilkS)
    # No copper pour over the host antenna end (x >= 46 mm).
    # Pad/track positions are also checked by KiCad DRC and netlist parity.
    pcb.SaveBoard(str(HERE / (NAME + ".kicad_pcb")), b)
    del app


if __name__ == "__main__":
    schematic()
    with tempfile.TemporaryDirectory(prefix="drawbridge-netlist-") as temp:
        netlist = Path(temp) / "netlist.xml"
        subprocess.run(
            [
                str(SUPPORT.parent / "MacOS/kicad-cli"),
                "sch",
                "export",
                "netlist",
                "--format",
                "kicadxml",
                str(HERE / (NAME + ".kicad_sch")),
                "-o",
                str(netlist),
            ],
            check=True,
        )
        board(netlist)
    project = {
        "meta": {"filename": NAME + ".kicad_pro", "version": 1},
        "board": {
            "design_settings": {
                "rules": {
                    "min_clearance": 0.2,
                    "min_copper_edge_clearance": 0.3,
                    "min_track_width": 0.3,
                    "min_via_diameter": 0.6,
                    "min_via_annular_width": 0.15,
                    "min_through_hole_diameter": 0.3,
                    "min_hole_to_hole": 0.25,
                    "min_hole_clearance": 0.25,
                    "min_silk_clearance": 0.15,
                    "min_text_height": 0.8,
                    "min_text_thickness": 0.15,
                }
            }
        },
        "net_settings": {
            "classes": [
                {
                    "name": "Default",
                    "clearance": 0.2,
                    "track_width": 0.3,
                    "via_diameter": 0.7,
                    "via_drill": 0.3,
                }
            ],
            "meta": {"version": 3},
        },
    }
    (HERE / (NAME + ".kicad_pro")).write_text(json.dumps(project, indent=2) + "\n")
    bom_parts = {
        "J1": ("Feather-compatible 1x16 header", "Harwin", "M20-9991646"),
        "J2": ("Feather-compatible 1x12 header", "Harwin", "M20-9991246"),
        "Q1": ("NPN transistor, TO-92, EBC", "onsemi", "2N3904BU"),
        "R1": ("1 kOhm 1% axial resistor, 0.25 W", "Yageo", "CFR-25JB-52-1K"),
        "R2": ("100 kOhm 1% axial resistor, 0.25 W", "Yageo", "CFR-25JB-52-100K"),
        "R3": ("1 kOhm 1% axial resistor, 0.25 W", "Yageo", "CFR-25JB-52-1K"),
        "R4": ("1 kOhm 1% axial resistor, 0.25 W", "Yageo", "CFR-25JB-52-1K"),
        "R5": ("1 kOhm 1% axial resistor, 0.25 W", "Yageo", "CFR-25JB-52-1K"),
        "D1": ("3 mm cool-white LED, THT", "Kingbright", "WP7104QWC/D"),
        "D2": ("3 mm blue LED, THT", "Kingbright", "L-7104QBC-D"),
        "D3": ("3 mm green LED, THT", "Lite-On", "L-7104LGD"),
    }
    with (HERE / "bom.csv").open("w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(
            [
                "Reference",
                "Value",
                "Description",
                "Manufacturer",
                "Manufacturer Part Number",
                "Footprint",
                "Quantity",
                "Populate",
            ]
        )
        for ref, value, _, fp, *rest in PARTS:
            if ref == "J3":
                continue
            desc, manufacturer, mpn = bom_parts[ref]
            w.writerow([ref, value, desc, manufacturer, mpn, fp, 1, "Yes"])
    print("Generated review schematic, PCB and BOM")
