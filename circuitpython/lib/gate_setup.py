"""Pure helpers for physical UI intent and recoverable setup restart."""

from device_enrollment import validate_pairing_secret


def valid_reset_id(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("invalid setup reset id")
    return value


def toggle_next_boot(config):
    result = dict(config or {})
    if result.get("next_boot_setup") is True:
        result.pop("next_boot_setup")
    else:
        result["next_boot_setup"] = True
    return result


def consume_next_boot(config):
    result = dict(config or {})
    requested = result.pop("next_boot_setup", False) is True
    return result, requested


def pending_reset_config(config, reset_id):
    result = dict(config)
    result.update(setup_reset_id=valid_reset_id(reset_id), setup_reset_pending=True)
    return result


def cleared_setup_config(config, reset_id):
    reset_id = valid_reset_id(reset_id)
    if config.get("setup_reset_id") != reset_id or config.get("setup_reset_pending") is not True:
        raise ValueError("setup reset acknowledgment mismatch")
    return {"pairing_secret": validate_pairing_secret(config.get("pairing_secret")),
            "setup_reset_id": reset_id, "registration_pending": True, "wifi_networks": []}


class ButtonEdge:
    def __init__(self, pressed, now):
        self.sync(pressed, now)

    def sync(self, pressed, now):
        self.stable = bool(pressed)
        self.observed = self.stable
        self.changed_at = now

    def update(self, pressed, now):
        pressed = bool(pressed)
        if pressed != self.observed:
            self.observed = pressed
            self.changed_at = now
        if pressed != self.stable and now - self.changed_at >= .04:
            self.stable = pressed
            return pressed
        return False
