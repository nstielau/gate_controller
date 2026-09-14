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


def route_45(points, bevel=0.4):
    """Octilinear segments with 45-degree chamfers at right-angle bends."""
    path = [points[0]]
    for end in points[1:]:
        start = path[-1]
        dx, dy = end[0] - start[0], end[1] - start[1]
        if abs(dx) > 1e-6 and abs(dy) > 1e-6 and abs(abs(dx) - abs(dy)) > 1e-6:
            if abs(dx) > abs(dy):
                path.append((end[0] - math.copysign(abs(dy), dx), start[1]))
            else:
                path.append((start[0], end[1] - math.copysign(abs(dx), dy)))
        if math.dist(path[-1], end) > 1e-6:
            path.append(end)
    result = [path[0]]
    for a, corner, z in zip(path, path[1:], path[2:]):
        u = (corner[0] - a[0], corner[1] - a[1])
        v = (z[0] - corner[0], z[1] - corner[1])
        la, lz = math.hypot(*u), math.hypot(*v)
        cosine = (u[0] * v[0] + u[1] * v[1]) / (la * lz)
        if cosine < -1e-5:
            raise ValueError(f"Route doubles back at {corner}: {points}")
        if abs(cosine) < 1e-5:
            trim = min(bevel, la / 3, lz / 3)
            result.extend(
                [
                    (corner[0] - trim * u[0] / la, corner[1] - trim * u[1] / la),
                    (corner[0] + trim * v[0] / lz, corner[1] + trim * v[1] / lz),
                ]
            )
        else:
            result.append(corner)
    result.append(path[-1])
    return result


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
TERMINAL_FP = "Drawbridge:ExitTerminal"
INDICATOR_X = (32.65, 37.55, 42.45)
BOARD_CENTER_Y = 22.86 / 2
TRANSISTOR_STACK_SPACING = 4.75
INDICATOR_STACK_SPACING = (16.5 - (5.5 + 3.81)) / 2
INDICATOR_RESISTOR_Y = BOARD_CENTER_Y - INDICATOR_STACK_SPACING - 3.81
INDICATOR_LED_Y = BOARD_CENTER_Y + INDICATOR_STACK_SPACING
# Center the castle between the board's left edge and R1's left pad edge.
R1_LEFT_EDGE_X = 21.44 - 0.8
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
    # Keep the transistor/resistor stack aligned, 0.15 mm left of board
    # centre to clear the Wi-Fi LED assembly courtyard. Their pad-1 origins are therefore 3.81 mm left of center.
    (
        "R1",
        "1k",
        "Device:R",
        R_FP,
        {"1": "CTRL_D11", "2": "BASE"},
        (135, 50),
        (21.44, BOARD_CENTER_Y - TRANSISTOR_STACK_SPACING, 0),
    ),
    (
        "R2",
        "100k",
        "Device:R",
        R_FP,
        {"1": "BASE", "2": "GND"},
        (135, 80),
        (21.44, BOARD_CENTER_Y + TRANSISTOR_STACK_SPACING, 0),
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
        (23.98, BOARD_CENTER_Y, 0),
    ),
    # Top-side terminal: wire entry faces the right edge, away from USB.
    # A +90 degree rotation puts pin 2 (GND) above pin 1 (OUT_OC).
    (
        "J3",
        "OUT / GND",
        "Connector_Generic:Conn_01x02",
        TERMINAL_FP,
        {"1": "OUT_OC", "2": "GND"},
        (220, 58),
        (47.4, 10.5, 90),
    ),
]
for i, (role, signal, x) in enumerate(
    [
        ("WIFI", "WIFI_D5", INDICATOR_X[0] - 1.27),
        ("MQTT", "MQTT_D6", INDICATOR_X[1] - 1.27),
        ("HOLD", "HOLD_D9", INDICATOR_X[2] - 1.27),
    ]
):
    PARTS.extend(
        [
            (
                f"R{i + 3}",
                "1k",
                "Device:R",
                R_FP,
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
        # Bottom-side model orientation differs from our intentionally
        # unmirrored pad coordinates. Align the rendering with those pads.
        for model in sub(fp, "model"):
            field(field(model, "rotate"), "xyz")[3] = "180"
        for graphic in list(fp):
            if not isinstance(graphic, list) or not graphic[0].startswith("fp_"):
                continue
            if sub(graphic, "layer") and field(graphic, "layer")[1] == '"F.SilkS"':
                fp.remove(graphic)
            elif sub(graphic, "layer") and field(graphic, "layer")[1] == '"F.CrtYd"':
                field(graphic, "start")[1:] = ["-1.52", "-1.52"]
                field(graphic, "end")[1:] = ["1.52", str((count - 1) * 2.54 + 1.52)]
        (local_library / f"FeatherHeader{count}.kicad_mod").write_text(dump(fp) + "\n")
    # The stock Phoenix footprint includes the two 1.1 mm locating holes.
    # Use 0.25 mm body-to-courtyard margin, and omit the wire-entry-side silk
    # where the housing sits close to the board edge. Copper/drills stay stock.
    terminal = expr(
        (
            SUPPORT
            / "footprints/TerminalBlock_Phoenix.pretty/TerminalBlock_Phoenix_MPT-0,5-2-2.54_1x02_P2.54mm_Horizontal.kicad_mod"
        ).read_text()
    )
    terminal[1] = quoted("ExitTerminal")
    for graphic in list(terminal):
        if (
            not isinstance(graphic, list)
            or not graphic[0].startswith("fp_")
            or not sub(graphic, "layer")
        ):
            continue
        if field(graphic, "layer")[1] == '"F.SilkS"':
            terminal.remove(graphic)
        elif field(graphic, "layer")[1] == '"F.CrtYd"':
            field(graphic, "start")[1:] = ["-1.75", "-3.35"]
            field(graphic, "end")[1:] = ["4.29", "3.35"]
    for a, z in [
        ((-1.62, 2.1), (-1.62, -3.22)),
        ((-1.62, -3.22), (4.16, -3.22)),
        ((4.16, -3.22), (4.16, 2.1)),
    ]:
        terminal.append(
            expr(
                f'(fp_line (start {a[0]} {a[1]}) (end {z[0]} {z[1]}) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))'
            )
        )
    (local_library / "ExitTerminal.kicad_mod").write_text(dump(terminal) + "\n")
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
        points = route_45(points)
        for a, z in zip(points, points[1:]):
            dx, dy = abs(z[0] - a[0]), abs(z[1] - a[1])
            if min(dx, dy) > 1e-6 and abs(dx - dy) > 1e-6:
                raise ValueError(f"Non-45-degree track on {net}: {a} -> {z}")
            t = pcb.PCB_TRACK(b)
            t.SetStart(pos(*a))
            t.SetEnd(pos(*z))
            t.SetLayer(layer)
            t.SetWidth(pcb.FromMM(width))
            t.SetNet(nets[net])
            b.Add(t)

    track("CTRL_D11", ["J2.6", (29.06, 3.3), (21.44, 3.3), "R1.1"])
    track("BASE", ["R1.2", (25.25, 10.49), "Q1.2"])
    track("BASE", ["Q1.2", (25.25, 12.37), "R2.1"])
    track("OUT_OC", ["Q1.3", (26.52, 8.4), (44.2, 8.4)], pcb.B_Cu, 0.5)
    output_via = pcb.PCB_VIA(b)
    output_via.SetPosition(pos(44.2, 8.4))
    output_via.SetWidth(pcb.FromMM(0.8))
    output_via.SetDrill(pcb.FromMM(0.4))
    output_via.SetLayerPair(pcb.F_Cu, pcb.B_Cu)
    output_via.SetNet(nets["OUT_OC"])
    b.Add(output_via)
    track("OUT_OC", [(44.2, 8.4), (44.2, 9.2), (45.5, 10.5), "J3.1"], pcb.F_Cu, 0.5)
    track(
        "GND",
        [
            "J3.2",
            (46, 7.96),
            (46, 9.5),
            (30, 9.5),
            (30, 13.5),
            (22, 13.5),
            (22, BOARD_CENTER_Y),
            "Q1.1",
        ],
        pcb.B_Cu,
        0.5,
    )
    track(
        "GND",
        ["Q1.1", (20, BOARD_CENTER_Y), (20, 18.4), (19, 19.4), (13.97, 19.4), "J1.4"],
        pcb.B_Cu,
        0.5,
    )
    track("GND", ["J1.4", (13.97, 19.4), (INDICATOR_X[-1] - 1.27, 19.4)], pcb.B_Cu, 0.5)
    track("GND", ["R2.2", (29.06, 19.4)], pcb.B_Cu, 0.5)
    for i, center in enumerate(INDICATOR_X):
        track("GND", [f"D{i + 1}.1", (center - 1.27, 19.4)], pcb.B_Cu, 0.5)
        track(["WIFI_A", "MQTT_A", "HOLD_A"][i], [f"R{i + 3}.2", f"D{i + 1}.2"])
    track("WIFI_D5", ["J2.10", (40.0, 4.0)], pcb.B_Cu)
    via = pcb.PCB_VIA(b)
    via.SetPosition(pos(40.0, 4.0))
    via.SetWidth(pcb.FromMM(0.7))
    via.SetDrill(pcb.FromMM(0.3))
    via.SetLayerPair(pcb.F_Cu, pcb.B_Cu)
    via.SetNet(nets["WIFI_D5"])
    b.Add(via)
    track("WIFI_D5", [(40.0, 4.0), (40, 6.0), (32.65, 6.0), "R3.1"])
    track("MQTT_D6", ["J2.9", (37.55, 3.05), "R4.1"], pcb.B_Cu)
    track("HOLD_D9", ["J2.8", (34.29, 2.8), (42.45, 2.8), "R5.1"])
    # Frame the castle with the product name above and revision below while
    # staying clear of the mounting holes and Feather header pads.
    text("DRAWBRIDGE", CASTLE_CENTER_X + 0.75, 3.7, 0.9)
    text(f"rev {REVISION}", CASTLE_CENTER_X + 0.75, 19, 0.7)
    text("WIFI", INDICATOR_X[0], INDICATOR_LED_Y + 3.2, 0.7)
    text("MQTT", INDICATOR_X[1], INDICATOR_LED_Y + 3.2, 0.7)
    text("HOLD", INDICATOR_X[2], INDICATOR_LED_Y + 3.2, 0.7)
    # Transistor pin order is documented in the schematic note; keep the
    # crowded TO-92 body clear on the PCB silkscreen.
    text("R1 1k", 25.25, BOARD_CENTER_Y - TRANSISTOR_STACK_SPACING - 2.3, 0.7)
    text("R2 100k", 25.25, BOARD_CENTER_Y + TRANSISTOR_STACK_SPACING + 2.1, 0.7)
    text("R3", INDICATOR_X[0], BOARD_CENTER_Y - INDICATOR_STACK_SPACING + 0.19, 0.7)
    text("1k", INDICATOR_X[0], BOARD_CENTER_Y - INDICATOR_STACK_SPACING + 1.69, 0.7)
    text("R4", INDICATOR_X[1], BOARD_CENTER_Y - INDICATOR_STACK_SPACING + 0.19, 0.7)
    text("1k", INDICATOR_X[1], BOARD_CENTER_Y - INDICATOR_STACK_SPACING + 1.69, 0.7)
    text("R5", INDICATOR_X[2], BOARD_CENTER_Y - INDICATOR_STACK_SPACING + 0.19, 0.7)
    text("1k", INDICATOR_X[2], BOARD_CENTER_Y - INDICATOR_STACK_SPACING + 1.69, 0.7)
    # Keep the destination label vertical beside the matching output pads.
    text("(To EXIT)", 49.2, 15.5, 0.7, angle=90)
    text("GND", 46.7, 5.6, 0.6)
    text("OUT", 46.4, 13.0, 0.6)
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
        "J1": (
            "Feather-compatible 1x16 male header, 2.54 mm, 3/6 mm pins",
            "XKB",
            "X6511WV-16H-C30D60",
        ),
        "J2": (
            "Feather-compatible 1x12 male header, 2.54 mm, 3/6 mm pins",
            "XKB",
            "X6511WV-12H-C30D60",
        ),
        "J3": ("2-position screw terminal, 2.54 mm, side wire entry", "Phoenix Contact", "1725656"),
        "Q1": ("NPN transistor, TO-92, EBC", "onsemi", "2N3904BU"),
        "R1": ("1 kOhm 5% axial resistor, 0.25 W", "Yageo", "CFR-25JB-52-1K"),
        "R2": ("100 kOhm 5% axial resistor, 0.5 W", "Yageo", "MFR50SJT-52-100K"),
        "R3": ("1 kOhm 5% axial resistor, 0.25 W", "Yageo", "CFR-25JB-52-1K"),
        "R4": ("1 kOhm 5% axial resistor, 0.25 W", "Yageo", "CFR-25JB-52-1K"),
        "R5": ("1 kOhm 5% axial resistor, 0.25 W", "Yageo", "CFR-25JB-52-1K"),
        "D1": ("3 mm cool-white LED, THT", "Everlight", "204-15UTC/S400-X9"),
        "D2": ("3 mm blue LED, THT", "Everlight", "204-10SUBC/S400-A4"),
        "D3": ("3 mm green LED, THT", "Everlight", "204-10SUGD/S400-A5"),
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
            desc, manufacturer, mpn = bom_parts[ref]
            w.writerow([ref, value, desc, manufacturer, mpn, fp, 1, "Yes"])
    print("Generated review schematic, PCB and BOM")
