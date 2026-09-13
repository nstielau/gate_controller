const { createHash } = require("node:crypto");
const DURATIONS = new Set([0, 60, 900, 3600, 21600]);
const DEVICE_ID = /^[a-z0-9-]{1,64}$/;
function fail(code, message) {
  const error = new Error(message);
  error.publicCode = code;
  throw error;
}
function userId(request) {
  if (!request.auth) fail("unauthenticated", "Sign in with Google to continue.");
  const {uid, token} = request.auth;
  if (typeof uid !== "string" || !uid || token?.email_verified !== true ||
      token?.firebase?.sign_in_provider !== "google.com") {
    fail("permission-denied", "A verified Google sign-in is required.");
  }
  return uid;
}
function canControl(device, deviceId, uid) {
  return device?.enabled === true && DEVICE_ID.test(deviceId) &&
    Array.isArray(device.allowedUsers) && device.allowedUsers.includes(uid) &&
    device.commandTopic === `gate/v1/devices/${deviceId}/command`;
}
function publicHold(value) {
  if (!value || !Number.isSafeInteger(value.startedAtMs) ||
      !Number.isInteger(value.durationSeconds) || !DURATIONS.has(value.durationSeconds) ||
      value.durationSeconds === 0) return null;
  return {startedAtMs: value.startedAtMs, durationSeconds: value.durationSeconds};
}
function publicHoldCount(value) {
  return Number.isSafeInteger(value) && value >= 0 ? value : 0;
}
function createController({store, publish, now = Date.now}) {
  return {
    async renameGate(request) {
      const uid = userId(request);
      const {deviceId, nickname} = request.data || {};
      if (typeof deviceId !== "string" || !DEVICE_ID.test(deviceId) ||
          typeof nickname !== "string" || !nickname.trim() || nickname.trim().length > 80 ||
          /[\u0000-\u001f\u007f]/.test(nickname)) {
        fail("invalid-argument", "Enter a gate nickname between 1 and 80 characters.");
      }
      const name = nickname.trim();
      await store.rename({uid, deviceId, name});
      return {id: deviceId, name};
    },
    async listDevices(request) {
      const uid = userId(request);
      const devices = await store.list(uid);
      return {devices: devices.filter(d => canControl(d, d.id, uid)).map(d => ({
        id: d.id, name: typeof d.name === "string" ? d.name.slice(0, 80) : d.id,
        hold: publicHold(d.activeHold), holdCount: publicHoldCount(d.holdCount)
      }))};
    },
    async holdGate(request) {
      const uid = userId(request);
      const {deviceId, durationSeconds, requestId, issuedAtMs} = request.data || {};
      if (typeof deviceId !== "string" || !DEVICE_ID.test(deviceId) ||
          !Number.isInteger(durationSeconds) || !DURATIONS.has(durationSeconds) ||
          typeof requestId !== "string" || !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(requestId) ||
          !Number.isSafeInteger(issuedAtMs)) fail("invalid-argument", "Invalid hold request.");
      const time = now();
      if (time - issuedAtMs > 60000 || issuedAtMs - time > 10000) {
        fail("failed-precondition", "Request expired. Check your device clock and try again.");
      }
      const id = createHash("sha256").update(`${uid}:${requestId.toLowerCase()}`).digest("hex");
      const reserved = await store.reserve({id, uid, deviceId, durationSeconds, time});
      if (!reserved.fresh) return {commandId: id, status: reserved.status};
      try {
        await publish(reserved.topic, {
          version: 1, type: "hold_gate", duration_seconds: durationSeconds, command_id: id
        });
      } catch {
        await store.finish({id, status: "unknown", deviceId, durationSeconds, time: now()});
        return {commandId: id, status: "unknown"};
      }
      const acceptedAtMs = now();
      try { await store.finish({id, status: "accepted", deviceId, durationSeconds, time: acceptedAtMs}); }
      catch { return {commandId: id, status: "unknown"}; }
      return {commandId: id, status: "accepted", hold: durationSeconds === 0 ? null : {
        startedAtMs: acceptedAtMs, durationSeconds
      }};
    }
  };
}
module.exports = {createController, canControl, fail, publicHold, publicHoldCount};
