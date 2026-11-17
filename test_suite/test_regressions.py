"""Host regression tests: real MiniMQTT with simulated hardware boundaries."""

import errno
import importlib.util
import json
from pathlib import Path
import socket
import sys
import tempfile
import time
import tomllib
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from adafruit_minimqtt.adafruit_minimqtt import MQTT, ticks_ms
sys.path.insert(0, str(ROOT / "circuitpython"))
sys.path.insert(0, str(ROOT / "circuitpython/lib"))
from gate_mqtt import GateMQTT, NETWORK_SECONDS
from gate_state import BlinkState, parse_command
from mqtt_blink import command_payload, mqtt_string, packet, publish_mqtt
from env_config import load_dotenv
from render_settings_toml import render_settings
from test_mqtt_cycles import verify_event
from deploy import deploy


class WireSocket:
    """A byte-fragmenting socket; emulate CircuitPython's timeout behavior."""
    def __init__(self, incoming=b"", timeout=5):
        self.incoming = bytearray(incoming)
        self.timeout = timeout
        self.read_timeouts = []
        self.sent = []

    def settimeout(self, value):
        self.timeout = value

    def recv_into(self, buffer, count=None):
        self.read_timeouts.append(self.timeout)
        if not self.incoming:
            time.sleep(min(self.timeout, 0.01))
            raise OSError(errno.ETIMEDOUT, "timed out")
        count = min(len(buffer), count or len(buffer), 3, len(self.incoming))
        buffer[:count] = self.incoming[:count]
        del self.incoming[:count]
        return count

    def recv(self, count):
        # Publisher expects an EOF when no more fake responses remain.
        chunk = bytes(self.incoming[:min(count, 3)])
        del self.incoming[:len(chunk)]
        return chunk

    def send(self, data):
        self.sent.append(bytes(data))
        return len(data)

    def sendall(self, data):
        self.sent.append(bytes(data))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class MQTTRegressionTests(unittest.TestCase):
    def client(self, incoming=b""):
        client = GateMQTT(broker="unused", socket_pool=socket,
                          socket_timeout=NETWORK_SECONDS, recv_timeout=10)
        client._socket_pool = SimpleNamespace()  # Native socketpool has no .timeout.
        client._sock = WireSocket(incoming)
        client._is_connected = True
        client._last_msg_sent_timestamp = ticks_ms()
        return client

    def test_original_timeout_configuration_reproduces_live_failure(self):
        client = MQTT(broker="unused", socket_pool=socket)
        with self.assertRaisesRegex(ValueError, "must be >= socket timeout"):
            client.loop(timeout=0.02)

    def test_idle_poll_returns_promptly_and_preserves_connection_timeout(self):
        client = self.client()
        started = time.monotonic()
        self.assertIsNone(client.poll())
        self.assertLess(time.monotonic() - started, 0.15)
        self.assertEqual(client._socket_timeout, 5)
        self.assertEqual(client._sock.timeout, 5)
        self.assertTrue(all(t == 0.01 for t in client._sock.read_timeouts))
        self.assertTrue(client.is_connected())

    def test_fragmented_qos1_message_arrives_once_and_is_acknowledged(self):
        payload = command_payload(300, "cycle-one")
        incoming = packet(0x33, mqtt_string("gate/command") + b"\x00\x07" + payload.encode())
        client = self.client(incoming)
        messages = []
        client.on_message = lambda _client, topic, body: messages.append((topic, body))
        client.poll()
        client.poll()
        self.assertEqual(messages, [("gate/command", payload)])
        self.assertEqual(client._sock.sent, [b"\x40\x02\x00\x07"])
        self.assertEqual(client._sock.read_timeouts[0], 0.01)
        self.assertTrue(all(t == 5 for t in client._sock.read_timeouts[1:-6]))
        self.assertEqual(client._sock.timeout, 5)

    def test_network_failure_restores_timeout_and_propagates(self):
        client = self.client()
        with patch.object(client._sock, "recv_into", side_effect=ConnectionError("lost")):
            with self.assertRaises(Exception):
                client.poll()
        self.assertEqual(client._socket_timeout, 5)


