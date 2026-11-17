"""One-shot reboot intent and coordinated reset state, without physical I/O."""

from pathlib import Path
import sys
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1] / "circuitpython/lib"))
from gate_setup import ButtonEdge, cleared_setup_config, consume_next_boot, pending_reset_config, toggle_next_boot


class SetupControlTests(unittest.TestCase):
    def test_selection_is_persistent_one_shot_and_preserves_identity(self):
        original = {"wifi_networks": [{"ssid": "Example", "password": ""}], "pairing_secret": "a" * 64,
                    "mqtt_username": "test-user", "registration_complete": True}
        selected = toggle_next_boot(original)
        self.assertTrue(selected["next_boot_setup"])
        self.assertNotIn("next_boot_setup", original)
        cancelled = toggle_next_boot(selected)
        self.assertNotIn("next_boot_setup", cancelled)
        consumed, requested = consume_next_boot(selected)
        self.assertTrue(requested)
        self.assertEqual(consumed, original)
        again, requested = consume_next_boot(consumed)
        self.assertFalse(requested)
        self.assertEqual(again, original)

    def test_button_has_one_event_per_stable_press_and_honors_initial_polarity(self):
        button = ButtonEdge(False, 0)
        self.assertFalse(button.update(True, .01))
        self.assertFalse(button.update(False, .02))
        self.assertFalse(button.update(True, .03))
        self.assertTrue(button.update(True, .08))
        self.assertFalse(button.update(True, 10))
        self.assertFalse(button.update(False, 10.01))
        self.assertFalse(button.update(False, 10.07))
        self.assertFalse(button.update(True, 11))
        self.assertTrue(button.update(True, 11.06))
        initially_held = ButtonEdge(True, 0)
        self.assertFalse(initially_held.update(True, 1))
        initially_held.sync(False, 2)
        self.assertFalse(initially_held.update(True, 3))
        self.assertTrue(initially_held.update(True, 3.1))

    def test_reset_marker_retains_credentials_until_ack_then_clears_only_local_setup(self):
        original = {"ssid": "Example", "password": "", "pairing_secret": "a" * 64,
                    "mqtt_username": "test-user", "registration_complete": True, "next_boot_setup": True}
        reset_id = "b" * 64
        pending = pending_reset_config(original, reset_id)
        self.assertEqual(pending["ssid"], "Example")
        self.assertEqual(pending["mqtt_username"], "test-user")
        self.assertTrue(pending["setup_reset_pending"])
        self.assertNotIn("setup_reset_id", original)
        cleared = cleared_setup_config(pending, reset_id)
        self.assertEqual(cleared, {"pairing_secret": "a" * 64, "setup_reset_id": reset_id,
                                   "registration_pending": True, "wifi_networks": []})
        self.assertTrue(pending["registration_complete"])
        self.assertEqual(pending["ssid"], "Example")
        with self.assertRaises(ValueError):
            cleared_setup_config(pending, "c" * 64)
        with self.assertRaises(ValueError):
            pending_reset_config(original, "invalid")


