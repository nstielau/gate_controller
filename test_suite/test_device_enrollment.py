import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).parents[1] / "circuitpython" / "lib" / "device_enrollment.py"
spec = importlib.util.spec_from_file_location("device_enrollment", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ScanEntry:
    def __init__(self, ssid, rssi, authmode):
        self.ssid = ssid
        self.rssi = rssi
        self.authmode = authmode


class EnrollmentTests(unittest.TestCase):
    def test_open_and_wpa_networks_are_deduplicated_by_strongest_signal(self):
        entries = [
            ScanEntry("Cafe", -70, "OPEN"),
            ScanEntry("Cafe", -45, "OPEN"),
            ScanEntry("Home", -60, "WPA2"),
            ScanEntry("", -20, "WPA2"),
            ScanEntry("Legacy", -30, "WEP"),
            ScanEntry("Enterprise", -25, "WPA2_ENT"),
        ]
        self.assertEqual(module.visible_networks(entries), [
            {"ssid": "Cafe", "rssi": -45, "security": "open"},
            {"ssid": "Home", "rssi": -60, "security": "wpa"},
        ])

    def test_registration_payload_and_response_are_bounded(self):
        self.assertEqual(module.registration_payload("AB12CD"), {"device_id": "ab12cd"})
        parsed = module.parse_registration_response({
            "deviceId": "ab12cd", "username": "gate-ab12cd", "password": "pw", # pragma: allowlist secret
            "brokerHost": "broker.example", "brokerPort": 8883,
            "commandTopic": "gate/v1/devices/ab12cd/command",
            "statusTopic": "gate/v1/devices/ab12cd/status",
        })
        self.assertEqual(parsed["mqtt_username"], "gate-ab12cd")
        self.assertEqual(parsed["mqtt_password"], "pw") # pragma: allowlist secret
        with self.assertRaises(ValueError):
            module.registration_payload("bad id")
        with self.assertRaises(ValueError):
            module.parse_registration_response({"username": "x"})

    def test_registration_settings_replace_shared_mqtt_values(self):
        current = {"ssid": "Home", "password": "wifi", "mqtt_username": "old", "mqtt_password": "old"} # pragma: allowlist secret
        updated = module.apply_registration(current, {"deviceId": "ab12cd", "username": "gate-ab12cd", "password": "pw", "commandTopic": "gate/v1/devices/ab12cd/command", "statusTopic": "gate/v1/devices/ab12cd/status"}) # pragma: allowlist secret
        self.assertEqual(updated["mqtt_username"], "gate-ab12cd")
        self.assertEqual(updated["mqtt_password"], "pw") # pragma: allowlist secret
        self.assertEqual(updated["mqtt_command_topic"], "gate/v1/devices/ab12cd/command")
        self.assertEqual(updated["mqtt_topic"], "gate/v1/devices/ab12cd/status")


if __name__ == "__main__":
    unittest.main()
