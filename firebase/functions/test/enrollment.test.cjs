const {test} = require("node:test");
const assert = require("node:assert/strict");
const {createHash, randomBytes} = require("node:crypto");
const {createEnrollment, createRegistrationHandler, CLAIM_MS, PROVISIONING_LEASE_MS} = require("../enrollment.cjs");
const start = 1800000000000;
const auth = {uid: "owner", token: {email_verified: true, firebase: {sign_in_provider: "google.com"}}};
const digest = value => createHash("sha256").update(value).digest("hex");
const privateSecret = () => randomBytes(32).toString("hex");
function memoryDb(initial = {}) {
  const records = new Map(Object.entries(initial));
  const tx = {
    async get(target) { const value = records.get(target.path); return {exists: value !== undefined, data: () => structuredClone(value)}; },
    async getAll(...targets) { return Promise.all(targets.map(target => this.get(target))); },
    set(target, data) { records.set(target.path, structuredClone(data)); },
    update(target, data) { if (!records.has(target.path)) throw new Error("missing"); records.set(target.path, {...records.get(target.path), ...structuredClone(data)}); },
  };
  return {doc: path => ({path}), async runTransaction(fn) { return fn(tx); }, get: path => records.get(path), records};
}
function fixture() {
  const db = memoryDb(), secret = privateSecret(), code = digest(secret), id = "ab12cd", calls = [], hooks = {};
  db.records.set("devicePairingBindings/" + id, {pairingCode: code});
  let time = start;
  const broker = {async provision(value) { calls.push(value); if (hooks.provision) await hooks.provision(value); }, async remove() { throw new Error("Identity must never be deleted during retries"); }};
  const api = createEnrollment({db, broker, now: () => time});
  const request = {auth, data: {deviceId: id, pairingCode: code, nickname: "  Garden gate  "}};
  return {db, secret, code, id, calls, hooks, api, request, device: {device_id: id, device_secret: secret}, key: digest(id + ":" + code), advance(ms) { time += ms; }};
}

test("claims require verified Google identity, pairing code and a valid optional nickname", async () => {
  const f = fixture();
  await assert.rejects(f.api.claim({...f.request, auth: undefined}), {publicCode: "unauthenticated"});
  for (const token of [{email_verified: false, firebase: {sign_in_provider: "google.com"}}, {email_verified: true, firebase: {sign_in_provider: "password"}}]) {
    await assert.rejects(f.api.claim({...f.request, auth: {...auth, token}}), {publicCode: "permission-denied"});
  }
  for (const data of [{deviceId: f.id}, {...f.request.data, pairingCode: "bad"}, {...f.request.data, nickname: " "}, {...f.request.data, nickname: "x".repeat(81)}, {...f.request.data, nickname: "a\nb"}]) {
    await assert.rejects(f.api.claim({...f.request, data}), {publicCode: "invalid-argument"});
  }
  const result = await f.api.claim({...f.request, data: {...f.request.data, deviceId: " AB12CD "}});
  assert.deepEqual(result, {deviceId: f.id, state: "pending", expiresAtMs: start + CLAIM_MS});
  assert.equal(f.db.get("claims/" + f.key).nickname, "Garden gate");
  assert.equal(f.db.get("claims/" + f.id), undefined);
});

test("unrelated fake QR codes cannot reserve the real device's claim", async () => {
  const f = fixture();
  await assert.rejects(f.api.claim({...f.request, auth: {...auth, uid: "attacker"}, data: {...f.request.data, pairingCode: digest("fake")}}), {publicCode: "failed-precondition"});
  await f.api.claim(f.request);
  await assert.rejects(f.api.register({device_id: f.id}), {publicCode: "invalid-argument"});
  await assert.rejects(f.api.register({device_id: f.id, device_secret: f.code}), {publicCode: "failed-precondition"});
  assert.equal(f.calls.length, 0);
  const result = await f.api.register(f.device);
  assert.equal(result.deviceId, f.id);
  assert.deepEqual(f.db.get("devices/" + f.id).allowedUsers, [auth.uid]);
});

