#!/usr/bin/env python3
"""Passively verify connected LED states and D0 timing without changing D10."""

import argparse
import json
from pathlib import Path
import time

from test_mqtt_cycles import LogMonitor, verify_event
from xiao_console import open_console


def run(args):
    args.log.parent.mkdir(parents=True, exist_ok=True)
    boot_id = None
    started = None
    deadline = time.monotonic() + args.timeout
    last_heartbeat = None
    last_edges = None
    previous_sample = None
    samples = []
    heartbeats = 0
    summary = {"passed": False, "duration_seconds": args.duration}
    try:
        with args.log.open("w") as artifact, open_console(args.port) as port:
            monitor = LogMonitor(port, artifact)
            monitor.thread.start()
            try:
                while time.monotonic() < deadline:
                    try:
                        event = monitor.next_event(min(deadline, time.monotonic() + 15))
                    except AssertionError:
                        if started is not None and time.monotonic() >= deadline and time.monotonic() - last_heartbeat < 15:
                            break
                        raise
                    verify_event(event, boot_id)
                    if event["event"] == "heartbeat" and event.get("mqtt_connected"):
                        if not event.get("onboard_led_on"):
                            raise AssertionError("Expected connected onboard LED ON")
                        if boot_id is None:
                            boot_id = event["boot_id"]
                            started = time.monotonic()
                            deadline = started + args.duration
                        edges = event["hold_edge_count"]
                        last_edges = edges
                        last_heartbeat = time.monotonic()
                        previous_sample = None  # logging samples are separated by unlogged edges
                        heartbeats += 1
                        print("Connected: onboard ON, D10 HIGH, D0 edges {}".format(edges), flush=True)
                    elif boot_id is not None and event["event"] == "indicator_edge":
                        if event.get("pin") != "D0":
                            raise AssertionError("Unexpected indicator pin")
                        elapsed = event["elapsed_ms"]
                        if not 125 <= elapsed <= 200:
                            raise AssertionError("D0 transition took {} ms; expected 125–200 ms".format(elapsed))
                        if previous_sample is not None and event["on"] == previous_sample:
                            raise AssertionError("D0 samples did not alternate")
                        previous_sample = event["on"]
                        samples.append(elapsed)
                    elif boot_id is not None and event["event"] == "indicator_mode":
                        raise AssertionError("Indicator mode changed during stable connection")
                if heartbeats < 2:
                    raise AssertionError("Need at least two online heartbeats")
            finally:
                monitor.stop.set()
                monitor.thread.join(timeout=2)
        summary.update(passed=True, boot_id=boot_id, heartbeats=heartbeats, elapsed_ms=samples)
    except (AssertionError, OSError, ValueError) as error:
        summary["error"] = str(error)
        raise
    finally:
        args.log.with_suffix(".json").write_text(json.dumps(summary, indent=2) + "\n")
    print("PASS: {} s, {} heartbeats, {} D0 samples ({}–{} ms); logs {}".format(
        args.duration, heartbeats, len(samples), min(samples), max(samples), args.log))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="USB serial device; auto-detected by default")
    parser.add_argument("--duration", type=float, default=70)
    parser.add_argument("--timeout", type=float, default=40, help="Seconds to wait for first online heartbeat")
    parser.add_argument("--log", type=Path, default=Path(".artifacts/indicators.log"))
    args = parser.parse_args()
    if args.duration < 20 or args.timeout <= 0:
        parser.error("duration must be at least 20 seconds and timeout must be positive")
    try:
        run(args)
    except (AssertionError, OSError, ValueError) as error:
        raise SystemExit("FAIL: {} (logs: {})".format(error, args.log)) from None


if __name__ == "__main__":
    main()
