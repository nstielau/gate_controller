"""OTA application: command policy and independent status indicator schedules.

The USB bootstrap owns pins, TLS, output deadlines, and update storage.
This interface is a coding boundary, not a Python security sandbox.
"""

import json

APP_VERSION = "1.0.1"
APP_API_VERSION = 1


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
        # Two 100 ms flashes identify firmware 1.0.1 without blocking the loop.
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
