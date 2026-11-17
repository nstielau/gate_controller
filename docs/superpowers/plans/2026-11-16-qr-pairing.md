# QR registration implementation plan

User-approved flow: scan QR, verified Google login preserving intent, confirm
registration/nickname, device progress, then controls after device acknowledgment.
Deploy production and USB bundle; never actuate a gate during validation.

Contract:
- Device generates/persists `pairing_secret`, 32 random bytes encoded as 64
  lowercase hex characters. Pairing code is SHA256 of its UTF-8 hex text.
- QR URL: `/?device_id=<id>#pair=<64-hex-pairing-code>`. No private device secret,
  MQTT credentials or connection settings appear in URLs or browser responses.
- Browser createDeviceClaim/deviceClaimStatus data: {deviceId, pairingCode,
  nickname?}. Claim key hashes deviceId+pairingCode. Both claim and device
  provisioning require a matching server-owned `devicePairingBindings/<id>`
  public hash, established by trusted USB enrollment using project IAM. Public
  endpoints cannot create/replace this binding. Claims expire after 2 hours;
  existing encrypted credentials and acknowledgments remain recoverable.
- Device POST deviceRegister JSON: {device_id, device_secret, action?}.
  Default action provisions/recovers credentials with the private secret.
  `action: "complete"` acknowledges successful credential persistence + MQTT
  subscription. Browser state stays provisioning until that acknowledgment.
- Encrypt retryable device credential envelopes using AES-256-GCM with a key
  derived from the private secret. Store encrypted envelope only, server-owned;
  device proof must match before decrypting/replaying a response. Never rotate
  a previously provisioned identity on transport retries.
- Preserve exact MQTT topics/ACLs, verified auth/App Check, device allowlists,
  deny-all Firestore rules, existing XIAO OTA boundaries and saved networks.

Work:
1. Backend secure claim/provision/retry/ack and meaningful local-emulator tests.
2. Browser QR fragment/session handling across OAuth, confirmation/progress,
   existing-device handling; mobile Chromium/WebKit regressions.
3. Firmware secret persistence, secure QR, progress/ack, base bump + note;
   host and actual CircuitPython compatibility checks without printing secrets.
4. Integrate, security review, make test/precommit/web-test. Deploy full web,
   verify live auth/API gates. USB install and passive hardware observations.