class CommandTests(unittest.TestCase):
    def test_alternating_intervals_restart_schedule(self):
        state = BlinkState(0)
        for now, interval in [(0, 2000), (10, 300), (20, 2000), (30, 300)]:
            state.apply(command_payload(interval, str(now)), now)
            self.assertIsNone(state.tick(now + interval / 1000 - .001))
            self.assertAlmostEqual(state.tick(now + interval / 1000 + .001), interval + 1)

    def test_rejects_invalid_types_versions_and_ranges(self):
        for invalid in [None, [], 300, "hello", {}, True]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                parse_command(json.dumps(invalid))
        valid = json.loads(command_payload(300, "test"))
        for key, values in {"version": [True, 2, "1"], "blink_interval_ms": [True, 24, 60001, 300.5, "300"],
                            "command_id": [1, "", "x" * 65], "type": ["other"]}.items():
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    parse_command(json.dumps(dict(valid, **{key: value})))

    def test_bad_command_preserves_last_setting(self):
        state = BlinkState(0)
        state.apply(command_payload(300, "good"), 10)
        with self.assertRaises(ValueError):
            state.apply('{"version":1}', 20)
        self.assertEqual((state.interval_ms, state.command_id, state.last_edge), (300, "good", 10))

    def test_qos1_duplicate_does_not_restart_led_schedule(self):
        state = BlinkState(0)
        payload = command_payload(300, "same")
        self.assertTrue(state.apply(payload, 1))
        self.assertFalse(state.apply(payload, 1.29))
        self.assertAlmostEqual(state.tick(1.301), 301)

    def test_old_messages_without_command_id_remain_compatible(self):
        self.assertEqual(parse_command('{"version":1,"type":"set_blink_interval","blink_interval_ms":2000}'), (2000, None))


class PublisherTests(unittest.TestCase):
    def publish(self, wire):
        context = MagicMock()
        context.wrap_socket.return_value = wire
        with patch("mqtt_blink.socket.create_connection", return_value=wire), \
             patch("mqtt_blink.ssl.create_default_context", return_value=context) as tls:
            result = publish_mqtt("broker", 8883, Path("ca.crt"), "test-user", "test-pass",
                                  "gate/command", 300, command_id="test-id")
        tls.assert_called_once_with(cafile="ca.crt")
        context.wrap_socket.assert_called_once_with(wire, server_hostname="broker")
        return result

    def test_publish_is_retained_qos1_with_correlation_id(self):
        wire = WireSocket(b"\x20\x02\x00\x00\x40\x02\x00\x01")
        self.assertEqual(self.publish(wire), "test-id")
        self.assertEqual(wire.sent[1], packet(0x33, mqtt_string("gate/command") + b"\x00\x01" + command_payload(300, "test-id").encode()))
        self.assertEqual(wire.sent[-1], b"\xe0\x00")

    def test_no_success_without_matching_puback(self):
        for response in [b"", b"\x40\x02\x00\x02"]:
            with self.subTest(response=response), self.assertRaises(ConnectionError):
                self.publish(WireSocket(b"\x20\x02\x00\x00" + response))


