const {test} = require("node:test");
const assert = require("node:assert/strict");
const {createAdministration, validateManifest} = require("../administration.cjs");
const m = {schema: 1, app_version: "1.0.0", app_api_version: 1, minimum_bootstrap_version: "1.0.0", circuitpython_major: 10, supported_board_ids: ["seeed_xiao_esp32_s3_sense"], size: 100, sha256: "a".repeat(64), git_commit: "b".repeat(40), artifact_object: "firmware/1.0.0/" + "a".repeat(64) + "/drawbridge.py"};
test("firmware manifests constrain board, bootstrap, digest, size and object location", () => {
  assert.deepEqual(validateManifest({...m, unlisted: "must not escape"}), m);
  for (const changes of [{app_version: "../bad"}, {app_version: "01.0.0"}, {schema: true}, {app_api_version: 2}, {size: 65537}, {size: 0}, {size: 1.2}, {sha256: "bad"}, {circuitpython_major: 9}, {supported_board_ids: ["other"]}, {artifact_object: "https://evil.example/app.py"}, {minimum_bootstrap_version: "99.0.0"}]) {
    assert.throws(() => validateManifest({...m, ...changes}), {publicCode: "invalid-argument"});
  }
});
test("admin calls reject missing or nonverified Google identity before database access", async () => {
  const api = createAdministration({doc() { throw new Error("must not reach DB"); }});
  for (const auth of [undefined, {uid: "user", token: {email: "nick.stielau@gmail.com", email_verified: false, firebase: {sign_in_provider: "google.com"}}}, {uid: "user", token: {email: "nick.stielau@gmail.com", email_verified: true, firebase: {sign_in_provider: "password"}}}]) {
    await assert.rejects(api.session({auth}), e => ["unauthenticated", "permission-denied"].includes(e.publicCode));
    await assert.rejects(api.overview({auth}), e => ["unauthenticated", "permission-denied"].includes(e.publicCode));
    await assert.rejects(api.change({auth}), e => ["unauthenticated", "permission-denied"].includes(e.publicCode));
  }
});

