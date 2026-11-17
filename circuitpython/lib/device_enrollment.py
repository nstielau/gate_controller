"""Host-safe helpers for local Wi-Fi discovery and device registration."""


_DEVICE_ID_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789-")


def normalize_device_id(value):
    if not isinstance(value, str):
        raise ValueError("invalid device ID")
    result = value.strip().lower()
    if not result or len(result) > 64 or any(character not in _DEVICE_ID_CHARS for character in result):
        raise ValueError("invalid device ID")
    return result


def _auth_name(value):
    name = getattr(value, "name", None)
    return str(name if name is not None else value).upper()


def _security(value):
    name = _auth_name(value)
    if name in ("OPEN", "NONE", "0"):
        return "open"
    if "WPA" in name and "ENT" not in name:
        return "wpa"
    return None


def visible_networks(entries):
    """Return unique visible open/WPA networks, strongest result first."""
    strongest = {}
    for entry in entries:
        ssid = getattr(entry, "ssid", None)
        rssi = getattr(entry, "rssi", None)
        security = _security(getattr(entry, "authmode", None))
        if not isinstance(ssid, str) or not ssid or security is None:
            continue
        if not isinstance(rssi, int):
            rssi = -100
        current = strongest.get(ssid)
        if current is None or rssi > current["rssi"]:
            strongest[ssid] = {"ssid": ssid, "rssi": rssi, "security": security}
    return sorted(strongest.values(), key=lambda item: (-item["rssi"], item["ssid"]))


def validate_pairing_secret(secret):
    if (not isinstance(secret, str) or len(secret) != 64
            or any(c not in "0123456789abcdef" for c in secret)):
        raise ValueError("invalid pairing proof")
    return secret


def pairing_code(secret):
    # CircuitPython provides hashlib.new(), rather than hashlib.sha256().
    import hashlib
    digest = hashlib.new("sha256")
    digest.update(validate_pairing_secret(secret).encode("utf-8"))
    return "".join("{:02x}".format(value) for value in digest.digest())


def registration_payload(device_id, secret=None, action=None):
    result = {"device_id": normalize_device_id(device_id),
              "device_secret": validate_pairing_secret(secret)}
    if action is not None:
        if action != "complete":
            raise ValueError("invalid registration action")
        result["action"] = action
    return result


def parse_registration_response(body):
    if not isinstance(body, dict):
        raise ValueError("invalid registration response")
    required = ("deviceId", "username", "password", "commandTopic", "statusTopic")
    if any(not isinstance(body.get(key), str) or not body[key] for key in required):
        raise ValueError("invalid registration response")
    device_id = normalize_device_id(body["deviceId"])
    if body["commandTopic"] != "gate/v1/devices/{}/command".format(device_id):
        raise ValueError("invalid registration response")
    if body["statusTopic"] != "gate/v1/devices/{}/status".format(device_id):
        raise ValueError("invalid registration response")
    port = body.get("brokerPort", 8883)
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("invalid registration response")
    host = body.get("brokerHost", "jd3a6164.ala.us-east-1.emqxsl.com")
    if not isinstance(host, str) or not host or len(host) > 255:
        raise ValueError("invalid registration response")
    return {
        "device_id": device_id,
        "mqtt_username": body["username"],
        "mqtt_password": body["password"],
        "mqtt_broker": host,
        "mqtt_port": port,
        "mqtt_command_topic": body["commandTopic"],
        "mqtt_topic": body["statusTopic"],
    }


def apply_registration(config, body):
    result = dict(config or {})
    result.update(parse_registration_response(body))
    result.pop("registration_pending", None)
    result["registration_complete"] = True
    result["registration_acknowledged"] = False
    return result
