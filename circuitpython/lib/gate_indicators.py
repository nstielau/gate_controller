"""Independent LED schedules. No pin writes or networking in this module."""


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
        changed = (wifi_connected != self.wifi_connected
                   or mqtt_connected != self.mqtt_connected or holding != self.holding)
        alive_on = (now - self.alive_epoch) % 2 < 0.1
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
        self.mqtt_on = wifi_connected and (
            mqtt_connected or (now - self.mqtt_epoch) % 1 < 0.5)

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
