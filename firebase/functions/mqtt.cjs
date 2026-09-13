const mqtt = require("mqtt");
function publishHold(topic, payload, credentials, {connect = mqtt.connect, timeoutMs = 12000} = {}) {
  return new Promise((resolve, reject) => {
    let client, finished = false;
    const finish = error => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      client?.end(true);
      if (error) reject(new Error("MQTT delivery was not confirmed"));
      else resolve();
    };
    const timer = setTimeout(() => finish(new Error("timeout")), timeoutMs);
    try {
      client = connect("mqtts://jd3a6164.ala.us-east-1.emqxsl.com:8883", {
        ...credentials, rejectUnauthorized: true, reconnectPeriod: 0,
        connectTimeout: Math.min(timeoutMs, 10000), clean: true,
        clientId: `drawbridge-${payload.command_id.slice(0, 24)}`
      });
      client.on("error", finish);
      client.once("close", () => finish(new Error("closed before acknowledgement")));
      client.once("connect", () => {
        try { client.publish(topic, JSON.stringify(payload), {qos: 1, retain: false}, finish); }
        catch (error) { finish(error); }
      });
    } catch (error) { finish(error); }
  });
}
module.exports = {publishHold};
