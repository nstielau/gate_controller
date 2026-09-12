#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["svgelements==1.9.6"]
# ///
"""Generate a connected breadboard sketch: uv run tools/make_fritzing.py.

Fritzing uses 90 scene units/inch. Connections are bidirectional XML graph
edges; coincident pictures alone do not establish an electrical connection.
"""

import io
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

from svgelements import SVG

ROOT = Path(__file__).resolve().parents[1]
CORE = Path("/Applications/Fritzing.app/Contents/Resources/fritzing-parts/core")
SVGS = CORE.parent / "svg/core"
OUTPUT = ROOT / "docs/xiao-breadboard.fzz"
PART = ROOT / "docs/fritzing-parts/xiao-esp32s3.fzpz"
NS = "{http://www.w3.org/2000/svg}"
ET.register_namespace("", NS[1:-1])
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")


def xml(element):
    ET.indent(element)
    return ET.tostring(element, encoding="utf-8", xml_declaration=True)


class Sketch:
    def __init__(self):
        self.assets = {}
        self.parts = {}
        self.nodes = {}
        self.points = {}
        self.edges = []
        self.occupied = {}
        self.root = ET.Element("module", fritzingVersion="1.0.8", icon=".png")
        views = ET.SubElement(self.root, "views")
        for name in ("breadboardView", "schematicView", "pcbView"):
            ET.SubElement(views, "view", name=name, backgroundColor="#ffffff",
                          gridSize="0.1in", showGrid="1", alignToGrid="1", viewFromBelow="0")
        self.instances = ET.SubElement(self.root, "instances")
        self.counter = 100

    def import_core(self, filename, clone=None, resistance=None):
        part = ET.parse(CORE / filename).getroot()
        if clone:
            part.set("moduleId", "gate-mini-v4-" + clone)
            if clone == "j1-output":
                # Each screw contact and its solder pin are the same conductor.
                buses = ET.SubElement(part, "buses")
                for i in range(2):
                    bus = ET.SubElement(buses, "bus", id="terminal" + str(i))
                    for connector in (i, i + 2):
                        ET.SubElement(bus, "nodeMember", connectorId="connector" + str(connector))
            for pin in part.findall("./connectors/connector/views/breadboardView/p"):
                pin.attrib.pop("legId", None)
            filename = clone + ".fzp"
        for layers in part.findall("./views/*/layers"):
            reference = layers.get("image")
            data = (SVGS / reference).read_bytes()
            view, original = reference.split("/", 1)
            if clone:
                original = clone + "-" + view + ".svg"
                layers.set("image", view + "/" + original)
            if resistance and view == "breadboard":
                drawing = ET.fromstring(data)
                colors = {"band_1_st": "#8A3D06", "band_2_nd": "#000000",
                          "band_rd_multiplier": "#C40808" if resistance == 1000 else "#F4CE00"}
                for element in drawing.iter():
                    if element.get("id") in colors:
                        element.set("fill", colors[element.get("id")])
                data = xml(drawing)
            if clone and (clone.startswith('led-') or clone == 'q1-2n3904') and view == 'breadboard':
                drawing = ET.fromstring(data)
                by_id = {e.get('id'): e for e in drawing.iter()}
                for parent in drawing.iter():
                    for element in list(parent):
                        ident = element.get('id', '')
                        if ident.startswith('connector') and ident.endswith('leg'):
                            pin = by_id[ident[:-3]+'pin']
                            pin.set('y', str(float(element.get('y1'))-float(pin.get('height'))/2))
                            parent.remove(element)
                if clone == 'led-hold':
                    for element in drawing.iter():
                        if element.get('id', '').startswith('color_'):
                            element.set('fill', '#00B83F')
                data = xml(drawing)
            self.assets["svg." + view + "." + original] = data
        if resistance:
            part.find("title").text = str(resistance) + " ohm resistor"
            for prop in part.findall("./properties/property"):
                if prop.get("name").lower() == "resistance":
                    prop.text = str(resistance)
        self.assets["part." + filename] = xml(part)
        return part, "part." + filename

    def import_xiao(self):
        with zipfile.ZipFile(PART) as archive:
            for name in archive.namelist():
                if "/" in name or name.startswith("."):
                    raise ValueError("Unexpected upstream archive member: " + name)
                self.assets[name] = archive.read(name)
        filename = next(name for name in self.assets if name.startswith("part.prefix"))
        return ET.fromstring(self.assets[filename]), filename

    def adapt(self, info, tag, a=1, b=0, c=0, d=1):
        """Bake a physical scale/rotation into a unique breadboard SVG.

        The old mini-board art uses 72 px/in; normalize to a real 2.54 mm
        pitch. The contributed XIAO art also needs its header pitch corrected.
        All connector IDs remain intact, so Fritzing still knows each pin.
        """
        part, filename = info
        part.set("moduleId", "gate-mini-v4-" + tag)
        ref = part.find('./views/breadboardView/layers').get('image')
        old = ET.fromstring(self.assets['svg.' + ref.replace('/', '.', 1)])
        parsed = SVG.parse(io.BytesIO(ET.tostring(old)), ppi=90)
        w, h = parsed.width, parsed.height
        vx, vy, vw, vh = map(float, old.get('viewBox').split())
        corners = [(a*x+c*y, b*x+d*y) for x, y in ((0,0),(w,0),(0,h),(w,h))]
        xmin, ymin = min(p[0] for p in corners), min(p[1] for p in corners)
        width = max(p[0] for p in corners)-xmin
        height = max(p[1] for p in corners)-ymin
        root = ET.Element(NS+'svg', width=str(width/90)+'in', height=str(height/90)+'in',
                          viewBox='0 0 {} {}'.format(width,height))
        group = ET.SubElement(root, NS+'g', transform='matrix({} {} {} {} {} {})'.format(
            a*w/vw, b*w/vw, c*h/vh, d*h/vh,
            -xmin-a*w/vw*vx-c*h/vh*vy, -ymin-b*w/vw*vx-d*h/vh*vy))
        layer_id = part.find('./views/breadboardView/layers/layer').get('layerId')
        if not any(element.get('id') == layer_id for element in old.iter()):
            group.set('id', layer_id)
        for child in old:
            group.append(child)
        if tag == 'mini-170':
            board_layer = next(e for e in group.iter() if e.get('id') == 'breadboardbreadboard')
            labels = ET.SubElement(board_layer, NS+'g', fill='#555555',
                                   attrib={'font-family': 'Droid Sans', 'font-size': '2.8', 'text-anchor': 'middle'})
            for n in range(1,18):
                ET.SubElement(labels, NS+'text', x=str(7.3205+(n-1)*7.2), y='98').text = str(n)
            for i, letter in enumerate('ABCDEFGHIJ'):
                y = 10.857+i*7.2+(14.4 if i >= 5 else 0)
                for x in (2.3,127.5):
                    ET.SubElement(labels, NS+'text', x=str(x), y=str(y+1)).text = letter
        ids = {element.get('id') for element in root.iter()}
        for pin in part.findall('./connectors/connector/views/breadboardView/p'):
            if pin.get('terminalId') not in ids:
                pin.attrib.pop('terminalId', None)
        new_ref = 'breadboard/' + tag + '.svg'
        for layer in part.findall('./views/*/layers'):
            if layer.get('image') == ref:
                layer.set('image', new_ref)
        self.assets['svg.breadboard.'+tag+'.svg'] = xml(root)
        filename = 'part.'+tag+'.fzp'
        self.assets[filename] = xml(part)
        return part, filename

    def add(self, index, part_info, title, position=(0, 0), board=False):
        part, filename = part_info
        instance = ET.SubElement(self.instances, "instance", moduleIdRef=part.get("moduleId"),
                                 modelIndex=str(index), path=filename)
        ET.SubElement(instance, "title").text = title
        if "resistor" in title.lower() or title.startswith("R"):
            prop = next((p for p in part.findall("./properties/property")
                         if p.get("name").lower() == "resistance"), None)
            if prop is not None:
                ET.SubElement(instance, "property", name="resistance", value=prop.text)
        views = ET.SubElement(instance, "views")
        layer = part.find("./views/breadboardView/layers/layer").get("layerId")
        view = ET.SubElement(views, "breadboardView", layer=layer)
        geometry = ET.SubElement(view, "geometry", z="1" if board else "2.5",
                                 x=str(position[0]), y=str(position[1]))
        conns = ET.SubElement(view, "connectors")
        reference = part.find("./views/breadboardView/layers").get("image")
        drawing = SVG.parse(io.BytesIO(self.assets["svg." + reference.replace("/", ".", 1)]), ppi=90)
        shapes = {e.id: e for e in drawing.elements() if e.id}
        coords = {}
        for conn in part.findall("./connectors/connector"):
            pin = conn.find("./views/breadboardView/p")
            bounds = shapes[pin.get("svgId")].bbox()
            coords[conn.get("id")] = ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2)
        self.parts[index] = (part, geometry, conns, layer, coords)
        for connector, point in coords.items():
            self.points[index, connector] = (point[0] + position[0], point[1] + position[1])
        return index

    def place_on(self, index, pins):
        """Seat a part using its first pin; connect each remaining lead to a hole."""
        part, geom, conns, layer, coords = self.parts[index]
        first, hole = next(iter(pins.items()))
        target = self.points[0, hole]
        x, y = target[0] - coords[first][0], target[1] - coords[first][1]
        geom.set("x", str(x))
        geom.set("y", str(y))
        for connector, local in coords.items():
            self.points[index, connector] = (x + local[0], y + local[1])
        for connector, hole in pins.items():
            a, b = self.points[index, connector], self.points[0, hole]
            if max(abs(a[0] - b[0]), abs(a[1] - b[1])) > 1:
                raise ValueError("Part lead not aligned with hole: " + str((index, connector, hole, a, b)))
            self.use_hole(hole, (index, connector))
            self.connect((index, connector), (0, hole))

    def use_hole(self, hole, owner):
        if hole in self.occupied:
            raise ValueError('Two leads in hole {}: {} and {}'.format(hole, self.occupied[hole], owner))
        self.occupied[hole] = owner

    def node(self, key):
        if key not in self.nodes:
            index, connector = key
            _, _, connectors, layer, _ = self.parts[index]
            node = ET.SubElement(connectors, "connector", connectorId=connector, layer=layer)
            ET.SubElement(node, "geometry", x="0", y="0")
            self.nodes[key] = ET.SubElement(node, "connects")
        return self.nodes[key]

    def connect(self, a, b):
        for source, dest in ((a, b), (b, a)):
            ET.SubElement(self.node(source), "connect", modelIndex=str(dest[0]),
                          connectorId=dest[1], layer=self.parts[dest[0]][3])
        self.edges.append((a, b))

    def wire(self, a, b, color, bends=()):
        route = [self.points[a], *bends, self.points[b]]
        previous = a
        for start, end in zip(route, route[1:]):
            self.counter += 1
            index = self.counter
            ins = ET.SubElement(self.instances, "instance", moduleIdRef="WireModuleID",
                                modelIndex=str(index), path=":/resources/parts/core/wire.fzp")
            ET.SubElement(ins, "title").text = "Jumper " + str(index)
            views = ET.SubElement(ins, "views")
            view = ET.SubElement(views, "breadboardView", layer="breadboardWire")
            ET.SubElement(view, "geometry", z="3.5", x=str(start[0]), y=str(start[1]),
                          x1="0", y1="0", x2=str(end[0] - start[0]), y2=str(end[1] - start[1]), wireFlags="64")
            ET.SubElement(view, "wireExtras", mils="22.2222", color=color, opacity="1", banded="0")
            connectors = ET.SubElement(view, "connectors")
            self.parts[index] = (None, None, connectors, "breadboardWire", {})
            self.points[index, "connector0"] = start
            self.points[index, "connector1"] = end
            self.connect(previous, (index, "connector0"))
            self.edges.append(((index, "connector0"), (index, "connector1")))
            previous = index, "connector1"
        self.connect(previous, b)

    def validate(self):
        graph = {}
        def link(a, b):
            graph.setdefault(a, set()).add(b)
            graph.setdefault(b, set()).add(a)
        for a, b in self.edges:
            link(a, b)
        for index, (part, *_rest) in self.parts.items():
            if part is not None:
                for bus in part.findall("./buses/bus"):
                    members = [(index, n.get("connectorId")) for n in bus]
                    for member in members[1:]:
                        link(members[0], member)
        def net(key):
            found, todo = set(), [key]
            while todo:
                current = todo.pop()
                if current in found:
                    continue
                found.add(current)
                todo.extend(graph.get(current, ()))
            return found
        expected = [
            [(1, "connector10"), (2, "connector0")],
            [(2, "connector1"), (3, "connector1"), (6, "connector0")],
            [(1, "connector11"), (4, "connector1")],
            [(4, "connector0"), (5, "connector1")],
            [(1, "connector12"), (3, "connector0"), (6, "connector1"), (8, "connector0")],
            [(3, "connector2"), (5, "connector0")],
            [(1, "connector0"), (7, "connector1")],
            [(7, "connector0"), (8, "connector1")],
        ]
        for group in expected:
            assert all(key in net(group[0]) for key in group), ("Missing connection", group)
        for i, group in enumerate(expected):
            for other in expected[i + 1:]:
                assert other[0] not in net(group[0]), ("Short circuit", group, other)
        for key in self.points:
            if key[0] != 0:
                assert any(node in self.nodes for node in net(key)), ("Unconnected pin", key)
        used = {key for group in expected for key in group if key[0] == 1}
        for key in self.points:
            if key[0] == 1 and key not in used:
                assert not any(group[0] in net(key) for group in expected), ('Unused XIAO pin shorted', key)
        print("Verified eight distinct nets, breadboard buses, pin alignment and unique occupied holes.")

    def save(self):
        self.validate()
        # Bundle only referenced assets, avoiding stale duplicate custom parts.
        referenced = {instance.get('path') for instance in self.instances if instance.get('moduleIdRef') != 'WireModuleID'}
        for filename in list(referenced):
            part = ET.fromstring(self.assets[filename])
            for layer in part.findall('./views/*/layers'):
                referenced.add('svg.'+layer.get('image').replace('/','.',1))
        with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('xiao-breadboard.fz', xml(self.root))
            for name in sorted(referenced):
                archive.writestr(name, self.assets[name])
        print("Wrote", OUTPUT)