function restartFixture() {
  const {hash} = require("../administration.cjs");
  const time = 1800000000000, id = "test-gate", uid = "administrator", email = "administrator@example.test", code = "a".repeat(64);
  const records = new Map();
  const device = {enabled: true, enrollmentState: "registered", name: "Garden", allowedUsers: ["operator"],
    commandTopic: `gate/v1/devices/${id}/command`, statusTopic: `gate/v1/devices/${id}/status`, holdCount: 17, pendingCommandId: null, activeHold: null,
    firmwareTarget: {version: "1.0.3", enabled: true, sequence: 2}, maintenance: {supportsRestartSetup: true, appVersion: "1.0.4", baseVersion: "1.0.13", lastSeenAtMs: time}};
  records.set("devices/" + id, device);
  records.set("admins/" + hash(email), {email});
  records.set("devicePairingBindings/" + id, {pairingCode: code});
  records.set("deviceEnrollments/" + id, {state: "registered", claimKey: hash(id + ":" + code), envelope: {iv: "private", tag: "private", ciphertext: "private"}});
  const tx = {
    async get(ref) {
      if (ref.collection) return {docs: [...records].filter(([path]) => path.startsWith(ref.collection + "/")).map(([path, data]) => ({id: path.split("/")[1], data: () => structuredClone(data)}))};
      const value = records.get(ref.path); return {exists: value !== undefined, data: () => structuredClone(value)};
    },
    set(ref, value) { records.set(ref.path, structuredClone(value)); },
    update(ref, value) { records.set(ref.path, {...records.get(ref.path), ...structuredClone(value)}); },
    create(ref, value) { if (records.has(ref.path)) throw new Error("exists"); records.set(ref.path, structuredClone(value)); },
    delete(ref) { records.delete(ref.path); },
  };
  const db = {doc: path => ({path}), collection: collection => ({limit: () => ({collection})}), async runTransaction(fn) { return fn(tx); }};
  const auth = {uid, token: {email, email_verified: true, firebase: {sign_in_provider: "google.com"}}};
  const request = {auth, data: {action: "restartSetup", deviceId: id, requestId: "12345678-1234-4234-8234-123456789012", issuedAtMs: time}};
  return {db, records, device, request, api: createAdministration(db, () => time), time, id, uid, email, hash};
}
test("restart setup disables controls transactionally, preserves identity, and deduplicates its stable audit ID", async () => {
  const f = restartFixture(), before = structuredClone(f.device);
  assert.deepEqual(await f.api.change(f.request), {ok: true});
  const reset = {id: f.hash(f.uid + ":" + f.request.data.requestId), state: "pending", requestedAtMs: f.time, actor: f.uid};
  assert.deepEqual(f.records.get("devices/" + f.id), {...before, enabled: false, setupReset: reset});
  assert.equal(f.records.get("adminAudit/" + reset.id).action, "restartSetup");
  await f.api.change(f.request);
  assert.deepEqual(f.records.get("devices/" + f.id).setupReset, reset);
  await assert.rejects(f.api.change({...f.request, data: {...f.request.data, action: "pauseFirmware"}}), {publicCode: "invalid-argument"});
  await assert.rejects(f.api.change({...f.request, data: {...f.request.data, requestId: "22345678-1234-4234-8234-123456789012"}}), {publicCode: "failed-precondition"});
});
test("restart requires current admin role, trusted registered envelope, exact topics and compatible advertised maintenance", async () => {
  for (const change of [device => device.enabled = false, device => device.enrollmentState = "provisioning", device => device.commandTopic = "other", device => device.statusTopic = "other",
    device => device.maintenance.supportsRestartSetup = false, device => device.maintenance.baseVersion = "1.0.12", device => device.setupReset = {state: "awaiting_setup"}]) {
    const f = restartFixture(); change(f.records.get("devices/" + f.id));
    await assert.rejects(f.api.change(f.request), {publicCode: "failed-precondition"});
    assert.equal([...f.records.keys()].some(key => key.startsWith("adminAudit/")), false);
  }
  for (const path of ["devicePairingBindings/test-gate", "deviceEnrollments/test-gate"]) {
    const f = restartFixture(); f.records.delete(path);
    await assert.rejects(f.api.change(f.request), {publicCode: "failed-precondition"});
  }
  const f = restartFixture(); f.records.delete("admins/" + f.hash(f.email));
  await assert.rejects(f.api.change(f.request), {publicCode: "permission-denied"});
});
test("restart refuses active or pending/unknown-in-flight holds and leaves command audits intact", async () => {
  for (const change of [device => device.activeHold = {startedAtMs: 1800000000000, durationSeconds: 60}, device => device.pendingCommandId = "uncertain-command"]) {
    const f = restartFixture(); change(f.records.get("devices/" + f.id));
    f.records.set("commands/uncertain-command", {status: "unknown", durationSeconds: 60});
    const before = structuredClone(f.records.get("devices/" + f.id));
    await assert.rejects(f.api.change(f.request), {publicCode: "failed-precondition"});
    assert.deepEqual(f.records.get("devices/" + f.id), before);
    assert.deepEqual(f.records.get("commands/uncertain-command"), {status: "unknown", durationSeconds: 60});
  }
  const f = restartFixture(); f.records.get("devices/" + f.id).activeHold = {startedAtMs: f.time - 61000, durationSeconds: 60};
  f.records.set("commands/old-unknown", {status: "unknown", durationSeconds: 60});
  await f.api.change(f.request);
  assert.equal(f.records.get("commands/old-unknown").status, "unknown");
});
test("admin overview exposes allowlisted maintenance and reset progress without identifiers or credential data", async () => {
  const f = restartFixture();
  f.records.get("devices/" + f.id).maintenance.privateProof = "private";
  await f.api.change(f.request);
  const view = (await f.api.overview(f.request)).devices[0];
  assert.deepEqual(view.maintenance, {supportsRestartSetup: true, appVersion: "1.0.4", baseVersion: "1.0.13", lastSeenAtMs: f.time});
  assert.deepEqual(view.setupReset, {state: "pending", requestedAtMs: f.time});
  assert.equal(JSON.stringify(view).includes("private"), false);
  assert.equal(JSON.stringify(view).includes(f.uid), false);
  assert.equal(JSON.stringify(view).includes(f.records.get("devices/" + f.id).setupReset.id), false);
});


