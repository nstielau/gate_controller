# Device Enrollment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a verified Google user claim an unregistered device for two hours, let that device register over HTTPS, and provision per-device EMQX credentials while the web app and Reverse TFT guide the user.

**Architecture:** Firebase Functions own claims, registration, Firestore device creation, and EMQX management calls. The browser creates claims and polls a callable status function; it never receives broker secrets. The board keeps Wi-Fi setup local, polls a public registration endpoint while showing a TFT QR screen, persists the returned MQTT identity, and then enters the existing MQTT controller loop.

**Tech Stack:** Firebase Functions v2/Firestore Admin SDK, Node 22 built-in test runner, browser ES modules/Playwright, CircuitPython 10, Adafruit display APIs, EMQX v5 REST API.

---

### Task 1: Add the broker client and enrollment service

**Files:**
- Create: `firebase/functions/emqx.cjs`
- Create: `firebase/functions/enrollment.cjs`
- Test: `firebase/functions/test/emqx.test.cjs`
- Test: `firebase/functions/test/enrollment.test.cjs`

- [ ] **Step 1: Write failing broker request tests**

Test that `createEmqxClient({request})` sends Basic authorization, JSON content type, and the documented payloads:

```js
const {test} = require("node:test");
const assert = require("node:assert/strict");
const {createEmqxClient} = require("../emqx.cjs");

test("creates a device user and replaces its two topic rules", async () => {
  const calls = [];
  const client = createEmqxClient({baseUrl: "https://broker.example/api/v5", appId: "test-id", appSecret: "test-value", request: async call => { calls.push(call); return {status: 201, json: async () => ({})}; }});
  await client.provision({username: "gate-ab12cd", password: "pw-for-test", commandTopic: "gate/v1/devices/ab12cd/command", statusTopic: "gate/v1/devices/ab12cd/status"}); // pragma: allowlist secret
  assert.equal(calls[0].method, "POST");
  assert.match(calls[0].path, /authentication\/password_based%3Abuilt_in_database\/users$/);
  assert.deepEqual(calls[0].body, {user_id: "gate-ab12cd", password: "pw-for-test"});
  assert.equal(calls[1].method, "PUT");
  assert.deepEqual(calls[1].body.rules, [
    {action: "subscribe", permission: "allow", topic: "gate/v1/devices/ab12cd/command", qos: [1], retain: "all"},
    {action: "publish", permission: "allow", topic: "gate/v1/devices/ab12cd/status", qos: [0, 1], retain: "all"},
    {action: "all", permission: "deny", topic: "#"}
  ]);
});
```

- [ ] **Step 2: Run the focused test and verify the expected missing-module failure**

Run: `node --test firebase/functions/test/emqx.test.cjs`
Expected: FAIL with `Cannot find module '../emqx.cjs'`.

- [ ] **Step 3: Implement the minimal EMQX client**

`emqx.cjs` will validate the base URL, construct Basic auth internally, issue bounded `fetch` requests, accept 201/204 for writes, and throw an internal error without including response bodies or credentials. It will expose `provision`, `disable`, and `delete` for cleanup.

- [ ] **Step 4: Run the focused broker test**

Run: `node --test firebase/functions/test/emqx.test.cjs`
Expected: PASS.

- [ ] **Step 5: Write failing enrollment service tests**

Cover verified Google auth, device-ID validation, two-hour expiry, first-wins claim transaction, generic unknown/registered responses, registration idempotency, Firestore device creation, and broker failure rollback. Use an in-memory transaction harness and a fake broker; do not contact production EMQX in unit tests.

- [ ] **Step 6: Run the enrollment test and verify it fails for the missing service**

Run: `node --test firebase/functions/test/enrollment.test.cjs`
Expected: FAIL with `Cannot find module '../enrollment.cjs'`.

- [ ] **Step 7: Implement `createEnrollment`**

Use `claims/<deviceId>` records with `uid`, `createdAtMs`, `expiresAtMs`, `state`, and `attemptId`. `claim` transactionally rejects registered devices and active claims. `status` returns only the caller's claim state. `register` transactionally reserves a pending claim, provisions EMQX with deterministic username `gate-<deviceId>`, and transactionally creates `devices/<deviceId>` with `enabled`, `allowedUsers`, exact command/status topics, and `credentialVersion`. On broker failure, reset the claim to `pending`; return the credentials only once after successful finalization. Never return passwords to callable browser methods.

- [ ] **Step 8: Run all focused backend tests**

Run: `node --test firebase/functions/test/emqx.test.cjs firebase/functions/test/enrollment.test.cjs`
Expected: PASS.

- [ ] **Step 9: Commit the backend service**

