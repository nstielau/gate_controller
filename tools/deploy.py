#!/usr/bin/env python3
"""Preflight and copy changed files to CIRCUITPY; preserve unrelated files."""

import argparse
import os
from pathlib import Path

from render_settings_toml import render_settings

REPOSITORY = Path(__file__).resolve().parents[1]


def deploy(destination):
    destination = destination.resolve()
    if not (destination / "boot_out.txt").is_file():
        raise ValueError("CIRCUITPY not found at {}".format(destination))
    # Read/validate everything before the first device write. Only MQTT login
    # credentials are rendered; Deployment API credentials stay on the host.
    env_file = REPOSITORY / ".env"
    ca_file = REPOSITORY / "emqxsl-ca.crt"
    app = REPOSITORY / "circuitpython"
    if not env_file.is_file():
        raise ValueError("missing {}".format(env_file))
    if not ca_file.is_file():
        raise ValueError("missing {}".format(ca_file))
    settings = render_settings(env_file, destination / "settings.toml")
    files = [(path.relative_to(app), path.read_bytes()) for path in sorted((app / "lib").rglob("*"))
             if path.is_file() and path.suffix in (".py", ".mpy")]
    files.extend([
        (Path("certs/emqxsl-ca.crt"), ca_file.read_bytes()),
        (Path("settings.toml"), settings.encode()),
        (Path("drawbridge.py"), (app / "drawbridge.py").read_bytes()),
        (Path("boot.py"), (app / "boot.py").read_bytes()),
        (Path("code.py"), (app / "code.py").read_bytes()),
    ])
    changed = 0
    for relative, content in files:
        target = destination / relative
        if not target.exists() or target.read_bytes() != content:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            changed += 1
            print("Updated {}".format(relative))
    os.sync()
    print("Deployment complete: {} changed files".format(changed))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    try:
        deploy(parser.parse_args().destination)
    except (OSError, ValueError) as error:
        raise SystemExit("Deploy failed: {}".format(error)) from None
