#!/usr/bin/env python3
"""Publish a non-retained, TLS-verified timed gate hold command."""

import argparse
import json
import uuid

from env_config import load_dotenv
from mqtt_blink import DEFAULT_BROKER, DEFAULT_CA_FILE, DEFAULT_ENV_FILE, DEFAULT_PORT, publish_payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("duration", type=float, help="seconds to hold (0 cancels)")
    parser.add_argument("--device-id", default="b3640c")
    parser.add_argument("--topic")
    parser.add_argument("--command-id")
    args = parser.parse_args()
    if not 0 <= args.duration <= 86400:
        parser.error("duration must be between 0 and 86400 seconds")
    env = load_dotenv(DEFAULT_ENV_FILE)
    if not env.get("MQTT_USERNAME") or not env.get("MQTT_PASSWORD"):
        raise SystemExit("MQTT_USERNAME and MQTT_PASSWORD are required in .env")
    topic = args.topic or "gate/v1/devices/{}/command".format(args.device_id)
    command_id = args.command_id or uuid.uuid4().hex
    payload = json.dumps({"version": 1, "type": "hold_gate",
                          "duration_seconds": args.duration,
                          "command_id": command_id}, separators=(",", ":"))
    publish_payload(DEFAULT_BROKER, DEFAULT_PORT, DEFAULT_CA_FILE,
                    env["MQTT_USERNAME"], env["MQTT_PASSWORD"], topic, payload, retain=False)
    print("Published non-retained hold: {} seconds (command {})".format(args.duration, command_id))


if __name__ == "__main__":
    main()
