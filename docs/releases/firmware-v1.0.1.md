# Firmware 1.0.1

The onboard LED now gives two quick flashes every two seconds: 100 ms on,
150 ms off, 100 ms on, then off for the rest of the cycle. This repeating
pattern makes an installed 1.0.1 application easy to recognize. It uses the
existing nonblocking timer and active-low output handling.

Wi-Fi, MQTT and hold indicators retain their existing meanings. Gate command
validation, transistor output and hold deadlines are unchanged. The OTA asset
is only `drawbridge.py`, using application API 1 and bootstrap API 1.0.0.

After the release is imported, open **Administration**, select **1.0.1** for the
enrolled board and choose **Assign release**. The board checks on its existing
schedule (60–315 seconds after startup, then every six hours plus jitter);
assignment does not force an immediate check. Active holds defer the update.
After downloading, the application runs as a trial and confirms after 60
seconds of healthy MQTT connectivity. Check the reported version/state as
well as the new onboard flash pattern.

This release is intended for the already provisioned bench board. The bootstrap
fixes and remaining recovery/power-loss checks are tracked in
`docs/ota-bench-validation.md` in the working repository; publishing this
application does not update the USB-managed bootstrap or establish field
qualification.
