const {test, after} = require("node:test");
const assert = require("node:assert/strict");
const {randomUUID} = require("node:crypto");
const {initializeApp, deleteApp} = require("firebase-admin/app");
const {getFirestore} = require("firebase-admin/firestore");
const {createStore} = require("../store.cjs");
const {createController} = require("../controller.cjs");
if (!/^127\.0\.0\.1:\d+$/.test(process.env.FIRESTORE_EMULATOR_HOST || "")) throw new Error("Local emulator required; never test against production");
const app = initializeApp({projectId: "demo-drawbridge"});
const db = getFirestore(app), store = createStore(db);
after(async () => { await db.terminate(); await deleteApp(app); });
async function fixture() {
  const id = "test-" + randomUUID(), now = Date.now();
  const device = {enabled: true, allowedUsers: ["operator"], commandTopic: "gate/v1/devices/" + id + "/command"};
  await db.doc("devices/" + id).set(device);
  const request = {auth: {uid: "operator", token: {email_verified: true, firebase: {sign_in_provider: "google.com"}}}, data: {deviceId: id, durationSeconds: 60, requestId: randomUUID(), issuedAtMs: now}};
  const publishes = [];
  const controller = createController({store, now: () => now, publish: async (...args) => { publishes.push(args); }});
  return {id, now, device, request, publishes, controller};
}
test("concurrent duplicate requests publish once and persist the audit", async () => {
  const f = await fixture();
  const results = await Promise.all(Array.from({length: 6}, () => f.controller.holdGate(f.request)));
  assert.equal(f.publishes.length, 1);
  assert.equal(new Set(results.map(r => r.commandId)).size, 1);
  const doc = (await db.doc("commands/" + results[0].commandId).get()).data();
  assert.equal(doc.status, "accepted"); assert.equal(doc.uid, "operator");
  assert.equal(doc.durationSeconds, 60);
  assert.equal((await db.doc("devices/" + f.id).get()).data().holdCount, 1);
  assert.deepEqual((await db.doc("devices/" + f.id).get()).data().activeHold, {startedAtMs: f.now, durationSeconds: 60});
  assert.equal((await f.controller.holdGate(f.request)).status, "accepted");
  assert.equal(f.publishes.length, 1);
});
test("ACL revocation, disabled/missing gates, and topic tampering block all publishing", async () => {
  for (const changes of [{allowedUsers: []}, {enabled: false}, {commandTopic: "gate/v1/devices/other/command"}, null]) {
    const f = await fixture();
    if (changes) await db.doc("devices/" + f.id).update(changes);
    else await db.doc("devices/" + f.id).delete();
    await assert.rejects(f.controller.holdGate(f.request), {publicCode: "permission-denied"});
    assert.equal(f.publishes.length, 0);
  }
});
test("changed duplicate payload and rapid distinct requests are rejected", async () => {
  const f = await fixture();
  await f.controller.holdGate(f.request);
  await assert.rejects(f.controller.holdGate({...f.request, data: {...f.request.data, durationSeconds: 900}}), {publicCode: "invalid-argument"});
  await assert.rejects(f.controller.holdGate({...f.request, data: {...f.request.data, requestId: randomUUID()}}), {publicCode: "resource-exhausted"});
  assert.equal(f.publishes.length, 1);
});
test("concurrent distinct requests apply the device rate limit atomically", async () => {
  const f = await fixture();
  const result = await Promise.allSettled(Array.from({length: 5}, () => f.controller.holdGate({...f.request, data: {...f.request.data, requestId: randomUUID()}})));
  assert.equal(result.filter(r => r.status === "fulfilled").length, 1);
  assert.equal(f.publishes.length, 1);
});
test("uncertain publish is persisted and never retried", async () => {
  const f = await fixture(); let count = 0;
  const controller = createController({store, now: () => f.now, publish: async () => { count++; throw new Error("lost connection"); }});
  assert.equal((await controller.holdGate(f.request)).status, "unknown");
  assert.equal((await controller.holdGate(f.request)).status, "unknown");
  assert.equal(count, 1);
});
test("multiple command cycles work after the cooldown", async () => {
  const f = await fixture(); let now = f.now;
  const controller = createController({store, now: () => now, publish: async (...args) => f.publishes.push(args)});
  for (const durationSeconds of [60, 900, 3600, 21600, 0]) {
    assert.equal((await controller.holdGate({...f.request, data: {...f.request.data, requestId: randomUUID(), durationSeconds, issuedAtMs: now}})).status, "accepted");
    now += 4000;
  }
  assert.deepEqual(f.publishes.map(p => p[1].duration_seconds), [60, 900, 3600, 21600, 0]);
  assert.equal((await db.doc("devices/" + f.id).get()).data().activeHold, null);
  assert.equal((await db.doc("devices/" + f.id).get()).data().holdCount, 4);
});
test("expected hold survives a device refresh and an uncertain command clears it", async () => {
  const f = await fixture();
  const accepted = await f.controller.holdGate(f.request);
  assert.deepEqual(accepted.hold, {startedAtMs: f.now, durationSeconds: 60});
  assert.deepEqual((await f.controller.listDevices(f.request)).devices.find(d => d.id === f.id).hold, accepted.hold);
  const controller = createController({store, now: () => f.now + 4000, publish: async () => { throw new Error("lost"); }});
  const uncertain = await controller.holdGate({...f.request, data: {...f.request.data, requestId: randomUUID(), issuedAtMs: f.now + 4000}});
  assert.equal(uncertain.status, "unknown");
  assert.equal((await db.doc("devices/" + f.id).get()).data().activeHold, null);
});
test("Firestore rules deny direct client reads and writes, even when signed in", async () => {
  const f = await fixture();
  const encode = data => Buffer.from(JSON.stringify(data)).toString("base64url");
  const token = encode({alg: "none", typ: "JWT"}) + "." + encode({aud: "demo-drawbridge", iss: "https://securetoken.google.com/demo-drawbridge", sub: "operator", user_id: "operator", iat: Math.floor(Date.now() / 1000), exp: Math.floor(Date.now() / 1000) + 3600, firebase: {sign_in_provider: "google.com"}}) + ".";
  for (const auth of [null, token]) {
    const headers = {"Content-Type": "application/json", ...(auth ? {Authorization: "Bearer " + auth} : {})};
    for (const collection of ["devices", "commands", "users", "admins", "adminAudit", "firmwareReleases"]) {
      const url = "http://" + process.env.FIRESTORE_EMULATOR_HOST + "/v1/projects/demo-drawbridge/databases/(default)/documents/" + collection + "/" + f.id;
      assert.equal((await fetch(url, {headers})).status, 403);
      assert.equal((await fetch(url, {method: "PATCH", headers, body: JSON.stringify({fields: {enabled: {booleanValue: true}}})})).status, 403);
    }
  }
});
test("nickname persists for assigned users without changing gate configuration or publishing", async () => {
  const f = await fixture();
  await f.controller.renameGate({...f.request, data: {deviceId: f.id, nickname: "  Driveway  "}});
  assert.deepEqual((await db.doc("devices/" + f.id).get()).data(), {...f.device, name: "Driveway"});
  assert.equal((await f.controller.listDevices(f.request)).devices.find(d => d.id === f.id).name, "Driveway");
  assert.equal(f.publishes.length, 0);
  for (const changes of [{allowedUsers: []}, {enabled: false}, {commandTopic: "other"}]) {
    await db.doc("devices/" + f.id).set({...f.device, name: "Driveway", ...changes});
    await assert.rejects(f.controller.renameGate({...f.request, data: {deviceId: f.id, nickname: "Not allowed"}}), {publicCode: "permission-denied"});
    assert.equal((await db.doc("devices/" + f.id).get()).data().name, "Driveway");
  }
  await db.doc("devices/" + f.id).delete();
  await assert.rejects(f.controller.renameGate({...f.request, data: {deviceId: f.id, nickname: "Missing"}}), {publicCode: "permission-denied"});
});
