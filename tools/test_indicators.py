#!/usr/bin/env python3
"""Passively verify indicator states and hold timing without changing control."""

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
    last_alive_edges = None
    last_alive_change = None
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
                        if (
                            started is not None
                            and time.monotonic() >= deadline
                            and time.monotonic() - last_heartbeat < 15
                        ):
                            break
                        raise
                    verify_event(event, boot_id)
                    if event["event"] == "heartbeat" and event.get("mqtt_connected"):
                        if not all(
                            event.get(key)
                            for key in ("wifi_connected", "wifi_led_on", "mqtt_led_on")
                        ):
                            raise AssertionError("Expected connected Wi-Fi and MQTT LEDs ON")
                        alive_edges = event["alive_edge_count"]
                        if (
                            last_alive_edges is not None
                            and alive_edges <= last_alive_edges
                            and time.monotonic() - last_alive_change > 5
                        ):
                            raise AssertionError("Onboard heartbeat stopped toggling")
                        if last_alive_edges is None or alive_edges > last_alive_edges:
                            last_alive_change = time.monotonic()
                        last_alive_edges = alive_edges
                        if not event["transistor_high"] and event["hold_led_on"]:
                            raise AssertionError("Hold LED must be OFF without a hold")
                        if boot_id is None:
                            boot_id = event["boot_id"]
                            started = time.monotonic()
                            deadline = started + args.duration
                        edges = event["hold_edge_count"]
                        last_heartbeat = time.monotonic()
                        previous_sample = None  # logging samples are separated by unlogged edges
                        heartbeats += 1
                        print(
                            "Connected: Wi-Fi/MQTT ON, alive edges {}, control {}, hold edges {}".format(
                                alive_edges, "HIGH" if event["transistor_high"] else "LOW", edges
                            ),
                            flush=True,
                        )
                    elif boot_id is not None and event["event"] == "indicator_edge":
                        if event.get("pin") != args.hold_pin:
                            raise AssertionError("Unexpected indicator pin")
                        elapsed = event["elapsed_ms"]
                        if not 125 <= elapsed <= 200:
                            raise AssertionError(
                                "Hold transition took {} ms; expected 125–200 ms".format(elapsed)
                            )
                        if previous_sample is not None and event["on"] == previous_sample:
                            raise AssertionError("Hold LED samples did not alternate")
                        previous_sample = event["on"]
                        samples.append(elapsed)
                    elif boot_id is not None and event["event"] == "indicator_mode":
                        if not event.get("wifi_connected") or not event.get("mqtt_connected"):
                            raise AssertionError("Connectivity lost during observation")
                        previous_sample = None
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
    print(
        "PASS: {} s, {} heartbeats, {} hold samples; logs {}".format(
            args.duration, heartbeats, len(samples), args.log
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="USB serial device; auto-detected by default")
    parser.add_argument("--duration", type=float, default=70)
    parser.add_argument(
        "--hold-pin", choices=["D2", "D9"], default="D2", help="XIAO D2 (default), FeatherWing D9"
    )
    parser.add_argument(
        "--timeout", type=float, default=40, help="Seconds to wait for first online heartbeat"
    )
    parser.add_argument("--log", type=Path, default=Path("artifacts/indicators.log"))
    args = parser.parse_args()
    if args.duration < 20 or args.timeout <= 0:
        parser.error("duration must be at least 20 seconds and timeout must be positive")
    try:
        run(args)
    except (AssertionError, OSError, ValueError) as error:
        raise SystemExit("FAIL: {} (logs: {})".format(error, args.log)) from None


if __name__ == "__main__":
    main()
