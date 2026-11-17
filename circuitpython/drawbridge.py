"""OTA application: command policy and independent status indicator schedules.

The USB bootstrap owns pins, TLS, output deadlines, and update storage.
This interface is a coding boundary, not a Python security sandbox.
"""

import json

APP_VERSION = "1.1.0"
APP_API_VERSION = 2


class Indicators:
    def __init__(self, now):
        self.wifi_connected = None
        self.mqtt_connected = None
        self.holding = None
        self.alive_on = True
        self.alive_epoch = now
        self.alive_edges = 0
        self.wifi_on = False
        self.mqtt_on = False
        self.hold_on = False
        self.wifi_epoch = now
        self.mqtt_epoch = now
        self.hold_edge = now
        self.hold_edges = 0

    def tick(self, now, wifi_connected, mqtt_connected, holding):
        mqtt_connected = bool(wifi_connected and mqtt_connected)
        changed = (
            wifi_connected != self.wifi_connected
            or mqtt_connected != self.mqtt_connected
            or holding != self.holding
        )
        # Two 100 ms flashes show the loop is alive without blocking it.
        alive_phase = (now - self.alive_epoch) % 2
        alive_on = alive_phase < 0.1 or 0.25 <= alive_phase < 0.35
        if alive_on != self.alive_on:
            self.alive_edges += 1
        self.alive_on = alive_on
        if wifi_connected != self.wifi_connected:
            self.wifi_epoch = now
            self.mqtt_epoch = now
        if mqtt_connected != self.mqtt_connected:
            self.mqtt_epoch = now
        self.wifi_connected = wifi_connected
        self.mqtt_connected = mqtt_connected
        self.wifi_on = wifi_connected or (now - self.wifi_epoch) % 1 < 0.5
        self.mqtt_on = wifi_connected and (mqtt_connected or (now - self.mqtt_epoch) % 1 < 0.5)

        elapsed = None
        if holding != self.holding:
            self.holding = holding
            self.hold_on = holding
            self.hold_edge = now
        elif holding and now - self.hold_edge >= 0.125:
            elapsed = round((now - self.hold_edge) * 1000, 1)
            self.hold_on = not self.hold_on
            self.hold_edge = now
            self.hold_edges += 1
        return changed, elapsed


class App:
    def __init__(self, platform, now):
        self.platform = platform
        self.indicators = Indicators(now)

    def create_ui(self, physical_display, device_id):
        return DeviceUI(self.platform, ReverseTFT(physical_display, device_id))

    def on_message(self, message, retained, now):
        if retained:
            raise ValueError("retained hold commands are unsafe")
        value = json.loads(message)
        if (
            type(value) is not dict
            or type(value.get("version")) is not int
            or value.get("version") != 1
            or value.get("type") != "hold_gate"
        ):
            raise ValueError("invalid hold schema")
        self.platform.request_hold(value.get("duration_seconds"), value.get("command_id"), now)

    def tick(self, now, wifi_connected, mqtt_connected, holding):
        return self.indicators.tick(now, wifi_connected, mqtt_connected, holding)


def create_app(platform, now):
    return App(platform, now)


def normalize_device_id(value):
    if not isinstance(value, str):
        raise ValueError("invalid device ID")
    value = value.strip().lower()
    if (
        not value
        or len(value) > 64
        or any(not ("a" <= c <= "z" or "0" <= c <= "9" or c == "-") for c in value)
    ):
        raise ValueError("invalid device ID")
    return value


