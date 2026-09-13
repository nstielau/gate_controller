"""Exercise the web backend's MQTT publisher on an isolated, synthetic topic."""

import json
from pathlib import Path
import subprocess

from env_config import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def main():
    env = load_dotenv(ROOT / ".env")
    credentials = {
        "username": env.get("MQTT_USERNAME"),
        "password": env.get("MQTT_PASSWORD"),
        "ca": (ROOT / "emqxsl-ca.crt").read_text(),
    }
    if not all(credentials.values()):
        raise SystemExit("MQTT credentials and CA are required")
    result = subprocess.run(
        [str(ROOT / "node_modules/.bin/node"), str(ROOT / "firebase/functions/smoke.cjs")],
        input=json.dumps(credentials), text=True, cwd=ROOT, check=False,
    )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
