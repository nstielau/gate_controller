const {test} = require("node:test");
const assert = require("node:assert/strict");
const {randomUUID} = require("node:crypto");
const {createController, canControl} = require("../controller.cjs");
const auth = {uid: "operator", token: {email_verified: true, firebase: {sign_in_provider: "google.com"}}};
const time = 1800000000000;
const device = {id: "gate1", enabled: true, allowedUsers: ["operator"], commandTopic: "gate/v1/devices/gate1/command", name: "Garden"};
function request(data = {}) { return {auth, data: {deviceId: "gate1", durationSeconds: 60, requestId: randomUUID(), issuedAtMs: time, ...data}}; }
function harness({publishError = false, auditError = false} = {}) {
  const publishes = [], audits = [];
  let reserves = 0;
  const controller = createController({now: () => time, store: {
    list: async () => [device, {...device, id: "hidden", enabled: false}],
    reserve: async () => { reserves++; return {fresh: true, topic: device.commandTopic}; },
    finish: async (...args) => { audits.push(args); if (auditError) throw new Error("offline"); }
  }, publish: async (...args) => { publishes.push(args); if (publishError) throw new Error("broker-secret-must-not-leak"); }});
  return {controller, publishes, audits, reserves: () => reserves};
}
test("only verified Google users reach storage", async () => {
  for (const invalid of [null, {...auth, token: {}}, {...auth, token: {email_verified: false, firebase: {sign_in_provider: "google.com"}}}, {...auth, token: {email_verified: true, firebase: {sign_in_provider: "password"}}}]) {
    const h = harness();
    await assert.rejects(h.controller.holdGate({...request(), auth: invalid}));
    await assert.rejects(h.controller.listDevices({auth: invalid}));
    assert.equal(h.reserves(), 0);
  }
});
test("strict device, duration, UUID, and freshness validation", async () => {
  for (const data of [{durationSeconds: 1}, {durationSeconds: "600"}, {durationSeconds: true}, {durationSeconds: NaN}, {durationSeconds: -1}, {durationSeconds: 86400}, {deviceId: "../other"}, {deviceId: ""}, {requestId: "bad"}, {issuedAtMs: time - 60001}, {issuedAtMs: time + 10001}, {issuedAtMs: "now"}]) {
    const h = harness();
    await assert.rejects(h.controller.holdGate(request(data)));
    assert.equal(h.reserves(), 0);
  }
});
test("approved durations publish exact firmware schema with bounded IDs", async () => {
  const h = harness();
  for (const durationSeconds of [0, 60, 900, 3600, 21600]) {
    const response = await h.controller.holdGate(request({durationSeconds}));
    assert.equal(response.status, "accepted");
    assert.match(response.commandId, /^[a-f0-9]{64}$/);
    assert.deepEqual(h.publishes.at(-1), [device.commandTopic, {version: 1, type: "hold_gate", duration_seconds: durationSeconds, command_id: response.commandId}]);
  }
});
test("access requires enabled gate, exact topic, and UID assignment", () => {
  assert.equal(canControl(device, "gate1", "operator"), true);
  for (const changes of [{enabled: false}, {allowedUsers: []}, {allowedUsers: ["someone-else"]}, {commandTopic: "gate/v1/devices/other/command"}, {commandTopic: "#"}]) {
    assert.equal(canControl({...device, ...changes}, "gate1", "operator"), false);
  }
});
test("device listing exposes only labels, IDs, and a validated expected hold", async () => {
  const h = {controller: createController({store: {list: async () => [
    {...device, activeHold: {startedAtMs: time, durationSeconds: 60, commandId: "do-not-leak"}}
  ]}})};
  assert.deepEqual(await h.controller.listDevices({auth}), {devices: [
    {id: "gate1", name: "Garden", hold: {startedAtMs: time, durationSeconds: 60}}
  ]});
});
test("broker failures and audit failures after acceptance report uncertainty", async () => {
  for (const options of [{publishError: true}, {auditError: true}]) {
    const h = harness(options);
    assert.equal((await h.controller.holdGate(request())).status, "unknown");
    assert.equal(h.publishes.length, 1);
  }
});
test("accepted holds return a visual countdown state, while end-hold clears it", async () => {
  const h = harness();
  const started = await h.controller.holdGate(request({durationSeconds: 60}));
  assert.deepEqual(started.hold, {startedAtMs: time, durationSeconds: 60});
  const ended = await h.controller.holdGate(request({durationSeconds: 0}));
  assert.equal(ended.hold, null);
});
test("duplicate reservation never republishes, including pending and uncertain states", async () => {
  for (const status of ["pending", "accepted", "unknown"]) {
    const controller = createController({now: () => time, store: {reserve: async () => ({fresh: false, status})}, publish: () => assert.fail("duplicate publish")});
    assert.equal((await controller.holdGate(request())).status, status);
  }
});
test("nicknames require verified Google auth and valid device/name input", async () => {
  const writes = [];
  const controller = createController({store: {rename: async data => writes.push(data)}});
  await assert.rejects(controller.renameGate({data: {deviceId: "gate1", nickname: "Garden"}}), {publicCode: "unauthenticated"});
  await assert.rejects(controller.renameGate({auth: {...auth, token: {email_verified: false}}, data: {deviceId: "gate1", nickname: "Garden"}}), {publicCode: "permission-denied"});
  for (const nickname of [null, {}, "", "   ", "a".repeat(81), "Gate\nname", "Gate\u0000"]) {
    await assert.rejects(controller.renameGate({auth, data: {deviceId: "gate1", nickname}}), {publicCode: "invalid-argument"});
  }
  await assert.rejects(controller.renameGate({auth, data: {deviceId: "../other", nickname: "Garden"}}), {publicCode: "invalid-argument"});
  assert.equal(writes.length, 0);
  assert.deepEqual(await controller.renameGate({auth, data: {deviceId: "gate1", nickname: "  Garden gate 🌿  ", commandTopic: "other", enabled: false}}), {id: "gate1", name: "Garden gate 🌿"});
  assert.deepEqual(writes, [{uid: "operator", deviceId: "gate1", name: "Garden gate 🌿"}]);
});
