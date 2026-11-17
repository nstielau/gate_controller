const {test, after} = require("node:test");
const assert = require("node:assert/strict");
const {randomUUID, randomBytes} = require("node:crypto");
const {initializeApp, deleteApp} = require("firebase-admin/app");
const {getFirestore} = require("firebase-admin/firestore");
const {createAdministration, createDeviceService, hash, OWNER} = require("../administration.cjs");
if (!/^127\.0\.0\.1:\d+$/.test(process.env.FIRESTORE_EMULATOR_HOST || "")) throw new Error("Local emulator required");
const app = initializeApp({projectId: "demo-drawbridge"}, "administration"), db = getFirestore(app);
after(async () => { await db.terminate(); await deleteApp(app); });
const auth = email => ({uid: hash(email), token: {email, email_verified: true, firebase: {sign_in_provider: "google.com"}}});
async function fixture() {
  const email = randomUUID() + "@example.test", id = randomUUID(), time = Date.now();
  await db.doc("admins/" + hash(email)).set({email});
  const request = data => ({auth: auth(email), data: {requestId: randomUUID(), issuedAtMs: time, ...data}});
  const admin = createAdministration(db, () => time);
  return {email, id, time, request, admin};
}
test("admins can assign before login, revoke, and cannot remove owner or self-elevate", async () => {
  const f = await fixture(), other = randomUUID() + "@example.test";
  assert.deepEqual(await f.admin.session({auth: auth(other)}), {isAdmin: false});
  await assert.rejects(f.admin.change({...f.request({action: "grantAdmin", email: other}), auth: auth(other)}), {publicCode: "permission-denied"});
  await f.admin.change(f.request({action: "grantAdmin", email: other}));
  assert.deepEqual(await f.admin.session({auth: auth(other.toUpperCase())}), {isAdmin: true});
  await f.admin.overview({auth: auth(other)});
  await f.admin.change(f.request({action: "revokeAdmin", email: other}));
  await assert.rejects(f.admin.overview({auth: auth(other)}), {publicCode: "permission-denied"});
  await assert.rejects(f.admin.change(f.request({action: "revokeAdmin", email: OWNER})), {publicCode: "failed-precondition"});
  await db.doc("admins/" + hash(f.email)).delete();
  await assert.rejects(f.admin.change(f.request({action: "grantAdmin", email: other})), {publicCode: "permission-denied"});
});
test("targets use approved enrolled devices; duplicate clicks increment once; pause and rollback are explicit deployments", async () => {
  const f = await fixture(), ref = db.doc("devices/" + f.id), version = "1.0.9";
  const m = {schema: 1, app_version: version, app_api_version: 1, minimum_bootstrap_version: "1.0.0", circuitpython_major: 10, supported_board_ids: ["seeed_xiao_esp32_s3_sense"], size: 100, sha256: "a".repeat(64), git_commit: "b".repeat(40), artifact_object: `firmware/${version}/${"a".repeat(64)}/drawbridge.py`, approved: true};
  await db.doc("firmwareReleases/" + version).set(m);
  await ref.set({enabled: true, allowedUsers: ["operator"], commandTopic: "exact", otaCredentialHash: hash("secret-token")});
  const req = f.request({action: "targetFirmware", deviceId: f.id, version});
  await Promise.all([f.admin.change(req), f.admin.change(req)]);
  assert.equal((await ref.get()).data().firmwareTarget.sequence, 1);
  assert.equal((await ref.get()).data().commandTopic, "exact");
  await assert.rejects(f.admin.change({...req, data: {...req.data, action: "pauseFirmware"}}), {publicCode: "invalid-argument"});
  await f.admin.change(f.request({action: "pauseFirmware", deviceId: f.id}));
  assert.equal((await ref.get()).data().firmwareTarget.enabled, false);
  await f.admin.change(f.request({action: "targetFirmware", deviceId: f.id, version}));
  assert.equal((await ref.get()).data().firmwareTarget.sequence, 3);
  await ref.update({enabled: false});
  await assert.rejects(f.admin.change(f.request({action: "targetFirmware", deviceId: f.id, version})), {publicCode: "failed-precondition"});
  const data = await f.admin.overview(f.request({}));
  assert.equal(JSON.stringify(data).includes("otaCredentialHash"), false);
});
test("device authentication is scoped, revocable, rate limited, and manifests exclude secrets", async () => {
  const f = await fixture(), token = randomBytes(32).toString("hex"), ref = db.doc("devices/" + f.id);
  const service = createDeviceService(db, () => f.time);
  await ref.set({enabled: true, otaCredentialHash: hash(token), allowedUsers: ["private"]});
  for (const bad of ["", "bad", "a".repeat(64)]) await assert.rejects(service.authorize(f.id, bad, "manifest"), {publicCode: "unauthenticated"});
  const device = await service.authorize(f.id, token, "manifest");
  assert.equal((await ref.get()).data().lastSeenAtMs, f.time);
  assert.equal(await service.manifest(device), null);
  await assert.rejects(service.authorize(f.id, token, "manifest"), {publicCode: "resource-exhausted"});
  await assert.rejects(service.authorize("other-device", token, "manifest"), {publicCode: "unauthenticated"});
  await service.report(f.id, {state: "current", version: "1.0.0", sequence: 0, extra: "secret"});
  assert.equal((await ref.get()).data().reportedFirmware.extra, undefined);
  assert.equal((await ref.get()).data().reportedFirmware.base_version, null);
  await service.report(f.id, {state: "current", version: "1.0.9", base_version: "1.0.1", sequence: 2});
  assert.equal((await ref.get()).data().reportedFirmware.base_version, "1.0.1");
  assert.equal((await ref.get()).data().reportedFirmware.version, "1.0.9");
  for (const base_version of [null, "bad", "01.0.0", {}, true]) {
    await assert.rejects(service.report(f.id, {state: "current", version: "1.0.9", base_version, sequence: 2}), {publicCode: "invalid-argument"});
  }
  await assert.rejects(service.report(f.id, {state: "current", version: "bad", sequence: 0}), {publicCode: "invalid-argument"});
  await ref.update({enabled: false});
  await assert.rejects(service.authorize(f.id, token, "report"), {publicCode: "unauthenticated"});
});


