#!/usr/bin/env python3
"""Exercise real MQTT commands and require matching XIAO logs and LED timings.

Opens USB CDC once; never sends Ctrl-C, Ctrl-D or a board reset. The last
interval in --intervals is retained when the test completes.
"""

import argparse
import json
from pathlib import Path
import queue
import threading
import time
import uuid

from mqtt_blink import DEFAULT_BROKER, DEFAULT_PORT, DEFAULT_CA_FILE, DEFAULT_ENV_FILE, load_dotenv, publish_mqtt
from xiao_console import open_console


class LogMonitor:
    def __init__(self, port, artifact):
        self.port = port
        self.artifact = artifact
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.read, daemon=True)

    def read(self):
        pending = bytearray()
        try:
            while not self.stop.is_set():
                chunk = self.port.read(self.port.in_waiting or 1)
                if not chunk:
                    continue
                pending.extend(chunk)
                while b"\n" in pending:
                    line, _, pending = pending.partition(b"\n")
                    line = line.decode("utf-8", "replace").strip()
                    self.artifact.write(line + "\n")
                    self.artifact.flush()
                    if "GATE_LOG " in line:
                        self.events.put(json.loads(line.split("GATE_LOG ", 1)[1]))
                    elif "Traceback" in line or "soft reboot" in line or "code.py output:" in line:
                        self.events.put({"event": "unexpected_reset", "detail": line})
        except Exception as error:
            self.events.put({"event": "serial_error", "detail": str(error)})

    def next_event(self, deadline):
        try:
            return self.events.get(timeout=max(0, deadline - time.monotonic()))
        except queue.Empty:
            raise AssertionError("Timed out waiting for XIAO log confirmation") from None


def verify_event(event, boot_id):
    if event["event"] in ("serial_error", "unexpected_reset"):
        raise AssertionError(str(event))
    if boot_id is not None:
        if event.get("boot_id") != boot_id:
            raise AssertionError("XIAO restarted during command cycles")
        if event["event"] in ("boot", "connection_error", "mqtt_connected"):
            raise AssertionError("XIAO lost its session during command cycles: " + str(event))


def run_cycles(args):
    env = load_dotenv(DEFAULT_ENV_FILE)
    if not env.get("MQTT_USERNAME") or not env.get("MQTT_PASSWORD"):
        raise ValueError("MQTT_USERNAME and MQTT_PASSWORD are required in .env")
    topic = args.topic or "gate/v1/devices/{}/command".format(args.device_id)
    args.log.parent.mkdir(parents=True, exist_ok=True)
    summaries = []
    boot_id = None
    with args.log.open("w") as artifact, open_console(args.port) as port:
        monitor = LogMonitor(port, artifact)
        monitor.thread.start()
        try:
            for cycle in range(1, args.cycles + 1):
                for interval in args.intervals:
                    command_id = uuid.uuid4().hex
                    print("Cycle {}: sending {} ms, command {}".format(cycle, interval, command_id), flush=True)
                    publish_mqtt(args.broker, args.mqtt_port, DEFAULT_CA_FILE,
                                 env["MQTT_USERNAME"], env["MQTT_PASSWORD"], topic,
                                 interval, True, command_id)
                    deadline = time.monotonic() + args.timeout + 4 * interval / 1000
                    applied = False
                    samples = []
                    while len(samples) < 4:
                        event = monitor.next_event(deadline)
                        verify_event(event, boot_id)
                        if event.get("command_id") != command_id:
                            continue
                        if event["event"] == "command_applied":
                            if applied:
                                raise AssertionError("Duplicate application of the same command")
                            applied = True
                            boot_id = event["boot_id"]
                            if event["blink_interval_ms"] != interval:
                                raise AssertionError("XIAO applied the wrong interval")
                        elif event["event"] == "led_edge":
                            if not applied:
                                raise AssertionError("LED changed without command_applied confirmation")
                            elapsed = event["elapsed_ms"]
                            tolerance = max(75, interval * 0.15)
                            if abs(elapsed - interval) > tolerance:
                                raise AssertionError("LED edge took {} ms; expected {} ± {} ms".format(elapsed, interval, tolerance))
                            if samples and event["led_on"] == samples[-1]["led_on"]:
                                raise AssertionError("LED output did not alternate")
                            samples.append(event)
                    summary = {"cycle": cycle, "command_id": command_id, "interval_ms": interval,
                               "boot_id": boot_id, "elapsed_ms": [e["elapsed_ms"] for e in samples]}
                    summaries.append(summary)
                    print("PASS: applied {} ms; LED edges {} ms".format(interval, summary["elapsed_ms"]), flush=True)
            # Observe beyond the MQTT keepalive window to catch reconnect churn.
            deadline = time.monotonic() + args.soak
            last_heartbeat = time.monotonic()
            last_edges = None
            while time.monotonic() < deadline:
                try:
                    event = monitor.next_event(min(deadline, time.monotonic() + 15))
                except AssertionError:
                    if time.monotonic() >= deadline and time.monotonic() - last_heartbeat < 15:
                        break
                    raise
                verify_event(event, boot_id)
                if event["event"] == "heartbeat":
                    last_heartbeat = time.monotonic()
                    if last_edges is not None and event["edge_count"] <= last_edges:
                        raise AssertionError("LED stopped advancing during stability check")
                    last_edges = event["edge_count"]
                    print("Stable: uptime {} ms, edges {}".format(event["uptime_ms"], last_edges), flush=True)
        finally:
            monitor.stop.set()
            monitor.thread.join(timeout=2)
    args.log.with_suffix(".json").write_text(json.dumps(summaries, indent=2) + "\n")
    print("PASS: {} commands in {} cycles; {} s stability check; logs {}".format(
        len(summaries), args.cycles, args.soak, args.log), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-id", default="b3640c")
    parser.add_argument("--topic")
    parser.add_argument("--broker", default=DEFAULT_BROKER)
    parser.add_argument("--mqtt-port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--port", help="USB serial path; auto-detected if omitted")
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--intervals", type=int, nargs="+", default=[2000, 300])
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--soak", type=float, default=70)
    parser.add_argument("--log", type=Path, default=Path("artifacts/mqtt-cycles.log"))
    args = parser.parse_args()
    if args.cycles < 1 or args.timeout <= 0 or args.soak < 0 or any(not 25 <= n <= 60000 for n in args.intervals):
        parser.error("invalid cycles, timeout, soak or intervals")
    try:
        run_cycles(args)
    except (AssertionError, OSError, ValueError) as error:
        raise SystemExit("FAIL: {} (logs: {})".format(error, args.log)) from None


if __name__ == "__main__":
    main()
