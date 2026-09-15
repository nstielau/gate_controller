"""OTA power-loss, integrity, transport, app lease and recovery regressions."""

import json
from pathlib import Path
import sys
import tempfile
import runpy
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock, mock_open
import test_regressions as regressions

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "circuitpython/lib"))
sys.path.insert(0, str(ROOT / "circuitpython"))
from gate_ota import UpdateStore, digest, validate_manifest
from gate_http import Response, DeviceHTTP
from drawbridge import create_app


def manifest(data=b"APP_VERSION = '1.0.0'\n", sequence=1):
    return {
        "schema": 1,
        "app_version": "1.0.0",
        "app_api_version": 1,
        "minimum_bootstrap_version": "1.0.0",
        "circuitpython_major": 10,
        "supported_board_ids": ["seeed_xiao_esp32_s3_sense"],
        "sequence": sequence,
        "size": len(data),
        "sha256": digest(data),
    }


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name + "/ota"
        self.store = UpdateStore(self.root, sync=lambda: None)
        self.data = b"APP_VERSION = '1.0.0'\n"

    def stage(self, sequence=1, data=None):
        data = data or self.data
        return self.store.stage(manifest(data, sequence), [data], lambda: None)

    def reload(self):
        self.store = UpdateStore(self.root, sync=lambda: None)
        return self.store

    def test_confirmed_update_and_explicit_rollback_deployment(self):
        self.assertTrue(self.stage())
        path, item = self.reload().begin_boot()
        self.assertEqual(Path(path).read_bytes(), self.data)
        self.assertEqual(item["sequence"], 1)
        self.store.confirm()
        self.assertFalse(self.stage())
        self.assertTrue(self.stage(2))
        self.reload().begin_boot()
        self.store.confirm()
        self.assertEqual(self.reload().state["active"]["sequence"], 2)

    def test_unconfirmed_trial_boot_rolls_back_without_retry(self):
        self.stage()
        self.reload().begin_boot()
        self.assertEqual(self.reload().begin_boot(), (None, None))
        self.assertEqual(self.store.state["outcome"], "rolled_back")
        self.assertFalse(self.stage())

    def test_previous_active_survives_new_trial_crash(self):
        self.stage()
        self.reload().begin_boot()
        self.store.confirm()
        original = self.store.path(self.store.state["active"])
        self.stage(2, b"raise RuntimeError('bad release')\n")
        self.reload().begin_boot()
        path, item = self.reload().begin_boot()
        self.assertEqual(path, original)
        self.assertEqual(item["sequence"], 1)

    def test_torn_state_or_corrupt_app_never_executes_unverified_bytes(self):
        self.stage()
        self.reload().begin_boot()
        self.store.confirm()
        self.stage(2, b"candidate")
        latest = Path(self.root) / f"state{self.store.state['generation'] % 2}.json"
        latest.write_text('{"body":')
        path, item = self.reload().begin_boot()
        self.assertEqual(Path(path).read_bytes(), self.data)
        Path(path).write_text("corrupt")
        self.assertEqual(self.reload().begin_boot(), (None, None))

    def test_failed_download_and_hold_abort_preserve_active(self):
        self.stage()
        self.reload().begin_boot()
        self.store.confirm()
        previous = dict(self.store.state)
        for chunks in ([b"bad"], [self.data + b"too long"]):
            with self.assertRaises(ValueError):
                self.store.stage(manifest(self.data, 2), chunks, lambda: None)
            self.assertEqual(self.reload().state, previous)

        def hold():
            raise OSError("hold_active")

        with self.assertRaises(OSError):
            self.store.stage(manifest(self.data, 2), [self.data], hold)
        self.assertEqual(self.reload().state, previous)

    def test_power_loss_before_journal_commit_leaves_active(self):
        self.stage()
        self.reload().begin_boot()
        self.store.confirm()
        previous = self.store.state["active"]
        with patch.object(self.store, "save", side_effect=OSError("power loss")):
            with self.assertRaises(OSError):
                self.stage(2)
        _, item = self.reload().begin_boot()
        self.assertEqual(item, previous)

    def test_size_and_compatibility_checks(self):
        good = manifest()
        validate_manifest(good, "seeed_xiao_esp32_s3_sense", 10)
        for changes in (
            {"schema": True},
            {"size": 0},
            {"size": 65537},
            {"size": True},
            {"sha256": "abc"},
            {"app_version": "../bad"},
            {"sequence": True},
            {"sequence": 0},
            {"supported_board_ids": ["other"]},
        ):
            with self.assertRaises(ValueError):
                validate_manifest(dict(good, **changes), "seeed_xiao_esp32_s3_sense", 10)
        with self.assertRaises(ValueError):
            validate_manifest(good, "other", 10)
        with patch("gate_ota.os.statvfs", return_value=(512, 512, 0, 0, 0)):
            with self.assertRaises(OSError):
                self.stage()


