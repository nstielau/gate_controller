const {test, after} = require("node:test");
const assert = require("node:assert/strict");
const {randomUUID} = require("node:crypto");
const {initializeApp, deleteApp} = require("firebase-admin/app");
const {getFirestore} = require("firebase-admin/firestore");
const {createDeviceAccess} = require("../device-access.cjs");
const {createController} = require("../controller.cjs");
const {createStore} = require("../store.cjs");
const {hash} = require("../administration.cjs");
if (!/^127\.0\.0\.1:\d+$/.test(process.env.FIRESTORE_EMULATOR_HOST || "")) throw new Error("Local emulator required; never test against production");
const app = initializeApp({projectId: "demo-drawbridge"}, "device-access"), db = getFirestore(app);
after(async () => { await db.terminate(); await deleteApp(app); });
async function fixture() {
  const id = randomUUID(), time = Date.now(), uid = randomUUID();
  const ref = db.doc("devices/" + id);
  const device = {name: "Garden gate", enabled: true, allowedUsers: [uid, "existing-user"],
    commandTopic: `gate/v1/devices/${id}/command`, activeHold: {startedAtMs: time, durationSeconds: 60}, holdCount: 2};
  await ref.set(device);
  // Auth is a local fake; Firestore transactions use the actual local emulator.
  const users = new Map(), calls = [], hooks = {};
  const auth = {
    async getUserByEmail(email) {
      calls.push(["get", email]);
      if (hooks.lookup) await hooks.lookup();
      if (!users.has(email)) throw Object.assign(new Error("missing"), {code: "auth/user-not-found"});
      return users.get(email);
    },
    async createUser(properties) {
      calls.push(["create", properties]);
      if (hooks.create) await hooks.create(properties);
      if (users.has(properties.email)) throw Object.assign(new Error("duplicate"), {code: "auth/email-already-exists"});
      const user = {...properties, uid: randomUUID()}; users.set(properties.email, user); return user;
    }
  };
  const identity = {uid, token: {email_verified: true, firebase: {sign_in_provider: "google.com"}}};
  const request = {auth: identity, data: {deviceId: id, email: "Guest@Example.test", requestId: randomUUID(), issuedAtMs: time}};
  const api = createDeviceAccess({db, auth, now: () => time});
  return {id, uid, time, ref, device, users, calls, hooks, auth, identity, request, api};
}
test("an assigned non-admin can invite before first login; only the UID allowlist changes", async () => {
  const f = await fixture();
  assert.deepEqual(await f.api.invite(f.request), {ok: true, email: "guest@example.test", deviceId: f.id});
  const recipient = f.users.get("guest@example.test");
  assert.equal(recipient.emailVerified, false);
  assert.deepEqual((await f.ref.get()).data(), {...f.device, allowedUsers: [...f.device.allowedUsers, recipient.uid]});
  const audit = (await db.doc("deviceAccessAudit/" + hash(f.uid + ":" + f.request.data.requestId)).get()).data();
  assert.equal(audit.actor, f.uid); assert.equal(audit.recipientUid, recipient.uid);
  const controller = createController({store: createStore(db), publish() { throw new Error("must never publish"); }});
  const login = {auth: {...f.identity, uid: recipient.uid}};
  assert.ok((await controller.listDevices(login)).devices.some(d => d.id === f.id));
  await assert.rejects(controller.listDevices({auth: {...login.auth, token: {...login.auth.token, email_verified: false}}}), {publicCode: "permission-denied"});
  // Invitees get the same sharing rights; no separate admin role is needed.
  await f.api.invite({...f.request, auth: login.auth, data: {...f.request.data, email: "next@example.test", requestId: randomUUID()}});
  assert.ok((await f.ref.get()).data().allowedUsers.includes(f.users.get("next@example.test").uid));
});
test("concurrent invitations preserve all users, reuse existing accounts, and deduplicate replay", async () => {
  const f = await fixture();
  f.users.set("guest@example.test", {uid: "known-user", email: "guest@example.test"});
  const second = {...f.request, data: {...f.request.data, email: "second@example.test", requestId: randomUUID()}};
  await Promise.all([f.api.invite(f.request), f.api.invite(f.request), f.api.invite(second)]);
  assert.deepEqual(new Set((await f.ref.get()).data().allowedUsers), new Set([...f.device.allowedUsers, "known-user", f.users.get("second@example.test").uid]));
  assert.equal(f.calls.some(c => c[0] === "create" && c[1].email === "guest@example.test"), false);
  const calls = f.calls.length;
  await f.ref.update({allowedUsers: f.device.allowedUsers});
  await f.api.invite({...f.request, data: {...f.request.data, requestId: f.request.data.requestId.toUpperCase()}});
  assert.equal(f.calls.length, calls);
  assert.deepEqual((await f.ref.get()).data().allowedUsers, f.device.allowedUsers);
  await assert.rejects(f.api.invite({...f.request, data: {...f.request.data, email: "changed@example.test"}}), {publicCode: "invalid-argument"});
});
test("Auth account creation races recover without overwriting or verifying an account", async () => {
  const f = await fixture();
  f.hooks.create = async ({email}) => f.users.set(email, {uid: "created-concurrently", email});
  await f.api.invite(f.request);
  assert.ok((await f.ref.get()).data().allowedUsers.includes("created-concurrently"));
});
test("unassigned, revoked, disabled, missing and misrouted devices block Auth lookups and grants", async () => {
  for (const changes of [{allowedUsers: []}, {enabled: false}, {commandTopic: "other"}, null]) {
    const f = await fixture();
    if (changes) await f.ref.update(changes); else await f.ref.delete();
    await assert.rejects(f.api.invite(f.request), {publicCode: "permission-denied"});
    assert.equal(f.calls.length, 0);
  }
  const f = await fixture();
  await db.doc("admins/" + hash("admin@example.test")).set({email: "admin@example.test"});
  await assert.rejects(f.api.invite({...f.request, auth: {...f.identity, uid: "unassigned-admin", token: {...f.identity.token, email: "admin@example.test"}}}), {publicCode: "permission-denied"});
  assert.equal(f.calls.length, 0);
});
test("access changes during Auth lookup are rechecked transactionally before granting", async () => {
  for (const changes of [{allowedUsers: ["remaining-user"]}, {enabled: false}, {commandTopic: "other"}, null]) {
    const f = await fixture();
    f.users.set("guest@example.test", {uid: "guest", email: "guest@example.test"});
    f.hooks.lookup = async () => { if (changes) await f.ref.update(changes); else await f.ref.delete(); };
    await assert.rejects(f.api.invite(f.request), {publicCode: "permission-denied"});
    assert.equal((await f.ref.get()).data()?.allowedUsers.includes("guest") || false, false);
    assert.equal((await db.doc("deviceAccessAudit/" + hash(f.uid + ":" + f.request.data.requestId)).get()).exists, false);
  }
});
test("disabled recipients and Auth failures never change device access", async () => {
  const f = await fixture();
  f.users.set("guest@example.test", {uid: "guest", disabled: true});
  await assert.rejects(f.api.invite(f.request), {publicCode: "failed-precondition"});
  f.hooks.lookup = async () => { throw Object.assign(new Error("unavailable"), {code: "auth/internal-error"}); };
  await assert.rejects(f.api.invite(f.request), {code: "auth/internal-error"});
  assert.deepEqual((await f.ref.get()).data(), f.device);
});