test("attacker-chosen secrets and matching forged claims cannot bypass the trusted USB binding", async () => {
  const f = fixture(), attackerSecret = privateSecret(), attackerCode = digest(attackerSecret);
  const request = {...f.request, auth: {...auth, uid: "attacker"}, data: {...f.request.data, pairingCode: attackerCode}};
  await assert.rejects(f.api.claim(request), {publicCode: "failed-precondition"});
  const fakeKey = digest(f.id + ":" + attackerCode);
  assert.equal(f.db.get("claims/" + fakeKey), undefined);
  // Even a legacy fake pending claim predating trusted binding enforcement cannot enroll.
  f.db.records.set("claims/" + fakeKey, {uid: "attacker", state: "pending", expiresAtMs: start + CLAIM_MS});
  await assert.rejects(f.api.register({device_id: f.id, device_secret: attackerSecret}), {publicCode: "failed-precondition"});
  assert.equal((await f.api.status(request)).state, "unknown");
  assert.equal(f.calls.length, 0);
  assert.equal(f.db.get("devices/" + f.id), undefined);
  f.db.records.delete("devicePairingBindings/" + f.id);
  await assert.rejects(f.api.claim(f.request), {publicCode: "failed-precondition"});
  await assert.rejects(f.api.register(f.device), {publicCode: "failed-precondition"});
  assert.equal(f.db.get("devicePairingBindings/" + f.id), undefined);
});

test("provisioned credentials replay privately without rotation and require device acknowledgment", async () => {
  const f = fixture();
  await f.api.claim(f.request);
  const first = await f.api.register(f.device);
  assert.equal(first.username, "gate-" + f.id);
  assert.equal(first.commandTopic, `gate/v1/devices/${f.id}/command`);
  assert.equal(first.statusTopic, `gate/v1/devices/${f.id}/status`);
  assert.equal(f.db.get("devices/" + f.id).name, "Garden gate");
  assert.equal(f.db.get("devices/" + f.id).enabled, false);
  const serialized = JSON.stringify([...f.db.records]);
  assert.equal(serialized.includes(first.password), false);
  assert.equal(serialized.includes(f.secret), false);
  assert.equal((await f.api.status(f.request)).state, "provisioning");
  assert.deepEqual(await f.api.register(f.device), first);
  assert.equal(f.calls.length, 1);
  await assert.rejects(f.api.register({...f.device, device_secret: f.code, action: "complete"}), {publicCode: "failed-precondition"});
  assert.equal((await f.api.status(f.request)).state, "provisioning");
  assert.deepEqual(await f.api.register({...f.device, action: "complete"}), {deviceId: f.id, state: "registered"});
  assert.equal(f.db.get("devices/" + f.id).enabled, true);
  assert.equal((await f.api.status(f.request)).state, "registered");
  assert.deepEqual(await f.api.register({...f.device, action: "complete"}), {deviceId: f.id, state: "registered"});
  assert.deepEqual(await f.api.register(f.device), first);
  assert.equal(f.calls.length, 1);
  for (const result of [await f.api.claim(f.request), await f.api.status(f.request)]) {
    assert.equal(JSON.stringify(result).includes(first.password), false);
    assert.equal(Object.hasOwn(result, "username"), false);
  }
});

test("binding changes block both broker finalization and later acknowledgment", async () => {
  const f = fixture(); await f.api.claim(f.request);
  f.hooks.provision = async () => { f.db.records.set("devicePairingBindings/" + f.id, {pairingCode: digest("replaced")}); };
  await assert.rejects(f.api.register(f.device), {publicCode: "unavailable"});
  assert.equal(f.db.get("devices/" + f.id), undefined);
  await assert.rejects(f.api.register(f.device), {publicCode: "failed-precondition"});
  f.db.records.set("devicePairingBindings/" + f.id, {pairingCode: f.code});
  f.hooks.provision = undefined;
  await f.api.register(f.device);
  f.db.records.delete("devicePairingBindings/" + f.id);
  await assert.rejects(f.api.register({...f.device, action: "complete"}), {publicCode: "failed-precondition"});
  assert.equal(f.db.get("devices/" + f.id).enabled, false);
  f.db.records.set("devicePairingBindings/" + f.id, {pairingCode: f.code});
  await f.api.register({...f.device, action: "complete"});
  assert.equal(f.db.get("devices/" + f.id).enabled, true);
  assert.deepEqual(f.calls[0], f.calls[1]);
});

test("claim expiry and ownership never allow takeover of provisioned or existing devices", async () => {
  const f = fixture();
  await f.api.claim(f.request);
  await assert.rejects(f.api.claim({...f.request, auth: {...auth, uid: "other"}}), {publicCode: "failed-precondition"});
  f.advance(CLAIM_MS + 1);
  assert.equal((await f.api.status(f.request)).state, "expired");
  await assert.rejects(f.api.register(f.device), {publicCode: "failed-precondition"});
  assert.equal(f.calls.length, 0);
  await f.api.claim(f.request);
  await f.api.register(f.device);
  f.advance(CLAIM_MS + 1);
  await assert.rejects(f.api.claim({...f.request, auth: {...auth, uid: "other"}}), {publicCode: "failed-precondition"});
  await f.api.register({...f.device, action: "complete"});
  assert.deepEqual(await f.api.claim(f.request), {deviceId: f.id, state: "registered", owned: true});
  assert.equal((await f.api.status({...f.request, auth: {...auth, uid: "other"}})).state, "unknown");
  const old = fixture();
  old.db.records.delete("devicePairingBindings/" + old.id);
  old.db.records.set("devices/" + old.id, {enabled: true, allowedUsers: [auth.uid], commandTopic: `gate/v1/devices/${old.id}/command`});
  assert.deepEqual(await old.api.claim(old.request), {deviceId: old.id, state: "registered", owned: true});
  assert.equal(old.db.get("devices/" + old.id).name, undefined);
  await assert.rejects(old.api.register(old.device), {publicCode: "failed-precondition"});
});

