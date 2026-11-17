"""Saved network management without hardware or private credentials."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.append(str(Path(__file__).parents[1] / "circuitpython/lib"))
from gate_wifi import profiles, update_network, forget_network, connection_order


class ProfileTests(unittest.TestCase):
    def test_profile_updates_work_with_circuitpython_one_argument_next(self):
        import gate_wifi

        def device_next(iterator):
            return next(iterator)

        with patch.object(gate_wifi, "next", device_next, create=True):
            config = update_network({}, "Example", "test-pass")
            config = update_network(config, "Other", "test-pass")
            config = update_network(config, "Example", "updated-test-pass")
        self.assertEqual(len(profiles(config)), 2)
        self.assertEqual(profiles(config)[0]["password"], "updated-test-pass")

    def test_legacy_profile_is_preserved_when_adding_another(self):
        original = {"ssid": "Old", "password": "old-test-pass", "mqtt_password": "identity"}  # pragma: allowlist secret
        updated = update_network(original, "New", "new-test-pass")
        self.assertEqual([p["ssid"] for p in profiles(updated)], ["Old", "New"])
        self.assertEqual(updated["mqtt_password"], "identity")
        self.assertNotIn("wifi_networks", original)

    def test_update_without_password_preserves_existing_and_explicit_open_clears(self):
        config = update_network({}, "One", "test-pass")
        self.assertEqual(profiles(update_network(config, "One", ""))[0]["password"], "test-pass")
        self.assertEqual(profiles(update_network(config, "One", "", open_network=True))[0]["password"], "")

    def test_forgetting_active_selects_remaining_without_losing_identity(self):
        config = update_network({"ssid": "One", "password": "test-pass", "registration_complete": True}, "Two", "")
        config = forget_network(config, "One")
        self.assertEqual(config["ssid"], "Two")
        self.assertTrue(config["registration_complete"])
        config = forget_network(config, "Two")
        self.assertEqual(profiles(config), [])
        self.assertNotIn("password", config)

    def test_limits_and_invalid_input_do_not_change_original(self):
        config = {}
        for n in range(5):
            config = update_network(config, str(n), "test-pass")
        for ssid, password in [("six", "test-pass"), ("x"*33, "test-pass"), ("", "test-pass"), ("0", "short")]:
            with self.assertRaises(ValueError):
                update_network(config, ssid, password)
        self.assertEqual(len(profiles(config)), 5)

    def test_visible_preferred_then_alternative_then_hidden(self):
        config = {"ssid": "Old", "password": "old-test-pass"}  # pragma: allowlist secret
        config = update_network(config, "Here", "test-pass")
        self.assertEqual([p["ssid"] for p in connection_order(config, [{"ssid": "Here", "rssi": -50}])], ["Here", "Old"])
        self.assertEqual([p["ssid"] for p in connection_order(config, [{"ssid": "Old", "rssi": -70}, {"ssid": "Here", "rssi": -30}])], ["Old", "Here"])


class PortalTests(unittest.TestCase):
    def test_portal_is_branded_offline_and_escapes_network_names(self):
        from gate_portal import render_page
        html = render_page("<script>bad</script>", [{"ssid": '<img onerror="bad">', "rssi": -40}], ["Home & Office"], "AB12CD")
        self.assertIn("#173f35", html)
        self.assertIn("<svg", html)
        self.assertIn("Home &amp; Office", html)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img", html)
        self.assertNotIn("https://", html)
        self.assertIn('name="wifi_action" value="forget"', html)
        self.assertIn('name="open_network"', html)
        self.assertNotIn('formmethod="get"', html)
        self.assertIn('href="/scan"', html)

    def test_confirmation_names_network_safely_and_counts_down(self):
        from gate_portal import render_confirmation
        html = render_confirmation('Example <Studio> & "Office"')
        self.assertIn('Example &lt;Studio&gt; &amp; &quot;Office&quot;', html)
        self.assertIn('Setup Wi-Fi closes in 10 seconds.', html)
        self.assertIn('Your other saved networks are unchanged.', html)
        self.assertNotIn('<form', html)
        self.assertIn('Network removed', render_confirmation('Example', forgotten=True))
