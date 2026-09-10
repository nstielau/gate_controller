#!/usr/bin/env python3
"""Publish a versioned blink-interval command to a Gate Controller.

Set MQTT_USERNAME and MQTT_PASSWORD before running this script. It uses only
the Python standard library and verifies the broker certificate with the
EMQX CA file stored at the repository root.
"""

import argparse
import base64
import json
from pathlib import Path
import socket
import ssl
import sys
import uuid
from urllib import error, request
from env_config import load_dotenv


DEFAULT_BROKER = "jd3a6164.ala.us-east-1.emqxsl.com"
DEFAULT_PORT = 8883
DEFAULT_CA_FILE = Path(__file__).resolve().parents[1] / "emqxsl-ca.crt"
DEFAULT_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def mqtt_string(value):
    encoded = value.encode("utf-8")
    if len(encoded) > 65535:
        raise ValueError("MQTT string is too long")
    return len(encoded).to_bytes(2, "big") + encoded


def remaining_length(value):
    encoded = bytearray()
    while True:
        digit = value % 128
        value //= 128
        if value:
            digit |= 0x80
        encoded.append(digit)
        if not value:
            return bytes(encoded)


def packet(header, payload):
    return bytes([header]) + remaining_length(len(payload)) + payload


def receive_exact(connection, count):
    data = bytearray()
    while len(data) < count:
        chunk = connection.recv(count - len(data))
        if not chunk:
            raise ConnectionError("MQTT broker closed the connection")
        data.extend(chunk)
    return bytes(data)


def receive_remaining_length(connection):
    value = 0
    multiplier = 1
    for _ in range(4):
        digit = receive_exact(connection, 1)[0]
        value += (digit & 0x7F) * multiplier
        if not digit & 0x80:
            return value
        multiplier *= 128
    raise ValueError("invalid MQTT remaining length")


def connect_packet(client_id, username, password):
    variable_header = mqtt_string("MQTT") + bytes([4, 0xC2]) + (60).to_bytes(2, "big")
    payload = mqtt_string(client_id) + mqtt_string(username) + mqtt_string(password)
    return packet(0x10, variable_header + payload)


def command_payload(interval_ms, command_id):
    if type(interval_ms) is not int or not 25 <= interval_ms <= 60000:
        raise ValueError("interval_ms must be an integer between 25 and 60000")
    return json.dumps({"version": 1, "type": "set_blink_interval",
                       "blink_interval_ms": interval_ms, "command_id": command_id},
                      separators=(",", ":"))


def receive_packet(connection):
    header = receive_exact(connection, 1)[0]
    length = receive_remaining_length(connection)
    if length > 65536:
        raise ValueError("MQTT response exceeds 64 KiB")
    return header, receive_exact(connection, length)


def publish_mqtt(broker, port, ca_file, username, password, topic, interval_ms, retain=True, command_id=None):
    if not topic or any(character in topic for character in "#+\x00"):
        raise ValueError("command topic must not be empty or contain wildcards or NUL")
    command_id = command_id or uuid.uuid4().hex
    payload = command_payload(interval_ms, command_id).encode("utf-8")
    context = ssl.create_default_context(cafile=str(ca_file))
    client_id = "gate-push-" + uuid.uuid4().hex[:16]
    with socket.create_connection((broker, port), timeout=10) as raw_socket:
        with context.wrap_socket(raw_socket, server_hostname=broker) as connection:
            connection.sendall(connect_packet(client_id, username, password))
            header, response = receive_packet(connection)
            if header != 0x20 or response != b"\x00\x00":
                raise ConnectionError("MQTT CONNECT rejected: {!r}{!r}".format(header, response))

            # QoS 1: don't claim success until the broker acknowledges packet 1.
            flags = 0x33 if retain else 0x32
            connection.sendall(packet(flags, mqtt_string(topic) + b"\x00\x01" + payload))
            header, response = receive_packet(connection)
            if header != 0x40 or response != b"\x00\x01":
                raise ConnectionError("MQTT broker did not acknowledge publish packet 1")
            connection.sendall(b"\xE0\x00")
    return command_id


