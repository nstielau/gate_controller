#!/usr/bin/env python3
"""Stream a USB-connected XIAO's CircuitPython output without resetting it.

Install dependencies with make setup, then use make console CONSOLE_WAIT=20.
"""

import argparse
import glob
import sys
import time

import serial


def find_port():
    ports = sorted(glob.glob("/dev/cu.usbmodem*"))
    if len(ports) == 1:
        return ports[0]
    if not ports:
        raise SystemExit("No XIAO USB serial port found; pass --port explicitly.")
    raise SystemExit("Multiple USB serial ports found; pass --port: {}".format(", ".join(ports)))


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="Serial device path. Defaults to the only /dev/cu.usbmodem* port.")
    parser.add_argument("--wait", type=float, default=3, help="Seconds to stream output (default: 3).")
    reload_options = parser.add_mutually_exclusive_group()
    reload_options.add_argument("--reload", action="store_true", help="Explicitly send Ctrl-C and Ctrl-D before monitoring.")
    reload_options.add_argument("--no-reload", action="store_true", help="Read without reloading (the default).")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.wait < 0:
        raise SystemExit("--wait must be zero or greater")
    port_name = args.port or find_port()
    with open_console(port_name) as port:
        if args.reload:
            port.write(b"\x03")
            time.sleep(0.3)
            port.write(b"\x04")
        deadline = time.monotonic() + args.wait
        while time.monotonic() < deadline:
            chunk = port.read(port.in_waiting or 1)
            if chunk:
                print(chunk.decode("utf-8", "replace"), end="", flush=True)


def open_console(port_name=None):
    """Open native USB CDC with DTR asserted and no reset sequence."""
    port = serial.Serial(port=None, baudrate=115200, timeout=0.1)
    port.dtr = True
    port.rts = False
    port.port = port_name or find_port()
    port.open()
    return port


if __name__ == "__main__":
    try:
        main()
    except serial.SerialException as error:
        print("XIAO console failed: {}".format(error), file=sys.stderr)
        raise SystemExit(1)
