"""Wi-Fi and MQTT provisioning for the Gate Controller XIAO ESP32-S3.

Join the open Gate-Setup-* access point and open http://192.168.4.1. The
portal stores Wi-Fi and MQTT credentials in microcontroller.nvm, outside the
USB-mounted CIRCUITPY filesystem.
"""

import json
import ipaddress
import microcontroller
import os
import ssl
import time
import wifi

import adafruit_connection_manager
import adafruit_minimqtt.adafruit_minimqtt as MQTT
import board
import digitalio
import supervisor
from gate_mqtt import GateMQTT, NETWORK_SECONDS
from drawbridge import Indicators, create_app, APP_VERSION
from gate_hold import HoldState
from gate_base import BASE_VERSION


CONFIG_SIZE = min(512, len(microcontroller.nvm))
CONFIG_MAGIC = b"GATE3"
OLD_CONFIG_MAGIC = b"GATE1"
OLD_CONFIG_SIZE = 192

MQTT_BROKER = "jd3a6164.ala.us-east-1.emqxsl.com"
MQTT_PORT = 8883
EMQX_CA_FILE = "/certs/emqxsl-ca.crt"
BOOT_ID = "".join("{:02x}".format(value) for value in os.urandom(6))

TRANSISTOR_CONTROL_PIN = board.D10
WIFI_INDICATOR_PIN = board.D0
MQTT_INDICATOR_PIN = board.D1
HOLD_INDICATOR_PIN = board.D2

led = digitalio.DigitalInOut(board.LED)
led.switch_to_output(value=False)  # Onboard LED is active LOW.

gate_output = None
hold_led = None
wifi_led = None
mqtt_led = None
indicators = Indicators(time.monotonic())
hold = HoldState()
hold_samples_left = 4
application = None
ota_store = None
ota_http = None
ota_version = APP_VERSION
ota_selected = None
ota_trial_started = 0
ota_healthy_since = None
ota_next_check = 0
ota_backoff = 60
ota_state = "disabled"
watchdog_timer = None


class Platform:
    def request_hold(self, seconds, command_id, now):
        # Bootstrap validates and owns the physical output deadline independently.
        hold.apply(
            json.dumps(
                {
                    "version": 1,
                    "type": "hold_gate",
                    "duration_seconds": seconds,
                    "command_id": command_id,
                }
            ),
            now,
        )


def initialize_application(allow_ota=True):
    global application, indicators, ota_store, ota_selected, ota_version
    global ota_trial_started, ota_state, watchdog_timer, ota_next_check
    factory = create_app
    if (
        allow_ota
        and os.getenv("OTA_ENABLED") in (1, "1")
        and board.board_id == "seeed_xiao_esp32_s3_sense"
    ):
        import storage

        if not storage.getmount("/").readonly:
            from gate_ota import UpdateStore
            from watchdog import WatchDogMode

            ota_store = UpdateStore()
            path, ota_selected = ota_store.begin_boot()
            watchdog_timer = microcontroller.watchdog
            watchdog_timer.timeout = 60
            watchdog_timer.mode = WatchDogMode.RESET
            if path:
                namespace = {"__name__": "drawbridge_candidate"}
                with open(path) as source:
                    exec(source.read(), namespace)
                if (
                    namespace.get("APP_API_VERSION") != 1
                    or namespace.get("APP_VERSION") != ota_selected["app_version"]
                ):
                    raise ValueError("invalid_app_interface")
                factory = namespace["create_app"]
                ota_version = namespace["APP_VERSION"]
            ota_state = ota_store.state["outcome"]
            ota_trial_started = time.monotonic()
            ota_next_check = ota_trial_started + 60 + int.from_bytes(os.urandom(1), "big")
    application = factory(Platform(), time.monotonic())
    indicators = application.indicators
    log_event(
        "application_ready",
        version=ota_version,
        base_version=BASE_VERSION,
        ota_state=ota_state,
        board_id=str(board.board_id),
    )


