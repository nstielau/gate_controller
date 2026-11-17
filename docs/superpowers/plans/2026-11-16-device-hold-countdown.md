# Device hold countdown implementation plan

User-approved design: keep the Drawbridge header and separate status rows.
Show the local lease's remaining time as M:SS or H:MM:SS during a hold, OFF
otherwise. Idle footer is “D1 + RESET: Wi-Fi setup”; active footer is “Reset
ends hold”. Keep countdown updates independent of Wi-Fi/MQTT availability.

1. Add failing display tests for time formatting, footer state and reuse of
   existing display objects. Add runtime tests for local lease countdown,
   second-level update bounds, offline operation, replacement and expiry.
2. Extend `device_display.py` with countdown formatting and cached status labels;
   update label text without rebuilding the display bitmap every second.
   Pass the rounded-up local lease remaining seconds through `code.py`'s
   status change detection. Preserve GPIO servicing before display work.
3. Bump USB base to 1.0.12 and add `docs/base-firmware/1.0.12.md`. Run `make test`
   and `make precommit`; inspect changes. No backend or web changes.
4. Confirm no active hold before intentionally stopping the board. Wait for
   REPL readiness, disable autoreload, deploy, validate the actual display APIs
   and formatting without actuating outputs, then restart deliberately.
5. Passively verify the installed base and online state with
   `make test-hardware TEST_ARGS='--hold-pin D9'`. Record actual verification
   limits; no automatic hold command or physical gate actuation.
