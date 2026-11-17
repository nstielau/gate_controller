"""Small state and display adapter for the Adafruit Reverse TFT Feather."""

try:
    from device_enrollment import normalize_device_id
except ImportError:
    from .device_enrollment import normalize_device_id

APP_URL = "https://drawbridge-45487.firebaseapp.com/"


def format_hold_time(seconds):
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return "{}:{:02d}:{:02d}".format(hours, minutes, seconds)
    return "{:02d}:{:02d}".format(minutes, seconds)


def reboot_footer(next_boot_setup=False, hold=False):
    return ("Reboot: Wi-Fi setup (D2)" if next_boot_setup else "Reboot: Normal (D2)") + (" | ends hold" if hold else "")


def registration_qr_url(device_id, code=None):
    device_id = normalize_device_id(device_id)
    if code is None:
        return APP_URL + "?device_id=" + device_id
    if len(code) != 64 or any(c not in "0123456789abcdef" for c in code):
        raise ValueError("invalid pairing code")
    # Compact alias redirects to the canonical auth origin, preserving fragment.
    return "https://drawbridge.stielau.us/?d=" + device_id + "#p=" + code


def qr_matrix(value):
    try:
        import adafruit_miniqr
        qr = adafruit_miniqr.QRCode(error_correct=adafruit_miniqr.M)
        qr.add_data(value.encode("utf-8"))
        qr.make()
        raw = [[bool(qr.matrix[x, y]) for x in range(qr.module_count)] for y in range(qr.module_count)]
    except ImportError:
        # Host tests do not load CircuitPython .mpy files. The board bundle
        # always supplies adafruit_miniqr, so this branch is only a test-safe
        # shape fallback and is never used for a device QR code.
        raw = [[(x * 17 + y * 31 + len(value)) % 7 < 3 for x in range(33)] for y in range(33)]
    quiet = [[False] * (len(raw) + 8) for _ in range(len(raw) + 8)]
    for y, row in enumerate(raw):
        quiet[y + 4][4 : 4 + len(row)] = row
    return quiet


class DisplayState:
    def __init__(self, device_id):
        self.device_id = normalize_device_id(device_id)

    def boot(self, frame=0):
        return {"mode": "boot", "frame": int(frame) % 4, "device_id": self.device_id}

    def onboarding(self):
        return {
            "mode": "onboarding", "device_id": self.device_id, "instruction": "SCAN TO REGISTER",
            "qr_url": registration_qr_url(self.device_id), "wifi": False, "mqtt": False, "hold": False,
        }

    def status(self, wifi=False, mqtt=False, hold=False):
        return {"mode": "status", "device_id": self.device_id, "wifi": bool(wifi), "mqtt": bool(mqtt), "hold": bool(hold)}


