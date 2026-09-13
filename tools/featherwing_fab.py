"""Rebuild and publish one complete, verified FeatherWing fabrication release."""

import fcntl
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
import zipfile
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "hardware/featherwing"
NAME = "drawbridge-featherwing"
BOARD = DESIGN / f"{NAME}.kicad_pcb"
SCHEMATIC = DESIGN / f"{NAME}.kicad_sch"
KICAD_APP = Path("/Applications/KiCad/KiCad.app/Contents")
KICAD = KICAD_APP / "MacOS/kicad-cli"
KICAD_PYTHON = KICAD_APP / "Frameworks/Python.framework/Versions/3.9/bin/python3.9"
OUTPUT = ROOT / "artifacts/featherwing"


def run(*args):
    subprocess.run([str(KICAD), *map(str, args)], check=True)


def determine_revision(output=OUTPUT):
    """Return a stable clean revision or the next successful dirty generation."""
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if len(head) < 3:
        raise RuntimeError("Git HEAD is too short to form a fabrication revision")
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    previous = {}
    manifest = output / "manifest.json"
    if manifest.is_file():
        try:
            previous = json.loads(manifest.read_text())
        except (json.JSONDecodeError, OSError):
            previous = {}
    generation = 0
    if dirty:
        generation = 1
        if previous.get("git_head") == head and previous.get("dirty") is True:
            old_generation = previous.get("dirty_generation")
            if isinstance(old_generation, int) and old_generation >= 1:
                generation = old_generation + 1
    short_ref = head[:3].lower()
    return {
        "revision": f"{short_ref}.{generation}",
        "git_head": head,
        "dirty": dirty,
        "dirty_generation": generation,
    }


def revision_marker(release):
    markers = list(release.glob("REV_*.txt"))
    if len(markers) != 1:
        raise RuntimeError(f"Expected exactly one revision marker, found {len(markers)}")
    return markers[0]


def regenerate_design(revision):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(KICAD_PYTHON.parent.parent / "lib/python3.9/site-packages")
    env["DRAWBRIDGE_REV"] = revision
    subprocess.run([str(KICAD_PYTHON), str(DESIGN / "generate.py")], env=env, check=True)


def archive_maps(release):
    """Each ZIP member maps to its canonical loose file in this release."""
    marker = revision_marker(release)
    loose = {
        p.relative_to(release).as_posix(): p
        for p in sorted(release.rglob("*"))
        if p.is_file() and p.suffix != ".zip" and p.name != "manifest.json"
    }
    return {
        f"{NAME}-pcbway.zip": {f"{NAME}/{name}": p for name, p in loose.items()},
        f"{NAME}-gerbers.zip": {
            **{
                p.name: p
                for name, p in loose.items()
                if name.startswith(("gerbers/", "drills/"))
            },
            marker.name: marker,
        },
        f"{NAME}-assembly-other.zip": {
            name: loose[name]
            for name in (
                "assembly-notes.txt",
                "fabrication-checks.txt",
                "board.png",
                "schematic.pdf",
                "silkscreen.svg",
                "drawbridge-silkscreen.svg",
                "drawbridge-silkscreen.png",
                "assembly-bom.xlsx",
                marker.name,
            )
        },
    }


def package_release(release, revision_info):
    """Build all archives, compare every member, and inventory all loose/ZIP files."""
    for name, members in archive_maps(release).items():
        with zipfile.ZipFile(release / name, "w", zipfile.ZIP_DEFLATED) as archive:
            for member, path in members.items():
                archive.write(path, member)
        with zipfile.ZipFile(release / name) as archive:
            if set(archive.namelist()) != set(members) or archive.testzip() is not None:
                raise RuntimeError(f"Archive inventory/CRC mismatch: {name}")
            for member, path in members.items():
                if archive.read(member) != path.read_bytes():
                    raise RuntimeError(f"Archive content mismatch: {name}: {member}")
    files = {
        p.relative_to(release).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(release.rglob("*"))
        if p.is_file() and p.name != "manifest.json"
    }
    (release / "manifest.json").write_text(
        json.dumps(
            {
                "built_at_utc": datetime.now(timezone.utc).isoformat(),
                **revision_info,
                "sha256": files,
            },
            indent=2,
        )
        + "\n"
    )


def write_bom_xlsx(source, destination):
    """Write the canonical CSV BOM as a dependency-free XLSX workbook."""
    with source.open(newline="") as stream:
        rows = list(csv.reader(stream))
    if not rows or not rows[0]:
        raise RuntimeError("BOM CSV is empty")

    def cell_ref(row, column):
        letters = ""
        while column:
            column, remainder = divmod(column - 1, 26)
            letters = chr(65 + remainder) + letters
        return f"{letters}{row}"

    cells = []
    for row_number, row in enumerate(rows, 1):
        row_cells = []
        for column_number, value in enumerate(row, 1):
            safe = escape(value)
            row_cells.append(
                f'<c r="{cell_ref(row_number, column_number)}" t="inlineStr">'
                f"<is><t>{safe}</t></is></c>"
            )
        cells.append(f'<row r="{row_number}">{"".join(row_cells)}</row>')
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(cells)}</sheetData></worksheet>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="BOM" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)


def replace_release(staging, output):
    """Replace the whole generated directory; restore the last release on rename failure."""
    if output.is_symlink():
        raise RuntimeError(f"Refusing to replace symlink: {output}")
    with tempfile.TemporaryDirectory(prefix=".featherwing-previous-", dir=output.parent) as temp:
        previous = Path(temp) / "previous"
        if output.exists():
            output.rename(previous)
        try:
            staging.rename(output)
        except BaseException:
            if previous.exists():
                previous.rename(output)
            raise


