const {test} = require("node:test");
const assert = require("node:assert/strict");
const {createEmqxClient} = require("../emqx.cjs");

test("creates a device user and replaces its two topic rules", async () => {
  const calls = [];
  const client = createEmqxClient({baseUrl: "https://broker.example/api/v5", appId: "test-id", appSecret: "test-value", request: async call => { calls.push(call); return {status: call.method === "PUT" ? 204 : 201, json: async () => ({})}; }});
  await client.provision({username: "gate-ab12cd", password: "pw-for-test", commandTopic: "gate/v1/devices/ab12cd/command", statusTopic: "gate/v1/devices/ab12cd/status"}); // pragma: allowlist secret
  assert.equal(calls[0].method, "POST");
  assert.match(calls[0].path, /authentication\/password_based%3Abuilt_in_database\/users$/);
  assert.deepEqual(calls[0].body, {user_id: "gate-ab12cd", password: "pw-for-test"}); // pragma: allowlist secret
  assert.equal(calls[1].method, "PUT");
  assert.deepEqual(calls[1].body.rules, [
    {action: "subscribe", permission: "allow", topic: "gate/v1/devices/ab12cd/command", qos: [1], retain: "all"},
    {action: "publish", permission: "allow", topic: "gate/v1/devices/ab12cd/status", qos: [0, 1], retain: "all"},
    {action: "all", permission: "deny", topic: "#"}
  ]);
});

test("rejects management errors without exposing response details", async () => {
  const client = createEmqxClient({baseUrl: "https://broker.example/api/v5", appId: "test-id", appSecret: "test-value", request: async () => ({status: 500, text: async () => "private response"})});
  await assert.rejects(client.provision({username: "gate-ab12cd", password: "pw-for-test", commandTopic: "command", statusTopic: "status"}), error => { // pragma: allowlist secret
    assert.equal(error.message, "EMQX provisioning failed");
    assert.equal(error.publicCode, "internal");
    return true;
  });
});