```bash
git add firebase/functions/emqx.cjs firebase/functions/enrollment.cjs firebase/functions/test/emqx.test.cjs firebase/functions/test/enrollment.test.cjs
git commit -m "feat: add device enrollment service"
```

### Task 2: Expose Firebase APIs and secrets

**Files:**
- Modify: `firebase/functions/index.js`
- Modify: `firebase/functions/test/index.test.cjs` (create if absent)
- Modify: `firebase/README.md`

- [ ] **Step 1: Add failing export/handler tests**

Assert that callable handlers reject missing or unverified Google auth, registration accepts only bounded JSON device IDs, and CORS/cache headers prevent caching registration responses.

- [ ] **Step 2: Run the test to verify the new exports are absent**

Run: `node --test firebase/functions/test/index.test.cjs`
Expected: FAIL because `createDeviceClaim`, `deviceClaimStatus`, and `deviceRegister` are not exported.

- [ ] **Step 3: Add functions and Secret Manager bindings**

Define `EMQX_APP_ID`, `EMQX_APP_SECRET`, `EMQX_API_URL`, and retain existing MQTT secrets. Export two App Check-protected callables (`createDeviceClaim`, `deviceClaimStatus`) and an App Check-free `onRequest` endpoint (`deviceRegister`) with bounded body parsing, `Cache-Control: no-store`, and generic 400 responses for unknown/expired IDs.

- [ ] **Step 4: Run backend unit tests**

Run: `npm test`
Expected: all existing and new Node tests pass.

- [ ] **Step 5: Document deployment secrets and local emulator behavior**

Add the three EMQX management values to the secret setup documentation; state that the App ID/secret are never browser or device values and that registration integration tests use a synthetic ID.

- [ ] **Step 6: Commit the API surface**

```bash
git add firebase/functions/index.js firebase/functions/test/index.test.cjs firebase/README.md
git commit -m "feat: expose device claim and registration APIs"
```

### Task 3: Add first-login web onboarding and polling

**Files:**
- Modify: `web/index.html`
- Modify: `web/app.js`
- Modify: `web/gateway.js`
- Modify: `web/styles.css`
- Modify: `web/test/gateway.js`
- Modify: `web/test/app.spec.cjs`

- [ ] **Step 1: Add failing browser tests**

Test that an authenticated user with no devices sees a device-ID form, can submit a claim, sees pending status, polls until registered/expired, and can reopen the same flow from the account dropdown without sending a gate command. Test that the form accepts only `[a-z0-9-]{1,64}` and stops polling on terminal state.

- [ ] **Step 2: Run the focused browser test and verify it fails**

Run: `npm run build && npx playwright test web/test/app.spec.cjs --grep "claim|onboarding"`
Expected: FAIL because the onboarding form and gateway methods do not exist.

- [ ] **Step 3: Add gateway callables**

Expose `createDeviceClaim({deviceId})` and `deviceClaimStatus({deviceId})` through `httpsCallable`, using 30-second timeouts and returning only claim status data.

- [ ] **Step 4: Add the onboarding view**

Add a hidden section with device ID input, claim button, status text, expiration timestamp, and a retry/new-device action. Show it after login when `devices.length === 0`; show an `Add device` menu item for any signed-in user. Poll every 3 seconds while pending, clear the timer on sign-out, terminal state, or generation change, and preserve the existing control/menu behavior.

- [ ] **Step 5: Add responsive styles and accessibility labels**

Keep the form within the existing mobile card width, use `role=status` for polling messages, focus the input on open, and disable submit while offline or polling.

- [ ] **Step 6: Run web unit and focused browser tests**

Run: `npm test` and `npm run build && npx playwright test web/test/app.spec.cjs --grep "claim|onboarding"`
Expected: PASS.

- [ ] **Step 7: Commit the browser flow**

```bash
git add web/index.html web/app.js web/gateway.js web/styles.css web/test/gateway.js web/test/app.spec.cjs
 git commit -m "feat: add web device onboarding"
```

### Task 4: Add SSID scanning and device registration helpers

**Files:**
- Create: `circuitpython/lib/device_enrollment.py`
- Modify: `circuitpython/code.py`
- Test: `test_suite/test_device_enrollment.py`

- [ ] **Step 1: Write failing host tests**

Test pure helpers for device-ID normalization, open/WPA SSID filtering with duplicate collapse and signal ordering, bounded registration JSON parsing, and config persistence fields. The tests inject fake Wi-Fi results and HTTP responses so they run without hardware.

- [ ] **Step 2: Run the focused firmware test and verify it fails**

Run: `.venv/bin/python -m unittest test_suite.test_device_enrollment -v`
Expected: FAIL because `device_enrollment.py` does not exist.

- [ ] **Step 3: Implement the helper module**

