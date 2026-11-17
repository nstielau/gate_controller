# Feather onboarding session — November 16, 2026

## Delivered

Installed CircuitPython 10.3.2 and the Drawbridge USB bundle on the Adafruit
ESP32-S3 Reverse TFT Feather, device `37cc02`. Resolved the initial starter-app
startup issue and iterated on Wi-Fi setup, registration, indicators and display.
The final installed versions were application **1.0.1** and USB base **1.0.11**.
Firmware source remains `circuitpython/`; credentials and NVM are not releases.
Feather OTA remains unsupported.

The local portal now retains up to five Wi-Fi networks, preferring the last
successful visible network while trying alternatives and hidden saved networks.
Adding a location preserves the other networks and the device's registration.
Hold D1 while restarting the Feather to reopen setup, join its
`Gate-Setup-<suffix>` AP and browse to `http://192.168.4.1`. Two saved networks
were preserved on the connected board.

The portal gained Drawbridge colors and logo, saved-network management, an
always-visible mobile Save and connect button, and manual SSID entry that hides
when a dropdown network is selected. Connection-closed failures required bounded
partial writes/EAGAIN retries and completing/closing the HTTP response before
restart. Successful submission shows the escaped saved SSID and a ten-second
countdown with instructions to reconnect the phone.

The device QR moved right, with Scan to Register above, a larger device ID below,
and a D1 restart reminder alongside. The QR uses a compact alias URL and a
four-module quiet zone. Native validation measured a 106-byte URL and a
49-module matrix including its quiet zone, rendered with two-pixel modules.

QR scanning now preserves the device and derived pairing code through the
canonical-origin redirect and Google OAuth. Signed-in users confirm Register,
optionally choose a nickname, and see progress until the device acknowledges.
Scanning works for people who already have another registered gate. The TFT
shows Wi-Fi, registration, credential persistence and MQTT connection progress.
The user confirmed successful registration in production.

Security review found that hashing a user-supplied proof alone still allowed
an attacker to choose their own proof and reserve an unregistered public ID.
USB/IAM enrollment now establishes a create-only trusted ID-to-public-hash
binding before public enrollment can succeed. The random private proof stays
in NVM and verified TLS device request bodies; only its derived hash enters the
QR fragment. Browser callables retain verified Google auth/App Check. Retryable
MQTT credentials are encrypted server-side; controls remain disabled until the
board saves credentials, subscribes and acknowledges. Registration sends no hold.

The final hardware investigation explained a dark green Hold LED despite a
TFT Hold ON message: the earlier Feather adaptation used virtual indicators and
inherited XIAO's D10 control alias. The fabricated Wing instead requires:

| Function | Feather pin / GPIO | Wing header |
| --- | --- | --- |
| Wi-Fi, white LED | D5 / GPIO5 | J2.10 |
| MQTT, blue LED | D6 / GPIO6 | J2.9 |
| Hold, green LED | D9 / GPIO9 | J2.8 |
| Transistor control | D11 / GPIO11 | J2.6 |

The corrected mapping was checked against `hardware/featherwing/generate.py`
and the board pin definitions. D0/D1/D2 remain buttons. XIAO behavior is unchanged.
Normal TFT status now has a forest-green Drawbridge header, cream background and
separate Wi-Fi, MQTT and enlarged Hold ON/OFF rows. The user confirmed it looks
good. J3 is an open-collector sink toward ground when active, not a driven HIGH
output or isolated contact.

## Validation and deployment

Functions, Hosting and Firestore rules were deployed to `drawbridge-45487`.
The canonical app remains `https://drawbridge-45487.firebaseapp.com`; both aliases
redirect there before auth. New EMQX management secrets were imported through
`make web-secrets` without exposing their contents. The USB bundle was installed
and its boot version and mounted files checked against source.

Before the implementation commit, checks passed:

- 97 firmware/host tests and all pre-commit hooks, including the staged base guard.
- 37 web/backend unit tests, 67 mobile browser tests and 24 Firestore emulator
  tests. One existing WebKit cached-offline-launch test remained skipped.
