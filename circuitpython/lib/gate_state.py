"""Validated blink commands and testable LED scheduling, without hardware imports."""

import json


def parse_command(message):
    payload = json.loads(message)
    if not isinstance(payload, dict):
        raise ValueError("command must be a JSON object")
    interval = payload.get("blink_interval_ms")
    if (type(payload.get("version")) is not int or payload["version"] != 1
            or payload.get("type") != "set_blink_interval"
            or type(interval) is not int or not 25 <= interval <= 60000):
        raise ValueError("unsupported command or interval")
    command_id = payload.get("command_id")
    if command_id is not None and (not isinstance(command_id, str) or not 1 <= len(command_id) <= 64):
        raise ValueError("command_id must be 1 to 64 characters")
    return interval, command_id


class BlinkState:
    def __init__(self, now):
        self.interval_ms = 150
        self.command_id = None
        self.last_edge = now
        self.samples_left = 0
        self.edge_count = 0

    def apply(self, message, now):
        interval, command_id = parse_command(message)
        if command_id is not None and command_id == self.command_id and interval == self.interval_ms:
            return False  # QoS 1 can deliver the same desired state more than once.
        self.interval_ms = interval
        self.command_id = command_id
        self.last_edge = now
        self.samples_left = 4
        return True

    def tick(self, now, online=True):
        interval = (self.interval_ms if online else 750) / 1000
        if now - self.last_edge < interval:
            return None
        elapsed = round((now - self.last_edge) * 1000, 1)
        self.last_edge = now
        self.edge_count += 1
        return elapsed
