#!/usr/bin/env python3
"""Render the XIAO's settings.toml from ignored .env MQTT credentials."""

import json
from pathlib import Path
import sys
import tomllib
from env_config import load_dotenv


def render_settings(env_path, destination):
    values = load_dotenv(env_path)
    required = ("MQTT_USERNAME", "MQTT_PASSWORD")
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise ValueError("missing {} in {}".format(", ".join(missing), env_path))
    previous = destination.read_text() if destination.exists() else ""
    # Preserve unrelated board settings, replacing only credential assignments.
    lines = [line for line in previous.splitlines()
             if line.split("=", 1)[0].strip() not in required]
    output = "\n".join(lines + [
        "{} = {}".format(key, json.dumps(values[key], ensure_ascii=False)) for key in required
    ]) + "\n"
    parsed = tomllib.loads(output)
    if any(parsed.get(key) != values[key] for key in required):
        raise ValueError("settings.toml must use top-level MQTT credentials")
    return output


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: render_settings_toml.py .env /path/to/settings.toml")
    destination = Path(sys.argv[2])
    output = render_settings(Path(sys.argv[1]), destination)
    if not destination.exists() or destination.read_text() != output:
        destination.write_text(output)


if __name__ == "__main__":
    main()