class RuntimeSetupTests(unittest.TestCase):
    def setUp(self):
        from test_regressions import ConfigTests
        ConfigTests.setUp(self, board_id="adafruit_feather_esp32s3_reverse_tft")
        self.app.application_ui = self.app.create_app(self.app.Platform(),0).create_ui(None,self.app.device_suffix())

    def test_buttons_have_separate_polarities_and_preserve_fresh_identity(self):
        from unittest.mock import patch
        self.app.initialize_buttons()
        self.assertEqual(len(self.app.ui_buttons), 3)
        self.assertFalse(self.app.ui_buttons[0][1])
        self.assertTrue(self.app.ui_buttons[1][1])
        self.assertTrue(self.app.ui_buttons[2][1])
        fresh = {"pairing_secret": "01"*32, "registration_complete": True}
        with patch.object(self.app, "load_config", return_value=fresh), patch.object(self.app, "save_config") as save:
            self.app.button_action(2, 100)
        self.assertTrue(save.call_args.args[0]["registration_complete"])
        self.assertTrue(self.app.next_boot_setup)
        self.app.button_action(0, 100)
        self.assertEqual(self.app.application_ui.website_until, 120)
        self.app.button_action(1, 101)
        self.assertEqual(self.app.application_ui.website_until, 0)

    def test_failed_reset_cleanup_keeps_pending_config_and_never_reloads(self):
        from unittest.mock import patch
        config = pending_reset_config({"pairing_secret":"01"*32, "ssid":"Example", "mqtt_password":"test-only"}, "a"*64)
        with patch.object(self.app, "registration_request", return_value={"state":"awaiting_setup", "setup_reset_id":"a"*64}), patch.object(self.app, "save_config", side_effect=OSError("NVM unavailable")), patch.object(self.app.supervisor, "reload") as reload:
            with self.assertRaises(OSError):
                self.app.finish_setup_reset(object(), config)
            reload.assert_not_called()
        self.assertEqual(config["ssid"], "Example")
        self.assertTrue(config["setup_reset_pending"])

    def test_maintenance_defers_for_actual_hold_and_saves_before_closing(self):
        from unittest.mock import MagicMock, patch
        config = {"pairing_secret":"01"*32, "registration_complete":True, "registration_acknowledged":True}
        client = MagicMock()
        response = {"restartSetup":{"id":"a"*64,"state":"pending"}}
        events = []
        with patch.object(self.app.hold, "active", return_value=True), patch.object(self.app, "registration_request") as request:
            self.assertFalse(self.app.check_maintenance(object(), config, client))
            request.assert_not_called()
        with patch.object(self.app.hold, "active", side_effect=[False, True]), patch.object(self.app, "registration_request", return_value=response), patch.object(self.app, "save_config") as save:
            self.assertFalse(self.app.check_maintenance(object(), config, client))
            save.assert_not_called()
        with patch.object(self.app.hold, "active", return_value=False), patch.object(self.app, "registration_request", return_value=response), patch.object(self.app, "save_config", side_effect=lambda c: events.append("save")):
            client.close.side_effect = lambda: events.append("close")
            self.assertTrue(self.app.check_maintenance(object(), config, client))
        self.assertEqual(events, ["save", "close"])
        self.assertTrue(config["setup_reset_pending"])

    def test_wifi_reconnect_preserves_button_choice_saved_in_service_callback(self):
        from unittest.mock import patch
        config = {"ssid":"Old", "password":"", "wifi_networks":[{"ssid":"New","password":""}], "registration_complete":True}
        self.app.save_config(config)
        services = []
        def service():
            services.append(True)
            if len(services) == 2:
                self.app.button_action(2, 100)
        with patch.object(self.app,"scan_networks", return_value=[]):
            self.app.connect_saved_wifi(config, service)
        saved = self.app.load_config()
        self.assertEqual(saved["ssid"], "New")
        self.assertTrue(saved["next_boot_setup"])
        self.assertTrue(config["next_boot_setup"])

    def test_payload_carries_generation_and_only_maintenance_has_versions(self):
        from device_enrollment import registration_payload
        for action in (None, "complete", "restart_setup_complete", "maintenance"):
            body = registration_payload("ab12cd", "01"*32, action, setup_reset_id="a"*64, app_version="1.0.1", base_version="1.0.13")
            self.assertEqual(body["setup_reset_id"], "a"*64)
            self.assertEqual("base_version" in body, action == "maintenance")
        with self.assertRaises(ValueError):
            registration_payload("ab12cd", "01"*32, "restart_setup_complete")


    def test_ack_must_match_device_and_generation_before_local_save(self):
        from unittest.mock import MagicMock, mock_open, patch
        config = {"pairing_secret":"01"*32,"setup_reset_id":"a"*64}
        for body in ({"deviceId":"wrong","state":"awaiting_setup","setup_reset_id":"a"*64},
                     {"deviceId":self.app.device_suffix().lower(),"state":"awaiting_setup","setup_reset_id":"b"*64}):
            response = MagicMock(status_code=200)
            response.json.return_value = body
            session = MagicMock()
            session.post.return_value = response
            with patch.object(self.app.ssl, "create_default_context"), patch("builtins.open", mock_open(read_data="public-root")), patch.object(self.app.adafruit_requests, "Session", return_value=session):
                with self.assertRaises(ValueError):
                    self.app.registration_request(object(), config, "restart_setup_complete")
            response.close.assert_called_once()

    def test_pending_reset_boot_retries_ack_without_connecting_mqtt(self):
        from unittest.mock import patch
        config = {"setup_reset_pending":True,"mqtt_command_topic":"test-command"}
        self.app.wifi.radio.connected = True
        # One failed ACK, then loop resumes and attempts it again, never MQTT.
        with patch.object(self.app, "service_outputs"), patch.object(self.app.time, "monotonic", side_effect=[0,0,21,22,42,43]), patch.object(self.app.time,"sleep"), patch.object(self.app, "finish_setup_reset", side_effect=[OSError("lost ACK"), KeyboardInterrupt]) as finish, patch.object(self.app,"connect_mqtt") as mqtt:
            with self.assertRaises(KeyboardInterrupt):
                self.app.run_configured_controller(object(), config)
            self.assertEqual(finish.call_count,2)
            mqtt.assert_not_called()

    def test_website_timeout_returns_to_status_without_touching_control(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock, patch
        self.app.gate_output = SimpleNamespace(value=False)
        self.app.display = MagicMock()
        self.app.application_ui.display = self.app.display
        self.app.application_ui.website_until = 120
        with patch.object(self.app.time, "monotonic", side_effect=[119,120]), patch.object(self.app,"service_status_led"):
            self.app.service_outputs(None, online=True)
            self.app.service_outputs(None, online=True)
        self.app.display.show_website.assert_called_once()
        self.app.display.show_status.assert_called_once()
        self.assertFalse(self.app.gate_output.value)


if __name__ == "__main__":
    unittest.main()