def build():
    s = Sketch()
    s.add(0, s.adapt(s.import_core("miniBreadboard.fzp"), "mini-170", a=1.25, d=1.25),
          "170-hole mini breadboard (no rails)", (60, 60), board=True)
    # USB faces left; headers land on C1-C7 and G1-G7 (0.6 inch apart).
    s.add(1, s.adapt(s.import_xiao(), "xiao-usb-left",
                    a=0, b=-54/56.31, c=54/53.67, d=0), "XIAO ESP32S3")
    s.place_on(1, {**{"connector"+str(i): "G"+str(i+1) for i in range(7)},
                   **{"connector"+str(13-i): "C"+str(i+1) for i in range(7)}})
    def resistor(index, tag, title, value, vertical=False):
        info = s.import_core("resistor.fzp", tag, value)
        # Five-pitch horizontal or six-pitch vertical formed leads.
        factor = (54 if vertical else 45)/36.825
        info = s.adapt(info, tag+"-seated", a=0 if vertical else factor,
                       b=factor if vertical else 0, c=-1 if vertical else 0,
                       d=0 if vertical else 1)
        s.add(index, info, title)
    resistor(2, "r1-base-1k", "R1 1k base", 1000)
    s.add(3, s.import_core("sparkfun-discretesemi-transistor_npn-to92.fzp", "q1-2n3904"),
          "Q1 2N3904 E B C")
    resistor(4, "r2-bench-1k", "R2 1k bench LED", 1000, True)
    s.add(5, s.import_core("LED-generic-5mm_6852162_005.fzp", "led-bench-red"), "LED1 steady bench load")
    resistor(6, "r3-pulldown-100k", "R3 100k pulldown", 100000, True)
    resistor(7, "r4-hold-1k", "R4 1k hold LED", 1000, True)
    s.add(8, s.import_core("LED-generic-5mm_6852162_005.fzp", "led-hold"), "LED2 blinking hold indicator")
    s.place_on(2, {"connector0": "A4", "connector1": "A9"})
    s.place_on(3, {"connector0": "E10", "connector1": "E11", "connector2": "E12"})
    s.place_on(4, {"connector0": "D14", "connector1": "H14"})
    s.place_on(5, {"connector0": "E13", "connector1": "E14"})
    s.place_on(6, {"connector0": "D9", "connector1": "H9"})
    s.place_on(7, {"connector0": "D17", "connector1": "H17"})
    s.place_on(8, {"connector0": "E16", "connector1": "E17"})
    def hole(name):
        return s.points[0, name]
    black, orange, red, green = "#333333", "#e87820", "#d42d2d", "#149447"
    s.wire((0, "B9"), (0, "A11"), orange)
    s.wire((0, "B2"), (0, "A10"), black,
           [(hole("B2")[0], 63), (hole("A10")[0], 63)])
    s.wire((0, "D10"), (0, "F10"), black)
    s.wire((0, "I9"), (0, "I10"), black)
    s.wire((0, "J10"), (0, "J16"), black)
    s.wire((0, "F16"), (0, "D16"), black)
    s.wire((0, "A12"), (0, "A13"), orange)
    s.wire((0, "B3"), (0, "I14"), red,
           [(hole("B3")[0], 58), (hole("A15")[0], 58),
            (hole("A15")[0], hole("I14")[1])])
    s.wire((0, "G1"), (0, "I17"), green,
           [(hole("G1")[0], 68), (hole("A9")[0]-4.5, 68),
            (hole("A9")[0]-4.5, hole("F9")[1]),
            (hole("F17")[0]+8, hole("F9")[1]),
            (hole("F17")[0]+8, hole("I17")[1])])
    s.save()


if __name__ == "__main__":
    build()
