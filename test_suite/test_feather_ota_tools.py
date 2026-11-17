"""Offline board-aware OTA enrollment, USB provisioning, and release metadata."""

from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "tools"))
import firmware_release
from ota_provision import provision
from env_config import load_dotenv

XIAO = "seeed_xiao_esp32_s3_sense"
FEATHER = "adafruit_feather_esp32s3_reverse_tft"


class FeatherProvisionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.board = self.root / "board"
        self.board.mkdir()
        for name in (
            "boot.py",
            "code.py",
            "drawbridge.py",
            "lib/gate_ota.py",
            "lib/gate_http.py",
            "certs/google-roots.pem",
        ):
            path = self.board / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture")
        self.settings = self.board / "settings.toml"
        self.settings.write_text('OTHER = "preserved"\nOTA_ENABLED = 0\n')
        self.credential = self.root / "device.env"

    def install(self, actual, enrolled=None, enable=True, environment=None):
        (self.board / "boot_out.txt").write_text(f"CircuitPython 10.3.0\nBoard ID:{actual}\n")
        text = "DEVICE_ID=test-device\nOTA_TOKEN=" + "a" * 64 + "\n"
        if enrolled is not None:
            text += "BOARD_ID=" + enrolled + "\n"
        self.credential.write_text(text)
        output = io.StringIO()
        with (
            patch.dict(os.environ, environment or {}, clear=True),
            patch("ota_provision.os.sync"),
            redirect_stdout(output),
        ):
            provision(self.board, self.credential, enable)
        self.assertNotIn("a" * 64, output.getvalue())
        return tomllib.loads(self.settings.read_text()), output.getvalue()

    def test_feather_matches_enrollment_preserves_settings_and_names_correct_recovery(self):
        settings, message = self.install(FEATHER, FEATHER)
        self.assertEqual(settings["OTHER"], "preserved")
        self.assertEqual(settings["OTA_ENABLED"], 1)
        self.assertEqual(settings["OTA_DEVICE_ID"], "test-device")
        self.assertIn("D1", message)
        self.assertIn("RESET", message)
        self.assertNotIn("D9", message)

    def test_credential_file_identity_is_not_replaced_by_process_environment(self):
        settings, _ = self.install(
            FEATHER,
            FEATHER,
            environment={"DEVICE_ID": "wrong-device", "OTA_TOKEN": "b" * 64, "BOARD_ID": XIAO},
        )
        self.assertEqual(settings["OTA_DEVICE_ID"], "test-device")
        self.assertEqual(settings["OTA_TOKEN"], "a" * 64)

    def test_legacy_credential_without_board_is_xiao_only(self):
        settings, message = self.install(XIAO)
        self.assertEqual(settings["OTA_ENABLED"], 1)
        self.assertIn("Ground D9", message)
        with self.assertRaises(ValueError):
            self.install(FEATHER)

    def test_cross_board_unknown_and_environment_spoofing_fail_before_writes(self):
        original = self.settings.read_text()
        for actual, enrolled, environment in (
            (FEATHER, XIAO, {}),
            (XIAO, FEATHER, {}),
            ("unknown", FEATHER, {}),
            (FEATHER, "unknown", {}),
            (FEATHER, XIAO, {"BOARD_ID": FEATHER}),
        ):
            with self.subTest(actual=actual, enrolled=enrolled):
                self.settings.write_text(original)
                with self.assertRaises(ValueError):
                    self.install(actual, enrolled, environment=environment)
                self.assertEqual(self.settings.read_text(), original)

    def test_feather_can_be_provisioned_without_enabling_loader(self):
        settings, message = self.install(FEATHER, FEATHER, enable=False)
        self.assertEqual(settings["OTA_ENABLED"], 0)
        self.assertIn("remains disabled", message)