def ota_service(runtime, client):
    global ota_http, ota_state, ota_next_check, ota_backoff, ota_healthy_since
    if ota_store is None:
        return
    now = time.monotonic()
    online = client is not None and wifi.radio.connected
    if watchdog_timer:
        watchdog_timer.feed()
    if ota_store.state["trial"]:
        if online:
            if ota_healthy_since is None:
                ota_healthy_since = now
            if now - ota_healthy_since >= 60:
                ota_store.confirm()
                ota_state = "current"
                log_event("ota_confirmed", version=ota_version)
        else:
            ota_healthy_since = None
        if ota_store.state["trial"] and now - ota_trial_started > 300:
            ota_store.rollback()
            supervisor.reload()
        return
    if not online or hold.active(now) or now < ota_next_check:
        return
    import sys
    from gate_http import DeviceHTTP
    from gate_ota import validate_manifest

    def service():
        client.poll()
        service_outputs(runtime, online=bool(wifi.radio.connected))
        if watchdog_timer:
            watchdog_timer.feed()
        if hold.active(time.monotonic()):
            raise OSError("hold_active")

    try:
        if ota_http is None:
            if os.getenv("OTA_DEVICE_ID") != device_suffix().lower():
                raise ValueError("ota_identity_mismatch")
            ota_http = DeviceHTTP(
                adafruit_connection_manager.get_radio_socketpool(wifi.radio),
                device_suffix().lower(),
                os.getenv("OTA_TOKEN") or "",
            )
        response = ota_http.request(
            "manifest", service, lambda r: None if r.status == 204 else r.json()
        )
        if response is not None:
            manifest = validate_manifest(response, board.board_id, sys.implementation.version[0])
            if manifest["sequence"] > ota_store.state["floor"]:
                installed = ota_http.request(
                    "artifact?sequence=" + str(manifest["sequence"]),
                    service,
                    lambda r: (
                        ota_store.stage(manifest, r.chunks(), service) if r.status == 200 else False
                    ),
                    limit=manifest["size"],
                )
                if installed:
                    log_event("ota_staged", version=manifest["app_version"])
                    supervisor.reload()
        ota_http.request(
            "report",
            service,
            lambda r: None,
            body={
                "state": ota_state,
                "version": ota_version,
                "base_version": BASE_VERSION,
                "sequence": ota_selected["sequence"] if ota_selected else 0,
            },
        )
        ota_backoff = 60
        ota_next_check = time.monotonic() + 21600 + int.from_bytes(os.urandom(2), "big") % 1800
    except (OSError, ValueError, RuntimeError):
        log_event("ota_check_failed")  # URLs and credentials are deliberately omitted.
        ota_next_check = time.monotonic() + ota_backoff
        ota_backoff = min(ota_backoff * 2, 86400)


# TEMPORARY STARTUP DIAGNOSTIC — remove this function and its call in main()
# once the external wiring has been verified. It flashes the three candidate
# signal pins together before Wi-Fi, MQTT, or any other controller work starts.
def startup_pin_diagnostic():
    pins = [digitalio.DigitalInOut(pin) for pin in (board.D0, board.D1, board.D2)]
    try:
        for output in pins:
            output.switch_to_output(value=False)
        for _ in range(3):
            for output in pins:
                output.value = True
            time.sleep(0.2)
            for output in pins:
                output.value = False
            time.sleep(0.2)
    finally:
        for output in pins:
            output.value = False
            output.deinit()


def service_status_led(wifi_connected, mqtt_connected, gate_active, now):
    """Independent health, Wi-Fi, MQTT and hold LEDs; never touch D10 here."""
    global hold_samples_left
    tick = application.tick if application is not None else indicators.tick
    changed, elapsed = tick(now, wifi_connected, mqtt_connected, gate_active)
    led.value = not indicators.alive_on
    wifi_led.value = indicators.wifi_on
    mqtt_led.value = indicators.mqtt_on
    hold_led.value = indicators.hold_on
    if changed:
        hold_samples_left = 4
        log_event("indicator_mode", **indicator_status())
    if elapsed is not None and hold_samples_left:
        hold_samples_left -= 1
        log_event("indicator_edge", pin="D2", on=indicators.hold_on, elapsed_ms=elapsed)


def indicator_status():
    return {
        "wifi_connected": bool(indicators.wifi_connected),
        "mqtt_connected": bool(indicators.mqtt_connected),
        "wifi_led_on": wifi_led.value,
        "mqtt_led_on": mqtt_led.value,
        "alive_edge_count": indicators.alive_edges,
        "transistor_high": bool(gate_output.value),
        "onboard_led_on": not led.value,
        "hold_led_on": hold_led.value,
        "hold_edge_count": indicators.hold_edges,
    }


def device_suffix():
    return "".join("{:02X}".format(value) for value in microcontroller.cpu.uid[-3:])