test("device observation persists authenticated contact and version reports without exposing private fields", async () => {
  const f = await fixture(), ref = db.doc("devices/" + f.id), token = randomBytes(32).toString("hex");
  let time = f.time;
  const service = createDeviceService(db, () => time);
  await ref.set({enabled: true, otaCredentialHash: hash(token), allowedUsers: ["private-user"],
    maintenance: {appVersion: "1.0.1", baseVersion: "1.0.13", lastSeenAtMs: time - 100, supportsRestartSetup: true}});
  await service.authorize(f.id, token, "manifest");
  assert.equal((await ref.get()).data().lastSeenAtMs, time);
  time += 1000;
  await service.report(f.id, {version: "1.0.9", state: "current", sequence: 0});
  assert.equal((await ref.get()).data().lastSeenAtMs, time);
  const getView = async () => (await f.admin.overview(f.request({}))).devices.find(d => d.id === f.id);
  let view = await getView();
  assert.deepEqual(view.observation, {lastSeenAtMs: time, appVersion: "1.0.9", baseVersion: null, boardId: null, reportedAtMs: time});
  time += 10001;
  await service.authorize(f.id, token, "manifest");
  view = await getView();
  assert.equal(view.observation.lastSeenAtMs, time);
  assert.equal(view.observation.reportedAtMs, time - 10001);
  assert.equal(JSON.stringify(view).includes("private-user"), false);
  assert.equal(JSON.stringify(view).includes(hash(token)), false);
  const stored = (await ref.get()).data();
  time += 10001;
  await assert.rejects(service.authorize(f.id, "a".repeat(64), "manifest"));
  await assert.rejects(service.report(f.id, {version: "invalid", state: "current", sequence: 0}));
  assert.deepEqual((await ref.get()).data(), stored);
});