test("broker failure and stale reservations retry identical credentials without deletion", async () => {
  const f = fixture();
  await f.api.claim(f.request);
  f.hooks.provision = async () => { throw new Error("private broker detail"); };
  await assert.rejects(f.api.register(f.device), {publicCode: "unavailable"});
  await assert.rejects(f.api.register({...f.device, action: "complete"}), {publicCode: "failed-precondition"});
  f.hooks.provision = undefined;
  const result = await f.api.register(f.device);
  assert.deepEqual(f.calls[0], f.calls[1]);
  assert.equal(result.password, f.calls[0].password);
  const g = fixture();
  await g.api.claim(g.request);
  let release, entered;
  const inBroker = new Promise(resolve => { entered = resolve; });
  const blocked = new Promise(resolve => { release = resolve; });
  g.hooks.provision = async () => { entered(); await blocked; };
  const first = g.api.register(g.device);
  await inBroker;
  await assert.rejects(g.api.register(g.device), {publicCode: "unavailable"});
  g.advance(PROVISIONING_LEASE_MS + 1);
  g.hooks.provision = undefined;
  const recovered = await g.api.register(g.device);
  release();
  await assert.rejects(first, {publicCode: "unavailable"});
  assert.deepEqual(g.calls[0], g.calls[1]);
  assert.deepEqual(await g.api.register(g.device), recovered);
  assert.equal(g.db.get("devices/" + g.id).enabled, false);
});

test("a lost database finalization retries the already-provisioned broker credentials", async () => {
  const f = fixture(); await f.api.claim(f.request);
  const transaction = f.db.runTransaction.bind(f.db);
  let loseFinalization = false;
  f.hooks.provision = async () => { loseFinalization = true; };
  f.db.runTransaction = async callback => {
    if (loseFinalization) { loseFinalization = false; throw new Error("database unavailable after broker acceptance"); }
    return transaction(callback);
  };
  await assert.rejects(f.api.register(f.device), {publicCode: "unavailable"});
  assert.equal(f.db.get("devices/" + f.id), undefined);
  f.hooks.provision = undefined;
  const recovered = await f.api.register(f.device);
  assert.equal(recovered.password, f.calls[0].password);
  assert.deepEqual(f.calls[0], f.calls[1]);
  assert.equal(f.db.get("devices/" + f.id).enabled, false);
});

test("ciphertext alteration and wrong device proofs never recover credentials", async () => {
  const f = fixture(); await f.api.claim(f.request); await f.api.register(f.device);
  const record = f.db.get("deviceEnrollments/" + f.id);
  record.envelope.ciphertext = Buffer.from("tampered").toString("base64");
  await assert.rejects(f.api.register(f.device), {publicCode: "unavailable"});
  await assert.rejects(f.api.register({...f.device, device_secret: privateSecret()}), {publicCode: "failed-precondition"});
  await assert.rejects(f.api.register({...f.device, action: "erase"}), {publicCode: "invalid-argument"});
  assert.equal(f.calls.length, 1);
});

test("HTTP handler forwards private proof and acknowledgment, uses no-store and generic errors", async () => {
  const f = fixture(); await f.api.claim(f.request);
  const handler = createRegistrationHandler(f.api);
  const response = {headers: {}, set(key, value) { this.headers[key] = value; }, status(value) { this.code = value; return this; }, json(value) { this.body = value; return this; }, send(value) { this.body = value; return this; }};
  await handler({method: "POST", body: {device_id: f.id}}, response);
  assert.equal(response.code, 400);
  assert.deepEqual(response.body, {error: "registration_unavailable"});
  assert.equal(response.headers["Cache-Control"], "no-store");
  await handler({method: "POST", body: f.device}, response);
  assert.equal(response.code, 200); assert.equal(response.body.username, "gate-" + f.id);
  await handler({method: "POST", body: {...f.device, action: "complete"}}, response);
  assert.deepEqual(response.body, {deviceId: f.id, state: "registered"});
  await handler({method: "GET"}, response); assert.equal(response.code, 405);
  await handler({method: "OPTIONS"}, response); assert.equal(response.code, 204);
});