class DeviceUI:
    """OTA-owned presentation and button policy; no GPIO or credential access."""

    def __init__(self, platform, display):
        self.platform = platform
        self.display = display
        self.website_until = 0
        self.last_status = None

    def on_button(self, index, now):
        if index == 2:
            self.platform.toggle_setup_reboot()
        elif index in (0, 1):
            self.website_until = 0 if self.website_until > now else now + 20
        self.last_status = None

    def invalidate(self):
        self.last_status = None

    def render_status(
        self, now, wifi=False, mqtt=False, hold=False, remaining_seconds=0, next_boot_setup=False
    ):
        status = (
            bool(wifi),
            bool(mqtt),
            bool(hold),
            remaining_seconds,
            next_boot_setup,
            self.website_until > now,
        )
        if status == self.last_status:
            return
        if status[-1]:
            self.display.show_website()
        else:
            self.display.show_status(
                wifi=wifi,
                mqtt=mqtt,
                hold=hold,
                remaining_seconds=remaining_seconds,
                next_boot_setup=next_boot_setup,
            )
        self.last_status = status


APP_URL = "https://drawbridge-45487.firebaseapp.com/"


def format_hold_time(seconds):
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return "{}:{:02d}:{:02d}".format(hours, minutes, seconds)
    return "{:02d}:{:02d}".format(minutes, seconds)


def reboot_footer(next_boot_setup=False, hold=False):
    return ("Reboot: Wi-Fi setup (D2)" if next_boot_setup else "Reboot: Normal (D2)") + (
        " | ends hold" if hold else ""
    )


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
        raw = [
            [bool(qr.matrix[x, y]) for x in range(qr.module_count)] for y in range(qr.module_count)
        ]
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
            "mode": "onboarding",
            "device_id": self.device_id,
            "instruction": "SCAN TO REGISTER",
            "qr_url": registration_qr_url(self.device_id),
            "wifi": False,
            "mqtt": False,
            "hold": False,
        }

    def status(self, wifi=False, mqtt=False, hold=False):
        return {
            "mode": "status",
            "device_id": self.device_id,
            "wifi": bool(wifi),
            "mqtt": bool(mqtt),
            "hold": bool(hold),
        }


