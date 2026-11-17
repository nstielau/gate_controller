import importlib.util
import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


sys.path.append(str(pathlib.Path(__file__).parents[1] / "circuitpython" / "lib"))

MODULE_PATH = pathlib.Path(__file__).parents[1] / "circuitpython" / "lib" / "device_display.py"
spec = importlib.util.spec_from_file_location("device_display", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DisplayTests(unittest.TestCase):
    def test_hold_countdown_formats_seconds_and_hours(self):
        for seconds, expected in ((0, "00:00"), (1, "00:01"), (272, "04:32"),
                                  (3599, "59:59"), (3600, "1:00:00"),
                                  (21600, "6:00:00"), (86400, "24:00:00")):
            with self.subTest(seconds=seconds):
                self.assertEqual(module.format_hold_time(seconds), expected)

    def test_countdown_and_footer_update_without_rebuilding_display(self):
        labels = MagicMock(side_effect=lambda font, **kwargs: SimpleNamespace(**kwargs))
        display = SimpleNamespace(width=240, height=135, root_group=None)
        bitmap = MagicMock(side_effect=lambda *args: {})
        drawing = SimpleNamespace(Group=list, Bitmap=bitmap, Palette=lambda *args: {}, TileGrid=MagicMock())
        text = SimpleNamespace(label=SimpleNamespace(Label=labels))
        renderer = module.ReverseTFT(display, "ab12cd")
        with patch.dict(sys.modules, {"displayio": drawing, "terminalio": SimpleNamespace(FONT=None), "adafruit_display_text": text}):
            renderer.show_status(wifi=True, mqtt=True, hold=False, remaining_seconds=0)
            group = display.root_group
            values = [item for item in group if hasattr(item, "text")]
            footer = next(item for item in values if item.text == "Reboot: Normal (D2)")
            hold = next(item for item in values if item.text == "OFF")
            self.assertLessEqual(footer.y + 6, 134)
            renderer.show_status(wifi=False, mqtt=False, hold=True, remaining_seconds=272)
            self.assertIs(display.root_group, group)
            self.assertEqual(hold.text, "04:32")
            self.assertEqual(footer.text, "Reboot: Normal (D2) | ends hold")
            self.assertEqual(hold.color, 0x173F35)
            renderer.show_status(wifi=False, mqtt=False, hold=True, remaining_seconds=271)
            self.assertEqual(hold.text, "04:31")
            renderer.show_status(wifi=True, mqtt=True, hold=False, remaining_seconds=0)
            self.assertEqual(hold.text, "OFF")
            self.assertEqual(footer.text, "Reboot: Normal (D2)")
            bitmap.assert_called_once()
            renderer.show_setup("Gate-Setup-test")
            renderer.show_status(wifi=True, mqtt=True, hold=True, remaining_seconds=3600)
            self.assertIsNot(display.root_group, group)
            self.assertEqual(bitmap.call_count, 2)
            self.assertIn("1:00:00", [item.text for item in display.root_group if hasattr(item, "text")])

    def test_website_qr_keeps_dark_header_and_uses_lower_screen_without_hold_or_d2(self):
        display = SimpleNamespace(width=240, height=135, root_group=None)
        labels = MagicMock(side_effect=lambda font, **kwargs: SimpleNamespace(**kwargs))
        bitmaps = []
        def bitmap(*args):
            result = {}
            bitmaps.append((args, result))
            return result
        tiles = MagicMock(return_value=SimpleNamespace())
        drawing = SimpleNamespace(Group=list, Bitmap=bitmap, Palette=lambda *args: {}, TileGrid=tiles)
        text = SimpleNamespace(label=SimpleNamespace(Label=labels))
        renderer = module.ReverseTFT(display, "ab12cd")
        with patch.dict(sys.modules, {"displayio": drawing, "terminalio": SimpleNamespace(FONT=None), "adafruit_display_text": text}), patch.object(module, "qr_matrix", return_value=[[False]*37 for _ in range(37)]) as qr:
            renderer.show_website()
            group = display.root_group
            renderer.show_website()
            self.assertIs(display.root_group, group)
            qr.assert_called_once_with(module.APP_URL)
            strings = [item.text for item in group if hasattr(item, "text")]
            self.assertEqual(set(strings), {"Drawbridge", "ab12cd", "Scan to open"})
            header = next(item for item in group if getattr(item,"text",None)=="Drawbridge")
            self.assertEqual((header.x,header.y,header.scale,header.color),(10,15,2,0xF3F4EB))
            self.assertTrue(all(bitmaps[0][1][x,y] == 1 for x in range(240) for y in range(32)))
            qr_tile = tiles.call_args_list[-1].kwargs
            width = bitmaps[-1][0][0]
            self.assertEqual(qr_tile["x"], (240-width)//2)
            self.assertGreaterEqual(qr_tile["y"], 48)
            self.assertLessEqual(qr_tile["y"]+width,135)
            renderer.show_status(next_boot_setup=True)
            self.assertIsNot(display.root_group, group)

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

    def test_registration_qr_is_on_right_with_d1_hint_on_left(self):
        display = SimpleNamespace(width=240, height=135, root_group=None)
        renderer = module.ReverseTFT(display, "ab12cd")
        tile = MagicMock()
        labels = MagicMock()
        drawing = SimpleNamespace(Group=list, Bitmap=lambda *args: {}, Palette=lambda *args: {}, TileGrid=tile)
        text = SimpleNamespace(label=SimpleNamespace(Label=labels))
        with patch.dict(sys.modules, {"displayio": drawing, "terminalio": SimpleNamespace(FONT=None), "adafruit_display_text": text}), patch.object(module, "qr_matrix", return_value=[[False]*41 for _ in range(41)]):
            renderer.show_qr()
        self.assertGreater(tile.call_args.kwargs["x"], 120)
        strings = [c.kwargs["text"] for c in labels.call_args_list]
        self.assertIn("D1 + RESET", strings)
        self.assertIn("Add Wi-Fi", strings)
        calls = {c.kwargs["text"]: c.kwargs for c in labels.call_args_list}
        qr = tile.call_args.kwargs
        title = calls["Scan to Register"]
        code = calls["ab12cd"]
        self.assertLess(title["anchored_position"][1], qr["y"])
        self.assertGreater(code["anchored_position"][1], qr["y"] + 86)
        self.assertEqual(code["scale"], 2)
        self.assertEqual(title["anchored_position"][0], code["anchored_position"][0])
        self.assertEqual(calls["D1 + RESET"]["x"], 4)

    def test_qr_matrix_is_square_and_has_quiet_zone(self):
        matrix = module.qr_matrix("https://drawbridge-45487.firebaseapp.com/?device_id=ab12cd")
        self.assertEqual(len(matrix), len(matrix[0]))
        self.assertGreaterEqual(len(matrix), 21)
        self.assertTrue(all(not any(row) for row in matrix[:4] + matrix[-4:]))
        self.assertTrue(all(not any(row[:4] + row[-4:]) for row in matrix))

    def test_secure_qr_uses_only_derived_code_and_fits_small_screen(self):
        code = "a" * 64
        url = module.registration_qr_url("ab12cd", code)
        self.assertEqual(url, "https://drawbridge.stielau.us/?d=ab12cd#p=" + code)
        self.assertLessEqual(len(url), 106)
        with self.assertRaises(ValueError):
            module.registration_qr_url("ab12cd", "invalid")

    def test_normal_status_has_brand_and_separate_readable_rows(self):
        labels = MagicMock()
        display = SimpleNamespace(width=240, height=135, root_group=None)
        drawing = SimpleNamespace(Group=list, Bitmap=lambda *args: {}, Palette=lambda *args: {}, TileGrid=MagicMock())
        text = SimpleNamespace(label=SimpleNamespace(Label=labels))
        renderer = module.ReverseTFT(display, "ab12cd")
        with patch.dict(sys.modules, {"displayio": drawing, "terminalio": SimpleNamespace(FONT=None), "adafruit_display_text": text}):
            renderer.show_status(wifi=True, mqtt=False, hold=True)
        calls = {c.kwargs["text"]: c.kwargs for c in labels.call_args_list}
        self.assertIn("Drawbridge", calls)
        self.assertIn("Connected", calls)
        self.assertIn("Reconnecting", calls)
        self.assertIn("ON", calls)
        self.assertEqual(len({calls[t]["y"] for t in ("Wi-Fi", "MQTT", "Hold")}), 3)
        self.assertTrue(all(32 < calls[t]["y"] < 123 for t in ("Wi-Fi", "MQTT", "Hold")))
        self.assertEqual(calls["ON"]["color"], 0x173F35)


if __name__ == "__main__":
    unittest.main()