def setup_ssid():
    """Derive an SSID that will not collide with another setup controller."""
    return "Gate-Setup-" + device_suffix()


def default_topic(message_kind):
    return "gate/v1/devices/{}/{}".format(device_suffix().lower(), message_kind)


def load_config():
    """Return saved configuration and migrate the earlier Wi-Fi-only record."""
    nvm = microcontroller.nvm
    magic = bytes(nvm[: len(CONFIG_MAGIC)])
    if magic == CONFIG_MAGIC:
        limit = CONFIG_SIZE
        start = len(CONFIG_MAGIC) + 2
        size = int.from_bytes(bytes(nvm[len(CONFIG_MAGIC) : start]), "big")
    elif magic in (OLD_CONFIG_MAGIC, b"GATE2"):
        limit = OLD_CONFIG_SIZE if magic == OLD_CONFIG_MAGIC else CONFIG_SIZE
        start = len(CONFIG_MAGIC) + 1
        size = nvm[len(CONFIG_MAGIC)]
    else:
        return None

    if size == 0 or size > limit - start:
        return None

    try:
        config = json.loads(bytes(nvm[start : start + size]).decode("utf-8"))
        if not isinstance(config, dict) or not config.get("ssid"):
            return None
        return config
    except (ValueError, UnicodeError):
        return None


def add_settings_credentials(config):
    """Use deploy-time MQTT credentials while keeping Wi-Fi in board NVM."""
    if not config:
        return None
    result = dict(config)
    username = os.getenv("MQTT_USERNAME")
    password = os.getenv("MQTT_PASSWORD")
    if username and password:
        result["mqtt_username"] = username
        result["mqtt_password"] = password
        result.setdefault("mqtt_topic", default_topic("status"))
        result.setdefault("mqtt_command_topic", default_topic("command"))
    return result


def save_config(config):
    """Store configuration outside CIRCUITPY so USB mounting cannot block writes."""
    payload = json.dumps(config).encode("utf-8")
    if len(payload) > CONFIG_SIZE - len(CONFIG_MAGIC) - 2:
        raise ValueError("Configuration is too long")

    record = bytearray(CONFIG_SIZE)
    record[: len(CONFIG_MAGIC)] = CONFIG_MAGIC
    start = len(CONFIG_MAGIC) + 2
    record[len(CONFIG_MAGIC) : start] = len(payload).to_bytes(2, "big")
    record[start : start + len(payload)] = payload
    microcontroller.nvm[:CONFIG_SIZE] = record


def url_decode(value):
    """Decode application/x-www-form-urlencoded text without an external lib."""
    decoded = bytearray()
    index = 0
    while index < len(value):
        character = value[index]
        if character == "+":
            decoded.append(32)
        elif character == "%" and index + 2 < len(value):
            try:
                decoded.append(int(value[index + 1 : index + 3], 16))
                index += 2
            except ValueError:
                decoded.extend(character.encode("utf-8"))
        else:
            decoded.extend(character.encode("utf-8"))
        index += 1
    return decoded.decode("utf-8")


def parse_form(body):
    fields = {}
    for item in body.decode("utf-8").split("&"):
        key, separator, value = item.partition("=")
        if separator:
            fields[url_decode(key)] = url_decode(value)
    return fields


def page(message=""):
    return """<!doctype html>
<html><head><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>Gate controller setup</title>
<style>body{{font:17px sans-serif;max-width:34rem;margin:3rem auto;padding:0 1rem}}input{{box-sizing:border-box;width:100%;padding:.7rem;margin:.3rem 0 1rem}}button{{padding:.7rem 1rem}}small{{display:block;margin-top:-.7rem;margin-bottom:1rem}}</style>
</head><body><h1>Gate controller setup</h1><p>{message}</p>
<form action=\"/configure\" method=\"post\"><h2>Wi-Fi</h2>
<label>Network name (SSID)</label><input name=\"ssid\" maxlength=\"32\" autofocus>
<small>Leave Wi-Fi fields blank to keep the saved network.</small>
<label>Wi-Fi password</label><input name=\"password\" type=\"password\" maxlength=\"63\">
<h2>EMQX MQTT</h2><p>Broker: <code>{broker}:{port}</code></p>
<label>MQTT username</label><input name=\"mqtt_username\" maxlength=\"96\" required>
<label>MQTT password</label><input name=\"mqtt_password\" type=\"password\" maxlength=\"128\" required>
<label>Status topic</label><input name=\"mqtt_topic\" maxlength=\"128\" value=\"{status_topic}\" required>
<small>The controller publishes retained status to this topic.</small>
<label>Command topic</label><input name=\"mqtt_command_topic\" maxlength=\"128\" value=\"{command_topic}\" required>
<small>Publish JSON blink commands here.</small>
<button type=\"submit\">Save and connect</button></form></body></html>""".format(
        message=message,
        broker=MQTT_BROKER,
        port=MQTT_PORT,
        status_topic=default_topic("status"),
        command_topic=default_topic("command"),
    )


