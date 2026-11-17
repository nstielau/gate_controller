# Reverse TFT Feather OTA bench validation — 2026-11-16

Device `37cc02` (Christiansen Gate), board ID
`adafruit_feather_esp32s3_reverse_tft`, CircuitPython 10.3.2, USB base 1.0.15,
application 1.1.0/API2, compatibility loader 1.1.0. Firmware release
[`firmware-v1.1.0`](https://github.com/nstielau/gate_controller/releases/tag/firmware-v1.1.0)
was built from clean tagged commit `6ff47b12af43bc4e54b368b7784e0c2fdb79d8de`.
The four release assets were published and the application imported into the
private Firebase firmware mirror after tagged-source/hash verification.

Only this Feather was enrolled, opted in and explicitly assigned the release.
The existing `b3640c` / 990 Butterfield target remains enabled on 1.0.0,
sequence 9. Publishing/importing releases does not advance device targets.
No gate commands were issued in these tests. GPIO observations establish
software writes, not terminal voltage, optical LED output or physical gate motion.

## Observed on the board

- USB install preserved NVM, reconnected Wi-Fi/MQTT and reported actual
  application/base versions 1.1.0/1.0.15.
- Native application UI/QR/button checks and Feather manifest validation passed.
- Opted-in hard reset reported `GATE_BOOT mode=ota` and macOS mounted CIRCUITPY
  read-only. No concurrent filesystem-write override was used.
- Physical D1 recovery reported `GATE_BOOT mode=maintenance` and restored host
  USB write access. Returning through hard reset restored OTA mode. D9 remained
  the FeatherWing Hold LED; XIAO recovery was not changed or tested here.
- Authenticated runtime TLS download staged sequence 2, loaded application 1.1.0
  as an API2 trial, reconnected MQTT, and confirmed after 60 seconds of
  online health. A post-confirmation heartbeat was observed.
- Local invalid-Python candidate sequence 3 and UI-construction exception
  sequence 4 both rolled back to confirmed sequence 2 and reconnected MQTT.
  Neither candidate was published or imported.
- Local loop-lockup candidate sequence 5 triggered a hardware watchdog reset;
  the reset reason was WATCHDOG. The previous confirmed application recovered
  and reconnected Wi-Fi/MQTT, with control LOW.
- After the local faults, native journal inspection found approved release 1.1.0
  confirmed as sequence 6 in slot 1, with no trial and the published application
  SHA-256 `622a82ef2f20ea5d7f4d1318e864388dbb0dc982309c55db3da194f0948f5336`.
  The board verified the active file against that digest. A subsequent reload
  reported current state with the actual 1.1.0/1.0.15 pair.
- Native isolated journal test preserved generation 2 and its verified active
  application after writing a truncated older journal. It used a separate
  temporary `/ota/feather_probe` directory, then removed it. Real controller
  journals/slots were not corrupted. This simulates a torn write, not power loss.
- The final passive 70-second hardware check passed with seven online heartbeats,
  steady Wi-Fi/MQTT indicators, increasing onboard heartbeat edges, control LOW,
  Hold LED OFF, and one stable boot/session. No hold was activated.

Local evidence is ignored under `artifacts/`: `feather-ota-native-boot.log`,
`feather-ota-enabled-boot.log`, `feather-ota-recovery-boot.txt`,
`feather-ota-download.log`, `feather-ota-first-update.log`,
`feather-ota-syntax-fault.log`, `feather-ota-ui-fault.log`,
`feather-ota-watchdog-fault.log`, `feather-ota-watchdog-reset.log`,
`feather-ota-journal-probe.log`, `feather-ota-final-status.log`,
`feather-ota-hardware.log`, and `feather-ota-hardware.json`.

## Validation and remaining qualification

The implementation passed 135 host tests, 55 web/backend unit tests, 87 mobile
browser tests (one existing offline-launch skip), 31 actual localhost Firestore
emulator tests, and pre-commit checks. Functions/Hosting/rules were deployed;
the canonical origin, both aliases and unsigned API denial passed live checks.

Physical power interruption during slot writes/journal transitions remains
outstanding. A watchdog reset or simulated truncated journal is not a power-cut
test. No Feather gate actuation or real live-hold update deferral was exercised;
the host regressions cover protected leases and deferral. Real no-MQTT trial
expiry, full storage, token revocation and a hold arriving mid-download remain
separate bench qualification tasks. Do not describe this release as fully
field-qualified.