class FeatherManifestTests(unittest.TestCase):
    def manifest(self, api, version="1.1.0"):
        self.assertTrue(
            hasattr(firmware_release, "application_manifest"),
            "Release metadata must support the application compatibility API",
        )
        source = f"APP_VERSION = '{version}'\nAPP_API_VERSION = {api}\n".encode()
        return firmware_release.application_manifest(source, version, "a" * 40), source

    def test_api_two_release_initially_targets_only_feather(self):
        manifest, source = self.manifest(2)
        self.assertEqual(manifest["app_api_version"], 2)
        self.assertEqual(manifest["minimum_bootstrap_version"], "1.1.0")
        self.assertEqual(manifest["supported_board_ids"], [FEATHER])
        self.assertEqual(manifest["size"], len(source))
        self.assertEqual(manifest["sha256"], hashlib.sha256(source).hexdigest())

    def test_api_one_manifest_remains_exactly_legacy_compatible(self):
        manifest, source = self.manifest(1, "1.0.0")
        checksum = hashlib.sha256(source).hexdigest()
        self.assertEqual(
            manifest,
            {
                "schema": 1,
                "app_version": "1.0.0",
                "app_api_version": 1,
                "minimum_bootstrap_version": "1.0.0",
                "circuitpython_major": 10,
                "supported_board_ids": [XIAO],
                "size": len(source),
                "sha256": checksum,
                "artifact_object": f"firmware/1.0.0/{checksum}/drawbridge.py",
                "git_commit": "a" * 40,
            },
        )

    def test_unknown_api_and_version_mismatch_cannot_make_manifest(self):
        self.assertTrue(hasattr(firmware_release, "application_manifest"))
        for source in (
            b"APP_VERSION='1.1.0'\nAPP_API_VERSION=3\n",
            b"APP_VERSION='1.0.0'\nAPP_API_VERSION=2\n",
        ):
            with self.assertRaises(ValueError):
                firmware_release.application_manifest(source, "1.1.0", "a" * 40)