class Wire:
    def __init__(self, data):
        self.data = bytearray(data)

    def recv_into(self, buf):
        count = min(len(buf), len(self.data), 3)
        buf[:count] = self.data[:count]
        del self.data[:count]
        return count


class BootstrapTests(unittest.TestCase):
    setUp = regressions.ConfigTests.setUp

    def test_boot_ownership_requires_opt_in_board_and_recovery_pin_high(self):
        for enabled, board_id, pin_high, writable in [
            (None, "seeed_xiao_esp32_s3_sense", True, False),
            (1, "other", True, False),
            (1, "seeed_xiao_esp32_s3_sense", False, False),
            (1, "seeed_xiao_esp32_s3_sense", True, True),
            ("1", "seeed_xiao_esp32_s3_sense", False, False),
            ("1", "seeed_xiao_esp32_s3_sense", True, True),
            ("0", "seeed_xiao_esp32_s3_sense", True, False),
        ]:
            storage, digitalio = MagicMock(), MagicMock()
            digitalio.DigitalInOut.return_value.__enter__.return_value.value = pin_high
            modules = {
                "storage": storage,
                "digitalio": digitalio,
                "board": SimpleNamespace(board_id=board_id, D9="recovery"),
            }
            with patch.dict(sys.modules, modules), patch("os.getenv", return_value=enabled):
                runpy.run_path(str(ROOT / "circuitpython/boot.py"))
            if writable:
                storage.remount.assert_called_once_with("/", readonly=False)
            else:
                storage.remount.assert_not_called()

    def test_maintenance_mode_never_loads_ota_candidate(self):
        self.app.board.board_id = "seeed_xiao_esp32_s3_sense"
        storage = SimpleNamespace(getmount=lambda _: SimpleNamespace(readonly=True))
        with (
            patch.dict(sys.modules, {"storage": storage}),
            patch("os.getenv", return_value=1),
            patch("gate_ota.UpdateStore") as store,
        ):
            self.app.initialize_application()
        store.assert_not_called()
        self.assertIsNone(self.app.ota_store)
        self.assertEqual(type(self.app.application).__name__, "App")

    def test_unprovisioned_device_never_starts_update_watchdog(self):
        self.app.board.board_id = "seeed_xiao_esp32_s3_sense"
        with patch("os.getenv", return_value=1), patch("gate_ota.UpdateStore") as store:
            self.app.initialize_application(allow_ota=False)
        store.assert_not_called()
        self.assertIsNone(self.app.watchdog_timer)

    def test_trial_requires_continuous_online_health_then_rolls_back_on_timeout(self):
        app = self.app
        app.ota_store = MagicMock(state={"trial": {"sequence": 1}})
        app.ota_trial_started = 0
        app.wifi.radio.connected = True
        client = MagicMock()
        with patch.object(app.time, "monotonic", return_value=10):
            app.ota_service(None, client)
        with patch.object(app.time, "monotonic", return_value=50):
            app.ota_service(None, None)
        self.assertIsNone(app.ota_healthy_since)
        with patch.object(app.time, "monotonic", return_value=60):
            app.ota_service(None, client)
        with patch.object(app.time, "monotonic", return_value=119):
            app.ota_service(None, client)
        app.ota_store.confirm.assert_not_called()
        with patch.object(app.time, "monotonic", return_value=120), patch.object(app, "log_event"):
            app.ota_service(None, client)
        app.ota_store.confirm.assert_called_once()
        with patch.object(app.time, "monotonic", return_value=301):
            app.ota_service(None, None)
        app.ota_store.rollback.assert_called_once()
        app.supervisor.reload.assert_called_once()

    def test_reports_running_base_and_app_independently(self):
        app = self.app
        app.ota_version = "1.2.3"
        app.ota_selected = {"sequence": 9}
        app.ota_state = "current"
        app.ota_store = MagicMock(state={"trial": None})
        app.ota_http = MagicMock()
        app.ota_http.request.return_value = None
        app.wifi.radio.connected = True
        with patch.object(app, "indicator_status", return_value={}):
            firmware = json.loads(app.status_payload(None))["firmware"]
        self.assertEqual(firmware["version"], "1.2.3")
        self.assertEqual(firmware["base_version"], app.BASE_VERSION)
        app.ota_service(None, MagicMock())
        report = next(
            c.kwargs["body"] for c in app.ota_http.request.call_args_list if c.args[0] == "report"
        )
        self.assertEqual(
            report,
            {
                "version": "1.2.3",
                "base_version": app.BASE_VERSION,
                "sequence": 9,
                "state": "current",
            },
        )

    def test_active_hold_defers_update_network_calls(self):
        app = self.app
        app.ota_store = MagicMock(state={"trial": None})
        app.hold = MagicMock()
        app.hold.active.return_value = True
        app.wifi.radio.connected = True
        with patch("gate_http.DeviceHTTP") as http:
            app.ota_service(None, MagicMock())
        http.assert_not_called()


