# Device enrollment and onboarding

## Goal

Allow a new device to be claimed by any signed-in user who enters its device ID,
then provision device-specific MQTT credentials without relying on a guessable ID
alone after the claim is created. Keep the device usable through a local Wi-Fi
setup portal and make onboarding understandable on the 240x135 Reverse TFT.

## Ownership and claim rules

- A verified Google user can create a claim for an unregistered device ID.
- A claim expires after two hours. It remains pending until it expires or the
  device completes registration; there is no cancel control in the first version.
- The device ID is the only device-side proof. The registration endpoint is
  available only while a matching, unexpired claim exists, and the first valid
  registration wins.
- An already registered device cannot be claimed through this onboarding flow.
- The successful claimant becomes the first allowed user. Existing device access
  and invitation behavior remains unchanged.

## Browser flow

On first login, if the user has no devices, show an add-device onboarding screen.
The device ID can be entered there or from the existing device dropdown. Creating
a claim calls a callable backend function and starts polling its status. The
browser never receives or stores EMQX management credentials.

Polling reports `pending`, `registered`, `expired`, or an actionable error. The
browser stops polling on terminal states and displays the device's MQTT
registration result only as a success state, never as broker credentials.

## Registration API and broker provisioning

The device calls a public HTTPS registration endpoint with its device ID. The
backend accepts the request only when a matching pending claim is unexpired and
not already being processed. It then:

1. Reserves the claim with a transactional state change and idempotency token.
2. Generates a random per-device MQTT password and deterministic username.
3. Creates or updates the EMQX built-in user through the management API.
4. Writes least-privilege ACLs for that identity: subscribe only to the device's
   command topic and publish only to its status topic.
5. Commits the Firestore device/claim state transactionally and marks the claim
   registered.
6. Returns the MQTT username, password, broker host/port, and CA identity to the
   device exactly for local persistence.

External EMQX calls are made by Firebase Functions using Secret Manager values.
The API key has been verified to reach both user and ACL management resources;
valid payloads still need integration tests against a synthetic device identity.
If provisioning fails, the claim is left in a retryable provisioning state and
any partially created broker identity is disabled or removed before retry.
Repeated device requests are idempotent and never return a second password after
successful completion.

The registration endpoint returns generic failure responses for missing,
expired, already-used, and unknown IDs; it must not disclose whether an
unclaimed device exists. Requests are rate limited and bounded by function
timeouts.

## Device firmware and portal

The first hardware target is the Adafruit ESP32-S3 Reverse TFT Feather. Existing
XIAO firmware behavior remains the compatibility baseline while the board
adapter is introduced.

When credentials are absent, the device starts `Gate-Setup-<device-id>` and the
local portal at `http://192.168.4.1`. The portal scans nearby networks and shows
open and WPA-protected SSIDs with signal strength, collapsing duplicates. A
refresh action rescans; a manual SSID field remains available for hidden
networks. Wi-Fi credentials stay local and are never sent to the cloud.

After Wi-Fi is configured, the TFT shows a real QR code containing the HTTPS
registration URL and device ID, sized to occupy roughly half the 240x135 panel,
with `SCAN TO REGISTER` and a compact device ID. The rest of the panel is left
for small Wi-Fi, MQTT, and hold status indicators. The device polls the
registration endpoint while displaying this screen, then saves returned MQTT
credentials to its persistent settings and transitions to normal status display.
A boot animation precedes the onboarding/status screens.

## Data model and security

Claims are stored in a server-owned Firestore collection with device ID,
claiming UID, creation/expiration timestamps, state, and an idempotency token.
Device documents store registration state, credential version, and access data;
secrets are not exposed to browser reads. Firestore client rules remain deny-all
for these collections, with callable/API functions enforcing verified Google
Auth and App Check where applicable.

The EMQX App ID and secret remain in the local ignored `.env` for development
and in Firebase Secret Manager for deployment. They are never placed in browser
assets, URLs, device firmware, or logs.

## Verification

- Unit tests cover claim authorization, expiry, first-wins concurrency,
  idempotent retries, generic error responses, and broker payload construction.
- Integration tests use a synthetic device ID to create an EMQX user, ACL, TLS
  connect, command subscribe, status publish, revoke, and cleanup.
- Web tests cover first-login onboarding, dropdown add-device, polling terminal
  states, and QR/SSID selection.
- Firmware host tests cover SSID filtering, portal submission, registration
  persistence, TFT state transitions, and offline/retry behavior.
- Production deployment keeps the existing verified Google sign-in, App Check,
  device access checks, MQTT topic validation, and deny-all Firestore rules.