test("admin observation selects the newest stored firmware pair without inferring target or missing base", async () => {
  const f = restartFixture(), device = f.records.get("devices/" + f.id);
  device.lastSeenAtMs = f.time + 30;
  device.reportedFirmware = {version: "2.0.0", base_version: "1.0.2", atMs: f.time - 10, state: "current", privateToken: "must-not-escape"};
  let view = (await f.api.overview(f.request)).devices[0];
  assert.deepEqual(view.observation, {lastSeenAtMs: f.time + 30, appVersion: "1.0.4", baseVersion: "1.0.13", reportedAtMs: f.time});
  device.reportedFirmware.atMs = f.time + 20;
  delete device.reportedFirmware.base_version;
  view = (await f.api.overview(f.request)).devices[0];
  assert.deepEqual(view.observation, {lastSeenAtMs: f.time + 30, appVersion: "2.0.0", baseVersion: null, reportedAtMs: f.time + 20});
  assert.equal(JSON.stringify(view).includes("must-not-escape"), false);
  delete device.lastSeenAtMs;
  delete device.maintenance;
  view = (await f.api.overview(f.request)).devices[0];
  assert.equal(view.observation.lastSeenAtMs, f.time + 20);
  device.reportedFirmware = null;
  view = (await f.api.overview(f.request)).devices[0];
  assert.deepEqual(view.observation, {lastSeenAtMs: null, appVersion: null, baseVersion: null, reportedAtMs: null});
});
test("admin observation ignores invalid timestamps and versions, never returning invalid dates or nested data", async () => {
  for (const stamp of [-1, 0, "123", null, 1.5, 8640000000000001]) {
    const f = restartFixture(), device = f.records.get("devices/" + f.id);
    device.lastSeenAtMs = stamp;
    device.maintenance = {appVersion: "bad", baseVersion: {private: true}, lastSeenAtMs: stamp};
    device.reportedFirmware = {version: "01.2.3", base_version: true, atMs: stamp};
    const view = (await f.api.overview(f.request)).devices[0];
    assert.deepEqual(view.observation, {lastSeenAtMs: null, appVersion: null, baseVersion: null, reportedAtMs: null});
  }
});


test("an older retried OTA report cannot replace a newer firmware snapshot", async () => {
  const f = restartFixture(), {createDeviceService} = require("../administration.cjs");
  let time = f.time;
  const service = createDeviceService(f.db, () => time), runTransaction = f.db.runTransaction.bind(f.db);
  f.db.runTransaction = async fn => {
    f.db.runTransaction = runTransaction;
    time += 100;
    await service.report(f.id, {version: "1.0.2", base_version: "1.0.14", state: "current", sequence: 2});
    return runTransaction(fn);
  };
  await service.report(f.id, {version: "1.0.1", base_version: "1.0.13", state: "current", sequence: 1});
  const stored = f.records.get("devices/" + f.id);
  assert.equal(stored.lastSeenAtMs, f.time + 100);
  assert.equal(stored.reportedFirmware.version, "1.0.2");
  assert.equal(stored.reportedFirmware.base_version, "1.0.14");
  assert.equal(stored.reportedFirmware.atMs, f.time + 100);
});