def send_response(client, body, status="200 OK"):
    encoded_body = body.encode("utf-8")
    headers = (
        "HTTP/1.1 {}\r\nContent-Type: text/html; charset=utf-8\r\n"
        "Content-Length: {}\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n"
    ).format(status, len(encoded_body))
    client.sendall(headers.encode("utf-8"))
    client.sendall(encoded_body)


def config_from_form(fields):
    previous = load_config() or {}
    submitted_ssid = fields.get("ssid", "").strip()
    submitted_password = fields.get("password", "")
    ssid = submitted_ssid or previous.get("ssid", "")
    password = (
        submitted_password
        if submitted_ssid and submitted_ssid != previous.get("ssid")
        else submitted_password or previous.get("password", "")
    )
    if not ssid:
        raise ValueError("Enter a Wi-Fi network name.")
    if password and not 8 <= len(password) <= 63:
        raise ValueError("Wi-Fi passwords must be 8 to 63 characters.")

    username = fields.get("mqtt_username", "").strip()
    mqtt_password = fields.get("mqtt_password", "")
    topic = fields.get("mqtt_topic", "").strip()
    command_topic = fields.get("mqtt_command_topic", "").strip()
    if not username or not mqtt_password:
        raise ValueError("Enter the MQTT username and password.")
    if not topic:
        raise ValueError("Enter an MQTT status topic.")
    if not command_topic:
        raise ValueError("Enter an MQTT command topic.")
    if topic == command_topic or any(c in topic + command_topic for c in "#+\x00"):
        raise ValueError("Use distinct MQTT topics without wildcards.")
    return {
        "ssid": ssid,
        "password": password,
        "mqtt_username": username,
        "mqtt_password": mqtt_password,
        "mqtt_topic": topic,
        "mqtt_command_topic": command_topic,
    }


def read_http_request(client):
    """Read bounded headers and the entire body, including fragmented POSTs."""
    request = bytearray()
    buffer = bytearray(512)
    while b"\r\n\r\n" not in request:
        received = client.recv_into(buffer)
        if not received:
            raise ValueError("incomplete HTTP headers")
        request.extend(buffer[:received])
        if len(request) > 4096:
            raise ValueError("HTTP headers too large")
    header, _, body = bytes(request).partition(b"\r\n\r\n")
    length = 0
    for line in header.split(b"\r\n")[1:]:
        key, _, value = line.partition(b":")
        if key.lower() == b"content-length":
            length = int(value.strip())
        if key.lower() == b"transfer-encoding":
            raise ValueError("unsupported transfer encoding")
    if not 0 <= length <= 4096:
        raise ValueError("HTTP body too large")
    while len(body) < length:
        received = client.recv_into(buffer)
        if not received:
            raise ValueError("incomplete HTTP body")
        body += bytes(buffer[:received])
    return header, body[:length]


def service_http(server):
    """Process one configuration request, if a browser has made one."""
    try:
        client, _ = server.accept()
    except OSError:
        return

    try:
        client.settimeout(1)
        header, body = read_http_request(client)
        request_line = header.split(b"\r\n", 1)[0].split(b" ")

        if (
            len(request_line) >= 2
            and request_line[0] == b"POST"
            and request_line[1] == b"/configure"
        ):
            save_config(config_from_form(parse_form(body)))
            send_response(
                client, page("Saved. The controller is restarting and will connect securely.")
            )
            time.sleep(1)
            supervisor.reload()
        else:
            send_response(client, page())
    except (OSError, UnicodeError, ValueError):
        try:
            send_response(client, page("Please check the fields and try again."), "400 Bad Request")
        except OSError:
            pass
    finally:
        client.close()