class FeatherEnrollmentTests(unittest.TestCase):
    def test_iam_enrollment_validates_board_and_persists_binding_without_rotation(self):
        script = r"""
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {enrollmentBoardId, enrollDevice} = require(process.argv[1]);
(async () => {
  assert.equal(typeof enrollmentBoardId, 'function');
  assert.equal(typeof enrollDevice, 'function');
  const feather = 'adafruit_feather_esp32s3_reverse_tft';
  assert.equal(enrollmentBoardId(feather), feather);
  assert.equal(enrollmentBoardId(), 'seeed_xiao_esp32_s3_sense');
  assert.throws(() => enrollmentBoardId('unknown'));
  let record = {enabled: true};
  let updates = 0;
  const ref = {get: async () => ({exists: true, data: () => record})};
  const db = {doc: () => ref, runTransaction: async fn => fn({get: ref.get, update: (_ref, value) => {record = {...record, ...value}; updates++;}})};
  const folder = process.argv[2];
  const output = await enrollDevice({db, deviceId: 'test-device', boardId: feather, folder});
  const bytes = readFileSync(output, 'utf8');
  assert.match(bytes, new RegExp('BOARD_ID=' + feather));
  assert.equal(record.otaBoardId, feather);
  assert.equal(record.otaCredentialHash.length, 64);
  assert.equal(record.firmwareTarget.enabled, false);
  await assert.rejects(() => enrollDevice({db, deviceId: 'test-device', boardId: feather, folder}));
  assert.equal(updates, 1);
  assert.equal(readFileSync(output, 'utf8'), bytes);
  record = {enabled: true};
  await assert.rejects(() => enrollDevice({db, deviceId: 'test-device', boardId: feather, folder}));
  assert.equal(updates, 1);
  assert.equal(readFileSync(output, 'utf8'), bytes);
})().catch(error => {console.error(error.message); process.exitCode = 1;});
"""
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run(
                [
                    str(ROOT / "node_modules/.bin/node"),
                    "-e",
                    script,
                    str(ROOT / "tools/firmware_admin.cjs"),
                    temporary,
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_make_enrollment_passes_explicit_board_identity(self):
        result = subprocess.run(
            ["make", "-n", "ota-enroll", "DEVICE_ID=test-device", f"BOARD_ID={FEATHER}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn(f'BOARD_ID="{FEATHER}"', result.stdout)


class FeatherReleaseBuildTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "OTA Fixture")
        self.git("config", "core.hooksPath", "/dev/null")
        for name, text in {
            ".gitignore": "artifacts/\n",
            "circuitpython/drawbridge.py": "APP_VERSION='1.1.0'\nAPP_API_VERSION=2\n",
            "circuitpython/lib/gate_base.py": "BASE_VERSION='1.0.15'\n",
            "circuitpython/boot.py": "# USB fixture\n",
        }.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        self.git("add", ".")
        self.git("commit", "-qm", "Fixture")
        self.git("tag", "firmware-v1.1.0")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, text=True).strip()

    def build(self, version="1.1.0"):
        run_process = subprocess.run
        test_runs = []

        def run(command, **kwargs):
            if command[0] == str(self.root / ".venv/bin/python"):
                test_runs.append((command, kwargs))
                return subprocess.CompletedProcess(command, 0)
            return run_process(command, **kwargs)

        with (
            patch.object(firmware_release, "ROOT", self.root),
            patch("firmware_release.subprocess.run", side_effect=run),
        ):
            output = firmware_release.build_release(version)
            self.assertEqual(len(test_runs), 1)
            self.assertEqual(test_runs[0][1]["check"], True)
            return output

    def test_clean_tag_build_emits_feather_metadata_and_preserves_existing_release_bytes(self):
        output = self.build()
        manifest = json.loads((output / "manifest.json").read_text())
        self.assertEqual(manifest["supported_board_ids"], [FEATHER])
        self.assertEqual(manifest["app_api_version"], 2)
        before = {path.name: path.read_bytes() for path in output.iterdir()}
        self.build()
        self.assertEqual(before, {path.name: path.read_bytes() for path in output.iterdir()})
        (output / "manifest.json").write_text("existing immutable release")
        with self.assertRaisesRegex(ValueError, "existing release"):
            self.build()
        self.assertEqual((output / "manifest.json").read_text(), "existing immutable release")

    def test_legacy_tag_build_remains_xiao_only(self):
        app = self.root / "circuitpython/drawbridge.py"
        app.write_text("APP_VERSION='1.0.0'\nAPP_API_VERSION=1\n")
        self.git("add", "circuitpython/drawbridge.py")
        self.git("commit", "-qm", "Legacy fixture")
        self.git("tag", "firmware-v1.0.0")
        output = self.build("1.0.0")
        manifest = json.loads((output / "manifest.json").read_text())
        self.assertEqual(manifest["supported_board_ids"], [XIAO])
        self.assertEqual(manifest["app_api_version"], 1)
        self.assertEqual(manifest["minimum_bootstrap_version"], "1.0.0")

    def test_dirty_or_retagged_source_never_builds(self):
        (self.root / "untracked.txt").write_text("dirty")
        with self.assertRaisesRegex(ValueError, "Commit all"):
            self.build()
        self.git("add", "untracked.txt")
        self.git("commit", "-qm", "New head")
        with self.assertRaisesRegex(ValueError, "tag must point"):
            self.build()


class EnrollmentFileParsingTests(unittest.TestCase):
    def test_explicit_environment_preserves_literal_file_values_and_default_behavior(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "device.env"
            path.write_text('export DEVICE_ID="file-device"\nBOARD_ID=literal-board\n')
            with patch.dict(os.environ, {"DEVICE_ID": "ambient-device"}, clear=True):
                self.assertEqual(load_dotenv(path)["DEVICE_ID"], "ambient-device")
                self.assertEqual(load_dotenv(path, environ={})["DEVICE_ID"], "file-device")
                self.assertEqual(load_dotenv(path, environ={})["BOARD_ID"], "literal-board")
