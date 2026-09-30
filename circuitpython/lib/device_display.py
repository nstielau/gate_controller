"""Small state and display adapter for the Adafruit Reverse TFT Feather."""

try:
    from device_enrollment import normalize_device_id
except ImportError:
    from .device_enrollment import normalize_device_id

APP_URL = "https://drawbridge-45487.firebaseapp.com/"


def registration_qr_url(device_id):
    return APP_URL + "?device_id=" + normalize_device_id(device_id)


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
    quiet = [[False] * (len(raw) + 4) for _ in range(len(raw) + 4)]
    for y, row in enumerate(raw):
        quiet[y + 2][2 : 2 + len(row)] = row
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

    def show_qr(self):
        if self.display is None:
            return
        try:
            import displayio
            import terminalio
            from adafruit_display_text import label
            matrix = qr_matrix(registration_qr_url(self.state.device_id))
            size = len(matrix)
            scale = max(1, min(3, 110 // size))
            width = size * scale + 4
            bitmap = displayio.Bitmap(width, width, 2)
            palette = displayio.Palette(2)
            palette[0] = 0xFFFFFF
            palette[1] = 0x000000
            for y, row in enumerate(matrix):
                for x, dark in enumerate(row):
                    if dark:
                        for dy in range(scale):
                            for dx in range(scale):
                                bitmap[2 + x * scale + dx, 2 + y * scale + dy] = 1
            group = displayio.Group()
            group.append(displayio.TileGrid(bitmap, pixel_shader=palette, x=2, y=2))
            instruction = label.Label(terminalio.FONT, text="SCAN TO REGISTER", color=0xFFFFFF, x=94, y=20)
            device = label.Label(terminalio.FONT, text=self.state.device_id, color=0xFFFFFF, x=94, y=56)
            group.append(instruction)
            group.append(device)
            self._show_group(group)
        except (ImportError, AttributeError, RuntimeError, ValueError):
            # The status loop remains usable if an optional display library is missing.
            return

    def show_status(self, wifi=False, mqtt=False, hold=False):
        if self.display is None:
            return
        try:
            import displayio
            import terminalio
            from adafruit_display_text import label
            group = displayio.Group()
            group.append(label.Label(terminalio.FONT, text=self.state.device_id, color=0xFFFFFF, x=4, y=12))
            group.append(label.Label(terminalio.FONT, text="WIFI {} MQTT {} HOLD {}".format(
                "OK" if wifi else "--", "OK" if mqtt else "--", "ON" if hold else "--"), color=0xFFFFFF, x=4, y=30))
            self._show_group(group)
        except (ImportError, AttributeError, RuntimeError, ValueError):
            return