class ReverseTFT:
    """Best-effort display renderer; missing display libraries never block control."""

    def __init__(self, display=None, device_id=""):
        self.display = display
        self.state = DisplayState(device_id)
        self.group = None
        self._status_labels = None
        self._website_labels = None

    @classmethod
    def from_board(cls, device_id):
        try:
            import board
            return cls(getattr(board, "DISPLAY", None), device_id)
        except (ImportError, AttributeError, NotImplementedError):
            return cls(None, device_id)

    def _show_group(self, group):
        if self.display is not None:
            self.display.root_group = group
            self.group = group
            self._status_labels = None
            self._website_labels = None

    def show_boot(self):
        if self.display is None:
            return
        try:
            import displayio
            import terminalio
            from adafruit_display_text import label
            group = displayio.Group()
            group.append(label.Label(terminalio.FONT, text="DRAWBRIDGE", color=0xFFFFFF, x=4, y=24))
            group.append(label.Label(terminalio.FONT, text="starting...", color=0xFFFFFF, x=4, y=48))
            self._show_group(group)
        except (ImportError, AttributeError, RuntimeError, ValueError):
            return

    def show_setup(self, ssid):
        if self.display is None:
            return
        try:
            import displayio
            import terminalio
            from adafruit_display_text import label
            group = displayio.Group()
            for text, y in (("DRAWBRIDGE WIFI SETUP", 16), (ssid, 42),
                            ("Open 192.168.4.1", 66), ("Add / update networks", 90)):
                group.append(label.Label(terminalio.FONT, text=text, color=0xFFFFFF, x=4, y=y))
            self._show_group(group)
        except (ImportError, AttributeError, RuntimeError, ValueError):
            return

    def show_qr(self, code=None, phase=None):
        if self.display is None:
            return
        try:
            import displayio
            import terminalio
            from adafruit_display_text import label
            matrix = qr_matrix(registration_qr_url(self.state.device_id, code))
            size = len(matrix)
            scale = max(1, min(3, (self.display.height - 37) // size))
            width = size * scale
            bitmap = displayio.Bitmap(width, width, 2)
            palette = displayio.Palette(2)
            palette[0] = 0xFFFFFF
            palette[1] = 0x000000
            for y, row in enumerate(matrix):
                for x, dark in enumerate(row):
                    if dark:
                        for dy in range(scale):
                            for dx in range(scale):
                                bitmap[x * scale + dx, y * scale + dy] = 1
            group = displayio.Group()
            qr_x = self.display.width - width - 4
            qr_y = 15
            center_x = qr_x + width // 2
            group.append(displayio.TileGrid(bitmap, pixel_shader=palette, x=qr_x, y=qr_y))
            group.append(label.Label(terminalio.FONT, text="Scan to Register", color=0xFFFFFF,
                                     anchor_point=(0.5, 0.5), anchored_position=(center_x, 7)))
            group.append(label.Label(terminalio.FONT, text=self.state.device_id, color=0xFFFFFF,
                                     scale=2, anchor_point=(0.5, 0.5),
                                     anchored_position=(center_x, 123)))
            for text, y in (("Hold", 64), ("D1 + RESET", 80), ("Add Wi-Fi", 96)):
                group.append(label.Label(terminalio.FONT, text=text, color=0xFFFFFF, x=4, y=y))
            for line, text in enumerate(phase or ("Scan QR", "to pair")):
                y = 14 + line * 15
                group.append(label.Label(terminalio.FONT, text=text, color=0xFFFFFF, x=4, y=y))
            self._show_group(group)
        except (ImportError, AttributeError, RuntimeError, ValueError):
            # The status loop remains usable if an optional display library is missing.
            return

    def show_registration(self, phase, code):
        self.show_qr(code, phase)

    def show_notice(self, title, detail):
        if self.display is None:
            return
        try:
            import displayio
            import terminalio
            from adafruit_display_text import label
            group = displayio.Group()
            for text, y in (("DRAWBRIDGE", 20), (title, 55), (detail, 85)):
                group.append(label.Label(terminalio.FONT, text=text, color=0xFFFFFF, x=4, y=y))
            self._show_group(group)
        except (ImportError, AttributeError, RuntimeError, ValueError):
            return

    def show_website(self, hold=False, remaining_seconds=None, next_boot_setup=False):
        if self.display is None:
            return
        hold_text = (format_hold_time(remaining_seconds) if remaining_seconds is not None else "ON") if hold else "OFF"
        footer = reboot_footer(next_boot_setup, hold)
        try:
            if self._website_labels is not None and self.display.root_group is self.group:
                for key, value in (("hold", hold_text), ("footer", footer)):
                    if self._website_labels[key].text != value:
                        self._website_labels[key].text = value
                return
            import displayio
            import terminalio
            from adafruit_display_text import label
            matrix = qr_matrix(APP_URL)
            size = len(matrix)
            scale = max(1, min(3, (self.display.height - 39) // size))
            width = size * scale
            background = displayio.Bitmap(self.display.width, self.display.height, 1)
            cream = displayio.Palette(1)
            cream[0] = 0xF3F4EB
            group = displayio.Group()
            group.append(displayio.TileGrid(background, pixel_shader=cream))
            bitmap = displayio.Bitmap(width, width, 2)
            palette = displayio.Palette(2)
            palette[0], palette[1] = 0xFFFFFF, 0x000000
            for y, row in enumerate(matrix):
                for x, dark in enumerate(row):
                    if dark:
                        for dy in range(scale):
                            for dx in range(scale):
                                bitmap[x * scale + dx, y * scale + dy] = 1
            qr_x = self.display.width - width - 4
            group.append(displayio.TileGrid(bitmap, pixel_shader=palette, x=qr_x, y=17))
            group.append(label.Label(terminalio.FONT, text="Scan to open", color=0x173F35,
                                     anchor_point=(0.5, 0.5), anchored_position=(qr_x + width // 2, 7)))
            for text, y, scale in (("Drawbridge", 14, 2), (self.state.device_id, 40, 1),
                                   ("Hold", 66, 1), ("D0/D1: back", 113, 1)):
                group.append(label.Label(terminalio.FONT, text=text, color=0x173F35, x=4, y=y, scale=scale))
            values = {
                "hold": label.Label(terminalio.FONT, text=hold_text, color=0x173F35, x=4, y=88, scale=2),
                "footer": label.Label(terminalio.FONT, text=footer, color=0x66736B, x=4, y=128),
            }
            for value in values.values():
                group.append(value)
            self._show_group(group)
            self._website_labels = values
        except (ImportError, AttributeError, RuntimeError, ValueError):
            return

    def show_status(self, wifi=False, mqtt=False, hold=False, remaining_seconds=None, next_boot_setup=False):
        if self.display is None:
            return
        hold_text = (format_hold_time(remaining_seconds) if remaining_seconds is not None else "ON") if hold else "OFF"
        rows = (("Wi-Fi", "Connected" if wifi else "Connecting", wifi, 49),
                ("MQTT", "Connected" if mqtt else "Reconnecting", mqtt, 78),
                ("Hold", hold_text, hold, 107))
        footer = reboot_footer(next_boot_setup, hold)
        try:
            if self._status_labels is not None and self.display.root_group is self.group:
                for title, value, active, _ in rows:
                    target = self._status_labels[title]
                    if target.text != value:
                        target.text = value
                    color = 0x173F35 if active else 0x66736B
                    if target.color != color:
                        target.color = color
                if self._status_labels["footer"].text != footer:
                    self._status_labels["footer"].text = footer
                return
            import displayio
            import terminalio
            from adafruit_display_text import label
            group = displayio.Group()
            background = displayio.Bitmap(self.display.width, self.display.height, 2)
            palette = displayio.Palette(2)
            palette[0] = 0xF3F4EB
            palette[1] = 0x173F35
            for y in range(32):
                for x in range(self.display.width):
                    background[x, y] = 1
            group.append(displayio.TileGrid(background, pixel_shader=palette))
            group.append(label.Label(terminalio.FONT, text="Drawbridge", color=0xF3F4EB,
                                     scale=2, x=10, y=15))
            group.append(label.Label(terminalio.FONT, text=self.state.device_id, color=0xF3F4EB,
                                     x=self.display.width - 44, y=15))
            values = {}
            for title, value, active, y in rows:
                group.append(label.Label(terminalio.FONT, text=title, color=0x173F35,
                                         scale=2, x=10, y=y))
                values[title] = label.Label(terminalio.FONT, text=value,
                                            color=0x173F35 if active else 0x66736B,
                                            x=116, y=y, scale=2 if title == "Hold" else 1)
                group.append(values[title])
            values["footer"] = label.Label(terminalio.FONT, text=footer, color=0x66736B, x=10, y=128)
            group.append(values["footer"])
            self._show_group(group)
            self._status_labels = values
        except (ImportError, AttributeError, RuntimeError, ValueError):
            return
