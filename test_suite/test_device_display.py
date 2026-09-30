import importlib.util
import pathlib
import sys
import unittest


sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / "circuitpython" / "lib"))

MODULE_PATH = pathlib.Path(__file__).parents[1] / "circuitpython" / "lib" / "device_display.py"
spec = importlib.util.spec_from_file_location("device_display", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DisplayTests(unittest.TestCase):
    def test_registration_qr_url_contains_only_device_id(self):
        url = module.registration_qr_url("AB12CD")
        self.assertEqual(url, "https://drawbridge-45487.firebaseapp.com/?device_id=ab12cd")
        self.assertNotIn("password", url)

    def test_display_state_keeps_qr_and_status_indicators_compact(self):
        state = module.DisplayState("AB12CD")
        self.assertEqual(state.onboarding(), {
            "mode": "onboarding", "device_id": "ab12cd", "instruction": "SCAN TO REGISTER",
            "qr_url": "https://drawbridge-45487.firebaseapp.com/?device_id=ab12cd",
            "wifi": False, "mqtt": False, "hold": False,
        })
        self.assertEqual(state.status(wifi=True, mqtt=True, hold=True)["mode"], "status")

    def test_qr_matrix_is_square_and_has_quiet_zone(self):
        matrix = module.qr_matrix("https://drawbridge-45487.firebaseapp.com/?device_id=ab12cd")
        self.assertEqual(len(matrix), len(matrix[0]))
        self.assertGreaterEqual(len(matrix), 21)
        self.assertTrue(all(not any(row[:2]) for row in matrix[:2]))


if __name__ == "__main__":
    unittest.main()
