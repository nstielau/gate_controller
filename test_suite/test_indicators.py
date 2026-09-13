"""Pin-level and scheduler regressions for the independent status LEDs."""

from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, call, patch
import test_regressions as regressions
from gate_indicators import Indicators
from gate_hold import HoldState


class IndicatorTests(unittest.TestCase):
    def test_connectivity_leds_follow_wifi_and_mqtt_independently(self):
        for holding in (False, True):
            state = Indicators(0)
            for now, wifi, mqtt, expected in [
                (0, False, False, (True, False)),
                (0.5, False, False, (False, False)),
                (1, True, False, (True, True)),
                (1.5, True, False, (True, False)),
                (2, True, True, (True, True)),
                (2.5, True, True, (True, True)),
                (3, True, False, (True, True)),
                (3.5, True, False, (True, False)),
                (4, False, True, (True, False)),
                (4.5, False, True, (False, False)),
            ]:
                state.tick(now, wifi, mqtt, holding)
                self.assertEqual((state.wifi_on, state.mqtt_on), expected)

    def test_alive_pulses_do_not_restart_when_connectivity_or_hold_changes(self):
        state = Indicators(0)
        for now, expected in [
            (0, True),
            (0.099, True),
            (0.101, False),
            (1, False),
            (2, True),
            (2.101, False),
            (100, True),
        ]:
            state.tick(now, now >= 1, now >= 2, now >= 2)
            self.assertEqual(state.alive_on, expected)
        self.assertGreater(state.alive_edges, 0)

    def test_hold_indicator_has_four_full_cycles_per_second(self):
        state = Indicators(0)
        state.tick(0, True, True, False)
        self.assertFalse(state.hold_on)
        state.tick(1, True, True, True)
        self.assertTrue(state.hold_on)
        for n in range(1, 9):
            _, elapsed = state.tick(1 + n * 0.125, False, False, True)
            self.assertEqual(elapsed, 125)
            self.assertEqual(state.hold_on, n % 2 == 0)
        state.tick(2.01, True, True, False)
        self.assertFalse(state.hold_on)
        state.tick(200, False, False, False)
        self.assertFalse(state.hold_on)

    def test_hold_duration_expires_and_zero_cancels(self):
        state = HoldState()
        state.apply(
            '{"version":1,"type":"hold_gate","duration_seconds":3600,"command_id":"hour"}', 10
        )
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
        self.app.wifi_led = SimpleNamespace(value=False)
        self.app.mqtt_led = SimpleNamespace(value=False)
        self.app.indicators = Indicators(0)
        with patch.object(self.app, "log_event"):
            for n in range(40):
                self.app.service_status_led(True, True, True, n * 0.125)
                self.assertEqual(self.app.led.value, not self.app.indicators.alive_on)
                self.assertTrue(self.app.wifi_led.value)
                self.assertTrue(self.app.mqtt_led.value)
                self.assertEqual(self.app.hold_led.value, n % 2 == 0)
                self.assertTrue(self.app.gate_output.value)
            self.app.service_status_led(True, True, False, 10)
            self.assertFalse(self.app.hold_led.value)

    def test_invalid_legacy_command_cannot_change_indicators(self):
        client = SimpleNamespace(user_data={"command_topic": "test"})
        with patch.object(self.app, "log_event") as log:
            self.app.on_mqtt_message(
                client, "test", '{"type":"set_blink_interval","blink_interval_ms":2000}'
            )
            self.assertEqual(log.call_args.args[0], "command_rejected")

    def test_retained_hold_command_is_rejected(self):
        client = SimpleNamespace(user_data={"command_topic": "test"}, message_retained=True)
        with patch.object(self.app, "log_event") as log:
            self.app.on_mqtt_message(
                client, "test", '{"version":1,"type":"hold_gate","duration_seconds":10}'
            )
            self.assertEqual(log.call_args.args[0], "command_rejected")

    def test_main_runs_temporary_pin_diagnostic_then_claims_runtime_outputs(self):
        self.app.microcontroller.cpu.reset_reason = "test"
        outputs = []

        def make_output(pin):
            output = MagicMock(value=False)
            outputs.append((pin, output))
            return output

        self.app.digitalio.DigitalInOut.reset_mock()
        self.app.digitalio.DigitalInOut.side_effect = make_output
        with (
            patch.object(self.app, "log_event"),
            patch.object(self.app, "service_outputs"),
            patch.object(self.app.time, "sleep") as sleep,
            patch.object(self.app, "load_config", return_value=None),
            patch.object(self.app, "run_portal", side_effect=KeyboardInterrupt),
        ):
            with self.assertRaises(KeyboardInterrupt):
                self.app.main()
        self.assertEqual(
            [c.args[0] for c in self.app.digitalio.DigitalInOut.call_args_list],
            [
                self.app.board.D0,
                self.app.board.D1,
                self.app.board.D2,
                self.app.board.D10,
                self.app.board.D0,
                self.app.board.D1,
                self.app.board.D2,
            ],
        )
        self.assertEqual(sleep.call_args_list, [call(0.2), call(0.2)] * 3)
        for _, output in outputs:
            output.switch_to_output.assert_called_once_with(value=False)
            self.assertFalse(output.value)
            output.deinit.assert_called_once()
        self.app.hold_led.switch_to_output.assert_called_once_with(value=False)
        self.app.gate_output.switch_to_output.assert_called_once_with(value=False)
        self.assertFalse(self.app.hold_led.value)
        self.assertFalse(self.app.gate_output.value)
        self.app.hold_led.deinit.assert_called_once()
        self.app.gate_output.deinit.assert_called_once()
