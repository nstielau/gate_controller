"""Install a device OTA credential over USB; activation requires --enable."""

import argparse
import json
import os
from pathlib import Path
import re
import tomllib
from env_config import load_dotenv


XIAO_BOARD = "seeed_xiao_esp32_s3_sense"
FEATHER_BOARD = "adafruit_feather_esp32s3_reverse_tft"
SUPPORTED_BOARDS = {XIAO_BOARD, FEATHER_BOARD}


def provision(board, credential, enable=False):
    version = (board / "boot_out.txt").read_text()
    match = re.search(r"(?m)^Board ID:\s*([a-z0-9_]+)\s*$", version)
    actual_board = match.group(1) if match else None
    if actual_board not in SUPPORTED_BOARDS:
        raise ValueError("Unsupported CircuitPython board for OTA")
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
    # Enrollment is a single file identity; ambient shell values cannot replace
    # any part of its device/board/token binding.
    values = load_dotenv(credential, environ={})
    enrolled_board = values.get("BOARD_ID", XIAO_BOARD)
    if enrolled_board not in SUPPORTED_BOARDS or enrolled_board != actual_board:
        raise ValueError("Enrollment board does not match the connected board")
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
    recovery = (
        "Hold D1 while pressing RESET for USB recovery."
        if actual_board == FEATHER_BOARD
        else "Ground D9 during reset for USB recovery."
    )
    print(
        "OTA credential installed; "
        + ("enabled after hard reset. " + recovery if enable else "OTA remains disabled.")
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
