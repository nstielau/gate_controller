const {test, after} = require("node:test");
const assert = require("node:assert/strict");
const {createHash, randomBytes, randomUUID} = require("node:crypto");
const {initializeApp, deleteApp} = require("firebase-admin/app");
const {getFirestore} = require("firebase-admin/firestore");
const {createEnrollment, CLAIM_MS, PROVISIONING_LEASE_MS} = require("../enrollment.cjs");
const {createController} = require("../controller.cjs");
const {createStore} = require("../store.cjs");
const {createAdministration} = require("../administration.cjs");
if (!/^127\.0\.0\.1:\d+$/.test(process.env.FIRESTORE_EMULATOR_HOST || "")) throw new Error("Local emulator required; never test against production");
const app = initializeApp({projectId: "demo-drawbridge"}, "enrollment"), db = getFirestore(app);
after(async () => { await db.terminate(); await deleteApp(app); });
const hash = value => createHash("sha256").update(value).digest("hex");
async function fixture() {
  const id = randomUUID(), secret = randomBytes(32).toString("hex"), pairingCode = hash(secret), uid = randomUUID();
  const auth = {uid, token: {email_verified: true, firebase: {sign_in_provider: "google.com"}}};
  let time = Date.now();
  const calls = [], hooks = {};
  const api = createEnrollment({db, now: () => time, broker: {
    async provision(value) { calls.push(value); if (hooks.provision) await hooks.provision(value); },
    async remove() { throw new Error("Must never remove a possibly valid broker identity"); },
  }});
  const request = {auth, data: {deviceId: id, pairingCode, nickname: "  Garden  "}};
  await db.doc("devicePairingBindings/" + id).set({pairingCode});
  return {id, secret, pairingCode, uid, auth, calls, hooks, api, request, get time() { return time; },
    device: {device_id: id, device_secret: secret}, key: hash(id + ":" + pairingCode),
    advance(ms) { time += ms; }};
}
test("concurrent claims atomically select one owner for a pairing proof without fake-code public-ID reservation", async () => {
  const f = await fixture();
  await assert.rejects(f.api.claim({...f.request, auth: {...f.auth, uid: "unrelated"}, data: {...f.request.data, pairingCode: hash("fake")}}), {publicCode: "failed-precondition"});
  const attempts = await Promise.allSettled(Array.from({length: 5}, (_, index) => f.api.claim({...f.request, auth: {...f.auth, uid: "owner-" + index}})));
  assert.equal(attempts.filter(value => value.status === "fulfilled").length, 1);
  const record = (await db.doc("claims/" + f.key).get()).data();
  assert.equal(record.nickname, "Garden");
  assert.equal((await db.doc("claims/" + f.id).get()).exists, false);
  await f.api.register(f.device);
  assert.deepEqual((await db.doc("devices/" + f.id).get()).data().allowedUsers, [record.uid]);
});
test("a matching attacker-chosen proof and forged claim cannot enroll a USB-bound ID", async () => {
  const f = await fixture(), attackerSecret = randomBytes(32).toString("hex"), attackerCode = hash(attackerSecret);
  const request = {...f.request, auth: {...f.auth, uid: "attacker"}, data: {...f.request.data, pairingCode: attackerCode}};
  await assert.rejects(f.api.claim(request), {publicCode: "failed-precondition"});
  const fakeRef = db.doc("claims/" + hash(f.id + ":" + attackerCode));
  assert.equal((await fakeRef.get()).exists, false);
  await fakeRef.set({uid: "attacker", state: "pending", expiresAtMs: Date.now() + CLAIM_MS});
  await assert.rejects(f.api.register({device_id: f.id, device_secret: attackerSecret}), {publicCode: "failed-precondition"});
  assert.equal((await f.api.status(request)).state, "unknown");
  assert.equal(f.calls.length, 0);
  assert.equal((await db.doc("devices/" + f.id).get()).exists, false);
  await db.doc("devicePairingBindings/" + f.id).delete();
  await assert.rejects(f.api.claim(f.request), {publicCode: "failed-precondition"});
  await assert.rejects(f.api.register(f.device), {publicCode: "failed-precondition"});
});
test("simultaneous registration only provisions once, replay uses ciphertext, and controls wait for acknowledgment", async () => {
  const f = await fixture(); await f.api.claim(f.request);
  let entered, release;
  const enteredBroker = new Promise(resolve => { entered = resolve; });
  const brokerRelease = new Promise(resolve => { release = resolve; });
  f.hooks.provision = async () => { entered(); await brokerRelease; };
  const initial = f.api.register(f.device);
  await enteredBroker;
  const duplicates = await Promise.allSettled(Array.from({length: 4}, () => f.api.register(f.device)));
  assert.ok(duplicates.every(value => value.status === "rejected" && value.reason.publicCode === "unavailable"));
  release(); const first = await initial;
  assert.equal(f.calls.length, 1);
  assert.deepEqual(await f.api.register(f.device), first);
  const controller = createController({store: createStore(db), publish() { throw new Error("Never actuate hardware in enrollment tests"); }});
  assert.equal((await controller.listDevices(f.request)).devices.some(device => device.id === f.id), false);
  assert.equal((await f.api.status(f.request)).state, "provisioning");
  const record = (await db.doc("deviceEnrollments/" + f.id).get()).data();
  assert.equal(JSON.stringify(record).includes(first.password), false);
  assert.equal(JSON.stringify(record).includes(f.secret), false);
  await assert.rejects(f.api.register({...f.device, device_secret: f.pairingCode, action: "complete"}), {publicCode: "failed-precondition"});
  f.advance(CLAIM_MS + 1);
  await f.api.register({...f.device, action: "complete"});
  assert.equal((await f.api.status(f.request)).state, "registered");
  assert.ok((await controller.listDevices(f.request)).devices.some(device => device.id === f.id));
  assert.deepEqual(await f.api.register(f.device), first);
  assert.equal(f.calls.length, 1);
});
test("stale worker recovery fences finalization while reusing the broker identity", async () => {
  const f = await fixture(); await f.api.claim(f.request);
  let entered, release;
  const enteredBroker = new Promise(resolve => { entered = resolve; });
  const brokerRelease = new Promise(resolve => { release = resolve; });
  f.hooks.provision = async () => { entered(); await brokerRelease; };
  const stale = f.api.register(f.device);
  await enteredBroker;
  f.advance(PROVISIONING_LEASE_MS + 1);
  f.hooks.provision = undefined;
  const recovery = await f.api.register(f.device);
  release();
  await assert.rejects(stale, {publicCode: "unavailable"});
  assert.deepEqual(f.calls[0], f.calls[1]);
  assert.deepEqual(await f.api.register(f.device), recovery);
  await f.api.register({...f.device, action: "complete"});
  assert.equal((await db.doc("devices/" + f.id).get()).data().enabled, true);
});
test("uncertain broker result retries identical credentials and ownership cannot change after provisioning", async () => {
  const f = await fixture(); await f.api.claim(f.request);
  f.hooks.provision = async () => { throw new Error("uncertain transport result"); };
  await assert.rejects(f.api.register(f.device), {publicCode: "unavailable"});
  await assert.rejects(f.api.register({...f.device, action: "complete"}), {publicCode: "failed-precondition"});
  f.hooks.provision = undefined;
  await f.api.register(f.device);
  assert.deepEqual(f.calls[0], f.calls[1]);
  f.advance(CLAIM_MS + 1);
  await assert.rejects(f.api.claim({...f.request, auth: {...f.auth, uid: "other"}}), {publicCode: "failed-precondition"});
  await f.api.register({...f.device, action: "complete"});
  assert.deepEqual(await f.api.claim(f.request), {deviceId: f.id, state: "registered", owned: true});
  assert.equal((await f.api.status({...f.request, auth: {...f.auth, uid: "other"}})).state, "unknown");
});
test("Firestore clients cannot inspect or alter encrypted enrollment and claim records", async () => {
  const f = await fixture(); await f.api.claim(f.request); await f.api.register(f.device);
  const encode = data => Buffer.from(JSON.stringify(data)).toString("base64url");
  const token = encode({alg: "none", typ: "JWT"}) + "." + encode({aud: "demo-drawbridge", iss: "https://securetoken.google.com/demo-drawbridge", sub: f.uid, user_id: f.uid, iat: Math.floor(Date.now() / 1000), exp: Math.floor(Date.now() / 1000) + 3600, firebase: {sign_in_provider: "google.com"}}) + ".";
  for (const auth of [null, token]) {
    const headers = {"Content-Type": "application/json", ...(auth ? {Authorization: "Bearer " + auth} : {})};
    for (const path of ["claims/" + f.key, "deviceEnrollments/" + f.id, "devicePairingBindings/" + f.id, "devices/" + f.id, "adminAudit/" + f.id]) {
      const url = "http://" + process.env.FIRESTORE_EMULATOR_HOST + "/v1/projects/demo-drawbridge/databases/(default)/documents/" + path;
      assert.equal((await fetch(url, {headers})).status, 403);
      assert.equal((await fetch(url, {method: "PATCH", headers, body: JSON.stringify({fields: {state: {stringValue: "registered"}}})})).status, 403);
    }
  }
});

