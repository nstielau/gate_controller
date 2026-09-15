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
