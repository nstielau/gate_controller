"""USB-installed OTA ownership. Default is normal USB-writable maintenance.

OTA_ENABLED=1 opts in on XIAO ESP32S3 only. Ground D9 during a hard reset to
recover USB write access. D9 is GPIO8 on this board; other boards fail closed.
Never enable concurrent host/device filesystem writes.
"""

import os
import board
import digitalio
import storage

mode = "usb"
# CircuitPython 10.1+ returns strings from getenv, including TOML integers.
if os.getenv("OTA_ENABLED") in (1, "1") and board.board_id == "seeed_xiao_esp32_s3_sense":
    with digitalio.DigitalInOut(board.D9) as recovery:
        recovery.switch_to_input(pull=digitalio.Pull.UP)
        if recovery.value:
            storage.remount("/", readonly=False)
            mode = "ota"
        else:
            mode = "maintenance"
print("GATE_BOOT mode=" + mode)
