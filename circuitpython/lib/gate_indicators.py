"""Independent LED schedules. No pin writes or networking in this module."""


class Indicators:
    def __init__(self, now):
        self.connected = None
        self.holding = None
        self.connection_on = True
        self.hold_on = False
        self.connection_edge = now
        self.hold_edge = now
        self.hold_edges = 0

    def tick(self, now, connected, holding):
        changed = (connected != self.connected or holding != self.holding)
        if connected != self.connected:
            self.connected = connected
            self.connection_on = True
            self.connection_edge = now
        elif not connected and now - self.connection_edge >= 0.5:
            self.connection_on = not self.connection_on
            self.connection_edge = now

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
