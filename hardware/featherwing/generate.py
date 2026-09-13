"""Generate the revision-A review design with KiCad 10's bundled Python.

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
        {"6": "CTRL_IO7", "8": "HOLD_IO1", "9": "MQTT_IO38", "10": "WIFI_IO33"},
        (95, 55),
        (16.51, 1.27, 90),
    ),
    ("R1", "1k", "Device:R", R_FP, {"1": "CTRL_IO7", "2": "BASE"}, (135, 50), (18, 5, 0)),
    ("R2", "100k", "Device:R", R_FP, {"1": "BASE", "2": "GND"}, (135, 80), (18, 15, 0)),
    (
        "Q1",
        "2N3904",
        "Transistor_BJT:Q_NPN_EBC",
        "Package_TO_SOT_THT:TO-92_Inline",
        {"1": "GND", "2": "BASE", "3": "OUT_OC"},
        (170, 58),
        (18, 10, 0),
    ),
    # Keep the exit pins in a vertical row at the far end of the wing, clear
    # of the Feather USB connector. Pin 1 is the upper square pad (OUT_OC);
    # pin 2 directly below it is GND.
    (
        "J3",
        "OUT / GND",
        "Connector_Generic:Conn_01x02",
        "Drawbridge:GateOutputHeader",
        {"1": "OUT_OC", "2": "GND"},
        (220, 58),
        (48, 8, 0),
    ),
]
for i, (role, signal, x) in enumerate(
    [("WIFI", "WIFI_IO33", 30), ("MQTT", "MQTT_IO38", 36), ("HOLD", "HOLD_IO1", 42)]
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
                (x + 2.54, 6.5, -90),
            ),
            (
                f"D{i + 1}",
                role,
                "Device:LED",
                LED_FP,
                {"1": "GND", "2": role + "_A"},
                (120 + i * 45, 140),
                (x, 17.5, 0),
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
        '(title_block (title "Drawbridge FeatherWing - FeatherS3[D]") (rev "A DRAFT") (comment 1 "USB-powered host; no Feather module in assembly BOM") (comment 2 "Prototype open-collector output; gate interface not released"))',
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
    notes = "D5 / IO33: Wi-Fi   D6 / IO38: MQTT   D9 / IO1: Hold\nD11 / IO7: transistor (do not use the XIAO pin map)\nQ1: onsemi 2N3904, pads 1=E, 2=B, 3=C\nJ3: open collector and common GND; NOT an isolated contact\nNo connection to VBUS, VBAT, EN, LDO2, USB or strapping pins."
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
        for graphic in list(fp):
            if not isinstance(graphic, list) or not graphic[0].startswith("fp_"):
                continue
            if sub(graphic, "layer") and field(graphic, "layer")[1] == '"F.SilkS"':
                fp.remove(graphic)
            elif sub(graphic, "layer") and field(graphic, "layer")[1] == '"F.CrtYd"':
                field(graphic, "start")[1:] = ["-1.52", "-1.52"]
                field(graphic, "end")[1:] = ["1.52", str((count - 1) * 2.54 + 1.52)]
        (local_library / f"FeatherHeader{count}.kicad_mod").write_text(dump(fp) + "\n")
    output_fp = expr(
        (
            SUPPORT
            / "footprints/Connector_PinHeader_2.54mm.pretty/PinHeader_1x02_P2.54mm_Vertical.kicad_mod"
        ).read_text()
    )
    output_fp[1] = '"GateOutputHeader"'
    for graphic in list(output_fp):
        if isinstance(graphic, list) and graphic[0].startswith("fp_") and sub(graphic, "layer"):
            if field(graphic, "layer")[1] in ('"F.SilkS"', '"B.SilkS"', '"F.CrtYd"', '"B.CrtYd"'):
                output_fp.remove(graphic)
    (local_library / "GateOutputHeader.kicad_mod").write_text(dump(output_fp) + "\n")
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

    def text(label, x, y, size=0.85, layer=pcb.F_SilkS):
        t = pcb.PCB_TEXT(b)
        t.SetText(label)
        t.SetPosition(pos(x, y))
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
                (1.5 + a[0] * 0.1, 4 + a[1] * 0.1), (1.5 + z[0] * 0.1, 4 + z[1] * 0.1), pcb.F_SilkS
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

    track("CTRL_IO7", ["J2.6", (27.94, 2.54), (27.94, 3.3), (16.5, 3.3), (16.5, 5), "R1.1"])
    track("BASE", ["R1.2", (25.62, 9), (22.62, 12), (19.27, 12), "Q1.2"])
    track("BASE", [(19.27, 12), (18, 13.27), "R2.1"])
    track("OUT_OC", ["Q1.3", (22, 8.54), (35, 8.54), (35, 10), "J3.1"], pcb.B_Cu, 0.5)
    track("GND", ["J3.2", (50.1, 10.54), (50.1, 16), (40, 16), (40, 19.4)], pcb.B_Cu, 0.5)
    track("GND", ["Q1.1", (15, 10), (15, 18.3), (13.97, 19.33), "J1.4"], pcb.B_Cu, 0.5)
    track("GND", ["J1.4", (13.97, 19.4), (42, 19.4), (42, 17.5)], pcb.B_Cu, 0.5)
    track("GND", ["R2.2", (25.62, 19.4)], pcb.B_Cu, 0.5)
    for i, x in enumerate([30, 36, 42]):
        track("GND", [f"D{i + 1}.1", (x, 19.4)], pcb.B_Cu, 0.5)
        track(["WIFI_A", "MQTT_A", "HOLD_A"][i], [f"R{i + 3}.2", f"D{i + 1}.2"])
    track("WIFI_IO33", ["J2.10", (39.37, 3.8)], pcb.B_Cu)
    via = pcb.PCB_VIA(b)
    via.SetPosition(pos(39.37, 3.8))
    via.SetWidth(pcb.FromMM(0.7))
    via.SetDrill(pcb.FromMM(0.3))
    via.SetLayerPair(pcb.F_Cu, pcb.B_Cu)
    via.SetNet(nets["WIFI_IO33"])
    b.Add(via)
    track("WIFI_IO33", [(39.37, 3.8), (32.54, 3.8), "R3.1"])
    track("MQTT_IO38", ["J2.9", (36.83, 4.79), "R4.1"], pcb.B_Cu)
    track("HOLD_IO1", ["J2.8", (34.29, 2.8), (44.54, 2.8), "R5.1"])
    # The revision mark belongs with the castle artwork at the USB end.
    text("DRAWBRIDGE rev A", 9.5, 20, 0.75)
    text("WIFI", 31.27, 20.3, 0.7)
    text("MQTT", 37.27, 20.3, 0.7)
    text("HOLD", 43.27, 20.3, 0.7)
    # Transistor pin order is documented in the schematic note; keep the
    # crowded TO-92 body clear on the PCB silkscreen.
    text("R1 1k", 23, 7.1, 0.7)
    text("R2 100k", 21.5, 17.1, 0.7)
    text("R3", 30, 10.5, 0.7)
    text("1k", 30, 14.5, 0.7)
    text("R4", 36, 10.5, 0.7)
    text("1k", 36, 14.5, 0.7)
    text("R5", 42, 10.5, 0.7)
    text("1k", 42, 14.5, 0.7)
    # Place the wire destination directly above the vertically arranged J3
    # pins, rather than leaving it detached in the open centre area.
    text("(To EXIT)", 48, 4.8, 0.7)
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
        "J3": ("2-pin wire header, 2.54 mm pitch", "Harwin", "M20-9990246"),
        "Q1": ("NPN transistor, TO-92, EBC", "onsemi", "2N3904BU"),
        "R1": ("1 kOhm 1% axial resistor, 0.25 W", "Yageo", "CFR-25JB-52-1K"),
        "R2": ("100 kOhm 1% axial resistor, 0.25 W", "Yageo", "CFR-25JB-52-100K"),
        "R3": ("1 kOhm 1% axial resistor, 0.25 W", "Yageo", "CFR-25JB-52-1K"),
        "R4": ("1 kOhm 1% axial resistor, 0.25 W", "Yageo", "CFR-25JB-52-1K"),
        "R5": ("1 kOhm 1% axial resistor, 0.25 W", "Yageo", "CFR-25JB-52-1K"),
        "D1": ("3 mm red LED, THT", "Lite-On", "L-7104LID"),
        "D2": ("3 mm yellow LED, THT", "Lite-On", "L-7104LYD"),
        "D3": ("3 mm green LED, THT", "Lite-On", "L-7104LGD"),
    }
    with (HERE / "bom.csv").open("w", newline="") as f:
        w = csv.writer(f)
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
