const {test, after, beforeEach} = require("node:test");
const assert = require("node:assert/strict");
const {randomUUID} = require("node:crypto");
const {initializeApp, deleteApp} = require("firebase-admin/app");
const {getFirestore} = require("firebase-admin/firestore");
const {hash} = require("../administration.cjs");
const {createStatistics} = require("../statistics.cjs");
if (!/^127\.0\.0\.1:\d+$/.test(process.env.FIRESTORE_EMULATOR_HOST || "")) throw new Error("Local emulator required; never test against production");
const app = initializeApp({projectId: "demo-drawbridge"}, "statistics");
// A separate local database isolates fleet-wide queries from concurrent suites.
const db = getFirestore(app, "statistics");
after(async () => { await db.terminate(); await deleteApp(app); });
beforeEach(async () => {
  await Promise.all([db.recursiveDelete(db.collection("devices")), db.recursiveDelete(db.collection("admins"))]);
});
async function fixture() {
  const email = randomUUID() + "@example.test", id = randomUUID();
  const adminRef = db.doc("admins/" + hash(email));
  await adminRef.set({email});
  const deviceRef = db.doc("devices/" + id);
  await deviceRef.set({name: "Garden gate", holdCount: 99, allowedUsers: ["private-uid"], commandTopic: "secret-topic", otaCredentialHash: "secret"});
  const users = new Map(), calls = [], hooks = {};
  // Identity service stays local; database reads are real emulator transactions.
  const auth = {async getUsers(ids) {
    calls.push(ids);
    if (hooks.lookup) await hooks.lookup();
    return {users: ids.filter(({uid}) => users.has(uid)).map(({uid}) => users.get(uid)), notFound: ids.filter(({uid}) => !users.has(uid))};
  }};
  const identity = {uid: "administrator", token: {email: email.toUpperCase(), email_verified: true, firebase: {sign_in_provider: "google.com"}}};
  const request = data => ({auth: identity, data});
  return {id, adminRef, deviceRef, users, calls, hooks, request, api: createStatistics({db, auth})};
}
test("summary allowlist, name sort, invalid counters and missing device behavior use real Firestore", async () => {
  const f = await fixture();
  await db.doc("devices/alpha").set({name: "Alpha", holdCount: -2, secret: "private"}); // pragma: allowlist secret -- Dummy DTO leak marker
  await db.doc("devices/zebra").set({name: "Zebra", holdCount: "wrong"});
  await db.doc("devices/missing-name").set({holdCount: Number.MAX_SAFE_INTEGER + 1});
  const before = (await f.deviceRef.get()).data();
  const result = await f.api.read(f.request({}));
  assert.deepEqual(result, {devices: [
    {id: "alpha", name: "Alpha", holdCount: 0}, {id: f.id, name: "Garden gate", holdCount: 99},
    {id: "missing-name", name: "missing-name", holdCount: 0}, {id: "zebra", name: "Zebra", holdCount: 0}
  ], truncated: false});
  assert.equal(f.calls.length, 0);
  assert.deepEqual((await f.deviceRef.get()).data(), before);
  await assert.rejects(f.api.read(f.request({deviceId: "not-present"})), {publicCode: "not-found"});
  assert.deepEqual(await f.api.read(f.request({deviceId: f.id})), {deviceId: f.id, people: [], truncated: false});
});
test("nonadmins cannot read fleet statistics or start Auth lookups, even with device access", async () => {
  const f = await fixture();
  await f.deviceRef.update({allowedUsers: [f.request({}).auth.uid]});
  await f.adminRef.delete();
  for (const data of [{}, {deviceId: f.id}]) await assert.rejects(f.api.read(f.request(data)), {publicCode: "permission-denied"});
  assert.equal(f.calls.length, 0);
});
test("people are sorted and resolve deleted users anonymously without writes or profile leakage", async () => {
  const f = await fixture(), collection = f.deviceRef.collection("usagePeople");
  const counters = [
    [hash("first-user"), {uid: "first-user", holdCount: 5, commandId: "secret"}],
    [hash("deleted-user"), {uid: "deleted-user", holdCount: 2}],
    [hash("invalid-count"), {uid: "invalid-count", holdCount: "invalid"}],
    [hash("forged"), {uid: "other-user", holdCount: 9}],
    [hash("no-uid"), {holdCount: 8}]
  ];
  for (const [id, counter] of counters) await collection.doc(id).set(counter);
  f.users.set("first-user", {uid: "first-user", displayName: "First Person", email: "first@example.test", disabled: false, providerData: [{private: "secret"}]});
  const before = (await collection.get()).docs.map(doc => [doc.id, doc.data()]);
  const deviceBefore = (await f.deviceRef.get()).data();
  assert.deepEqual(await f.api.read(f.request({deviceId: f.id})), {deviceId: f.id, people: [
    {id: hash("first-user"), name: "First Person", email: "first@example.test", holdCount: 5},
    {id: hash("deleted-user"), name: null, email: null, holdCount: 2},
    {id: hash("invalid-count"), name: null, email: null, holdCount: 0}
  ], truncated: false});
  assert.deepEqual((await collection.get()).docs.map(doc => [doc.id, doc.data()]), before);
  assert.deepEqual((await f.deviceRef.get()).data(), deviceBefore);
  assert.equal(f.calls.flat().some(({uid}) => uid === "other-user"), false);
  assert.deepEqual((await db.listCollections()).map(col => col.id).sort(), ["admins", "devices"]);
});
test("admin removal during Auth lookup is rechecked before identities are returned", async () => {
  const f = await fixture();
  await f.deviceRef.collection("usagePeople").doc(hash("person")).set({uid: "person", holdCount: 1});
  f.users.set("person", {uid: "person", displayName: "Private Name", email: "private@example.test"});
  f.hooks.lookup = async () => f.adminRef.delete();
  await assert.rejects(f.api.read(f.request({deviceId: f.id})), {publicCode: "permission-denied"});
  assert.equal(f.calls.length, 1);
});
test("actual fleet and people queries cap 200, mark truncation and batch identity lookup", async () => {
  const f = await fixture(), batch = db.batch();
  for (let n = 0; n < 202; n++) {
    const suffix = String(n).padStart(3, "0");
    batch.set(db.doc("devices/gate-" + suffix), {name: "Gate " + suffix, holdCount: n});
    batch.set(f.deviceRef.collection("usagePeople").doc(hash("person-" + suffix)), {uid: "person-" + suffix, holdCount: n});
  }
  await batch.commit();
  const fleet = await f.api.read(f.request({}));
  assert.equal(fleet.truncated, true); assert.equal(fleet.devices.length, 200);
  const result = await f.api.read(f.request({deviceId: f.id}));
  assert.equal(result.truncated, true); assert.equal(result.people.length, 200);
  assert.deepEqual(result.people.map(person => person.holdCount), Array.from({length: 200}, (_, n) => 201 - n));
  assert.deepEqual(f.calls.map(call => call.length), [100, 100]);
});
test("Auth failures leave counters intact and fail instead of claiming missing accounts", async () => {
  const f = await fixture(), counter = f.deviceRef.collection("usagePeople").doc(hash("person"));
  await counter.set({uid: "person", holdCount: 4});
  f.hooks.lookup = async () => { throw Object.assign(new Error("Auth down"), {code: "auth/internal-error"}); };
  await assert.rejects(f.api.read(f.request({deviceId: f.id})), {code: "auth/internal-error"});
  assert.deepEqual((await counter.get()).data(), {uid: "person", holdCount: 4});
});
