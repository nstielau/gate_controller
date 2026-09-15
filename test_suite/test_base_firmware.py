"""Staged-change protection and independently identifiable USB release bundles."""

import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.append(str(Path(__file__).resolve().parents[1] / "tools"))
from check_base_firmware import check
from firmware_release import base_bundle


class BaseFirmwareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Base Test")
        self.git("config", "core.hooksPath", "/dev/null")
        for name, data in {
            "circuitpython/code.py": "# networking\n",
            "circuitpython/boot.py": "# ownership\n",
            "circuitpython/drawbridge.py": "APP_VERSION = '1.0.1'\n",
            "circuitpython/lib/gate_base.py": "BASE_VERSION = '1.0.1'\n",
            "circuitpython/lib/dependency.mpy": "compiled library",
            ".gitignore": "circuitpython/settings.toml\n",
        }.items():
            self.write(name, data)
        self.git("add", ".")
        self.git("commit", "-qm", "Base inputs")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root).decode().strip()

    def write(self, name, value):
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value)

    def bump(self, version="1.0.2"):
        self.write("circuitpython/lib/gate_base.py", f"BASE_VERSION = '{version}'\n")
        self.write(
            f"docs/base-firmware/{version}.md",
            "Intentional USB base change: updated networking. USB bench validation required.\n",
        )
        self.git("add", "circuitpython/lib/gate_base.py", "docs")

    def test_app_only_commit_does_not_require_base_bump(self):
        self.write("circuitpython/drawbridge.py", "# application change\n")
        self.git("add", "circuitpython/drawbridge.py")
        check(self.root)

    def test_base_change_requires_staged_version_and_note(self):
        self.write("circuitpython/code.py", "# changed networking\n")
        self.git("add", "circuitpython/code.py")
        with self.assertRaisesRegex(ValueError, "USB-managed"):
            check(self.root)
        self.write("circuitpython/lib/gate_base.py", "BASE_VERSION = '1.0.2'\n")
        with self.assertRaises(ValueError):
            check(self.root)  # An unstaged bump cannot approve the staged source.
        self.git("add", "circuitpython/lib/gate_base.py")
        with self.assertRaises(ValueError):
            check(self.root)  # A version alone is not an intentional-change note.
        self.bump()
        check(self.root)

    def test_renamed_or_deleted_base_and_library_changes_are_protected(self):
        for path in ("circuitpython/boot.py", "circuitpython/lib/dependency.mpy"):
            with self.subTest(path=path):
                self.git("rm", path)
                with self.assertRaises(ValueError):
                    check(self.root)
                self.git("reset", "-q", "HEAD", "--", path)
                self.git("restore", path)
        self.git("mv", "circuitpython/boot.py", "moved.txt")
        with self.assertRaises(ValueError):
            check(self.root)

    def test_unchanged_or_lower_version_is_rejected(self):
        for version in ("1.0.1", "1.0.0"):
            self.write("circuitpython/code.py", "# changed\n")
            self.git("add", "circuitpython/code.py")
            self.bump(version)
            with self.assertRaises(ValueError):
                check(self.root)

    def test_bundle_is_repeatable_excludes_secrets_and_separates_app_identity(self):
        self.write("circuitpython/settings.toml", "private device settings")
        head = self.git("rev-parse", "HEAD")
        one, archive = base_bundle(self.root, head, b"app one")
        self.assertEqual((one, archive), base_bundle(self.root, head, b"app one"))
        two, _ = base_bundle(self.root, head, b"app two")
        a, b = json.loads(one), json.loads(two)
        self.assertEqual(a["base_version"], "1.0.1")
        self.assertEqual(a["base_sha256"], b["base_sha256"])
        self.assertNotEqual(a["recovery_app_sha256"], b["recovery_app_sha256"])
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            self.assertNotIn("settings.toml", zipped.namelist())
            self.assertEqual(zipped.read("drawbridge.py"), b"app one")
            self.assertEqual(zipped.read("base-manifest.json"), one)
            for name, digest in a["files"].items():
                self.assertEqual(hashlib.sha256(zipped.read(name)).hexdigest(), digest)
