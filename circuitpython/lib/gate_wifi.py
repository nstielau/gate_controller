"""Bounded local Wi-Fi profiles; credentials never leave the device."""

MAX_NETWORKS = 5


def profiles(config):
    if not config:
        return []
    saved = config.get("wifi_networks")
    if saved is None:
        saved = [{"ssid": config["ssid"], "password": config.get("password", "")}] if config.get("ssid") else []
    result = []
    for entry in saved:
        if not isinstance(entry, dict):
            raise ValueError("Invalid saved network")
        ssid = entry.get("ssid", "")
        password = entry.get("password", "")
        validate(ssid, password)
        if any(p["ssid"] == ssid for p in result):
            raise ValueError("Duplicate saved network")
        result.append({"ssid": ssid, "password": password})
    if len(result) > MAX_NETWORKS:
        raise ValueError("Save at most five networks")
    return result


def validate(ssid, password):
    if not isinstance(ssid, str) or not 1 <= len(ssid.encode("utf-8")) <= 32 or "\x00" in ssid:
        raise ValueError("Network names must be 1 to 32 bytes")
    if not isinstance(password, str) or (password and not 8 <= len(password) <= 63):
        raise ValueError("Wi-Fi passwords must be 8 to 63 characters")


def update_network(config, ssid, password, open_network=False):
    saved = profiles(config)
    existing = None
    for network in saved:
        if network["ssid"] == ssid:
            existing = network
            break
    if not password and existing and not open_network:
        password = existing["password"]
    if open_network:
        password = ""
    validate(ssid, password)
    if existing is None and len(saved) >= MAX_NETWORKS:
        raise ValueError("Save at most five networks; forget one first")
    entry = {"ssid": ssid, "password": password}
    if existing is None:
        saved.append(entry)
    else:
        saved[saved.index(existing)] = entry
    result = dict(config or {})
    result["wifi_networks"] = saved
    if not result.get("ssid") or result["ssid"] == ssid:
        result.update(entry)
    return result


def forget_network(config, ssid):
    result = dict(config or {})
    saved = [p for p in profiles(config) if p["ssid"] != ssid]
    result["wifi_networks"] = saved
    if result.get("ssid") == ssid:
        result.pop("ssid", None)
        result.pop("password", None)
        if saved:
            result.update(saved[0])
    return result


def connection_order(config, visible):
    signals = {p["ssid"]: p["rssi"] for p in visible}
    last = config.get("ssid")
    return sorted(profiles(config), key=lambda p: (
        p["ssid"] not in signals,
        p["ssid"] != last,
        -signals.get(p["ssid"], -100),
    ))
