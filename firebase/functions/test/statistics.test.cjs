const {test} = require("node:test");
const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const {hash} = require("../administration.cjs");
const {createStatistics} = require("../statistics.cjs");
const identity = {uid: "admin-user", token: {email: "Admin@Example.test", email_verified: true, firebase: {sign_in_provider: "google.com"}}};
const adminPath = "admins/" + hash("admin@example.test");
function fixture() {
  const records = new Map([[adminPath, {email: "admin@example.test"}]]), reads = [], lookups = [], users = new Map(), hooks = {};
  let inTransaction = false;
  const snapshot = path => ({id: path.split("/").pop(), exists: records.has(path), data: () => records.get(path)});
  const db = {
    doc(path) { return {path}; },
    collection(path) {
      const query = {path, limit(size) { return {...this, size}; }, orderBy(field, direction) { return {...this, field, direction}; }};
      return query;
    },
    async runTransaction(callback) {
      inTransaction = true;
      try { return await callback({async get(ref) {
        reads.push(ref);
        if (ref.size === undefined) return snapshot(ref.path);
        let docs = [...records.keys()].filter(path => path.startsWith(ref.path + "/") && path.split("/").length === ref.path.split("/").length + 1).map(snapshot);
        if (ref.field) docs = docs.filter(doc => doc.data()[ref.field] !== undefined).sort((a, b) => (a.data()[ref.field] < b.data()[ref.field] ? 1 : -1));
        return {docs: docs.slice(0, ref.size)};
      }}); } finally { inTransaction = false; }
    }
  };
  const auth = {async getUsers(ids) {
    assert.equal(inTransaction, false, "Auth must stay outside retryable transactions");
    lookups.push(ids);
    if (hooks.lookup) await hooks.lookup();
    return {users: ids.filter(({uid}) => users.has(uid)).map(({uid}) => users.get(uid)), notFound: ids.filter(({uid}) => !users.has(uid))};
  }};
  const api = createStatistics({db, auth});
  const request = data => ({auth: identity, data});
  return {records, reads, lookups, users, hooks, db, api, request};
}
test("statistics exports its isolated read API", () => assert.equal(typeof createStatistics, "function"));
test("verified Google authentication and a valid email precede database access", async () => {
  const f = fixture();
  for (const auth of [undefined, {...identity, uid: ""}, {...identity, token: {...identity.token, email_verified: false}},
    {...identity, token: {...identity.token, firebase: {sign_in_provider: "password"}}}, {...identity, token: {...identity.token, email: "invalid"}}]) {
    await assert.rejects(f.api.read({auth, data: {}}), error => ["unauthenticated", "permission-denied", "invalid-argument"].includes(error.publicCode));
  }
  assert.equal(f.reads.length, 0); assert.equal(f.lookups.length, 0);
});
test("malformed payloads and device IDs never reach Firestore or Auth", async () => {
  const f = fixture();
  for (const data of [null, [], true, "all", 7, {extra: true}, {deviceId: "a", extra: true}, {deviceId: null}, {deviceId: 3},
    {deviceId: ["test"]}, {deviceId: ""}, {deviceId: "../other"}, {deviceId: "A"}, {deviceId: "a".repeat(65)}]) {
    await assert.rejects(f.api.read(f.request(data)), {publicCode: "invalid-argument"});
  }
  assert.equal(f.reads.length, 0); assert.equal(f.lookups.length, 0);
});
test("admin role is read before statistics; gate access grants no administrator role", async () => {
  const f = fixture(); f.records.delete(adminPath);
  f.records.set("devices/garden", {allowedUsers: [identity.uid], holdCount: 1});
  for (const data of [{}, {deviceId: "garden"}]) await assert.rejects(f.api.read(f.request(data)), {publicCode: "permission-denied"});
  assert.deepEqual(f.reads.map(ref => ref.path), [adminPath, adminPath]); assert.equal(f.lookups.length, 0);
});
test("summary DTOs sort device names, normalize invalid counts, and expose only public fields", async () => {
  const f = fixture();
  f.records.set("devices/z", {name: "Apple", holdCount: 10, allowedUsers: ["secret"], credentials: "secret"}); // pragma: allowlist secret -- Dummy DTO leak marker
  f.records.set("devices/a", {name: "Zebra", holdCount: -1, activeHold: {commandId: "secret"}}); // pragma: allowlist secret -- Dummy DTO leak marker
  f.records.set("devices/fallback", {name: {}, holdCount: 1.5});
  assert.deepEqual(await f.api.read(f.request({})), {devices: [{id: "z", name: "Apple", holdCount: 10}, {id: "fallback", name: "fallback", holdCount: 0}, {id: "a", name: "Zebra", holdCount: 0}], truncated: false});
  assert.equal(f.lookups.length, 0);
  assert.equal(f.reads[0].path, adminPath); assert.equal(f.reads[1].size, 201);
});
test("summary limit reads 201 and returns the first 200 with explicit truncation", async () => {
  const f = fixture();
  for (let n = 0; n < 202; n++) f.records.set("devices/d" + String(n).padStart(3, "0"), {name: "Gate " + n, holdCount: n});
  const result = await f.api.read(f.request({}));
  assert.equal(result.devices.length, 200); assert.equal(result.truncated, true);
  assert.equal(result.devices.some(device => device.id === "d200"), false);
  assert.equal(result.devices.some(device => device.id === "d201"), false);
});
test("empty summary and people results and missing devices are explicit", async () => {
  const f = fixture();
  assert.deepEqual(await f.api.read(f.request({})), {devices: [], truncated: false});
  await assert.rejects(f.api.read(f.request({deviceId: "missing"})), {publicCode: "not-found"});
  f.records.set("devices/empty", {});
  assert.deepEqual(await f.api.read(f.request({deviceId: "empty"})), {deviceId: "empty", people: [], truncated: false});
  assert.equal(f.lookups.length, 0);
});
test("people use exact hashed UID binding, bounded identities and anonymous deleted rows without private profiles", async () => {
  const f = fixture(); f.records.set("devices/garden", {holdCount: 99});
  f.records.set("devices/garden/usagePeople/" + hash("known"), {uid: "known", holdCount: 8, secret: "private"}); // pragma: allowlist secret -- Dummy DTO leak marker
  f.records.set("devices/garden/usagePeople/" + hash("deleted"), {uid: "deleted", holdCount: 4});
  f.records.set("devices/garden/usagePeople/" + hash("invalid-count"), {uid: "invalid-count", holdCount: -1});
  f.records.set("devices/garden/usagePeople/" + hash("forged"), {uid: "another-person", holdCount: 3});
  f.users.set("known", {uid: "known", displayName: "N".repeat(100), email: "e".repeat(280), providerData: [{private: true}], customClaims: {secret: true}});
  const before = structuredClone([...f.records]);
  const result = await f.api.read(f.request({deviceId: "garden"}));
  assert.deepEqual(result, {deviceId: "garden", people: [
    {id: hash("known"), name: "N".repeat(80), email: "e".repeat(254), holdCount: 8},
    {id: hash("deleted"), name: null, email: null, holdCount: 4},
    {id: hash("invalid-count"), name: null, email: null, holdCount: 0}
  ], truncated: false});
  assert.deepEqual(f.lookups.flat().map(item => item.uid), ["known", "deleted", "invalid-count"]);
  assert.deepEqual([...f.records], before);
  const query = f.reads.find(ref => ref.path.endsWith("usagePeople"));
  assert.equal(query.size, 201); assert.equal(query.field, "holdCount"); assert.equal(query.direction, "desc");
  assert.equal(f.reads.at(-1).path, adminPath);
});
test("top people are descending, bounded to 200 and resolved in batches of 100", async () => {
  const f = fixture(); f.records.set("devices/garden", {});
  for (let n = 0; n < 202; n++) f.records.set("devices/garden/usagePeople/" + hash("person" + n), {uid: "person" + n, holdCount: n});
  const result = await f.api.read(f.request({deviceId: "garden"}));
  assert.equal(result.truncated, true); assert.equal(result.people.length, 200);
  assert.equal(result.people[0].holdCount, 201); assert.equal(result.people.at(-1).holdCount, 2);
  assert.deepEqual(f.lookups.map(batch => batch.length), [100, 100]);
});
test("role revocation during external Auth lookup blocks returned identities", async () => {
  const f = fixture(); f.records.set("devices/garden", {});
  f.records.set("devices/garden/usagePeople/" + hash("known"), {uid: "known", holdCount: 1});
  f.users.set("known", {uid: "known", displayName: "Private person", email: "private@example.test"});
  f.hooks.lookup = async () => f.records.delete(adminPath);
  await assert.rejects(f.api.read(f.request({deviceId: "garden"})), {publicCode: "permission-denied"});
});
test("Auth service failures propagate instead of masquerading as deleted people", async () => {
  const f = fixture(); f.records.set("devices/garden", {});
  f.records.set("devices/garden/usagePeople/" + hash("known"), {uid: "known", holdCount: 1});
  f.hooks.lookup = async () => { throw Object.assign(new Error("Auth unavailable"), {code: "auth/internal-error"}); };
  await assert.rejects(f.api.read(f.request({deviceId: "garden"})), {code: "auth/internal-error"});
});
test("adminStats is an App Check protected callable using the existing runtime options", () => {
  const source = readFileSync(require.resolve("../index.js"), "utf8");
  assert.match(source, /createStatistics\(\{db: getFirestore\(\), auth: getAuth\(\)\}\)/);
  assert.match(source, /exports\.adminStats = onCall\(options, callable\(statistics\.read\)\)/);
});