class TransportTests(unittest.TestCase):
    def test_tls_socket_ownership_and_redirect_rejection(self):
        for status, error in ((200, False), (302, True)):
            wire = Wire(f"HTTP/1.1 {status} Reply\r\nContent-Length: 2\r\n\r\n{{}}".encode())
            raw, sock, context, pool = MagicMock(), MagicMock(), MagicMock(), MagicMock()
            pool.socket.return_value = raw
            context.wrap_socket.return_value = sock
            sock.send.side_effect = lambda data: min(7, len(data))
            sock.recv_into.side_effect = wire.recv_into
            with (
                patch("gate_http.ssl.create_default_context", return_value=context),
                patch("gate_http.open", mock_open(read_data="public Google roots"), create=True),
            ):
                http = DeviceHTTP(pool, "device", "a" * 64)
                if error:
                    with self.assertRaises(OSError):
                        http.request("manifest", lambda: None, lambda r: r.json())
                else:
                    self.assertEqual(http.request("manifest", lambda: None, lambda r: r.json()), {})
            context.wrap_socket.assert_called_once_with(
                raw, server_hostname="drawbridge-45487.firebaseapp.com"
            )
            context.load_verify_locations.assert_called_once_with(cadata="public Google roots")
            sock.close.assert_called_once()
            raw.close.assert_called_once()

    def response(self, data, limit=4096):
        return Response(Wire(data), limit, lambda: None, float("inf"))

    def test_fragmented_length_and_chunked_bodies(self):
        for data in (
            b"Content-Length: 5\r\n\r\nhello",
            b"Transfer-Encoding: chunked\r\n\r\n2\r\nhe\r\n3\r\nllo\r\n0\r\n\r\n",
        ):
            response = self.response(b"HTTP/1.1 200 OK\r\n" + data)
            self.assertEqual(b"".join(response.chunks()), b"hello")

    def test_circuitpython_buffers_do_not_support_item_deletion(self):
        class CircuitPythonBuffer(bytearray):
            def __delitem__(self, key):
                raise TypeError("'bytearray' object doesn't support item deletion")

            def __getitem__(self, key):
                value = super().__getitem__(key)
                return type(self)(value) if isinstance(key, slice) else value

        with patch("gate_http.bytearray", CircuitPythonBuffer, create=True):
            self.test_fragmented_length_and_chunked_bodies()

    def test_oversize_short_ambiguous_and_compressed_rejected(self):
        for headers in (
            b"Content-Length: 99999",
            b"Content-Length: -1",
            b"Content-Length: 1\r\nTransfer-Encoding: chunked",
            b"Content-Encoding: gzip\r\nContent-Length: 1",
        ):
            with self.assertRaises(ValueError):
                self.response(b"HTTP/1.1 200 OK\r\n" + headers + b"\r\n\r\nx")
        response = self.response(b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\nshort")
        with self.assertRaises(OSError):
            list(response.chunks())
        response = self.response(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\nfffff\r\n")
        with self.assertRaises(ValueError):
            list(response.chunks())

    def test_credentials_and_arbitrary_route_are_rejected_before_network(self):
        with self.assertRaises(ValueError):
            DeviceHTTP(None, "id\r\n", "a" * 64)
        http = DeviceHTTP(None, "test-device", "a" * 64)
        with self.assertRaises(ValueError):
            http.request("https://evil.example/", lambda: None, lambda r: None)

    def test_app_requests_bounded_lease_and_rejects_retained(self):
        class Platform:
            def __init__(self):
                self.calls = []

            def request_hold(self, *args):
                self.calls.append(args)

        p = Platform()
        app = create_app(p, 0)
        msg = json.dumps(
            {"version": 1, "type": "hold_gate", "duration_seconds": 3600, "command_id": "one"}
        )
        app.on_message(msg, False, 10)
        self.assertEqual(p.calls, [(3600, "one", 10)])
        with self.assertRaises(ValueError):
            app.on_message(msg, True, 11)
        self.assertEqual(len(p.calls), 1)
