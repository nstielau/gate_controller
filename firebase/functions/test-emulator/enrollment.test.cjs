const {test, after} = require("node:test");
const assert = require("node:assert/strict");
const {createHash, randomBytes, randomUUID} = require("node:crypto");
const {initializeApp, deleteApp} = require("firebase-admin/app");
const {getFirestore} = require("firebase-admin/firestore");
const {createEnrollment, CLAIM_MS, PROVISIONING_LEASE_MS} = require("../enrollment.cjs");
const {createController} = require("../controller.cjs");
const {createStore} = require("../store.cjs");
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
  return {id, secret, pairingCode, uid, auth, calls, hooks, api, request,
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
    for (const path of ["claims/" + f.key, "deviceEnrollments/" + f.id, "devicePairingBindings/" + f.id]) {
      const url = "http://" + process.env.FIRESTORE_EMULATOR_HOST + "/v1/projects/demo-drawbridge/databases/(default)/documents/" + path;
      assert.equal((await fetch(url, {headers})).status, 403);
      assert.equal((await fetch(url, {method: "PATCH", headers, body: JSON.stringify({fields: {state: {stringValue: "registered"}}})})).status, 403);
    }
  }
});
