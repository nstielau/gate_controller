# Drawbridge web app

Open [Drawbridge](https://drawbridge-45487.firebaseapp.com) and sign in with Google.
The `drawbridge.stielau.us` and `.web.app` aliases redirect to this canonical origin before initializing
authentication. Keep `web/origin.mjs` aligned with Google's OAuth redirect URI:
`https://drawbridge-45487.firebaseapp.com/__/auth/handler`. Firebase authorized
domains and Google OAuth redirect URIs are separate settings. Do not switch
`authDomain` to `.web.app` without first registering its callback with Google.
The mobile app offers **1 minute, 15 minutes, 60 minutes, 6 hours**, and
**End hold**. A six-hour hold asks for confirmation. Add it to your phone's
home screen for quick access.

The favicon uses `web/drawbridge-castle-128.png`, matching the header artwork.
Home-screen icons are checked-in exports in `web/icons/`; regenerate them with
`node tools/export_castle_icons.mjs` (requires the Playwright Chromium browser
installed by `make web-setup`). Regular builds only copy these files. The iPhone
touch icon and ordinary install icons use enlarged artwork; Android gets a
separate padded `castle-maskable-512.png` for safe cropping into other shapes.

The centered loading indicator uses the original icon's pixels, with its bridge
rotating about the doorway hinge and suspension chains following the free edge.
`tools/build_loader_artwork.mjs` builds `web/drawbridge-loader.svg` from the
original icon and `web/drawbridge-loader-background.png` (an image-edited patch
visible only where the old bridge/chains were). Reduced-motion users see the
original still icon. Web builds regenerate, hash, and cache the loader asset.
`node tools/render_loader_gif.mjs` refreshes `artifacts/drawbridge-loader.gif`
with a complete four-second cycle at 50 fps and a live SVG preview at
`artifacts/drawbridge-loader.html`; this preview needs Playwright and ffmpeg.

To name a gate, select it and tap **Edit nickname**, enter a name, then tap
**Save nickname**. Names are shared with everyone assigned to that gate and
persist across visits. Any assigned user can rename an enabled gate. Names
must contain 1–80 characters; renaming does not send an MQTT command.

To share a gate, select it, open the profile dropdown, and choose **Invite to
device**. Enter the person's Google account email and select **Grant access**.
Anyone with current access to an enabled gate can invite others to that gate.
Invitees can control the gate and invite other people; this does not grant
administrator access. No invitation email is sent: share
https://drawbridge-45487.firebaseapp.com with them yourself. They must sign in
with that verified Google account and use **Refresh access** if already signed in.
An account is reserved if they have not signed in before.

Only assigned users can control a gate. The browser receives gate IDs and
display names, never MQTT credentials or arbitrary broker/topic parameters.
The first assigned account is `nick.stielau@gmail.com`, for gate `b3640c`.

Administration has **Admins** and **Device Firmware** tabs and a refresh icon.
Firmware cards show the last reported app/base pair, separately from the assigned
target. Older boards show “Base not reported” until their USB bootstrap supports
independent reporting. See [OTA operations](../docs/ota-operations.md).


Compatible registered boards also offer **Restart setup** in Administration.
Confirming disables new web commands and queues a reset; an offline board waits
until it reconnects. An active or pending hold blocks the request, and the board
checks its own hold lease before acknowledging. After the board acknowledges,
its Wi-Fi setup portal opens. Add Wi-Fi, scan the registration QR and register
with an account that already has access. Identity, nickname, access and command
history are preserved. This requires USB base 1.0.13 or newer and a trusted
pairing enrollment; it does not require OTA. The browser polls progress while
open and never automatically retries the reset mutation.

## Architecture and behavior

New USB boards use a private NVM pairing proof and a derived SHA-256 code in
their QR fragment. After installing the current USB bundle, enroll the attached
board once with `make device-pairing-enroll PORT=/dev/cu.usbmodem...` using the
project's IAM account. This deliberately stops/restarts the application and
creates a server-only `devicePairingBindings/<id>` public hash. It refuses to
replace a different existing identity. Neither the private proof nor MQTT
credentials leave USB in this step. No public API can establish this binding.
Then scan the board QR, sign in, and confirm **Register** (nickname optional).
The browser waits while the board retrieves its encrypted/retryable credentials,
saves them and subscribes to MQTT. Controls become available after its final
acknowledgment. Browser registration never publishes a gate command.

Firebase Hosting serves bundled HTML/JS/CSS. Google Authentication identifies
the user; reCAPTCHA Enterprise App Check protects all callable functions.
`listDevices` returns assigned, enabled gates. `holdGate` checks verified Google
sign-in, the current device allowlist, enabled state, exact topic, approved
duration, UUID request ID, and request age (60 seconds; 10 seconds of future
clock tolerance). CORS allows the two Drawbridge Hosting domains.

Accepted timed holds are counted server-side in each device record as
`holdCount` and shown as a small “holds issued” metric in the web app. End-hold
commands and uncertain deliveries do not increment the count.

Firestore transactions reserve commands before publishing, enforce a
three-second per-device cooldown, and prevent a repeated request ID from
publishing again. A changed payload with the same ID is rejected. Commands
are stored in `commands/<sha256(uid:requestId)>` with operator UID, device,
duration, timestamps, and `pending`, `accepted`, or `unknown` status. Keep these
records for audit; automated record deletion is not configured.

The function uses the existing EMQX broker over verified TLS on port 8883,
with the CA and credentials in Secret Manager. It publishes QoS 1 with
`retain=false`, using the existing firmware schema:

```json
{"version":1,"type":"hold_gate","duration_seconds":60,"command_id":"64-character-request-hash"}
```

Zero ends a hold. The XIAO starts timing when it receives the command. A new
command replaces the previous duration; it does not add to it.

**Accepted means MQTT PUBACK, not confirmation that the board received the
command or that the gate moved.** There is no physical gate-position feedback.
A disconnect, timeout, or ambiguous audit update reports uncertain delivery.
The app never queues offline commands or automatically retries a hold.
Request deduplication prevents repeated HTTP requests from publishing twice;
MQTT QoS 1 itself does not guarantee exactly-once hardware execution.

When a hold is accepted, Drawbridge stores its expected start and duration on
the gate record. The matching duration button displays a countdown and an
elapsed left-to-right color sweep. It survives refreshes and is shared with
other authorized users. It is an expected countdown only: direct MQTT commands,
lost board connectivity, or a command accepted by the broker but not delivered
to the board can make it disagree with physical gate state. An uncertain web
command clears the displayed expected hold rather than showing stale progress.

The app shell is cached with content-hashed assets and a content-based service
worker release. HTML and the service worker revalidate; hashed assets use
immutable caching. Updates offer a reload button. Authentication helpers,
API responses, external resources, and POST requests are never cached by the
service worker. An offline launch can display the shell, but sign-in and
commands still require connectivity. A first command after idle may take a
few seconds because functions scale to zero.

## Local setup and commands

Use Node/npm, Firebase CLI (tested with 15.30.0), gcloud, Java 21+, and the
repository's uv-managed Python environment. `make web-setup` installs a pinned
local Node 22 runtime, matching deployed functions, plus browser test binaries.
Keep both npm lockfiles committed. The UUID override patches a transitive
Google SDK dependency; review it with future SDK updates.

```sh
make setup
make web-setup
make web-build
make web-test-unit       # fast, offline validation + MQTT transport failure tests
make web-test-browser    # mobile Chromium and WebKit with a test gateway
make web-test-emulator   # actual Firestore transactions and deny-all client rules
make web-test           # all three
make web-test-mqtt      # live broker, three synthetic-topic cycles; no gate actuation
make web-test-live      # deployed OAuth redirect and unauthenticated API rejection
make web-deploy         # full web tests, then Functions + Hosting + rules
make web-status
```

The emulator target uses `demo-drawbridge` and refuses non-local Firestore
hosts. On macOS it checks Java via the Homebrew path; override
`JAVA_BIN=/path/to/java/bin` on other installations. These tests never publish
to the real gate. Existing `make test` and `make deploy` still test/deploy the
CircuitPython firmware independently.

The browser tests use a separate build in `artifacts/web-test`. Production
builds always use the real Firebase gateway and require both ignored public
config files. Never deploy the test build. Production output is `web/dist`.

### Public configuration on another checkout

Project: `drawbridge-45487`; region: `us-east1`; web app:
`1:498911170567:web:67d0d78cf97be687c85aa2`.

`.firebaserc` selects this project. Do not run `firebase init` over the existing
configuration. Copy `web/firebase-config.example.js` to
`web/firebase-config.js` and populate it from:

```sh
firebase apps:sdkconfig WEB 1:498911170567:web:67d0d78cf97be687c85aa2 --project drawbridge-45487
.venv/bin/python tools/firebase_cloud.py appcheck
```

The App Check helper reuses the Drawbridge reCAPTCHA key, registers the two
production domains, and writes `web/app-check-config.js`. Both configs contain
public identifiers, not authorization credentials, and are ignored locally.
No debug-token bypass is included in the production app.

### Access and device administration

Gate-access helpers use your gcloud login as `nick.stielau@gmail.com` and
project IAM. The profile dropdown also exposes **Administration** to server-verified
administrators. That view manages admin email assignments and per-device firmware
targets, separately from gate-control UID allowlists. `make admin-seed` initializes
Nick's protected owner record. All browser admin calls require verified Google
sign-in, App Check, and transactional role checks. See
[OTA operations](../docs/ota-operations.md) for release publishing, enrollment,
private artifact storage, and USB recovery.

```sh
make web-grant EMAIL=person@example.com DEVICE_ID=b3640c
make web-revoke EMAIL=person@example.com DEVICE_ID=b3640c
node_modules/.bin/node firebase/functions/admin.cjs disable nick.stielau@gmail.com b3640c
node_modules/.bin/node firebase/functions/admin.cjs enable nick.stielau@gmail.com b3640c
```

Grant reserves a Firebase user UID if that email has not signed in yet.
The user must still complete verified Google sign-in. Existing device access
lists are updated without replacing other users. Newly created device
documents default to enabled with the canonical command topic. Revoking
access or disabling a device blocks future commands; it does not cancel an
already-running hold. Sign in and select **Refresh access** after assignment.

Device documents live at `devices/<device-id>`:

```json
{
  "name": "Driveway gate",
  "enabled": true,
  "commandTopic": "gate/v1/devices/b3640c/command",
  "allowedUsers": ["firebase-auth-uid"]
}
```

Change the display name in the app with **Edit nickname**, or in the Firestore
console. The `renameGate` callable checks access transactionally and updates
only `name`; it cannot change device IDs, topics, permissions, or enabled state.
Access is by UID, not email.
The `inviteDeviceUser` callable checks verified Google sign-in and App Check,
then verifies the inviter's current device access, enabled state, and exact
topic before looking up or reserving the recipient's Firebase Auth UID. It
rechecks device access transactionally at the write and only updates
`allowedUsers`, preserving existing users and gate configuration. It never
publishes MQTT. Grants are audited in server-only `deviceAccessAudit` records
with inviter, recipient, device, and time. Fresh request IDs deduplicate retries;
replaying an already-completed request cannot restore subsequently revoked access.
Administrators without device access cannot invite themselves through this API.
Assign additional device IDs to different users with the same helper. This
release supports multiple devices on the existing broker; additional brokers
require server configuration and additional Secret Manager bindings.

### Secrets and deployment

Before the first deployment with browser invitations, give the runtime service
account a custom role containing only Auth user lookup and creation permissions.
The [Firebase user-management API](https://firebase.google.com/docs/auth/admin/manage-users)
reserves a UID without marking the address verified; the
[Identity Platform IAM reference](https://docs.cloud.google.com/identity-platform/docs/access-control)
lists the required permissions. This setup is separate from ordinary deployment:

```sh
gcloud iam roles create drawbridgeDeviceInviter --project=drawbridge-45487 --account=nick.stielau@gmail.com --title='Drawbridge device invitations' --permissions=firebaseauth.users.get,firebaseauth.users.create --stage=GA
gcloud projects add-iam-policy-binding drawbridge-45487 --account=nick.stielau@gmail.com --member=serviceAccount:drawbridge-functions@drawbridge-45487.iam.gserviceaccount.com --role=projects/drawbridge-45487/roles/drawbridgeDeviceInviter --condition=None
```

If the custom role already exists, inspect its permissions before reusing it.
Do not grant project Editor or broad Firebase Auth administration for invitations.

```sh
make web-secrets
make web-deploy
```

The secret helper reads `MQTT_USERNAME`, `MQTT_PASSWORD`, `EMQX_API_URL`,
`EMQX_APP_ID`, and `EMQX_APP_SECRET` from ignored `.env`, plus PEM data from
ignored `emqxsl-ca.crt`. It uploads only changed values, without printing them.
Redeploy functions after rotation. Old secret versions remain;
disable superseded versions after confirming the new deployment works.

Runtime identity: `drawbridge-functions@drawbridge-45487.iam.gserviceaccount.com`.
It needs `roles/datastore.user` on the project and Secret Accessor on the MQTT
and EMQX secrets (the Firebase deploy command grants secret access). It does not
need project Editor. Browser invitations also require the custom Auth role above.
Functions use 256 MiB, zero minimum instances, two maximum
instances each, and a 30-second timeout. Function build images are cleaned up
after seven days. Blaze billing is enabled; no paid minimum instances are used.

## Verification and remaining manual checks

Automated coverage includes unauthenticated and non-Google rejection,
unassigned/disabled/missing devices, topic tampering, every duration, stale
requests, duplicate and concurrent requests, rate limiting, audit outcomes,
TLS options, timeout/error cleanup, mobile layout, sign-out, and offline
controls. Invitation tests cover current device access (including revocation
during Auth lookup), concurrent grants, account-creation races, duplicate
requests, new/existing accounts, and mobile success/offline/error states.
Firestore transactions use the local emulator; invitation Auth calls use a
local fake. Actual Google sign-in to a reserved account and runtime IAM still
require an interactive deployment check. The live MQTT smoke check verifies the real CA/credentials and
three publish/receive cycles on a unique `web-test-...` device topic.

Cached offline launch is automated in Chromium. The WebKit version of that
one test is explicitly skipped because Playwright's service-worker support
is Chromium-only; offline controls still run in both browsers. See
[Playwright service workers](https://playwright.dev/docs/service-workers).
Verify home-screen launch, Google redirect sign-in, and offline relaunch on
a real iPhone. Test a real hold only when gate actuation is intended, then use
End hold and check the board logs. Mock browser tests and synthetic MQTT
cycles do not prove a physical gate action.

For deployment checks, open the production app, confirm Google sign-in,
check that your assigned gate appears, and verify signed-out API requests
are rejected. First sign-in is an interactive step the CLI cannot complete
for you. The app deliberately does not claim a gate is open based solely on
broker acceptance.