def service_dns(dns_socket, ap_ip):
    """Resolve DNS requests to the setup page for captive-portal behavior."""
    packet = bytearray(256)
    try:
        size, client_address = dns_socket.recvfrom_into(packet)
    except OSError:
        return

    query = bytes(packet[:size])
    if len(query) < 17:
        return
    end = 12
    while end < len(query) and query[end] != 0:
        label_size = query[end]
        if label_size & 0xC0:
            return
        end += label_size + 1
    if end + 5 > len(query):
        return

    question = query[12 : end + 5]
    address_bytes = bytes(int(part) for part in ap_ip.split("."))
    response = (
        query[:2]
        + b"\x81\x80"
        + query[4:6]
        + b"\x00\x01\x00\x00\x00\x00"
        + question
        + b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x1e\x00\x04"
        + address_bytes
    )
    try:
        dns_socket.sendto(response, client_address)
    except OSError:
        pass


def mqtt_ready(config):
    return bool(
        config
        and config.get("mqtt_username")
        and config.get("mqtt_password")
        and config.get("mqtt_topic")
        and config.get("mqtt_command_topic")
    )


def log_event(event, **fields):
    fields.update(event=event, boot_id=BOOT_ID, uptime_ms=int(time.monotonic() * 1000))
    print("GATE_LOG " + json.dumps(fields))


def status_payload(runtime):
    return json.dumps(
        {
            "version": 1,
            "type": "device_status",
            "state": "online",
            "device_id": device_suffix().lower(),
            "ip": str(wifi.radio.ipv4_address),
            "boot_id": BOOT_ID,
            "uptime_ms": int(time.monotonic() * 1000),
            "indicators": indicator_status(),
            "hold_remaining_seconds": hold.remaining(time.monotonic()),
            "firmware": {
                "version": ota_version,
                "bootstrap": BASE_VERSION,
                "base_version": BASE_VERSION,
                "state": ota_state,
            },
        }
    )


def on_mqtt_message(client, topic, message):
    runtime = client.user_data
    if topic != runtime["command_topic"]:
        return
    if getattr(client, "message_retained", False):
        log_event("command_rejected", reason="retained hold commands are unsafe")
        return
    try:
        (application or create_app(Platform(), time.monotonic())).on_message(
            message, False, time.monotonic()
        )
    except ValueError:
        log_event("command_rejected", reason="invalid hold schema")
        return
    client.user_data["dirty"] = True
    log_event("hold_applied", command_id=hold.command_id, duration_seconds=hold.duration_seconds)


def service_outputs(runtime, online):
    now = time.monotonic()
    active = hold.active(now)
    gate_output.value = active
    service_status_led(bool(wifi.radio.connected), online, active, now)


def connect_mqtt(pool, config, runtime):
    ssl_context = ssl.create_default_context()
    with open(EMQX_CA_FILE, "r") as certificate_file:
        ssl_context.load_verify_locations(cadata=certificate_file.read())
    client = GateMQTT(
        broker=MQTT_BROKER,
        port=MQTT_PORT,
        username=config["mqtt_username"],
        password=config["mqtt_password"],
        client_id="gate-controller-" + device_suffix().lower(),
        is_ssl=True,
        socket_pool=pool,
        ssl_context=ssl_context,
        connect_retries=1,
        socket_timeout=NETWORK_SECONDS,
        recv_timeout=10,
        user_data=runtime,
    )
    client.will_set(
        config["mqtt_topic"],
        json.dumps(
            {
                "version": 1,
                "type": "device_status",
                "state": "offline",
                "device_id": device_suffix().lower(),
                "boot_id": BOOT_ID,
            }
        ),
        retain=True,
    )
    client.on_message = on_mqtt_message
    try:
        client.connect()
        client.subscribe(config["mqtt_command_topic"], qos=1)
    except BaseException:
        client.close()
        raise
    runtime["dirty"] = True
    log_event("mqtt_connected", command_topic=config["mqtt_command_topic"])
    return client


def start_portal():
    """Start the AP only for provisioning; normal operation is station-only."""
    ssid = setup_ssid()
    wifi.radio.tx_power = 15
    wifi.radio.start_ap(ssid, channel=6, max_connections=4)
    wifi.radio.set_ipv4_address_ap(
        ipv4=ipaddress.ip_address("192.168.4.1"),
        netmask=ipaddress.ip_address("255.255.255.0"),
        gateway=ipaddress.ip_address("192.168.4.1"),
    )
    wifi.radio.start_dhcp_ap()
    ap_ip = str(wifi.radio.ipv4_address_ap)
    pool = adafruit_connection_manager.get_radio_socketpool(wifi.radio)
    http = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
    http.setsockopt(pool.SOL_SOCKET, pool.SO_REUSEADDR, 1)
    http.bind((ap_ip, 80))
    http.listen(1)
    http.settimeout(0)

    dns = pool.socket(pool.AF_INET, pool.SOCK_DGRAM)
    dns.bind((ap_ip, 53))
    dns.settimeout(0)
    print("Setup Wi-Fi:", ssid)
    print("Setup network is open; open http://{}".format(ap_ip))
    return pool, http, dns, ap_ip