Use only CircuitPython-compatible standard APIs. Return SSIDs as `{ssid, rssi, security}` for open and WPA/WPA2 networks, skip hidden entries and unsupported authentication modes, and keep the strongest result for duplicate SSIDs. Add bounded registration response parsing and a config record containing `mqtt_username`, `mqtt_password`, broker, and exact topics.

- [ ] **Step 4: Integrate local portal scanning**

Update `code.py` portal rendering to call `wifi.radio.start_scanning_networks()` when available, show a selectable open/WPA list plus Refresh and manual hidden-SSID input, and preserve the existing AP address and password handling. Do not expose saved Wi-Fi credentials in the page.

- [ ] **Step 5: Run firmware tests and syntax checks**

Run: `.venv/bin/python -m unittest test_suite.test_device_enrollment -v` and `make check`
Expected: PASS.

- [ ] **Step 6: Commit the portal changes**

```bash
git add circuitpython/lib/device_enrollment.py circuitpython/code.py test_suite/test_device_enrollment.py
git commit -m "feat: scan Wi-Fi networks during device setup"
```

### Task 5: Add Reverse TFT onboarding and HTTPS registration

**Files:**
- Create: `circuitpython/lib/device_display.py`
- Modify: `circuitpython/code.py`
- Create: `test_suite/test_device_display.py`
- Create: `docs/base-firmware/1.0.2.md`
- Modify: `circuitpython/lib/gate_base.py`

- [ ] **Step 1: Write failing display-state tests**

Test boot, QR onboarding, registered, Wi-Fi, MQTT, and hold status states with a fake display, and verify the QR payload contains the configured registration URL and lowercase device ID.

- [ ] **Step 2: Run the focused display test and verify it fails**

Run: `.venv/bin/python -m unittest test_suite.test_device_display -v`
Expected: FAIL because `device_display.py` does not exist.

- [ ] **Step 3: Implement the display adapter**

Use `board.DISPLAY` when available on `adafruit_feather_esp32s3_reverse_tft`, keep display imports optional for XIAO compatibility, and render a short boot animation followed by a QR image sized for approximately half the 240x135 screen, `SCAN TO REGISTER`, the device ID, and compact Wi-Fi/MQTT/HOLD indicators. Use a fixed QR encoder dependency already present in the board bundle; if unavailable, render the registration URL text and log a bounded display warning rather than preventing control.

- [ ] **Step 4: Implement registration polling in `code.py`**

After Wi-Fi configuration and before MQTT connection, issue HTTPS POST requests to the registration endpoint with the device ID, using the existing verified TLS path and bounded timeouts. Treat 400 as a retryable “not claimed” response, parse a successful credential response, persist it in NVM, and then enter the existing MQTT loop. Never log credentials or registration response bodies.

- [ ] **Step 5: Bump the protected base version and write USB validation notes**

Increase `BASE_VERSION` strictly from `1.0.1` to `1.0.2` and document the Reverse TFT target, portal scanning, registration persistence, and required USB/hardware checks in `docs/base-firmware/1.0.2.md`.

- [ ] **Step 6: Run firmware tests and pre-commit checks**

Run: `make test` and `make precommit`
Expected: PASS, with the staged base version/note satisfying the firmware guard.

- [ ] **Step 7: Commit the board support**

```bash
git add circuitpython/code.py circuitpython/lib/device_display.py circuitpython/lib/gate_base.py test_suite/test_device_display.py docs/base-firmware/1.0.2.md
git commit -m "feat: add Reverse TFT enrollment display"
```

### Task 6: Integration validation and release preparation

**Files:**
- Modify: `firebase/functions/test-emulator/device-access.test.cjs` only if shared fixtures need claim coverage
- Modify: `docs/ota-operations.md` with enrollment rollout notes

- [ ] **Step 1: Run all offline checks**

Run: `make test`, `npm test`, and `npm run build`.
Expected: all pass.

- [ ] **Step 2: Run browser and emulator checks**

Run: `npx playwright install chromium webkit` if needed, then `make web-test`.
Expected: unit/browser/emulator suites pass; no production Firestore host is used.

- [ ] **Step 3: Run synthetic EMQX integration checks**

Using a disposable device ID, verify create user, replace ACL, TLS MQTT connect, command subscribe, status publish, delete/disable, and cleanup. Do not actuate a gate or use a production device ID.

- [ ] **Step 4: Review secrets and generated files**

Run `git status --short`, ensure `.env` remains ignored, confirm no App Secret/password appears in tracked files or logs, and inspect the built web output for absence of management credentials.

- [ ] **Step 5: Commit documentation and present the release checkpoint**

```bash
git add docs/ota-operations.md
git commit -m "docs: document device enrollment rollout"
```

Before deployment, report test evidence and the required one-time USB base update for the Reverse TFT board. Deployment remains a separate explicit action.