def export_release(release, revision):
    gerbers, drills = release / "gerbers", release / "drills"
    gerbers.mkdir()
    drills.mkdir()
    run("sch", "erc", SCHEMATIC, "--exit-code-violations", "-o", release / "erc.rpt")
    run("pcb", "drc", BOARD, "--exit-code-violations", "-o", release / "drc.rpt")
    run(
        "sch", "export", "netlist", SCHEMATIC, "--format", "kicadxml", "-o", release / "netlist.xml"
    )
    run(
        "pcb",
        "export",
        "gerbers",
        "-o",
        gerbers,
        "--layers",
        "F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,Edge.Cuts",
        BOARD,
    )
    run(
        "pcb",
        "export",
        "drill",
        "-o",
        drills,
        "--format",
        "excellon",
        "--excellon-units",
        "mm",
        "--excellon-separate-th",
        BOARD,
    )
    run(
        "pcb",
        "export",
        "pos",
        "-o",
        release / "assembly-position.csv",
        "--format",
        "csv",
        "--units",
        "mm",
        "--side",
        "both",
        BOARD,
    )
    # J3 is a board-only pair of hand-solder pads, not an assembled part.
    # Filter it after KiCad has generated the position file; exporting first
    # keeps this compatible with KiCad's normal CSV writer.
    position_file = release / "assembly-position.csv"
    position_lines = position_file.read_text().splitlines()
    position_file.write_text(
        "\n".join(line for line in position_lines if not line.startswith('"J3",')) + "\n"
    )
    run("sch", "export", "pdf", SCHEMATIC, "-o", release / "schematic.pdf")
    run("sch", "export", "svg", SCHEMATIC, "-o", release / "schematic-svg")
    svg_files = list((release / "schematic-svg").glob("*.svg"))
    if len(svg_files) != 1:
        raise RuntimeError("Expected the single-sheet schematic SVG")
    svg_files[0].rename(release / "schematic.svg")
    (release / "schematic-svg").rmdir()
    run(
        "pcb",
        "export",
        "svg",
        BOARD,
        "-o",
        release / "silkscreen.svg",
        "--layers",
        "F.Silkscreen,Edge.Cuts",
        "--mode-single",
        "--fit-page-to-board",
        "--exclude-drawing-sheet",
        "--black-and-white",
    )
    run(
        "pcb",
        "render",
        BOARD,
        "-o",
        release / "board.png",
        "--width",
        "1800",
        "--height",
        "1000",
        "--side",
        "top",
    )
    shutil.copyfile(DESIGN / "bom.csv", release / "assembly-bom.csv")
    write_bom_xlsx(DESIGN / "bom.csv", release / "assembly-bom.xlsx")
    shutil.copyfile(DESIGN / "README.md", release / "assembly-notes.txt")
    shutil.copyfile(
        DESIGN / "assets/drawbridge-silkscreen.svg", release / "drawbridge-silkscreen.svg"
    )
    subprocess.run(["node", str(ROOT / "tools/render_featherwing.mjs"), str(release)], check=True)
    (release / "fabrication-checks.txt").write_text(
        "ERC and DRC passed with --exit-code-violations. See erc.rpt and drc.rpt.\n"
        "J3 pin 1: OUT_OC; pin 2: GND. The Feather host is excluded from assembly.\n"
        "Logo SVG and PNG are references; the same vector geometry is already in F.Silkscreen.\n"
        "See manifest.json for build time and SHA-256 of every generated file and ZIP.\n"
    )
    marker_name = f"REV_{revision}.txt"
    (release / marker_name).write_text(revision + "\n")
    expected = [
        *(
            f"gerbers/{NAME}-{s}"
            for s in (
                "F_Cu.gtl",
                "B_Cu.gbl",
                "F_Mask.gts",
                "B_Mask.gbs",
                "F_Silkscreen.gto",
                "Edge_Cuts.gm1",
            )
        ),
        f"drills/{NAME}-PTH.drl",
        f"drills/{NAME}-NPTH.drl",
        "board.png",
        "schematic.png",
        "drawbridge-silkscreen.png",
        "assembly-bom.csv",
        "assembly-bom.xlsx",
        "assembly-position.csv",
        marker_name,
    ]
    for name in expected:
        if not (release / name).is_file() or (release / name).stat().st_size == 0:
            raise RuntimeError(f"Missing/empty export: {name}")


def main():
    if not KICAD.exists() or not KICAD_PYTHON.exists():
        raise SystemExit("KiCad 10 and its bundled Python are required in /Applications/KiCad")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    # Keep a stable lock inode outside the directory that gets replaced.
    with (OUTPUT.parent / ".featherwing-build.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Another FeatherWing build is running") from None
        with tempfile.TemporaryDirectory(prefix=".featherwing-build-", dir=OUTPUT.parent) as temp:
            release = Path(temp) / "release"
            release.mkdir()
            revision_info = determine_revision(OUTPUT)
            revision = revision_info["revision"]
            regenerate_design(revision)
            export_release(release, revision)
            package_release(release, revision_info)
            replace_release(release, OUTPUT)
    print(
        f"Replaced {OUTPUT} with revision {revision} "
        "(complete verified release; all ZIPs and loose files)."
    )


if __name__ == "__main__":
    main()