class ConfigTests(unittest.TestCase):
    def setUp(self, board_id=None):
        spec = importlib.util.spec_from_file_location("gate_app", ROOT / "circuitpython/code.py")
        self.app = importlib.util.module_from_spec(spec)
        self.nvm = bytearray(512)
        modules = {name: MagicMock() for name in ("board", "digitalio", "wifi", "supervisor")}
        if board_id is not None:
            modules["board"].board_id = board_id
        modules["digitalio"].DigitalInOut.side_effect = lambda pin: MagicMock(value=False)
        modules["microcontroller"] = SimpleNamespace(nvm=self.nvm, cpu=SimpleNamespace(uid=b"123456"))
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(self.app)

    def test_add_network_preserves_existing_registration_and_password(self):
        config = {"ssid": "Old", "password": "old-test-pass", "mqtt_username": "user", "mqtt_password": "identity", "mqtt_topic": "status", "mqtt_command_topic": "command", "registration_complete": True}  # pragma: allowlist secret
        self.app.save_config(config)
        result = self.app.config_from_form({"ssid": "New", "password": "new-test-pass"})
        self.assertEqual([p["ssid"] for p in result["wifi_networks"]], ["Old", "New"])
        self.assertTrue(result["registration_complete"])
        self.assertEqual(result["mqtt_password"], "identity")
        self.assertNotIn("old-test-pass", self.app.page())
        self.assertNotIn("identity", self.app.page())
        self.assertIn("Old", self.app.page())

    def test_wifi_connection_falls_through_and_persists_success_once(self):
        config = {"ssid": "Old", "password": "old-test-pass", "wifi_networks": [{"ssid": "Old", "password": "old-test-pass"}, {"ssid": "New", "password": "new-test-pass"}], "mqtt_password": "identity"}  # pragma: allowlist secret
        self.app.wifi.radio.connect.side_effect = [OSError("unavailable"), None]
        with patch.object(self.app, "scan_networks", return_value=[]), patch.object(self.app, "save_config") as save:
            self.app.connect_saved_wifi(config)
        self.assertEqual(self.app.wifi.radio.connect.call_count, 2)
        self.assertEqual(config["ssid"], "New")
        self.assertEqual(config["mqtt_password"], "identity")
        save.assert_called_once_with(config)

    def test_forgetting_last_network_round_trips_identity(self):
        self.app.save_config({"ssid": "Old", "password": "old-test-pass", "registration_complete": True})  # pragma: allowlist secret
        result = self.app.config_from_form({"wifi_action": "forget", "forget_ssid": "Old"})
        self.app.save_config(result)
        self.assertEqual(self.app.load_config()["wifi_networks"], [])
        self.assertTrue(self.app.load_config()["registration_complete"])

    def test_feather_setup_button_is_active_high_input_and_xiao_does_not_claim_it(self):
        self.app.IS_REVERSE_TFT = True
        button = MagicMock(value=True)
        self.app.digitalio.DigitalInOut.side_effect = lambda pin: button
        self.assertTrue(self.app.setup_requested())
        button.switch_to_input.assert_called_once_with(pull=self.app.digitalio.Pull.DOWN)
        button.deinit.assert_called_once()
        self.app.IS_REVERSE_TFT = False
        self.app.digitalio.DigitalInOut.reset_mock()
        self.assertFalse(self.app.setup_requested())
        self.app.digitalio.DigitalInOut.assert_not_called()

    def test_explicit_setup_never_enters_mqtt_or_registration(self):
        self.app.microcontroller.cpu.reset_reason = "test"
        config = {"ssid": "Old", "password": "test-pass", "mqtt_username": "user", "mqtt_password": "identity", "mqtt_topic": "status", "mqtt_command_topic": "command"}  # pragma: allowlist secret
        with (
            patch.object(self.app, "setup_requested", return_value=True),
            patch.object(self.app, "load_config", return_value=config),
            patch.object(self.app, "initialize_application") as init,
            patch.object(self.app, "service_outputs"),
            patch.object(self.app, "startup_pin_diagnostic"),
            patch.object(self.app, "run_portal", side_effect=KeyboardInterrupt),
            patch.object(self.app, "run_configured_controller") as controller,
            patch.object(self.app, "run_registration") as register,
        ):
            with self.assertRaises(KeyboardInterrupt):
                self.app.main()
        controller.assert_not_called()
        register.assert_not_called()
        init.assert_called_once_with(allow_ota=False)
        self.assertFalse(self.app.gate_output.value)

    def test_portal_response_sends_complete_html_in_small_chunks(self):
        class BoundedClient:
            def __init__(self):
                self.data = bytearray()
                self.sizes = []
                self.attempts = 0

            def send(self, data):
                self.attempts += 1
                if self.attempts == 2:
                    raise OSError(11, "would block")
                count = min(97, len(data))
                self.sizes.append(len(data))
                self.data.extend(data[:count])
                return count

            def sendall(self, data):
                self.sizes.append(len(data))
                if len(data) > 512:
                    raise ValueError("write exceeds bounded socket buffer")
                self.data.extend(data)

        client = BoundedClient()
        body = self.app.page(networks=[])
        with patch.object(self.app.time, "sleep"), patch.object(self.app, "log_event"):
            self.app.send_response(client, body)
        header, payload = bytes(client.data).split(b"\r\n\r\n", 1)
        self.assertEqual(payload, body.encode("utf-8"))
        self.assertIn(b"Content-Length: " + str(len(payload)).encode(), header)
        self.assertIn(b"Save and connect", payload)
        self.assertLessEqual(max(client.sizes), 512)
        self.assertGreater(client.attempts, 2)

    def test_successful_save_closes_socket_before_waiting_and_restarting(self):
        events = []
        client = MagicMock()
        client.close.side_effect = lambda: events.append("close")
        server = MagicMock()
        server.accept.return_value = (client, None)
        with (
            patch.object(self.app, "read_http_request", return_value=(b"POST /configure HTTP/1.1", b"")),
            patch.object(self.app, "config_from_form", return_value={"ssid": "Example"}),
            patch.object(self.app, "save_config"),
            patch.object(self.app, "log_event"),
            patch.object(self.app, "send_response", side_effect=lambda *args: events.append("send")),
            patch.object(self.app.time, "sleep", side_effect=lambda seconds: events.append("wait")),
            patch.object(self.app.supervisor, "reload", side_effect=lambda: events.append("reload")),
        ):
            self.app.service_http(server)
        self.assertEqual(events, ["send", "close", "wait", "reload"])

    def test_pairing_secret_persists_once_and_registration_posts_private_proof(self):
        config = {"ssid": "Example", "password": ""}
        with patch.object(self.app, "save_config") as save:
            self.app.ensure_pairing_config(config)
            first = config["pairing_secret"]
            self.app.ensure_pairing_config(config)
        self.assertEqual(len(first), 64)
        self.assertEqual(save.call_count, 1)
        response = MagicMock(status_code=400)
        session = MagicMock()
        session.post.return_value = response
        with patch.object(self.app.ssl, "create_default_context"), patch("builtins.open", unittest.mock.mock_open(read_data="public-root")), patch.object(self.app.adafruit_requests, "Session", return_value=session):
            self.assertIsNone(self.app.registration_request(object(), config))
        posted = session.post.call_args.kwargs["json"]
        self.assertEqual(posted["device_secret"], first)
        self.assertNotIn(first, session.post.call_args.args[0])
        response.close.assert_called_once()

    def test_pairing_completion_is_saved_only_after_server_ack(self):
        config = {"pairing_secret": "01"*32, "registration_complete": True}
        with patch.object(self.app, "registration_request", return_value=None), patch.object(self.app, "save_config") as save:
            self.assertFalse(self.app.complete_registration(object(), config))
            save.assert_not_called()
        with patch.object(self.app, "registration_request", return_value={"state":"registered"}), patch.object(self.app, "save_config") as save:
            self.assertTrue(self.app.complete_registration(object(), config))
            self.assertTrue(config["registration_acknowledged"])
            save.assert_called_once_with(config)

    def test_nvm_record_larger_than_one_byte_length(self):
        config = {"ssid": "test", "password": "p" * 63, "mqtt_password": "q" * 128, "mqtt_topic": "gate/test/status"}
        self.assertGreater(len(json.dumps(config)), 255)
        self.app.save_config(config)
        self.assertEqual(self.app.load_config(), config)

    def test_transistor_control_uses_d10(self):
        self.assertIs(self.app.TRANSISTOR_CONTROL_PIN, self.app.board.D10)

    def test_loads_both_legacy_nvm_formats(self):
        payload = b'{"ssid":"test","password":"testpass"}'  # pragma: allowlist secret
        for magic in (b"GATE1", b"GATE2"):
            self.nvm[:6 + len(payload)] = magic + bytes([len(payload)]) + payload
            self.assertEqual(self.app.load_config(), json.loads(payload))

    def test_incomplete_or_oversized_http_body_rejected(self):
        for data in [b"POST /configure HTTP/1.1\r\nContent-Length: 4097\r\n\r\n", b"POST /configure HTTP/1.1\r\nContent-Length: 5\r\n\r\na"]:
            with self.assertRaises((OSError, ValueError)):
                self.app.read_http_request(WireSocket(data))

    def test_fragmented_form_body_is_complete(self):
        body = b"ssid=test&password=eight%2Bchars" * 40
        header = b"POST /configure HTTP/1.1\r\nContent-Length: " + str(len(body)).encode()
        self.assertEqual(self.app.read_http_request(WireSocket(header + b"\r\n\r\n" + body)), (header, body))

    def test_settings_and_publisher_share_literal_credential_parser(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {}, clear=True):
            env = Path(directory) / ".env"
            settings = Path(directory) / "settings.toml"
            env.write_text('MQTT_USERNAME=old\nexport MQTT_USERNAME="new"\nMQTT_PASSWORD=\'space # dollar$\'\nEMQX_APP_SECRET=private\n')
            settings.write_text('OTHER_SETTING = 1\nMQTT_USERNAME="stale"\n')
            parsed = tomllib.loads(render_settings(env, settings))
            self.assertEqual(parsed["MQTT_USERNAME"], load_dotenv(env)["MQTT_USERNAME"])
            self.assertEqual(parsed["MQTT_PASSWORD"], "space # dollar$")
            self.assertEqual(parsed["OTHER_SETTING"], 1)
            self.assertNotIn("EMQX_APP_SECRET", parsed)


