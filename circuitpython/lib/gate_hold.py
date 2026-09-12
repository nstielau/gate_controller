"""Validated, monotonic timed gate hold state."""

import json


class HoldState:
    def __init__(self):
        self.command_id = None
        self.duration_seconds = 0
        self.deadline = None

    def apply(self, message, now):
        try:
            value = json.loads(message)
            if (type(value) is not dict or value.get("version") != 1 or
                    value.get("type") != "hold_gate"):
                raise ValueError
            duration = value["duration_seconds"]
            if type(duration) not in (int, float) or isinstance(duration, bool) or not 0 <= duration <= 86400:
                raise ValueError
            command_id = value.get("command_id")
            if command_id is not None and (type(command_id) is not str or not 1 <= len(command_id) <= 64):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise ValueError("invalid hold command") from None
        self.command_id = command_id
        self.duration_seconds = duration
        self.deadline = now + duration if duration else None

    def active(self, now):
        return self.deadline is not None and now < self.deadline

    def remaining(self, now):
        return max(0, self.deadline - now) if self.deadline is not None else 0
