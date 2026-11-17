"""Trust a physically attached board's QR identity using project IAM.

Only the public SHA-256 pairing code leaves the USB board. The private proof
stays in NVM. This intentionally interrupts and restarts the application.
"""

import argparse
import json
import re
import time
import urllib.error

import serial

from firebase_cloud import Cloud, PROJECT


def validate_binding(binding):
    if not isinstance(binding, dict) or not re.fullmatch(r"[a-z0-9-]{1,64}", binding.get("deviceId", "")):
        raise ValueError("Invalid USB device identity")
    if not re.fullmatch(r"[0-9a-f]{64}", binding.get("pairingCode", "")):
        raise ValueError("Invalid USB pairing code")
    return binding


def read_binding(port):
    """Read only the derived public code; never dump settings or NVM."""
    script = (
        "import code,json\n"
        "c=code.ensure_pairing_config(code.load_config())\n"
        "print('PAIRING_BINDING '+json.dumps({'deviceId':code.device_suffix().lower(),"
        "'pairingCode':code.pairing_code(c['pairing_secret'])}))\n"
    )
    connection = serial.Serial(port=None, baudrate=115200, timeout=0.2, exclusive=True)
    connection.dtr = True
    connection.rts = False
    connection.port = port
    connection.open()
    with connection:
        try:
            connection.reset_input_buffer()
            connection.write(b"\x03\x03\r\n")
            output = bytearray()
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and b">>> " not in output:
                output.extend(connection.read(1024))
            if b">>> " not in output:
                raise RuntimeError("USB board did not enter the REPL; close other serial readers and retry")
            connection.reset_input_buffer()
            connection.write(b"\x01")
            time.sleep(0.3)
            connection.reset_input_buffer()
            connection.write(script.encode() + b"\x04")
            output = bytearray()
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline and len(output) < 16384:
                output.extend(connection.read(1024))
                match = re.search(rb"PAIRING_BINDING (\{[^\r\n]+\})", output)
                if match:
                    return validate_binding(json.loads(match.group(1)))
            raise RuntimeError("USB board did not return a pairing identity; install current base firmware first")
        finally:
            connection.write(b"\x02\x04")


def enroll(cloud, binding):
    binding = validate_binding(binding)
    root = f"https://firestore.googleapis.com/v1/projects/{PROJECT}/databases/(default)/documents"
    url = root + "/devicePairingBindings/" + binding["deviceId"]
    try:
        existing = cloud.call(url)
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        try:
            cloud.call(root + "/devicePairingBindings?documentId=" + binding["deviceId"], "POST", {
                "fields": {"pairingCode": {"stringValue": binding["pairingCode"]}},
            })
            return
        except urllib.error.HTTPError as error:
            if error.code != 409:
                raise
            existing = cloud.call(url)
    if existing.get("fields", {}).get("pairingCode", {}).get("stringValue") != binding["pairingCode"]:
        raise ValueError("Device ID already has a different trusted pairing identity; refusing replacement")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    args = parser.parse_args()
    try:
        cloud = Cloud()
        binding = read_binding(args.port)
        enroll(cloud, binding)
    except urllib.error.HTTPError as error:
        raise SystemExit(f"Google API returned HTTP {error.code}; pairing identity was not enrolled") from None
    print("Trusted USB pairing identity enrolled for " + binding["deviceId"])


if __name__ == "__main__":
    main()