class HardwareTestGuardTests(unittest.TestCase):
    def test_session_losses_fail_even_if_interval_still_matches(self):
        for kind in ("boot", "connection_error", "mqtt_connected", "unexpected_reset", "serial_error"):
            with self.subTest(kind=kind), self.assertRaises(AssertionError):
                verify_event({"event": kind, "boot_id": "original"}, "original")
        with self.assertRaises(AssertionError):
            verify_event({"event": "led_edge", "boot_id": "new"}, "original")


class DeploymentTests(unittest.TestCase):
    def test_updates_existing_library_and_preserves_unrelated_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "circuitpython/lib").mkdir(parents=True)
            (root / "circuitpython/certs").mkdir()
            (root / "circuitpython/certs/google-roots.pem").write_text("public Google roots")
            (root / "board/lib").mkdir(parents=True)
            (root / "circuitpython/lib/fix.py").write_text("new library")
            (root / "circuitpython/drawbridge.py").write_text("# app\n")
            (root / "circuitpython/boot.py").write_text("# boot\n")
            (root / "circuitpython/code.py").write_text("new code")
            (root / "emqxsl-ca.crt").write_text("test cert")
            (root / ".env").write_text("MQTT_USERNAME=test\nMQTT_PASSWORD=secret\n")
            (root / "board/boot_out.txt").write_text("CircuitPython")
            (root / "board/lib/fix.py").write_text("old library")
            (root / "board/preserve.txt").write_text("keep")
            import os
            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                with patch("deploy.REPOSITORY", root), \
                     patch("deploy.render_settings", return_value='MQTT_USERNAME="test"\n'), \
                     patch("deploy.os.sync"), patch("builtins.print"):
                    deploy(root / "board")
                    self.assertEqual((root / "board/lib/fix.py").read_text(), "new library")
                    self.assertEqual((root / "board/preserve.txt").read_text(), "keep")
                    with patch.object(Path, "write_bytes", side_effect=AssertionError("unnecessary write")):
                        deploy(root / "board")
            finally:
                os.chdir(old_cwd)

    def test_deploy_paths_follow_repository_not_caller(self):
        from deploy import REPOSITORY
        self.assertTrue((REPOSITORY / "circuitpython").is_dir())


if __name__ == "__main__":
    unittest.main()
