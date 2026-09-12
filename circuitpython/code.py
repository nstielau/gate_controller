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
from gate_indicators import Indicators
from gate_hold import HoldState


CONFIG_SIZE = min(512, len(microcontroller.nvm))
CONFIG_MAGIC = b"GATE3"
OLD_CONFIG_MAGIC = b"GATE1"
OLD_CONFIG_SIZE = 192

MQTT_BROKER = "jd3a6164.ala.us-east-1.emqxsl.com"
MQTT_PORT = 8883
EMQX_CA_FILE = "/certs/emqxsl-ca.crt"
BOOT_ID = "".join("{:02x}".format(value) for value in os.urandom(6))

TRANSISTOR_CONTROL_PIN = board.D10
HOLD_INDICATOR_PIN = board.D0

led = digitalio.DigitalInOut(board.LED)
led.switch_to_output(value=False)  # Onboard LED is active LOW.

gate_output = None
hold_led = None
indicators = Indicators(time.monotonic())
hold = HoldState()
hold_samples_left = 4


def service_status_led(connected, gate_active, now):
    """Connectivity on board. Hold indication on D0; never touch D10 here."""
    global hold_samples_left
    changed, elapsed = indicators.tick(now, connected, gate_active)
    led.value = not indicators.connection_on
    hold_led.value = indicators.hold_on
    if changed:
        hold_samples_left = 4
        log_event("indicator_mode", **indicator_status())
    if elapsed is not None and hold_samples_left:
        hold_samples_left -= 1
        log_event("indicator_edge", pin="D0", on=indicators.hold_on, elapsed_ms=elapsed)


def indicator_status():
    return {"mqtt_connected": bool(indicators.connected),
            "transistor_high": bool(gate_output.value),
            "onboard_led_on": not led.value, "hold_led_on": hold_led.value,
            "hold_edge_count": indicators.hold_edges}


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
        size = int.from_bytes(bytes(nvm[len(CONFIG_MAGIC):start]), "big")
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
    record[len(CONFIG_MAGIC):start] = len(payload).to_bytes(2, "big")
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
    password = (submitted_password if submitted_ssid and submitted_ssid != previous.get("ssid")
                else submitted_password or previous.get("password", ""))
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

        if len(request_line) >= 2 and request_line[0] == b"POST" and request_line[1] == b"/configure":
            save_config(config_from_form(parse_form(body)))
            send_response(client, page("Saved. The controller is restarting and will connect securely."))
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
        query[:2] + b"\x81\x80" + query[4:6] + b"\x00\x01\x00\x00\x00\x00"
        + question + b"\xC0\x0C\x00\x01\x00\x01\x00\x00\x00\x1E\x00\x04" + address_bytes
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
    return json.dumps({
        "version": 1, "type": "device_status", "state": "online",
        "device_id": device_suffix().lower(), "ip": str(wifi.radio.ipv4_address),
        "boot_id": BOOT_ID, "uptime_ms": int(time.monotonic() * 1000),
        "indicators": indicator_status(), "hold_remaining_seconds": hold.remaining(time.monotonic()),
    })


def on_mqtt_message(client, topic, message):
    runtime = client.user_data
    if topic != runtime["command_topic"]:
        return
    if getattr(client, "message_retained", False):
        log_event("command_rejected", reason="retained hold commands are unsafe")
        return
    try:
        hold.apply(message, time.monotonic())
    except ValueError:
        log_event("command_rejected", reason="invalid hold schema")
        return
    client.user_data["dirty"] = True
    log_event("hold_applied", command_id=hold.command_id,
              duration_seconds=hold.duration_seconds)


def service_outputs(runtime, online):
    now = time.monotonic()
    active = hold.active(now)
    gate_output.value = active
    service_status_led(online, active, now)


def connect_mqtt(pool, config, runtime):
    ssl_context = ssl.create_default_context()
    with open(EMQX_CA_FILE, "r") as certificate_file:
        ssl_context.load_verify_locations(cadata=certificate_file.read())
    client = GateMQTT(
        broker=MQTT_BROKER, port=MQTT_PORT,
        username=config["mqtt_username"], password=config["mqtt_password"],
        client_id="gate-controller-" + device_suffix().lower(), is_ssl=True,
        socket_pool=pool, ssl_context=ssl_context, connect_retries=1,
        socket_timeout=NETWORK_SECONDS, recv_timeout=10, user_data=runtime,
    )
    client.will_set(config["mqtt_topic"], json.dumps({
        "version": 1, "type": "device_status", "state": "offline",
        "device_id": device_suffix().lower(), "boot_id": BOOT_ID,
    }), retain=True)
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
        except (ConnectionError, MQTT.MMQTTException, OSError) as error:
            # ValueError is a programming/configuration error, not a network failure.
            log_event("connection_error", error=str(error))
            service_outputs(runtime, online=False)
            if client is not None:
                client.close()
                client = None
            next_attempt = time.monotonic() + 5
        time.sleep(0.001)


def main():
    global gate_output, hold_led
    log_event("boot", reset_reason=str(microcontroller.cpu.reset_reason))
    hold_led = digitalio.DigitalInOut(HOLD_INDICATOR_PIN)
    hold_led.switch_to_output(value=False)
    gate_output = digitalio.DigitalInOut(TRANSISTOR_CONTROL_PIN)
    try:
        gate_output.switch_to_output(value=False)
        service_outputs(None, online=False)
        config = add_settings_credentials(load_config())
        if config and mqtt_ready(config):
            pool = adafruit_connection_manager.get_radio_socketpool(wifi.radio)
            run_configured_controller(pool, config)
        else:
            log_event("provisioning")
            run_portal()
    finally:
        gate_output.value = False
        gate_output.deinit()
        hold_led.value = False
        hold_led.deinit()


if __name__ == "__main__":
    main()
