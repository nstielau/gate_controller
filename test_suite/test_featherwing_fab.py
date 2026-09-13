"""Offline regressions for fabrication release freshness and recovery."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools import featherwing_fab as fab


class FabricationReleaseTests(unittest.TestCase):
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
            "assembly-position.csv",
            "schematic.png",
            "drc.rpt",
        ]
        for name in names:
            path = release / name
            path.parent.mkdir(exist_ok=True)
            path.write_text(f"{revision}: {name}")

    def test_repeated_release_replaces_all_archives_loose_files_and_old_attempts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "featherwing"
            for revision in ("first", "second"):
                staging = root / "staging"
                self.populate(staging, revision)
                fab.package_release(staging)
                fab.replace_release(staging, output)
                manifest = json.loads((output / "manifest.json").read_text())["sha256"]
                actual = {
                    p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()
                }
                self.assertEqual(actual, set(manifest) | {"manifest.json"})
                for name, digest in manifest.items():
                    self.assertEqual(
                        hashlib.sha256((output / name).read_bytes()).hexdigest(), digest
                    )
                self.assertEqual(len(list(output.glob("*.zip"))), 3)
                for archive_name, members in fab.archive_maps(output).items():
                    with zipfile.ZipFile(output / archive_name) as archive:
                        self.assertEqual(set(archive.namelist()), set(members))
                        for member, loose in members.items():
                            self.assertEqual(archive.read(member), loose.read_bytes())
                            self.assertTrue(archive.read(member).startswith(revision.encode()))
                if revision == "first":
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
                patch.object(fab, "regenerate_design"),
                patch.object(fab, "export_release", side_effect=RuntimeError("DRC failed")),
                self.assertRaisesRegex(RuntimeError, "DRC failed"),
            ):
                fab.main()
            self.assertEqual(previous.read_bytes(), b"last successful release")
            self.assertEqual(list(output.iterdir()), [previous])
            self.assertEqual(list(Path(temp).glob(".featherwing-build-*")), [])

    def test_failed_directory_swap_restores_previous_release(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "featherwing"
            output.mkdir()
            (output / "previous.zip").write_bytes(b"previous")
            with self.assertRaises(FileNotFoundError):
                fab.replace_release(root / "missing-stage", output)
            self.assertEqual((output / "previous.zip").read_bytes(), b"previous")


if __name__ == "__main__":
    unittest.main()
