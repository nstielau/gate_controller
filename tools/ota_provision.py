"""Install a device OTA credential over USB; activation requires --enable."""

import argparse
import json
import os
from pathlib import Path
import re
import tomllib
from env_config import load_dotenv


def provision(board, credential, enable=False):
    version = (board / "boot_out.txt").read_text()
    if "seeed_xiao_esp32_s3_sense" not in version:
        raise ValueError("OTA currently supports XIAO ESP32S3 only")
    for name in (
        "boot.py",
        "code.py",
        "drawbridge.py",
        "lib/gate_ota.py",
        "lib/gate_http.py",
        "certs/google-roots.pem",
    ):
        if not (board / name).is_file():
            raise ValueError("Run make deploy before OTA provisioning")
    values = load_dotenv(credential)
    token = values.get("OTA_TOKEN", "")
    if not re.fullmatch(r"[a-f0-9]{64}", token):
        raise ValueError("Invalid enrollment token")
    # Runtime compares this ID with the actual chip suffix before connecting.
    identity = values.get("DEVICE_ID", "")
    if not re.fullmatch(r"[a-z0-9-]{1,64}", identity):
        raise ValueError("Invalid enrollment device ID")
    settings = board / "settings.toml"
    previous = settings.read_text() if settings.exists() else ""
    names = {"OTA_TOKEN", "OTA_ENABLED", "OTA_DEVICE_ID"}
    lines = [line for line in previous.splitlines() if line.split("=", 1)[0].strip() not in names]
    text = (
        "\n".join(
            lines
            + [
                "OTA_TOKEN = " + json.dumps(token),
                "OTA_DEVICE_ID = " + json.dumps(identity),
                "OTA_ENABLED = " + str(int(enable)),
            ]
        )
        + "\n"
    )
    parsed = tomllib.loads(text)
    if any(
        parsed.get(key) != value
        for key, value in {
            "OTA_TOKEN": token,
            "OTA_DEVICE_ID": identity,
            "OTA_ENABLED": int(enable),
        }.items()
    ):
        raise ValueError("OTA settings must be top-level TOML keys")
    settings.write_text(text)
    os.sync()
    print(
        "OTA credential installed; "
        + (
            "enabled after hard reset. Ground D9 during reset for USB recovery."
            if enable
            else "OTA remains disabled."
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("credential", type=Path)
    parser.add_argument("--board", type=Path, default=Path("/Volumes/CIRCUITPY"))
    parser.add_argument("--enable", action="store_true")
    args = parser.parse_args()
    try:
        provision(args.board, args.credential, args.enable)
    except (OSError, ValueError):
        raise SystemExit(
            "OTA provisioning failed. Check board, enrollment file, and USB write access."
        ) from None