def publish_api(api_url, ca_file, app_id, app_secret, topic, interval_ms, retain):
    command = json.dumps(
        {"version": 1, "type": "set_blink_interval", "blink_interval_ms": interval_ms},
        separators=(",", ":"),
    )
    body = json.dumps(
        {"topic": topic, "payload": command, "qos": 1, "retain": retain},
        separators=(",", ":"),
    ).encode("utf-8")
    credentials = "{}:{}".format(app_id, app_secret).encode("utf-8")
    publish_request = request.Request(
        api_url.rstrip("/") + "/publish",
        data=body,
        headers={
            "Authorization": "Basic " + base64.b64encode(credentials).decode("ascii"),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    context = ssl.create_default_context(cafile=str(ca_file))
    try:
        with request.urlopen(publish_request, context=context, timeout=15) as response:
            return response.status, response.read().decode("utf-8")
    except error.HTTPError as response:
        return response.code, response.read().decode("utf-8")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("interval_ms", type=int, help="Blink interval in milliseconds (25–60000).")
    parser.add_argument("--device-id", help="Chip suffix from the portal, e.g. b3640c.")
    parser.add_argument("--topic", help="Command topic; overrides --device-id.")
    parser.add_argument("--broker", default=DEFAULT_BROKER)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--ca-file", type=Path, default=DEFAULT_CA_FILE)
    parser.add_argument("--transport", choices=("api", "mqtt"), default="mqtt", help="Transport to use (default: mqtt).")
    parser.add_argument("--api-url", help="EMQX Deployment API base URL, ending in /api/v5.")
    parser.add_argument("--retain", action=argparse.BooleanOptionalAction, default=True,
                        help="Retain the desired blink setting (default: true).")
    return parser.parse_args()


def main():
    args = parse_args()
    env = load_dotenv(DEFAULT_ENV_FILE)
    if not 25 <= args.interval_ms <= 60000:
        raise SystemExit("interval_ms must be between 25 and 60000")
    if not args.topic and not args.device_id:
        raise SystemExit("pass --device-id or --topic")
    if not args.ca_file.is_file():
        raise SystemExit("CA certificate not found: {}".format(args.ca_file))
    topic = args.topic or "gate/v1/devices/{}/command".format(args.device_id.lower())
    api_url = args.api_url or env.get("EMQX_API_URL")
    transport = args.transport
    if transport == "api":
        if not api_url:
            raise SystemExit("set EMQX_API_URL or pass --api-url")
        app_id = env.get("EMQX_APP_ID")
        app_secret = env.get("EMQX_APP_SECRET")
        if not app_id or not app_secret:
            raise SystemExit("set EMQX_APP_ID and EMQX_APP_SECRET before API publishing")
        status, response = publish_api(api_url, args.ca_file, app_id, app_secret, topic, args.interval_ms, args.retain)
        if status not in (200, 202):
            raise SystemExit("EMQX API publish failed ({}): {}".format(status, response))
        print("EMQX API response {}: {}".format(status, response))
    else:
        username = env.get("MQTT_USERNAME")
        password = env.get("MQTT_PASSWORD")
        if not username or not password:
            raise SystemExit("set MQTT_USERNAME and MQTT_PASSWORD before MQTT publishing")
        command_id = publish_mqtt(args.broker, args.port, args.ca_file, username, password, topic, args.interval_ms, args.retain)
        print("Broker acknowledged command {}".format(command_id))
    print("Published {} ms to {} (retained={}); device application not yet verified".format(args.interval_ms, topic, args.retain))


if __name__ == "__main__":
    try:
        main()
    except (ConnectionError, OSError, ssl.SSLError, ValueError) as error:
        print("MQTT publish failed: {}".format(error), file=sys.stderr)
        raise SystemExit(1)
