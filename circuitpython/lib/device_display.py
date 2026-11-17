"""Legacy import path for the USB recovery app's presentation helpers.

The rendering implementation lives in drawbridge.py, also delivered as the OTA
application. The loader attaches the selected application's own UI after boot;
this shim always remains a route to the USB recovery copy.
"""

from drawbridge import (
    APP_URL,
    DisplayState,
    ReverseTFT,
    format_hold_time,
    qr_matrix,
    reboot_footer,
    registration_qr_url,
)

__all__ = (
    "APP_URL", "DisplayState", "ReverseTFT", "format_hold_time", "qr_matrix",
    "reboot_footer", "registration_qr_url",
)