def run_portal():
    """Serve provisioning until the submitted form resets the controller."""
    _, http, dns, ap_ip = start_portal()
    while True:
        service_outputs(None, online=False)
        service_dns(dns, ap_ip)
        service_http(http)


def run_configured_controller(pool, config):
    """A single retry loop restores Wi-Fi before recreating the MQTT session."""
    global hold_samples_left
    runtime = {"command_topic": config["mqtt_command_topic"], "dirty": True}
    client = None
    next_attempt = 0
    last_status = 0
    while True:
        now = time.monotonic()
        if watchdog_timer:
            watchdog_timer.feed()
        service_outputs(runtime, online=client is not None and wifi.radio.connected)
        try:
            if client is None:
                if now < next_attempt:
                    time.sleep(0.01)
                    continue
                if not wifi.radio.connected:
                    log_event("wifi_connecting")
                    wifi.radio.connect(config["ssid"], config["password"], timeout=12)
                    log_event("wifi_connected", ip=str(wifi.radio.ipv4_address))
                service_outputs(runtime, online=False)
                client = connect_mqtt(pool, config, runtime)
            if not wifi.radio.connected:
                raise ConnectionError("Wi-Fi disconnected")
            client.poll()
            service_outputs(runtime, online=True)
            if runtime["dirty"] or now - last_status >= 10:
                client.publish(config["mqtt_topic"], status_payload(runtime), retain=True)
                runtime["dirty"] = False
                last_status = time.monotonic()
                log_event("heartbeat", **indicator_status())
                hold_samples_left = 4
            ota_service(runtime, client)
        except (ConnectionError, MQTT.MMQTTException, OSError) as error:
            # ValueError is a programming/configuration error, not a network failure.
            log_event("connection_error", error=str(error))
            service_outputs(runtime, online=False)
            if client is not None:
                client.close()
                client = None
            next_attempt = time.monotonic() + 5
            ota_service(runtime, None)
        time.sleep(0.001)


def main():
    global gate_output, hold_led, wifi_led, mqtt_led
    log_event("boot", reset_reason=str(microcontroller.cpu.reset_reason))
    outputs = []
    try:
        for pin in (
            TRANSISTOR_CONTROL_PIN,
            WIFI_INDICATOR_PIN,
            MQTT_INDICATOR_PIN,
            HOLD_INDICATOR_PIN,
        ):
            output = digitalio.DigitalInOut(pin)
            outputs.append(output)
            output.switch_to_output(value=False)
            if pin is TRANSISTOR_CONTROL_PIN:
                # TEMPORARY diagnostic; D10 is already LOW and never blinks.
                startup_pin_diagnostic()
        gate_output, wifi_led, mqtt_led, hold_led = outputs
        config = add_settings_credentials(load_config())
        # Provisioning may run indefinitely; do not trial an app/start its
        # watchdog until saved Wi-Fi/MQTT settings are available.
        initialize_application(allow_ota=bool(config and mqtt_ready(config)))
        service_outputs(None, online=False)
        if config and mqtt_ready(config):
            pool = adafruit_connection_manager.get_radio_socketpool(wifi.radio)
            run_configured_controller(pool, config)
        else:
            log_event("provisioning")
            run_portal()
    except Exception:
        for output in outputs:
            output.value = False
        if ota_store is not None and ota_selected is not None:
            if ota_store.state["trial"]:
                ota_store.rollback()
            else:
                ota_store.save(dict(ota_store.state, active=None, outcome="rolled_back"))
            log_event("ota_rolled_back")
            supervisor.reload()
        raise
    finally:
        for output in outputs:
            output.value = False
            output.deinit()
        led.value = True  # Active-low heartbeat stops when the program exits.
        led.deinit()
        if watchdog_timer:
            # Output cleanup must run even if a port cannot disable its watchdog.
            watchdog_timer.mode = None


if __name__ == "__main__":
    main()