async function resetFixture() {
  const f = await fixture(); await f.api.claim(f.request);
  f.credentials = await f.api.register(f.device);
  await f.api.register({...f.device, action: "complete"});
  f.ref = db.doc("devices/" + f.id);
  await f.ref.update({allowedUsers: [f.uid, "shared-owner"], holdCount: 19, firmwareTarget: {version: "1.0.4", sequence: 9, enabled: true}, reportedFirmware: {version: "1.0.4", base_version: "1.0.13"}});
  f.maintenance = {...f.device, action: "maintenance", app_version: "1.0.4", base_version: "1.0.13"};
  await f.api.register(f.maintenance);
  const email = randomUUID() + "@example.test";
  await db.doc("admins/" + hash(email)).set({email});
  f.admin = createAdministration(db, () => f.time);
  f.adminAuth = {uid: randomUUID(), token: {email, email_verified: true, firebase: {sign_in_provider: "google.com"}}};
  f.adminRequest = () => ({auth: f.adminAuth, data: {action: "restartSetup", deviceId: f.id, issuedAtMs: f.time, requestId: randomUUID()}});
  return f;
}
test("restart setup preserves identity through lost acknowledgments, fresh shared-owner QR claim, and generation fencing", async () => {
  const f = await resetFixture(), before = (await f.ref.get()).data(), envelope = (await db.doc("deviceEnrollments/" + f.id).get()).data().envelope;
  const request = f.adminRequest();
  await Promise.all([f.admin.change(request), f.admin.change(request)]);
  const reset = (await f.ref.get()).data().setupReset;
  assert.equal(reset.id, hash(f.adminAuth.uid + ":" + request.data.requestId));
  assert.equal((await f.ref.get()).data().enabled, false);
  assert.deepEqual(await f.api.register(f.maintenance), {deviceId: f.id, restartSetup: {id: reset.id, state: "pending"}});
  assert.equal((await f.api.claim(f.request)).state, "pending");
  assert.notEqual((await f.api.status(f.request)).state, "registered");
  await assert.rejects(f.api.register(f.device), {publicCode: "failed-precondition"});
  const device = {...f.device, setup_reset_id: reset.id};
  const acknowledge = {...device, action: "restart_setup_complete"};
  const acknowledgment = {deviceId: f.id, state: "awaiting_setup", setup_reset_id: reset.id};
  assert.deepEqual(await f.api.register(acknowledge), acknowledgment);
  assert.deepEqual(await f.api.register(acknowledge), acknowledgment);
  assert.equal((await db.doc("claims/" + f.key).get()).data().state, "expired");
  await assert.rejects(f.api.register(device), {publicCode: "failed-precondition"});
  const stranger = {...f.request, auth: {...f.auth, uid: "stranger"}};
  await assert.rejects(f.api.claim(stranger), {publicCode: "failed-precondition"});
  assert.equal((await f.api.status(stranger)).state, "unknown");
  const sharedOwner = {...f.request, auth: {...f.auth, uid: "shared-owner"}, data: {...f.request.data, nickname: "Must preserve old name"}};
  assert.equal((await f.api.claim(sharedOwner)).state, "pending");
  f.advance(CLAIM_MS + 1);
  await assert.rejects(f.api.register(device), {publicCode: "failed-precondition"});
  await f.api.claim(sharedOwner);
  assert.deepEqual(await f.api.register(device), f.credentials);
  assert.deepEqual(await f.api.register(device), f.credentials);
  assert.equal((await f.api.status(sharedOwner)).state, "provisioning");
  await assert.rejects(f.api.register({...f.device, action: "complete"}), {publicCode: "failed-precondition"});
  await assert.rejects(f.api.register(acknowledge), {publicCode: "failed-precondition"});
  await f.api.register({...device, action: "complete"});
  assert.deepEqual(await f.api.register({...device, action: "complete"}), {deviceId: f.id, state: "registered"});
  const finished = (await f.ref.get()).data();
  assert.equal(finished.enabled, true); assert.equal(finished.setupReset.state, "complete");
  for (const key of ["allowedUsers", "holdCount", "name", "firmwareTarget", "reportedFirmware", "mqttUsername", "commandTopic", "statusTopic"]) assert.deepEqual(finished[key], before[key]);
  assert.deepEqual((await db.doc("deviceEnrollments/" + f.id).get()).data().envelope, envelope);
  assert.equal(f.calls.length, 1);
  await f.ref.update({enabled: false});
  await f.api.register({...device, action: "complete"});
  assert.equal((await f.ref.get()).data().enabled, false);
  // Retrying the original admin mutation does not queue a second reset or reenable.
  await f.admin.change({...request, data: {...request.data, issuedAtMs: f.time}});
  assert.equal((await f.ref.get()).data().setupReset.state, "complete");
  await f.ref.update({enabled: true});
  await f.admin.change(f.adminRequest());
  await assert.rejects(f.api.register({...device, action: "complete"}), {publicCode: "failed-precondition"});
  await assert.rejects(f.api.register(acknowledge), {publicCode: "failed-precondition"});
  const overview = (await f.admin.overview({auth: f.adminAuth})).devices.find(value => value.id === f.id);
  assert.equal(overview.setupReset.state, "pending");
  assert.equal(JSON.stringify(overview).includes("ciphertext"), false);
  assert.equal(JSON.stringify(overview).includes(reset.id), false);
  assert.equal(Object.hasOwn(overview.setupReset, "actor"), false);
});
test("hold/reset transactions cannot both succeed, and new gate commands are blocked by queued reset", async () => {
  const f = await resetFixture(), publishes = [];
  const controller = createController({store: createStore(db), now: () => f.time, publish: async (...args) => { publishes.push(args); }});
  const hold = {auth: f.auth, data: {deviceId: f.id, durationSeconds: 60, requestId: randomUUID(), issuedAtMs: f.time}};
  const results = await Promise.allSettled([controller.holdGate(hold), f.admin.change(f.adminRequest())]);
  assert.equal(results.filter(value => value.status === "fulfilled").length, 1);
  const device = (await f.ref.get()).data();
  if (device.setupReset) {
    assert.equal(publishes.length, 0);
    await assert.rejects(controller.holdGate({...hold, data: {...hold.data, requestId: randomUUID()}}), {publicCode: "permission-denied"});
  } else {
    assert.equal(publishes.length, 1);
    assert.ok(device.activeHold);
    await assert.rejects(f.admin.change(f.adminRequest()), {publicCode: "failed-precondition"});
  }
});
test("overlapping commands cannot hide an earlier pending publish from restart setup", async () => {
  const f = await resetFixture(); let entered, release;
  const publishing = new Promise(resolve => { entered = resolve; }), finish = new Promise(resolve => { release = resolve; });
  let publishes = 0;
  const controller = createController({store: createStore(db), now: () => f.time, publish: async () => { publishes++; if (publishes > 1) return; entered(); await finish; throw new Error("uncertain local test transport"); }});
  const hold = {auth: f.auth, data: {deviceId: f.id, durationSeconds: 60, requestId: randomUUID(), issuedAtMs: f.time}};
  const command = controller.holdGate(hold); await publishing;
  let result;
  try {
    // A slower broker publish may still be pending after the per-device cooldown.
    // B must not replace its pointer and then clear it while A remains in flight.
    f.advance(4000);
    assert.equal((await controller.holdGate(hold)).status, "pending");
    await assert.rejects(controller.holdGate({...hold, data: {...hold.data, requestId: randomUUID(), issuedAtMs: f.time}}), {publicCode: "resource-exhausted"});
    assert.equal(publishes, 1);
    await assert.rejects(f.admin.change(f.adminRequest()), {publicCode: "failed-precondition"});
  } finally { release(); result = await command; }
  assert.equal(result.status, "unknown");
  const auditRef = db.doc("commands/" + result.commandId), audit = (await auditRef.get()).data();
  await f.admin.change(f.adminRequest());
  assert.deepEqual((await auditRef.get()).data(), audit);
  await assert.rejects(controller.holdGate(hold), {publicCode: "permission-denied"});
  assert.equal(publishes, 1);
});
