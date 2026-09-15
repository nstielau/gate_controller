"""Offline regressions for fabrication release freshness and recovery."""

import csv
import ast
import hashlib
import json
import math
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools import featherwing_fab as fab


class FabricationReleaseTests(unittest.TestCase):
    def test_route_corners_are_chamfered_and_endpoints_preserved(self):
        source = ast.parse((fab.DESIGN / "generate.py").read_text())
        function = next(
            n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == "route_45"
        )
        namespace = {"math": math}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "route_45", "exec"), namespace)
        route = namespace["route_45"]
        for points in [[(0, 0), (4, 0), (4, 5)], [(0, 0), (2, 2), (4, 0)], [(0, 0), (3, 6)]]:
            output = route(points)
            self.assertEqual(output[0], points[0])
            self.assertEqual(output[-1], points[-1])
            for a, b, c in zip(output, output[1:], output[2:]):
                u, v = (b[0] - a[0], b[1] - a[1]), (c[0] - b[0], c[1] - b[1])
                cosine = sum(x * y for x, y in zip(u, v)) / (math.hypot(*u) * math.hypot(*v))
                self.assertGreaterEqual(cosine, math.sqrt(0.5) - 1e-6)
            for a, b in zip(output, output[1:]):
                dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
                self.assertTrue(min(dx, dy) < 1e-6 or abs(dx - dy) < 1e-6)

    def test_exit_terminal_is_populated_and_seeed_uses_manufacturer_sourcing(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "seeed.csv"
            fab.write_seeed_bom(fab.DESIGN / "bom.csv", output)
            with output.open() as source:
                row = next(r for r in csv.DictReader(source) if r["Designator"] == "J3")
            self.assertEqual(row["Manufacturer Part Number or Seeed SKU"], "1725656")
            self.assertEqual(row["Qty"], "1")
            self.assertEqual(row["Link"], fab.EXTERNAL_PARTS["1725656"])

    @staticmethod
    def revision_info(revision):
        return {"revision": revision, "git_head": revision + "0" * 37, "dirty": False}

    @staticmethod
    def git(root, *args):
        return subprocess.run(
            ["git", *args], cwd=root, check=True, capture_output=True, text=True
        ).stdout.strip()

    def init_repo(self, root):
        self.git(root, "init")
        self.git(root, "config", "user.email", "test@example.invalid")
        self.git(root, "config", "user.name", "Fabrication Test")
        self.git(root, "config", "core.hooksPath", "/dev/null")
        (root / ".gitignore").write_text("artifacts/\n")
        (root / "tracked.txt").write_text("committed input")
        self.git(root, "add", ".")
        self.git(root, "commit", "-m", "Test inputs")
        return self.git(root, "rev-parse", "HEAD")

    def populate(self, release, revision):
        release.mkdir()
        names = [
            "gerbers/board-F_Silkscreen.gto",
            "drills/board-PTH.drl",
            "assembly-notes.txt",
            "fabrication-checks.txt",
            "board.png",
            "schematic.pdf",
            "silkscreen.svg",
            "drawbridge-silkscreen.svg",
            "drawbridge-silkscreen.png",
            "assembly-bom.csv",
            "assembly-bom.xlsx",
            "seeed-assembly-bom.csv",
            "assembly-position.csv",
            "schematic.png",
            "drc.rpt",
        ]
        for name in names:
            path = release / name
            path.parent.mkdir(exist_ok=True)
            path.write_text(f"{revision}: {name}")
        (release / f"REV_{revision}.txt").write_text(revision + "\n")

    def test_repeated_release_replaces_all_archives_loose_files_and_old_attempts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "featherwing"
            for revision in ("abc", "def"):
                staging = root / "staging"
                self.populate(staging, revision)
                fab.package_release(staging, self.revision_info(revision))
                fab.replace_release(staging, output)
                manifest_data = json.loads((output / "manifest.json").read_text())
                self.assertEqual(manifest_data["revision"], revision)
                manifest = manifest_data["sha256"]
                actual = {
                    p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()
                }
                self.assertEqual(actual, set(manifest) | {"manifest.json"})
                for name, digest in manifest.items():
                    self.assertEqual(
                        hashlib.sha256((output / name).read_bytes()).hexdigest(), digest
                    )
                marker = output / f"REV_{revision}.txt"
                self.assertEqual(
                    marker.read_text(),
                    f"{revision}\nGit commit: {self.revision_info(revision)['git_head']}\n",
                )
                self.assertEqual(len(list(output.glob("*.zip"))), 3)
                for archive_name, members in fab.archive_maps(output).items():
                    with zipfile.ZipFile(output / archive_name) as archive:
                        self.assertEqual(set(archive.namelist()), set(members))
                        for member, loose in members.items():
                            self.assertEqual(archive.read(member), loose.read_bytes())
                            self.assertTrue(archive.read(member).startswith(revision.encode()))
                if revision == "abc":
                    (output / "old-attempt").mkdir()
                    (output / "old-attempt/stale.gto").write_text("old logo")
                    (output / "old-preview.png").write_text("old preview")
            self.assertFalse((output / "old-attempt").exists())
            self.assertFalse((output / "old-preview.png").exists())

    def test_failed_export_keeps_previous_complete_release(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "featherwing"
            output.mkdir()
            previous = output / "previous.zip"
            previous.write_bytes(b"last successful release")
            with (
                patch.object(fab, "OUTPUT", output),
                patch.object(fab, "KICAD", previous),
                patch.object(fab, "KICAD_PYTHON", previous),
                patch.object(
                    fab,
                    "determine_revision",
                    return_value=self.revision_info("abc"),
                ),
                patch.object(fab, "snapshot_sources"),
                patch.object(fab, "regenerate_design"),
                patch.object(fab, "export_release", side_effect=RuntimeError("DRC failed")),
                self.assertRaisesRegex(RuntimeError, "DRC failed"),
            ):
                fab.main()
            self.assertEqual(previous.read_bytes(), b"last successful release")
            self.assertEqual(list(output.iterdir()), [previous])
            self.assertEqual(list(Path(temp).glob(".featherwing-build-*")), [])

    def test_clean_revision_is_stable_and_ignores_build_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            head = self.init_repo(root)
            with patch.object(fab, "ROOT", root):
                expected = {"revision": head[:3], "git_head": head, "dirty": False}
                self.assertEqual(fab.determine_revision(), expected)
                (root / "artifacts").mkdir()
                (root / "artifacts/manifest.json").write_text('{"revision":"old.99"}')
                self.assertEqual(fab.determine_revision(), expected)

    def test_dirty_checkout_refuses_before_generation_and_preserves_artifacts(self):
        for kind in ("unstaged", "staged", "untracked", "deleted"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                self.init_repo(root)
                if kind == "deleted":
                    (root / "tracked.txt").unlink()
                elif kind == "untracked":
                    (root / "new.txt").write_text("new input")
                else:
                    (root / "tracked.txt").write_text("edited input")
                    if kind == "staged":
                        self.git(root, "add", "tracked.txt")
                output = root / "artifacts/featherwing"
                output.mkdir(parents=True)
                previous = output / "previous.zip"
                previous.write_bytes(b"last successful release")
                with (
                    patch.object(fab, "ROOT", root),
                    patch.object(fab, "OUTPUT", output),
                    patch.object(fab, "KICAD", previous),
                    patch.object(fab, "KICAD_PYTHON", previous),
                    patch.object(fab, "snapshot_sources") as snapshot,
                    self.assertRaisesRegex(RuntimeError, "clean Git checkout"),
                ):
                    fab.main()
                snapshot.assert_not_called()
                self.assertEqual(previous.read_bytes(), b"last successful release")
                self.assertEqual(list(output.iterdir()), [previous])

    def test_snapshot_uses_committed_sources_without_mutating_checkout(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.init_repo(root)
            design = root / "hardware/featherwing"
            design.mkdir(parents=True)
            (design / "generate.py").write_text("committed generator")
            (root / "tools").mkdir()
            (root / "tools/render_featherwing.mjs").write_text("committed renderer")
            self.git(root, "add", ".")
            self.git(root, "commit", "-m", "Design inputs")
            output = root / "artifacts"
            output.mkdir()
            with patch.object(fab, "ROOT", root):
                before = fab.determine_revision()
                staged = fab.snapshot_sources(output / "source", before["git_head"])
                self.assertEqual((staged / "generate.py").read_text(), "committed generator")
                self.assertEqual(
                    (staged.parents[1] / "tools/render_featherwing.mjs").read_text(),
                    "committed renderer",
                )
                (staged / "generate.py").write_text("generated changes")
                self.assertEqual(fab.determine_revision(), before)
                self.assertEqual((design / "generate.py").read_text(), "committed generator")

    def test_head_change_during_build_preserves_previous_release(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "featherwing"
            output.mkdir()
            previous = output / "previous.zip"
            previous.write_bytes(b"previous")
            with (
                patch.object(fab, "OUTPUT", output),
                patch.object(fab, "KICAD", previous),
                patch.object(fab, "KICAD_PYTHON", previous),
                patch.object(
                    fab,
                    "determine_revision",
                    side_effect=[self.revision_info("abc"), self.revision_info("def")],
                ),
                patch.object(fab, "snapshot_sources"),
                patch.object(fab, "regenerate_design"),
                patch.object(fab, "export_release"),
                patch.object(fab, "package_release"),
                self.assertRaisesRegex(RuntimeError, "HEAD changed"),
            ):
                fab.main()
            self.assertEqual(list(output.iterdir()), [previous])
            self.assertEqual(previous.read_bytes(), b"previous")

    def test_failed_directory_swap_restores_previous_release(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "featherwing"
            output.mkdir()
            (output / "previous.zip").write_bytes(b"previous")
            with self.assertRaises(FileNotFoundError):
                fab.replace_release(root / "missing-stage", output)
            self.assertEqual((output / "previous.zip").read_bytes(), b"previous")

    def test_generated_design_uses_portable_feather_net_names(self):
        design = fab.DESIGN
        expected = ("WIFI_D5", "MQTT_D6", "HOLD_D9", "CTRL_D11")
        obsolete = ("WIFI_IO33", "MQTT_IO38", "HOLD_IO1", "CTRL_IO7")
        for filename in ("drawbridge-featherwing.kicad_sch", "drawbridge-featherwing.kicad_pcb"):
            contents = (design / filename).read_text()
            for net_name in expected:
                self.assertIn(net_name, contents, f"{net_name} missing from {filename}")
            for net_name in obsolete:
                self.assertNotIn(net_name, contents, f"{net_name} remains in {filename}")

    def test_seeed_bom_groups_assembled_parts_and_excludes_unpopulated_parts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "bom.csv"
            destination = root / "seeed.csv"
            source.write_text(
                "Reference,Manufacturer,Manufacturer Part Number,Quantity,Populate\n"
                "R1,Yageo,CFR-25JB-52-1K,1,Yes\n"
                "R2,Yageo,CFR-25JB-52-1K,1,Yes\n"
                "Q1,onsemi,2N3904BU,1,Yes\n"
                "J3,Harwin,DO-NOT-ASSEMBLE,1,No\n"
            )
            fab.write_seeed_bom(source, destination)
            with destination.open(newline="") as stream:
                rows = list(csv.reader(stream))
            self.assertEqual(
                rows,
                [
                    [
                        "Designator",
                        "Manufacturer Part Number or Seeed SKU",
                        "Qty",
                        "Link",
                    ],
                    [
                        "R1,R2",
                        "CFR-25JB-52-1K",
                        "2",
                        "https://www.seeedstudio.com/opl.html?keywords=CFR-25JB-52-1K",
                    ],
                    [
                        "Q1",
                        "2N3904BU",
                        "1",
                        "https://www.seeedstudio.com/opl.html?keywords=2N3904BU",
                    ],
                ],
            )

    def test_seeed_bom_rejects_an_unreviewed_part(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "bom.csv"
            source.write_text(
                "Reference,Manufacturer,Manufacturer Part Number,Quantity,Populate\n"
                "R1,Unknown,NOT-IN-OPL,1,Yes\n"
            )
            with self.assertRaisesRegex(RuntimeError, "has not been reviewed"):
                fab.write_seeed_bom(source, root / "seeed.csv")


if __name__ == "__main__":
    unittest.main()
