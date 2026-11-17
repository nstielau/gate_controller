# Feather USB installation plan

Install the full Drawbridge USB runtime on the attached Reverse TFT Feather.
Preserve XIAO behavior, hold deadlines, and OTA restriction to XIAO. Use the
Feather screen for connectivity/hold status and its active-high onboard LED
for heartbeat; never drive D0/D1/D2 button pins. Keep D10 LOW until a valid
command. No live hold commands are part of this installation.

1. Repair host test path ordering and add failing Feather pin/polarity tests.
2. Add board-specific status output handling, bump USB base to 1.0.3, document.
3. Run host tests and precommit, then deploy the bundle with autoreload paused.
4. Restart and passively verify boot, display, provisioning or online status.
