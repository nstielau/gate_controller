// Local integration check. Never publish to a physical gate's topic.
const {readFileSync} = require("node:fs");
const {randomUUID} = require("node:crypto");
const assert = require("node:assert/strict");
const mqtt = require("mqtt");
const {publishHold} = require("./mqtt.cjs");
const credentials = JSON.parse(readFileSync(0, "utf8"));
const device = "web-test-" + randomUUID();
const topic = "gate/v1/devices/" + device + "/command";
let subscriber;
(async () => {
  subscriber = mqtt.connect("mqtts://jd3a6164.ala.us-east-1.emqxsl.com:8883", {
    ...credentials, rejectUnauthorized: true, reconnectPeriod: 0, connectTimeout: 10000,
    clientId: "test-sub-" + randomUUID().slice(0, 16), clean: true
  });
  subscriber.on("error", () => {});
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("subscribe timeout")), 15000);
    const finish = error => { clearTimeout(timer); error ? reject(error) : resolve(); };
    subscriber.once("error", finish);
    subscriber.once("connect", () => subscriber.subscribe(topic, {qos: 1}, (error, grants) => {
      finish(error || (grants?.[0]?.qos > 1 ? new Error("subscription denied") : null));
    }));
  });
  for (const duration of [60, 900, 0]) {
    const payload = {version: 1, type: "hold_gate", duration_seconds: duration, command_id: randomUUID()};
    const received = new Promise((resolve, reject) => {
      const timer = setTimeout(() => { subscriber.off("message", onMessage); reject(new Error("receive timeout")); }, 15000);
      function onMessage(receivedTopic, bytes, packet) {
        if (receivedTopic !== topic) return;
        clearTimeout(timer); subscriber.off("message", onMessage);
        try { assert.deepEqual(JSON.parse(bytes.toString()), payload); assert.equal(packet.retain, false); resolve(); }
        catch (error) { reject(error); }
      }
      subscriber.on("message", onMessage);
    });
    await Promise.all([received, publishHold(topic, payload, credentials)]);
  }
  console.log("PASS: three TLS/QoS 1 publish-and-receive cycles on synthetic topic; no physical gate commands.");
})().catch(() => { console.error("MQTT smoke test failed; check credentials, ACLs, and connectivity."); process.exitCode = 1; })
  .finally(() => subscriber?.end(true));
