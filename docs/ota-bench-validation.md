# OTA bench validation — 2026-09-14

Board `b3640c`, XIAO ESP32S3 Sense firmware, CircuitPython 10.3.0. The owner
confirmed that the gate output wires were disconnected. Tests below measure
software GPIO state, not gate motion or electrical output.

## Observed on the board

| Check | Result | Local evidence under `artifacts/ota-bench/` |
| --- | --- | --- |
| SHA-256 and fragmented HTTP parsing | Passed after parser fix | `probe-output.log` |
| Authenticated Firebase download | All 2,932 bytes match release 1.0.0 SHA-256 | `probe-output.log` |
| Timed MQTT hold | D10 HIGH for about 3 seconds, then LOW; D2 samples 125–157 ms | `indicators.log` |
| Connectivity and indicators | 70 seconds, eight heartbeats, four D2 samples | `indicators-summary.log` |
| Normal OTA boot | `GATE_BOOT mode=ota`; macOS mounts CIRCUITPY read-only | `boot_out.txt` on board |
| First OTA install | Sequence 2 staged, booted as trial, reconnected MQTT, confirmed after 60 seconds | `first-update.log` |
| Invalid Python candidate | Locally staged sequence 3 rolled back to confirmed sequence 2 | `syntax-fault.log` |
| Startup exception | Locally staged sequence 4 rolled back to confirmed sequence 2 | `startup-fault.log` |
| Loop lockup | Locally staged sequence 5 triggered the hardware watchdog; board rebooted and recovered sequence 2 | `watchdog-fault.log`, `watchdog-reset.log` |
| Hold deferral | D10 HIGH for 120.004 s; update staged 3.306 s after release, never during hold | `hold-deferral.json`, `update.log` |
| Update after failures | Sequence 6 installed in the other slot and confirmed after its MQTT health trial | `update.log`, `update-summary.log` |

The fault candidates were injected locally through USB REPL into the inactive
slot. They were not published to GitHub or approved in Firebase. The previous
confirmed application survived each test. Firebase has subsequently been
assigned approved release 1.0.0 as sequence 6, above the consumed fault-test
sequences. This second installation is confirmed and the board's MQTT status
reports version 1.0.0, state current, with no active hold.

## Fixes required by the physical tests

- Replace bytearray slice deletion with slicing; CircuitPython rejects item
  deletion. Host regression tests now model that restriction.
- Load Google's public GTS root certificates explicitly for Firebase HTTPS.
  The built-in bundle failed validation. Certificate and hostname verification
  remain enabled; `certs/README.md` records the certificate sources.
- Accept the string `"1"` in `boot.py`: CircuitPython 10.1+ returns strings from
  `os.getenv`, even for TOML integers. Tests cover both older integer and newer
  string representations, with D9 HIGH and LOW.

These are USB bootstrap fixes. The immutable GitHub application asset remains
unchanged. Use the corrected repository bootstrap, not the bootstrap files in
the original firmware-v1.0.0 source archive. The offline suite has 55 passing
tests, and secret/lint hooks passed.

## Still outstanding

- Repeat D9 recovery with the corrected boot setting check. The initial test
  was inconclusive because the setting bug kept every boot in USB mode.
- Confirm the Firebase device version report.
- Remove power during slot writes and journal transitions; a watchdog reset
  is not a power-loss test.
- Real no-MQTT trial timeout, full storage, damaged files, token revocation,
  paused target, and a hold arriving during download. Host tests cover several
  of these paths but do not establish physical flash/power-loss behavior.

Do not describe this as completed field qualification. Keep the controller
disconnected while conducting the remaining fault and recovery tests.