class ReverseTFT:
    """Best-effort display renderer; missing display libraries never block control."""

    def __init__(self, display=None, device_id=""):
        self.display = display
        self.state = DisplayState(device_id)
        self.group = None
        self._status_labels = None
        self._website_visible = False

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
            self._website_visible = False

    def show_boot(self):
        if self.display is None:
            return
        import displayio
        import terminalio
        from adafruit_display_text import label

        group = displayio.Group()
        group.append(label.Label(terminalio.FONT, text="DRAWBRIDGE", color=0xFFFFFF, x=4, y=24))
        group.append(label.Label(terminalio.FONT, text="starting...", color=0xFFFFFF, x=4, y=48))
        self._show_group(group)

    def show_setup(self, ssid):
        if self.display is None:
            return
        import displayio
        import terminalio
        from adafruit_display_text import label

        group = displayio.Group()
        for text, y in (
            ("DRAWBRIDGE WIFI SETUP", 16),
            (ssid, 42),
            ("Open 192.168.4.1", 66),
            ("Add / update networks", 90),
        ):
            group.append(label.Label(terminalio.FONT, text=text, color=0xFFFFFF, x=4, y=y))
        self._show_group(group)

    def show_qr(self, code=None, phase=None):
        if self.display is None:
            return
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
        group.append(
            label.Label(
                terminalio.FONT,
                text="Scan to Register",
                color=0xFFFFFF,
                anchor_point=(0.5, 0.5),
                anchored_position=(center_x, 7),
            )
        )
        group.append(
            label.Label(
                terminalio.FONT,
                text=self.state.device_id,
                color=0xFFFFFF,
                scale=2,
                anchor_point=(0.5, 0.5),
                anchored_position=(center_x, 123),
            )
        )
        for text, y in (("Hold", 64), ("D1 + RESET", 80), ("Add Wi-Fi", 96)):
            group.append(label.Label(terminalio.FONT, text=text, color=0xFFFFFF, x=4, y=y))
        for line, text in enumerate(phase or ("Scan QR", "to pair")):
            y = 14 + line * 15
            group.append(label.Label(terminalio.FONT, text=text, color=0xFFFFFF, x=4, y=y))
        self._show_group(group)

    def show_registration(self, phase, code):
        self.show_qr(code, phase)

    def show_notice(self, title, detail):
        if self.display is None:
            return
        import displayio
        import terminalio
        from adafruit_display_text import label

        group = displayio.Group()
        for text, y in (("DRAWBRIDGE", 20), (title, 55), (detail, 85)):
            group.append(label.Label(terminalio.FONT, text=text, color=0xFFFFFF, x=4, y=y))
        self._show_group(group)

    def show_website(self):
        if self.display is None:
            return
        if self._website_visible and self.display.root_group is self.group:
            return
        import displayio
        import terminalio
        from adafruit_display_text import label

        matrix = qr_matrix(APP_URL)
        size = len(matrix)
        scale = max(1, min(3, (self.display.height - 50) // size))
        width = size * scale
        background = displayio.Bitmap(self.display.width, self.display.height, 2)
        colors = displayio.Palette(2)
        colors[0], colors[1] = 0xF3F4EB, 0x173F35
        for y in range(32):
            for x in range(self.display.width):
                background[x, y] = 1
        group = displayio.Group()
        group.append(displayio.TileGrid(background, pixel_shader=colors))
        group.append(
            label.Label(terminalio.FONT, text="Drawbridge", color=0xF3F4EB, scale=2, x=10, y=15)
        )
        group.append(
            label.Label(
                terminalio.FONT,
                text=self.state.device_id,
                color=0xF3F4EB,
                x=self.display.width - 44,
                y=15,
            )
        )
        bitmap = displayio.Bitmap(width, width, 2)
        palette = displayio.Palette(2)
        palette[0], palette[1] = 0xFFFFFF, 0x000000
        for y, row in enumerate(matrix):
            for x, dark in enumerate(row):
                if dark:
                    for dy in range(scale):
                        for dx in range(scale):
                            bitmap[x * scale + dx, y * scale + dy] = 1
        qr_x = (self.display.width - width) // 2
        group.append(displayio.TileGrid(bitmap, pixel_shader=palette, x=qr_x, y=50))
        group.append(
            label.Label(
                terminalio.FONT,
                text="Scan to open",
                color=0x173F35,
                anchor_point=(0.5, 0.5),
                anchored_position=(self.display.width // 2, 41),
            )
        )
        self._show_group(group)
        self._website_visible = True

    def show_status(
        self, wifi=False, mqtt=False, hold=False, remaining_seconds=None, next_boot_setup=False
    ):
        if self.display is None:
            return
        hold_text = (
            (format_hold_time(remaining_seconds) if remaining_seconds is not None else "ON")
            if hold
            else "OFF"
        )
        rows = (
            ("Wi-Fi", "Connected" if wifi else "Connecting", wifi, 49),
            ("MQTT", "Connected" if mqtt else "Reconnecting", mqtt, 78),
            ("Hold", hold_text, hold, 107),
        )
        footer = reboot_footer(next_boot_setup, hold)
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
        group.append(
            label.Label(terminalio.FONT, text="Drawbridge", color=0xF3F4EB, scale=2, x=10, y=15)
        )
        group.append(
            label.Label(
                terminalio.FONT,
                text=self.state.device_id,
                color=0xF3F4EB,
                x=self.display.width - 44,
                y=15,
            )
        )
        values = {}
        for title, value, active, y in rows:
            group.append(
                label.Label(terminalio.FONT, text=title, color=0x173F35, scale=2, x=10, y=y)
            )
            values[title] = label.Label(
                terminalio.FONT,
                text=value,
                color=0x173F35 if active else 0x66736B,
                x=116,
                y=y,
                scale=2 if title == "Hold" else 1,
            )
            group.append(values[title])
        values["footer"] = label.Label(terminalio.FONT, text=footer, color=0x66736B, x=10, y=128)
        group.append(values["footer"])
        self._show_group(group)
        self._status_labels = values
