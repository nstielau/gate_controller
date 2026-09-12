"""Pin-level and scheduler regressions for the independent status LEDs."""

from types import SimpleNamespace
import unittest
from unittest.mock import patch
import test_regressions as regressions
from gate_indicators import Indicators
from gate_hold import HoldState


class IndicatorTests(unittest.TestCase):
    def test_connectivity_led_is_independent_of_hold(self):
        for holding in (False, True):
            state = Indicators(0)
            state.tick(0, False, holding)
            self.assertTrue(state.connection_on)
            state.tick(0.5, False, holding)
            self.assertFalse(state.connection_on)
            state.tick(1, True, holding)
            self.assertTrue(state.connection_on)
            for now in (1.125, 1.25, 2, 100):
                state.tick(now, True, holding)
                self.assertTrue(state.connection_on)
            state.tick(101, False, holding)
            state.tick(101.5, False, holding)
            self.assertFalse(state.connection_on)

    def test_hold_indicator_has_four_full_cycles_per_second(self):
        state = Indicators(0)
        state.tick(0, True, False)
        self.assertFalse(state.hold_on)
        state.tick(1, True, True)
        self.assertTrue(state.hold_on)
        for n in range(1, 9):
            _, elapsed = state.tick(1 + n * 0.125, True, True)
            self.assertEqual(elapsed, 125)
            self.assertEqual(state.hold_on, n % 2 == 0)
        state.tick(2.01, True, False)
        self.assertFalse(state.hold_on)
        state.tick(200, False, False)
        self.assertFalse(state.hold_on)

    def test_hold_duration_expires_and_zero_cancels(self):
        state = HoldState()
        state.apply('{"version":1,"type":"hold_gate","duration_seconds":3600,"command_id":"hour"}', 10)
        self.assertTrue(state.active(10))
        self.assertAlmostEqual(state.remaining(3610), 0)
        self.assertFalse(state.active(3610))
        state.apply('{"version":1,"type":"hold_gate","duration_seconds":0}', 20)
        self.assertFalse(state.active(20))


class OutputTests(unittest.TestCase):
    setUp = regressions.ConfigTests.setUp

    def test_pin_polarity_and_transistor_never_toggled_by_indicators(self):
        self.app.gate_output = SimpleNamespace(value=True)
        self.app.hold_led = SimpleNamespace(value=False)
        self.app.indicators = Indicators(0)
        with patch.object(self.app, "log_event"):
            for n in range(40):
                self.app.service_status_led(True, True, n * 0.125)
                self.assertFalse(self.app.led.value)  # active-low onboard ON
                self.assertEqual(self.app.hold_led.value, n % 2 == 0)
                self.assertTrue(self.app.gate_output.value)
            self.app.service_status_led(True, False, 10)
            self.assertFalse(self.app.hold_led.value)

    def test_invalid_legacy_command_cannot_change_indicators(self):
        client = SimpleNamespace(user_data={"command_topic": "test"})
        with patch.object(self.app, "log_event") as log:
            self.app.on_mqtt_message(client, "test", '{"type":"set_blink_interval","blink_interval_ms":2000}')
            self.assertEqual(log.call_args.args[0], "command_rejected")

    def test_retained_hold_command_is_rejected(self):
        client = SimpleNamespace(user_data={"command_topic": "test"}, message_retained=True)
        with patch.object(self.app, "log_event") as log:
            self.app.on_mqtt_message(client, "test", '{"version":1,"type":"hold_gate","duration_seconds":10}')
            self.assertEqual(log.call_args.args[0], "command_rejected")

    def test_main_claims_only_d9_d10_and_led_and_releases_outputs(self):
        self.app.microcontroller.cpu.reset_reason = "test"
        with patch.object(self.app, "log_event"), patch.object(self.app, "service_outputs"), \
             patch.object(self.app, "load_config", return_value=None), \
             patch.object(self.app, "run_portal", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.app.main()
        self.assertEqual([c.args[0] for c in self.app.digitalio.DigitalInOut.call_args_list],
                         [self.app.board.LED, self.app.board.D0, self.app.board.D10])
        self.app.hold_led.switch_to_output.assert_called_once_with(value=False)
        self.app.gate_output.switch_to_output.assert_called_once_with(value=False)
        self.assertFalse(self.app.hold_led.value)
        self.assertFalse(self.app.gate_output.value)
        self.app.hold_led.deinit.assert_called_once()
        self.app.gate_output.deinit.assert_called_once()