test("API2 target assignment and manifest/artifact serving enforce enrolled and newest reported board/base without advancing other targets", async () => {
  const f = await fixture(), ref = db.doc("devices/" + f.id), feather = "adafruit_feather_esp32s3_reverse_tft", xiao = "seeed_xiao_esp32_s3_sense";
  const version = "1.1.0", releaseRef = db.doc("firmwareReleases/" + version);
  const release = {schema: 1, app_version: version, app_api_version: 2, minimum_bootstrap_version: "1.1.0", circuitpython_major: 10,
    supported_board_ids: [feather], size: 100, sha256: "a".repeat(64), git_commit: "b".repeat(40), artifact_object: `firmware/${version}/${"a".repeat(64)}/drawbridge.py`, approved: true};
  const oldTarget = {version: "1.0.9", sequence: 4, enabled: true};
  const other = db.doc("devices/" + randomUUID());
  await other.set({enabled: true, firmwareTarget: oldTarget});
  await releaseRef.set(release);
  const token = randomBytes(32).toString("hex");
  await ref.set({enabled: true, otaCredentialHash: hash(token), firmwareTarget: oldTarget,
    maintenance: {appVersion: "1.1.0", baseVersion: "1.0.15", boardId: feather, lastSeenAtMs: f.time}});
  const request = f.request({action: "targetFirmware", deviceId: f.id, version});
  // Publishing/importing a manifest by itself never advances fleet targets.
  assert.deepEqual((await other.get()).data().firmwareTarget, oldTarget);
  await assert.rejects(f.admin.change(request), {publicCode: "failed-precondition"});
  for (const changes of [
    {otaBoardId: xiao},
    {otaBoardId: feather, maintenance: {appVersion: "1.1.0", baseVersion: "1.0.14", boardId: feather, lastSeenAtMs: f.time}},
    {otaBoardId: feather, maintenance: {appVersion: "1.1.0", baseVersion: "1.0.15", lastSeenAtMs: f.time}},
    {otaBoardId: feather, maintenance: {appVersion: "1.1.0", baseVersion: "1.0.15", boardId: xiao, lastSeenAtMs: f.time}},
  ]) {
    await ref.update(changes);
    await assert.rejects(f.admin.change(request), {publicCode: "failed-precondition"});
    assert.deepEqual((await ref.get()).data().firmwareTarget, oldTarget);
  }
  await ref.update({otaBoardId: feather, maintenance: {appVersion: "1.1.0", baseVersion: "1.0.15", boardId: feather, lastSeenAtMs: f.time}});
  await Promise.all([f.admin.change(request), f.admin.change(request)]);
  assert.deepEqual((await ref.get()).data().firmwareTarget, {version, sequence: 5, enabled: true});
  assert.deepEqual((await other.get()).data().firmwareTarget, oldTarget);
  assert.deepEqual((await releaseRef.get()).data(), release);
  let time = f.time;
  const service = createDeviceService(db, () => time);
  const {createFirmwareHandler} = require("../firmware-http.cjs");
  let downloads = 0;
  const handler = createFirmwareHandler(service, {file() { downloads++; throw new Error("Incompatible device must not access artifacts"); }});
  async function get(route) {
    time += 10001;
    const response = {code: 200, set() {}, status(code) { this.code = code; return this; }, end() { return this; }, json(body) { this.body = body; return this; }};
    await handler({method: "GET", path: "/device-api/v1/" + route, query: {sequence: "5"}, get(key) { return {"X-Device-ID": f.id, Authorization: "Bearer " + token}[key]; }}, response);
    return response;
  }
  assert.equal((await get("manifest")).body.app_api_version, 2);
  for (const report of [{version, base_version: "1.0.14", board_id: feather}, {version, base_version: "1.0.15", board_id: xiao}, {version}]) {
    await ref.update({reportedFirmware: {...report, atMs: f.time + 1, state: "current", sequence: 5}});
    assert.equal((await get("manifest")).code, 204);
    assert.equal((await get("artifact")).code, 204);
  }
  assert.equal(downloads, 0);
  await ref.update({reportedFirmware: {version, base_version: "1.0.15", board_id: feather, atMs: f.time + 2, state: "current", sequence: 5}});
  assert.equal((await get("manifest")).body.app_api_version, 2);
  await db.doc("admins/" + hash(f.email)).delete();
  await assert.rejects(f.admin.change({...request, data: {...request.data, requestId: randomUUID()}}), {publicCode: "permission-denied"});
});
test("legacy XIAO enrollment without board metadata retains API1 target and manifest behavior", async () => {
  const f = await fixture(), ref = db.doc("devices/" + f.id), version = "1.0.0", token = randomBytes(32).toString("hex");
  const release = {schema: 1, app_version: version, app_api_version: 1, minimum_bootstrap_version: "1.0.0", circuitpython_major: 10,
    supported_board_ids: ["seeed_xiao_esp32_s3_sense"], size: 100, sha256: "a".repeat(64), git_commit: "b".repeat(40), artifact_object: `firmware/${version}/${"a".repeat(64)}/drawbridge.py`, approved: true};
  await db.doc("firmwareReleases/" + version).set(release);
  await ref.set({enabled: true, otaCredentialHash: hash(token)});
  await f.admin.change(f.request({action: "targetFirmware", deviceId: f.id, version}));
  const service = createDeviceService(db, () => f.time);
  assert.deepEqual(await service.manifest(await service.authorize(f.id, token, "manifest")), {...Object.fromEntries(Object.entries(release).filter(([key]) => key !== "approved")), sequence: 1});
  await ref.update({otaBoardId: "adafruit_feather_esp32s3_reverse_tft"});
  assert.equal(await service.manifest((await ref.get()).data()), null);
  await assert.rejects(f.admin.change(f.request({action: "targetFirmware", deviceId: f.id, version})), {publicCode: "failed-precondition"});
});
