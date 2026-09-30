const {test} = require("node:test");
const assert = require("node:assert/strict");
const {createEnrollment} = require("../enrollment.cjs");
const time = 1800000000000;
const auth = {uid: "owner", token: {email_verified: true, firebase: {sign_in_provider: "google.com"}}};

function memoryDb(initial = {}) {
  const records = new Map(Object.entries(initial));
  const ref = path => ({path});
  const read = path => records.get(path);
  const tx = {
    async get(target) { const value = read(target.path); return {exists: value !== undefined, data: () => value}; },
    async getAll(...targets) { return Promise.all(targets.map(target => this.get(target))); },
    create(target, data) { if (read(target.path) !== undefined) throw new Error("exists"); records.set(target.path, structuredClone(data)); },
    set(target, data) { records.set(target.path, structuredClone(data)); },
    update(target, data) { const current = read(target.path); if (current === undefined) throw new Error("missing"); records.set(target.path, {...current, ...structuredClone(data)}); },
  };
  return {doc: ref, async runTransaction(fn) { return fn(tx); }, get(path) { return read(path); }};
}

function service(options = {}) {
  return createEnrollment({db: memoryDb(options.records), broker: options.broker || {provision: async () => {}}, now: () => time, randomBytes: () => Buffer.from("abc123", "hex")});
}

test("claim requires verified Google auth and reserves an unregistered normalized device ID", async () => {
  const api = service();
  await assert.rejects(api.claim({data: {deviceId: "AB12CD"}}), {publicCode: "unauthenticated"});
  const result = await api.claim({auth, data: {deviceId: "AB12CD"}});
  assert.equal(result.deviceId, "ab12cd");
  assert.equal(result.state, "pending");
  assert.equal(result.expiresAtMs, time + 2 * 60 * 60 * 1000);
});

test("claim rejects registered and active claims for another owner", async () => {
  const api = service({records: {
    "devices/ab12cd": {enabled: true},
    "claims/ef34aa": {uid: "other", state: "pending", expiresAtMs: time + 10},
  }});
  await assert.rejects(api.claim({auth, data: {deviceId: "ab12cd"}}), {publicCode: "failed-precondition"});
  await assert.rejects(api.claim({auth, data: {deviceId: "ef34aa"}}), {publicCode: "failed-precondition"});
});

test("registration creates the device once and returns per-device credentials", async () => {
  const calls = [];
  const api = service({broker: {provision: async value => calls.push(value)}});
  await api.claim({auth, data: {deviceId: "ab12cd"}});
  const result = await api.register({deviceId: "AB12CD"});
  assert.deepEqual(result, {deviceId: "ab12cd", username: "gate-ab12cd", password: "abc123", brokerHost: "jd3a6164.ala.us-east-1.emqxsl.com", brokerPort: 8883, commandTopic: "gate/v1/devices/ab12cd/command", statusTopic: "gate/v1/devices/ab12cd/status"}); // pragma: allowlist secret
  assert.deepEqual(calls[0], {username: "gate-ab12cd", password: "abc123", commandTopic: "gate/v1/devices/ab12cd/command", statusTopic: "gate/v1/devices/ab12cd/status"}); // pragma: allowlist secret
});

test("registration rejects unknown, expired, and repeated claims without broker calls", async () => {
  const calls = [];
  const api = service({broker: {provision: async value => calls.push(value)}});
  for (const id of ["missing", "expired"]) {
    if (id === "expired") {
      const ownerApi = service({records: {"claims/expired": {uid: "owner", state: "pending", expiresAtMs: time - 1}}});
      await assert.rejects(ownerApi.register({deviceId: id}), {publicCode: "failed-precondition"});
    } else await assert.rejects(api.register({deviceId: id}), {publicCode: "failed-precondition"});
  }
  await api.claim({auth, data: {deviceId: "ab12cd"}});
  await api.register({deviceId: "ab12cd"});
  await assert.rejects(api.register({deviceId: "ab12cd"}), {publicCode: "failed-precondition"});
  assert.equal(calls.length, 1);
});

test("broker failure returns a retryable error and leaves the claim pending", async () => {
  const records = {};
  const db = memoryDb(records);
  const api = createEnrollment({db, now: () => time, randomBytes: () => Buffer.from("abc123", "hex"), broker: {provision: async () => { throw new Error("broker detail"); }}});
  await api.claim({auth, data: {deviceId: "ab12cd"}});
  await assert.rejects(api.register({deviceId: "ab12cd"}), {publicCode: "unavailable"});
  assert.equal(db.get("claims/ab12cd").state, "pending");
});

test("registration HTTP handler never caches or reveals lookup details", async () => {
  const {createRegistrationHandler} = require("../enrollment.cjs");
  const statuses = [];
  const service = {register: async ({deviceId}) => {
    if (deviceId === "ab12cd") return {deviceId, username: "gate-ab12cd", password: "one-time"}; // pragma: allowlist secret
    const error = new Error("private"); error.publicCode = "failed-precondition"; throw error;
  }};
  const handler = createRegistrationHandler(service);
  const response = {headers: {}, set(name, value) {this.headers[name] = value;}, status(code) {statuses.push(code); this.code = code; return this;}, json(value) {this.body = value; return this;}, send(value) {this.body = value; return this;}};
  await handler({method: "POST", body: {device_id: "missing"}}, response);
  assert.equal(response.headers["Cache-Control"], "no-store");
  assert.deepEqual(response.body, {error: "registration_unavailable"});
  await handler({method: "POST", body: {device_id: "ab12cd"}}, response);
  assert.deepEqual(response.body, {deviceId: "ab12cd", username: "gate-ab12cd", password: "one-time"}); // pragma: allowlist secret
  assert.deepEqual(statuses, [400, 200]);
});
