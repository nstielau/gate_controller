const {test} = require("node:test");
const assert = require("node:assert/strict");
const {EventEmitter} = require("node:events");
const {publishHold} = require("../mqtt.cjs");
const payload = {command_id: "a".repeat(64), duration_seconds: 600};
test("TLS validation, non-retained QoS 1, and cleanup after acknowledgement", async () => {
  let connected, published, ended = 0;
  const client = new EventEmitter();
  client.end = force => { assert.equal(force, true); ended++; client.emit("close"); };
  client.publish = (...args) => { published = args.slice(0, 3); args[3](); client.emit("error", new Error("late")); };
  await publishHold("test-topic", payload, {username: "test-user", password: "test-only", // pragma: allowlist secret
    ca: "test-ca"}, {connect: (url, options) => {
    connected = {url, options}; queueMicrotask(() => client.emit("connect")); return client;
  }});
  assert.equal(connected.url.startsWith("mqtts://"), true);
  assert.equal(connected.options.rejectUnauthorized, true);
  assert.equal(connected.options.reconnectPeriod, 0);
  assert.equal(connected.options.ca, "test-ca");
  assert.deepEqual(published, ["test-topic", JSON.stringify(payload), {qos: 1, retain: false}]);
  assert.equal(ended, 1);
});
test("timeout, early close, connect errors and publish errors reject without leaking details", async () => {
  for (const mode of ["timeout", "close", "error", "throw", "publish"]) {
    const client = new EventEmitter(); let ended = 0;
    client.end = () => { ended++; };
    client.publish = () => { throw new Error("secret-broker-detail"); };
    await assert.rejects(publishHold("test", payload, {}, {timeoutMs: 10, connect: () => {
      if (mode === "throw") throw new Error("secret-broker-detail");
      queueMicrotask(() => {
        if (mode === "close") client.emit("close");
        if (mode === "error") client.emit("error", new Error("secret-broker-detail"));
        if (mode === "publish") client.emit("connect");
      });
      return client;
    }}), {message: "MQTT delivery was not confirmed"});
    assert.equal(ended, mode === "throw" ? 0 : 1);
  }
});
