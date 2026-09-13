"""Offline regressions for fabrication release freshness and recovery."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from tools import featherwing_fab as fab


class FabricationReleaseTests(unittest.TestCase):
    @staticmethod
    def revision_info(revision, generation=1):
        return {
            "revision": revision,
            "git_head": "abcdef0123456789",
            "dirty": generation > 0,
            "dirty_generation": generation,
        }

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
            for revision in ("first", "second"):
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
                patch.object(
                    fab,
                    "determine_revision",
                    return_value=self.revision_info("abc.1"),
                ),
                patch.object(fab, "regenerate_design"),
                patch.object(fab, "export_release", side_effect=RuntimeError("DRC failed")),
                self.assertRaisesRegex(RuntimeError, "DRC failed"),
            ):
                fab.main()
            self.assertEqual(previous.read_bytes(), b"last successful release")
            self.assertEqual(list(output.iterdir()), [previous])
            self.assertEqual(list(Path(temp).glob(".featherwing-build-*")), [])

    def test_revision_is_clean_zero_or_next_dirty_generation(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            head = "abcdef0123456789"
            clean = {
                "revision": "abc.0",
                "git_head": head,
                "dirty": False,
                "dirty_generation": 0,
            }
            dirty = {
                "revision": "abc.4",
                "git_head": head,
                "dirty": True,
                "dirty_generation": 4,
            }

            def git_result(stdout):
                result = Mock()
                result.stdout = stdout
                return result

            with patch.object(
                fab.subprocess,
                "run",
                side_effect=[git_result(head + "\n"), git_result("")],
            ):
                self.assertEqual(fab.determine_revision(output), clean)

            (output / "manifest.json").write_text(json.dumps(dirty))
            with patch.object(
                fab.subprocess,
                "run",
                side_effect=[git_result(head + "\n"), git_result(" M file\n")],
            ):
                self.assertEqual(
                    fab.determine_revision(output),
                    {**dirty, "revision": "abc.5", "dirty_generation": 5},
                )

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


if __name__ == "__main__":
    unittest.main()
