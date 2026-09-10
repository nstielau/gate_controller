# Implementation audit

The original MQTT failure was reproduced against MiniMQTT 8.1.0: the app
called `loop(timeout=0.02)` while the client socket timeout was one second.
MiniMQTT raised `ValueError`; the old broad reconnect handler treated that as a
network failure, repeatedly reconnecting and replaying the retained command.
The app also reset the microcontroller on connection errors, which explained
USB disconnect warnings.

The current implementation uses a small `GateMQTT` adapter for short idle
polls while retaining longer TLS and packet-read deadlines. `ValueError` is no
longer classified as a network failure, network recovery does not reset the
board, MQTT publishing is outside the receive callback, and duplicate delivery
of the same command ID does not restart the blink timer. The publisher uses
native TLS, QoS 1, and waits for PUBACK before reporting broker success.

The host suite tests the real pinned MiniMQTT package, fragmented packets,
command validation and timing, NVM migration, fragmented portal requests,
publisher acknowledgments, and content-based deployment updates. The hardware
runner correlates unique command IDs with four LED GPIO-edge logs, checks
alternation and timing, detects boot/session loss, and observes heartbeats
after the command cycles.

Use `make test-hardware-smoke` for one 300 ms command and a short 15-second
stability check while iterating. Use the default `make test-hardware` as the
release check: three alternating 2000/300 ms cycles followed by 70 seconds of
stability. Both tests leave their final command retained; the smoke test is a
fast feedback tool and does not replace the full check before hardware changes
are considered complete.

The edge measurements are software writes to `board.LED`, not optical
measurements. They establish firmware scheduling and session stability for the
tested window; an external sensor is needed to validate emitted light timing.