- Live checks for all three OAuth entry URLs, pairing-intent preservation,
  unauthenticated callable rejection and missing-device-proof rejection.
- A 70-second post-install passive check: seven online heartbeats, advancing
  alive counts, steady Wi-Fi/MQTT indicators, transistor LOW and hold OFF.

Implementation was committed and pushed as `27d2942` on `main`. Detailed USB
change notes are in `docs/base-firmware/1.0.3.md` through `1.0.11.md`; local logs
are ignored under `artifacts/`, including `artifacts/circuitpython-install/`.
Temporary `.superpowers/` preview files were intentionally left uncommitted.

## Remaining physical checks

The passive run issued no holds and captured no D9 hold edges. After the pin
correction, physical green-LED illumination, D11 voltage and J3 switching still
need observation/meter validation during an intended bench hold. The user's
earlier Hold ON observation preceded that correction. Software status and a
broker acknowledgment do not prove electrical behavior or physical gate motion.
No field gate interface or Feather OTA qualification was completed here.

## Guidance carried into AGENTS.md

Make board identification and physical-header tracing prerequisites; keep XIAO
and Feather rules explicit. Preserve NVM identity during Wi-Fi work, and prevent
legacy deployment credentials from overwriting registered per-device identity.
Record trusted USB pairing enrollment and acknowledgment requirements. Preserve
mobile portal controls and close-before-restart behavior. Wait for serial/REPL
operations to finish, use DTR/RTS settings from the console helper, and validate
CircuitPython APIs on the device. Keep software evidence distinct from electrical
and physical validation.

## Restart setup and physical shortcuts

Base 1.0.13 adds D0/D1 website QR shortcuts (press again or wait 20 seconds),
and D2 selects the next reboot's Normal/Wi-Fi setup action on the bottom row.
Selection is one-shot and does not reboot immediately. The QR shortcut has no
pairing intent; onboarding retains its separate secure QR. D1 held at startup
remains recovery. Buttons do not alter the local hold lease.

Administration can explicitly restart setup for compatible registered boards.
The server disables new commands and the idle board acknowledges a unique reset
before clearing local network settings. Wi-Fi setup and a fresh owner QR claim
then replay the existing encrypted broker identity. Device ownership, access,
nickname and audit records survive. This is for retesting, not ownership transfer
or broker credential rotation. Power loss/lost responses resume the same reset.

USB base 1.0.13 was installed on 37cc02 with app 1.0.1/CP 10.3.2. Native QR,
label caching/bounds and input polarity checks passed; the board reconnected.
Validation passed 113 host tests, all pre-commit checks, 46 web/backend unit
tests, 83 browser tests (one existing skip) and 27 local Firestore tests. The
production restart-setup/owner registration cycle still needs an interactive
user test. No production reset, new gate hold or ownership change was issued.

## Admin observation and simplified website QR

Administration now shows stored last-authenticated-contact time and the newest
reported app/base pair for all devices, including non-OTA boards. Missing data
stays unreported; targets and older reports never fill in a missing base. Common
lastSeenAtMs is persisted on authenticated maintenance/OTA requests with legacy
report fallback. Delayed transaction retries cannot replace a newer version
snapshot. Only existing admin overview exposes the allowlisted metadata; use
Refresh administration to update it. This is not live MQTT/gate confirmation.

USB base 1.0.14 keeps the dark Drawbridge/device-ID header on the ordinary website
QR shortcut, centers the QR below, and hides hold/D2 text in that view. Normal
status and button behavior are unchanged. Native layout/cache/input checks and
70-second passive observation passed on 37cc02 (app 1.0.1, CP 10.3.2), with no
active hold, reset-setup request or credential changes. Validation: 113 host,
50 unit, 87 browser (one existing WebKit skip) and 28 actual local emulator tests,
plus hooks. Cloud metadata confirms this actual app/base pair and stored contact
time. Production Wi-Fi-reset/registration and electrical validation remain
separate interactive checks.
