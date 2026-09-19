const {test} = require("node:test");
const assert = require("node:assert/strict");
const {randomUUID} = require("node:crypto");
const {createDeviceAccess} = require("../device-access.cjs");
const time = 1800000000000;
const auth = {uid: "operator", token: {email_verified: true, firebase: {sign_in_provider: "google.com"}}};
const data = {deviceId: "test-device", email: "guest@example.test", requestId: randomUUID(), issuedAtMs: time};
const api = createDeviceAccess({
  db: {doc() { throw new Error("must reject before DB access"); }},
  auth: {}, now: () => time
});
test("invitations require verified Google identity before any lookup", async () => {
  for (const identity of [undefined, {...auth, uid: ""}, {...auth, token: {...auth.token, email_verified: false}},
    {...auth, token: {...auth.token, firebase: {sign_in_provider: "password"}}}]) {
    await assert.rejects(api.invite({auth: identity, data}), error => ["unauthenticated", "permission-denied"].includes(error.publicCode));
  }
});
test("invitation validation rejects invalid emails, devices, IDs, and expired requests", async () => {
  for (const changes of [{email: null}, {email: 3}, {email: "bad"}, {email: "a@b.test\nc@d.test"},
    {email: "a".repeat(250) + "@example.test"}, {deviceId: "../other"}, {deviceId: ["test-device"]},
    {requestId: "bad"}, {issuedAtMs: "now"}, {issuedAtMs: time - 60001}, {issuedAtMs: time + 10001}]) {
    await assert.rejects(api.invite({auth, data: {...data, ...changes}}), error => ["invalid-argument", "failed-precondition"].includes(error.publicCode));
  }
});
