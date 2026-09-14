# Future plan: safe OTA application upgrades

Status: original design proposal, retained for context. The first implementation
now exists; see [OTA operations](ota-operations.md) for the actual two-slot
storage, authenticated download endpoint, administrator UI, commands, and
outstanding physical verification. The original rename-based algorithm below
was replaced by two application slots and checksummed journals. Channel-wide
promotion and signed manifests remain future work.

## Recommendation

Use a small, stable `code.py` as the safety shell and update one self-contained
`drawbridge.py` application file over the air. GitHub Releases should be the
human-visible source of released artifacts. A device-authenticated Firebase
HTTP endpoint should decide which release a particular controller should run,
and the released file should be mirrored under an immutable, versioned object
name in Google Cloud Storage.

This first version should deliberately exclude OTA changes to `boot.py`,
`code.py`, CircuitPython itself, certificates, and `.mpy` libraries. Those
components define the updater and its recovery path and should continue to use
the tested USB deployment process. A later package updater can be considered
after the single-file design has accumulated field experience.

## Proposed firmware split

### `boot.py`: filesystem ownership

CircuitPython normally gives the USB host write access to `CIRCUITPY`, which
prevents application code from safely replacing its own files. A future
`boot.py` would make the filesystem writable by CircuitPython during normal
field operation. CircuitPython documents that filesystem ownership must be
chosen at boot; disabling concurrent-write protection risks corruption
([storage documentation](https://docs.circuitpython.org/en/stable/shared-bindings/storage/)).

There must also be an explicit physical maintenance mode that leaves the drive
writable by the USB host for recovery and `make deploy`. A candidate is a
normally unused pin held low during reset, but its board mapping and strapping
behavior must be checked on both supported controllers before choosing it. The
maintenance path must be tested before enabling OTA. Do not rely on simultaneous
host/device writes or `disable_concurrent_write_protection=True`.

### `code.py`: stable bootstrap and safety shell

`code.py` would remain USB-managed and own:

- immediate initialization of D10 and all indicators to LOW;
- configuration/NVM migration and captive-portal provisioning;
- Wi-Fi, TLS, MQTT connection and reconnect behavior;
- the bounded physical output lease for D10;
- status publication and fail-safe cleanup after any application exception;
- firmware-manifest checks, streaming download, verification, activation,
  health confirmation, and rollback;
- the narrow API passed to `drawbridge.py`.

The downloaded application must not receive a raw GPIO object for D10. It may
request a bounded hold lease, and `code.py` validates the requested duration,
owns the monotonic deadline, drives the transistor, and forces it LOW on exit.
This keeps the physical safety behavior in the component that OTA cannot
replace.

### `drawbridge.py`: replaceable application

The first refactor should combine the current app-specific behavior from
`gate_hold.py`, `gate_indicators.py`, and the relevant parts of `code.py` into
one ordinary Python source file. Keeping the OTA unit to one file avoids a
partially installed set of modules.

The interface should be small and versioned. One possible shape is:

```python
APP_VERSION = "1.0.0"
APP_API_VERSION = 1

def create_app(platform): ...
# app.on_message(topic, payload, retained, now)
# app.tick(now)
# app.status_fields(now)
```

`platform` would expose bounded operations such as `request_hold(seconds,
command_id)` and logical indicator setters. It would not expose credentials,
filesystem mutation, arbitrary MQTT publication, or direct access to D10.
The initial split must be behavior-preserving and deployed by USB before any
OTA checks are enabled.

## Release and control plane

### Release production

A release should start from a clean, tagged commit such as
`firmware-v1.2.0`. CI would run the full offline firmware suite and build these
release assets:

- `drawbridge.py`;
- `manifest.json`;
- an optional human-readable change log.

The manifest should contain only fixed, validated fields:

```json
{
  "schema": 1,
  "app_version": "1.2.0",
  "app_api_version": 1,
  "minimum_bootstrap_version": "1.0.0",
  "circuitpython_major": 10,
  "supported_board_ids": ["seeed_xiao_esp32_s3_sense"],
  "size": 28417,
  "sha256": "...",
  "artifact_object": "firmware/1.2.0/<sha256>/drawbridge.py",
  "git_commit": "...",
  "released_at": "..."
}
```

CI should attach the file and manifest to a GitHub Release, then copy the exact
bytes to a create-only Cloud Storage object containing both the semantic
version and SHA-256 in its path. GitHub's release-asset API can serve public
assets but clients must handle either a direct response or redirect
([GitHub release asset documentation](https://docs.github.com/en/rest/releases/assets)).
The Google mirror is recommended for the device so the constrained client has
one tested TLS and redirect behavior. It also prevents a normal web deployment
from deleting historical firmware assets in `web/dist`.

Neither artifact location may contain Wi-Fi, MQTT, Firebase, or signing
secrets. Release automation must refuse to overwrite an existing version or
digest and must verify the GitHub and Google copies have identical SHA-256
values.

### Firebase records

Server-owned Firestore records could use this shape:

- `firmwareReleases/<version>`: approved manifest fields, immutable object
  location, rollout state, and release sequence;
- `devices/<device-id>.firmwareChannel`: normally `stable`, optionally
  `canary`;
- `devices/<device-id>.firmwareTarget`: optional per-device override;
- `devices/<device-id>.reportedFirmware`: last app/bootstrap version and
  update result reported by the device;
- `devices/<device-id>.otaCredentialHash`: hash of a random, device-specific
  OTA credential.

The browser should never write these fields directly. Existing deny-all client
Firestore rules should remain in place. Administration should use local IAM
tools or a tightly authorized admin function.

### Device API

CircuitPython should use a small ordinary HTTPS API rather than implementing
the Firebase callable protocol:

- `GET /device-api/v1/firmware` returns the selected manifest or `204`;
- `POST /device-api/v1/firmware/report` records download, activation, success,
  or rollback outcomes.

Requests should carry the stable device ID and a random per-device bearer token
in headers, never in a URL. The backend stores only a slow or keyed hash of the
token, rejects disabled devices, bounds request sizes, rate-limits checks, and
returns only server-approved manifests. A controller must not be allowed to
supply an arbitrary artifact URL. App Check is designed for supported Firebase
clients and is not a substitute for explicit microcontroller authentication.

The OTA token will be recoverable by someone with physical USB access, as the
MQTT credential is today. Per-device tokens limit that exposure to one device
and can be revoked independently. The token should not authorize gate commands,
user data, Firestore access, or another controller's firmware record.

## On-device update algorithm

The updater should check after Wi-Fi and MQTT have been healthy for a short
jittered interval, then approximately every six hours with jitter. Network
errors use exponential backoff capped at 24 hours and never reset the board.
The current application continues running after a failed check.

An update is permitted only when:

- D10 is LOW and no hold lease is active;
- Wi-Fi and MQTT are healthy;
- no previous trial or rollback is unresolved;
- the manifest schema, app API, board ID, CircuitPython major, and minimum
  bootstrap version match;
- the target release sequence is newer than the last applied deployment
  sequence, or the backend has issued an explicit newer rollback deployment;
- the declared size is within a bootstrap constant and free space can hold the
  active file, backup, staged file, and a safety margin.

Use a release/deployment sequence separate from the semantic app version. To
roll back to older application bytes, publish a new deployment sequence that
points to the older approved digest. This prevents accidental replay while
allowing deliberate rollback without a general `allowDowngrade` switch.

Download with a small fixed-size buffer into `drawbridge.new`; never load the
whole response into RAM. The Adafruit requests API supports streamed response
content and requires the response to be closed
([requests documentation](https://docs.circuitpython.org/projects/requests/en/stable/api.html)).
While downloading, continue servicing the physical output deadline, indicators,
and MQTT often enough to avoid turning a small update into a long network stall.
Reject redirects outside an allowlisted Google artifact origin, incorrect
content length, oversized bodies, timeouts, short reads, and digest mismatch.

After closing and flushing the staged file:

1. Compute SHA-256 locally and compare it with the authenticated manifest.
2. Write a pending-update marker using temporary-file-plus-rename.
3. Remove only a previously confirmed backup.
4. Rename `drawbridge.py` to `drawbridge.bak`.
5. Rename `drawbridge.new` to `drawbridge.py`.
6. Reload through `supervisor.reload()`.

At startup, `code.py` reconciles every possible interrupted state before
importing the application. If the active file is missing, it restores the
backup. If the new file cannot import, has the wrong API, throws during startup,
or resets repeatedly before health confirmation, it restores the backup and
reloads. Stale `.new` files are never executed.

The trial becomes healthy only after import succeeds, MQTT subscription is
restored, outputs remain serviceable, and the main loop runs for at least 60
seconds. Only then should the bootstrap record the installed deployment,
remove the pending marker, and eventually delete the backup. Update state needs
power-loss-safe storage; reserve and version a distinct NVM region only after
confirming capacity alongside the existing 512-byte configuration record.
Otherwise use two checksummed state files with alternating generations.

TLS plus SHA-256 means the authenticated Firebase response chooses the trusted
digest and the download is checked against it. It does not protect against a
compromised Firebase control plane. A later hardening step may sign manifests
offline and embed a public verification key in `code.py`, after confirming a
small, audited signature verifier works within CircuitPython memory limits.
Do not use one fleet-wide HMAC secret as a substitute.

## Operational behavior

Add app and bootstrap versions plus a bounded update status to the existing
retained MQTT status payload and `GATE_LOG`. Useful states are `idle`,
`available`, `deferred_hold_active`, `downloading`, `trial`, `current`, and
`rolled_back`, with an error category rather than raw exception data. Never log
the OTA token, signed URL query, Wi-Fi password, or MQTT credentials.

An admin workflow should eventually provide commands similar to:

```text
make firmware-release VERSION=1.2.0
make firmware-target DEVICE_ID=b3640c VERSION=1.2.0
make firmware-channel CHANNEL=canary VERSION=1.2.0
make firmware-status DEVICE_ID=b3640c
```

Release promotion should proceed from a USB-connected bench device, to one
canary controller, and then to `stable`. A target change must be reversible,
audited, and independent of user gate access. Updates should never be queued as
gate commands, and a restart must not replay an MQTT hold.

## Test plan

Host tests should model the updater as a state machine with fake network,
filesystem, clock, and output lease. Inject a simulated power loss before and
after every write, close, marker update, rename, import, and health transition.
At minimum, cover:

- exact manifest validation, compatibility bounds, size, and SHA-256;
- rejected unknown origins, traversal paths, malformed JSON, and oversized
  responses;
- storage-full, short-read, timeout, TLS, redirect, and hash failures;
- deferral for active holds and continued LOW output during bootstrap failures;
- new-app syntax/import/runtime failures and automatic backup restoration;
- interrupted activation with every combination of active, backup, staged,
  and pending files;
- replay prevention, explicit rollback deployment, backoff, and status redaction;
- an unreviewed `drawbridge.py` never reaching a release record.

Firebase emulator tests should cover device-token authentication, token
revocation, disabled devices, per-device/channel targeting, compatibility
selection, immutable release records, rate limits, and report validation. The
device endpoints use IAM-backed server access; Firestore client rules remain
deny-all.

Before field rollout, use a non-gate bench controller and test real HTTPS
streaming, SHA-256 memory use, filesystem ownership, host maintenance mode,
full-disk behavior, power removal during each activation step, bad Python
syntax, repeated crashes, recovery over USB, and a successful rollback. Then
run the existing passive hardware test plus a deliberate short hold. Hardware
evidence must confirm D10 stays LOW throughout update and recovery except for
that explicit hold.

## Delivery phases

1. **Behavior-preserving split:** create `code.py`/`drawbridge.py` boundaries,
   keep OTA disabled, and prove current MQTT, timing, indicators, provisioning,
   and USB deployment are unchanged.
2. **Recovery foundation:** add and verify `boot.py` ownership plus physical
   maintenance mode, staged file handling, trial health, and rollback using
   local test files only.
3. **Release pipeline:** build reproducible single-file artifacts, GitHub
   Releases, immutable Google mirrors, manifests, and secret scanning.
4. **Firebase control plane:** add device OTA credentials, release/target
   records, ordinary HTTPS endpoints, emulator coverage, audit records, and
   admin commands.
5. **Bench OTA:** enable checks only for a dedicated canary device and complete
   power-loss and failure-injection tests.
6. **Field canary and stable rollout:** promote one controller, observe it for
   at least a week, exercise rollback, then enable the stable channel.

The first implementation milestone should stop after phase 1 for review. The
filesystem and rollback work changes the device's recovery model and warrants a
separate, explicitly tested change before any network-delivered file can run.
