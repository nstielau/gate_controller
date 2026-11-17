"""USB/device filesystem ownership with board-specific physical recovery.

Opt in explicitly. Feather D1 HIGH at hard reset or XIAO D9 LOW recovers USB
write access. Never enable concurrent host/device filesystem writes.
"""

import os
import board
import digitalio
import storage

mode = "usb"
if os.getenv("OTA_ENABLED") in (1, "1"):
    if board.board_id == "seeed_xiao_esp32_s3_sense":
        recovery_pin, pressed_value, pull = board.D9, False, digitalio.Pull.UP
    elif board.board_id == "adafruit_feather_esp32s3_reverse_tft":
        recovery_pin, pressed_value, pull = board.D1, True, digitalio.Pull.DOWN
    else:
        recovery_pin = None
    if recovery_pin is not None:
        with digitalio.DigitalInOut(recovery_pin) as recovery:
            recovery.switch_to_input(pull=pull)
            if bool(recovery.value) == pressed_value:
                mode = "maintenance"
            else:
                storage.remount("/", readonly=False)
                mode = "ota"
print("GATE_BOOT mode=" + mode)
