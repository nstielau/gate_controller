const {randomBytes: cryptoRandomBytes, createHash, createCipheriv, createDecipheriv} = require("node:crypto");
const {userId, fail} = require("./controller.cjs");

const DEVICE_ID = /^[a-z0-9-]{1,64}$/;
const HEX_SECRET = /^[0-9a-f]{64}$/;
const VERSION = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;
function validVersion(value) {
  return typeof value === "string" && value.length <= 32 && VERSION.test(value) && value.split(".").every(part => Number.isSafeInteger(Number(part)));
}
function supportsRestartSetupVersion(value) {
  if (!validVersion(value)) return false;
  const [major, minor, patch] = value.split(".").map(Number);
  return major > 1 || (major === 1 && (minor > 0 || patch >= 13));
}
function exactDeviceTopics(device, id) {
  return device?.commandTopic === `gate/v1/devices/${id}/command` && device?.statusTopic === `gate/v1/devices/${id}/status`;
}
const CLAIM_MS = 2 * 60 * 60 * 1000;
const PROVISIONING_LEASE_MS = 2 * 60 * 1000;
const DEFAULT_BROKER_HOST = "jd3a6164.ala.us-east-1.emqxsl.com";
const DEFAULT_BROKER_PORT = 8883;
const hash = value => createHash("sha256").update(value, "utf8").digest("hex");

function normalizeDeviceId(value) {
  if (typeof value !== "string") fail("invalid-argument", "Enter a valid device ID.");
  const id = value.trim().toLowerCase();
  if (!DEVICE_ID.test(id)) fail("invalid-argument", "Enter a valid device ID.");
  return id;
}
function proof(value) {
  if (typeof value !== "string" || !HEX_SECRET.test(value)) fail("invalid-argument", "Invalid pairing proof.");
  return value;
}
function nickname(value) {
  if (value === undefined) return null;
  if (typeof value !== "string" || !value.trim() || value.trim().length > 80 || /[\u0000-\u001f\u007f]/.test(value)) {
    fail("invalid-argument", "Enter a gate nickname between 1 and 80 characters.");
  }
  return value.trim();
}
function credentialKey(secret) {
  return createHash("sha256").update("drawbridge-device-enrollment-v1:" + secret, "utf8").digest();
}
function encrypt(credentials, secret, context, randomBytes) {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", credentialKey(secret), iv);
  cipher.setAAD(Buffer.from(context, "utf8"));
  const ciphertext = Buffer.concat([cipher.update(JSON.stringify(credentials), "utf8"), cipher.final()]);
  return {iv: iv.toString("base64"), ciphertext: ciphertext.toString("base64"), tag: cipher.getAuthTag().toString("base64")};
}
function decrypt(envelope, secret, context) {
  try {
    const decipher = createDecipheriv("aes-256-gcm", credentialKey(secret), Buffer.from(envelope.iv, "base64"));
    decipher.setAAD(Buffer.from(context, "utf8"));
    decipher.setAuthTag(Buffer.from(envelope.tag, "base64"));
    return JSON.parse(Buffer.concat([decipher.update(Buffer.from(envelope.ciphertext, "base64")), decipher.final()]).toString("utf8"));
  } catch {
    fail("unavailable", "Device registration is temporarily unavailable. Try again.");
  }
}

function createEnrollment({db, broker, now = Date.now, randomBytes = cryptoRandomBytes,
  brokerHost = DEFAULT_BROKER_HOST, brokerPort = DEFAULT_BROKER_PORT} = {}) {
  if (!db || !broker) throw new Error("Enrollment dependencies are required");
  const claimRef = key => db.doc(`claims/${key}`);
  const deviceRef = id => db.doc(`devices/${id}`);
  const enrollmentRef = id => db.doc(`deviceEnrollments/${id}`);
  const bindingRef = id => db.doc(`devicePairingBindings/${id}`);
  const bindingMatches = (binding, code) => binding.exists && binding.data()?.pairingCode === code;
  const claimResult = (id, record) => ({deviceId: id, state: record.state, expiresAtMs: record.expiresAtMs});
  function ownedDevice(id, device, enrollment, uid) {
    return device && Array.isArray(device.allowedUsers) && device.allowedUsers.includes(uid) &&
      device.commandTopic === `gate/v1/devices/${id}/command` &&
      (device.enabled === true || (enrollment?.state === "ready" && device.enrollmentState === "provisioning"));
  }
  function ownedResult(id, enrollment) {
    return {deviceId: id, state: enrollment?.state === "ready" ? "provisioning" : "registered", owned: true};
  }
  function resetAccess(device, id, uid) {
    return exactDeviceTopics(device, id) && Array.isArray(device.allowedUsers) && device.allowedUsers.includes(uid);
  }
  function activeReset(device) {
    return device?.setupReset && device.setupReset.state !== "complete";
  }
  function currentResetClaim(claim, device, resetId, time, requireFresh = true) {
    return claim && claim.setupResetId === resetId && ["pending", "provisioning", "registered"].includes(claim.state) &&
      Array.isArray(device.allowedUsers) && device.allowedUsers.includes(claim.uid) && (!requireFresh || claim.expiresAtMs > time);
  }
  async function claim(request) {
    const uid = userId(request);
    const id = normalizeDeviceId(request?.data?.deviceId);
    const code = proof(request?.data?.pairingCode);
    const key = hash(id + ":" + code);
    const name = nickname(request?.data?.nickname);
    const time = now();
    return db.runTransaction(async tx => {
      const [deviceDoc, current, enrollmentDoc, binding] = await tx.getAll(deviceRef(id), claimRef(key), enrollmentRef(id), bindingRef(id));
      const device = deviceDoc.data(), enrollment = enrollmentDoc.data();
      if (deviceDoc.exists && activeReset(device)) {
        if (!resetAccess(device, id, uid) || !bindingMatches(binding, code)) fail("failed-precondition", "This device is already registered.");
        const reset = device.setupReset;
        if (reset.state === "pending") return {deviceId: id, state: "pending", owned: true};
        if (!["awaiting_setup", "provisioning"].includes(reset.state) || !enrollment || enrollment.claimKey !== key) fail("failed-precondition", "Device registration is unavailable.");
        const record = current.data();
        if (currentResetClaim(record, device, reset.id, time)) return claimResult(id, record);
        const next = {uid, deviceId: id, nickname: null, setupResetId: reset.id,
          state: reset.state === "provisioning" ? "provisioning" : "pending", createdAtMs: time, expiresAtMs: time + CLAIM_MS};
        tx.set(claimRef(key), next);
        return claimResult(id, next);
      }
      if (deviceDoc.exists) {
        if (!ownedDevice(id, device, enrollment, uid)) fail("failed-precondition", "This device is already registered.");
        return ownedResult(id, enrollment);
      }
      // Only the USB/admin workflow establishes this ID-to-proof binding.
      // Public callers cannot announce a new identity by choosing their own secret.
      if (!bindingMatches(binding, code)) fail("failed-precondition", "Device registration is unavailable.");
      if (enrollmentDoc.exists && (enrollment.claimKey !== key || enrollment.uid !== uid)) {
        fail("failed-precondition", "This device already has an active claim.");
      }
      const record = current.exists ? current.data() : null;
      if (record && (enrollmentDoc.exists || record.expiresAtMs > time)) {
        if (record.uid !== uid) fail("failed-precondition", "This device already has an active claim.");
        return claimResult(id, record);
      }
      const next = {uid, deviceId: id, nickname: name, state: "pending", createdAtMs: time, expiresAtMs: time + CLAIM_MS};
      tx.set(claimRef(key), next);
      return claimResult(id, next);
    });
  }
  async function status(request) {
    const uid = userId(request);
    const id = normalizeDeviceId(request?.data?.deviceId);
    const code = proof(request?.data?.pairingCode);
    const key = hash(id + ":" + code);
    return db.runTransaction(async tx => {
      const [claimDoc, deviceDoc, enrollmentDoc, binding] = await tx.getAll(claimRef(key), deviceRef(id), enrollmentRef(id), bindingRef(id));
      if (deviceDoc.exists && activeReset(deviceDoc.data())) {
        const device = deviceDoc.data(), reset = device.setupReset;
        if (!resetAccess(device, id, uid) || !bindingMatches(binding, code)) return {deviceId: id, state: "unknown"};
        if (reset.state === "pending") return {deviceId: id, state: "pending", owned: true};
        const record = claimDoc.data();
        if (!currentResetClaim(record, device, reset.id, now(), false)) return {deviceId: id, state: "awaiting_setup", owned: true};
        return record.expiresAtMs <= now() ? {deviceId: id, state: "expired", expiresAtMs: record.expiresAtMs} : claimResult(id, record);
      }
      if (deviceDoc.exists) {
        return ownedDevice(id, deviceDoc.data(), enrollmentDoc.data(), uid) ? ownedResult(id, enrollmentDoc.data()) : {deviceId: id, state: "unknown"};
      }
      if (!bindingMatches(binding, code) || !claimDoc.exists || claimDoc.data().uid !== uid) return {deviceId: id, state: "unknown"};
      const record = claimDoc.data();
      if (record.state === "pending" && record.expiresAtMs <= now()) return {deviceId: id, state: "expired", expiresAtMs: record.expiresAtMs};
      return claimResult(id, record);
    });
  }
  async function register(request) {
    const id = normalizeDeviceId(request?.device_id ?? request?.deviceId);
    const secret = proof(request?.device_secret ?? request?.deviceSecret);
    const action = request?.action ?? "provision";
    if (!["provision", "complete", "maintenance", "restart_setup_complete"].includes(action)) fail("invalid-argument", "Invalid registration action.");
    if (request?.setup_reset_id !== undefined && !HEX_SECRET.test(request.setup_reset_id)) fail("invalid-argument", "Invalid setup reset.");
    if (action === "maintenance" && (!validVersion(request.app_version) || !supportsRestartSetupVersion(request.base_version))) fail("failed-precondition", "Compatible device firmware is required.");
    // The QR contains hash(secret), never the private proof or encryption key.
    const code = hash(secret);
    const key = hash(id + ":" + code);
    const context = id + ":" + key;
    const time = now(), attemptId = randomBytes(16).toString("hex");
    const reservation = await db.runTransaction(async tx => {
      const [claimDoc, deviceDoc, enrollmentDoc, binding] = await tx.getAll(claimRef(key), deviceRef(id), enrollmentRef(id), bindingRef(id));
      if (!bindingMatches(binding, code)) fail("failed-precondition", "Device registration is unavailable.");
      let record = enrollmentDoc.exists ? enrollmentDoc.data() : null;
      if (record && record.claimKey !== key) fail("failed-precondition", "Device registration is unavailable.");
      const device = deviceDoc.data(), reset = device?.setupReset;
      if (["maintenance", "restart_setup_complete"].includes(action)) {
        if (!record || !deviceDoc.exists || !exactDeviceTopics(device, id) || !["registered", "awaiting_setup", "ready"].includes(record.state)) fail("failed-precondition", "Device registration is unavailable.");
        decrypt(record.envelope, secret, context);
        if (action === "maintenance") {
          tx.update(deviceRef(id), {maintenance: {appVersion: request.app_version, baseVersion: request.base_version, lastSeenAtMs: time, supportsRestartSetup: true}});
          return {response: {deviceId: id, restartSetup: reset ? {id: reset.id, state: reset.state} : null}};
        }
        if (!reset || reset.id !== request.setup_reset_id || !["pending", "awaiting_setup"].includes(reset.state)) fail("failed-precondition", "Device registration is unavailable.");
        if (reset.state === "pending") {
          tx.update(deviceRef(id), {enabled: false, enrollmentState: "awaiting_setup", setupReset: {...reset, state: "awaiting_setup", acknowledgedAtMs: time}});
          tx.update(enrollmentRef(id), {state: "awaiting_setup", setupResetId: reset.id});
          if (claimDoc.exists) tx.update(claimRef(key), {state: "expired", expiresAtMs: time});
        }
        return {response: {deviceId: id, state: "awaiting_setup", setup_reset_id: reset.id}};
      }
      // Every subsequent generation must carry its ID, including transport retries
      // after completion. A delayed pre-reset request cannot skip Wi-Fi/QR setup.
      if (reset) {
        if (request.setup_reset_id !== reset.id || !exactDeviceTopics(device, id) || reset.state === "pending") fail("failed-precondition", "Device registration is unavailable.");
        if (action === "provision" && ["awaiting_setup", "provisioning"].includes(reset.state)) {
          if (!record || record.setupResetId !== reset.id || !["awaiting_setup", "ready"].includes(record.state) ||
              !currentResetClaim(claimDoc.data(), device, reset.id, time)) fail("failed-precondition", "Device registration is unavailable.");
          const credentials = decrypt(record.envelope, secret, context);
          if (reset.state === "awaiting_setup") {
            tx.update(enrollmentRef(id), {state: "ready"});
            tx.update(deviceRef(id), {enrollmentState: "provisioning", setupReset: {...reset, state: "provisioning", provisioningAtMs: time}});
          }
          tx.update(claimRef(key), {state: "provisioning"});
          return {credentials};
        }
        if (action === "complete" && reset.state !== "complete" &&
            (reset.state !== "provisioning" || record?.setupResetId !== reset.id || !currentResetClaim(claimDoc.data(), device, reset.id, time, false))) fail("failed-precondition", "Device registration is unavailable.");
      } else if (request.setup_reset_id !== undefined) {
        fail("failed-precondition", "Device registration is unavailable.");
      }
      if (action === "complete") {
        if (!record || !["ready", "registered"].includes(record.state) || !deviceDoc.exists) fail("failed-precondition", "Device registration is unavailable.");
        // Decrypt before accepting proof, including repeated acknowledgments.
        decrypt(record.envelope, secret, context);
        if (record.state === "ready") {
          if (reset && (reset.state !== "provisioning" || device.enrollmentState !== "provisioning")) fail("failed-precondition", "Device registration is unavailable.");
          tx.update(deviceRef(id), {enabled: true, enrollmentState: "registered", registeredAtMs: time,
            ...(reset ? {setupReset: {...reset, state: "complete", completedAtMs: time}} : {})});
          tx.update(enrollmentRef(id), {state: "registered", registeredAtMs: time});
          tx.update(claimRef(key), {state: "registered", registeredAtMs: time});
        }
        return {complete: true};
      }
      if (record && ["ready", "registered"].includes(record.state)) return {credentials: decrypt(record.envelope, secret, context)};
      if (deviceDoc.exists) fail("failed-precondition", "Device registration is unavailable.");
      if (!record) {
        if (!claimDoc.exists || claimDoc.data().state !== "pending" || claimDoc.data().expiresAtMs <= time) {
          fail("failed-precondition", "Device registration is unavailable.");
        }
        const credentials = {deviceId: id, username: `gate-${id}`, password: randomBytes(24).toString("hex"), brokerHost, brokerPort,
          commandTopic: `gate/v1/devices/${id}/command`, statusTopic: `gate/v1/devices/${id}/status`};
        record = {claimKey: key, uid: claimDoc.data().uid, nickname: claimDoc.data().nickname, state: "provisioning",
          envelope: encrypt(credentials, secret, context, randomBytes), createdAtMs: time};
      } else if (record.attemptId && record.provisioningAtMs + PROVISIONING_LEASE_MS > time) {
        fail("unavailable", "Device registration is temporarily unavailable. Try again.");
      }
      const credentials = decrypt(record.envelope, secret, context);
      tx.set(enrollmentRef(id), {...record, attemptId, provisioningAtMs: time});
      tx.update(claimRef(key), {state: "provisioning"});
      return {credentials, provision: true};
    });
    if (reservation.response) return reservation.response;
    if (reservation.complete) return {deviceId: id, state: "registered"};
    if (!reservation.provision) return reservation.credentials;
    const {username, password, commandTopic, statusTopic} = reservation.credentials;
    try {
      // Every attempt uses the durable encrypted credential identity. Never delete
      // it on an uncertain outcome: a concurrent/stale worker may have succeeded.
      await broker.provision({username, password, commandTopic, statusTopic});
      await db.runTransaction(async tx => {
        const [enrollmentDoc, deviceDoc, binding] = await tx.getAll(enrollmentRef(id), deviceRef(id), bindingRef(id));
        const record = enrollmentDoc.data();
        if (!bindingMatches(binding, code) || !record || record.attemptId !== attemptId || deviceDoc.exists) fail("unavailable", "Device registration is temporarily unavailable. Try again.");
        tx.set(deviceRef(id), {
          id, name: record.nickname || id, enabled: false, enrollmentState: "provisioning", allowedUsers: [record.uid],
          commandTopic, statusTopic, mqttUsername: username, credentialVersion: 1,
          provisionedAtMs: now(), holdCount: 0, activeHold: null, pendingCommandId: null,
        });
        tx.update(enrollmentRef(id), {state: "ready", attemptId: null, provisioningAtMs: null});
      });
    } catch {
      try {
        await db.runTransaction(async tx => {
          const current = await tx.get(enrollmentRef(id));
          if (current.exists && current.data().attemptId === attemptId) tx.update(enrollmentRef(id), {attemptId: null, provisioningAtMs: null});
        });
      } catch {}
      fail("unavailable", "Device registration is temporarily unavailable. Try again.");
    }
    return reservation.credentials;
  }
  return {claim, status, register, normalizeDeviceId};
}

function createRegistrationHandler(service) {
  return async (request, response) => {
    response.set("Cache-Control", "no-store");
    response.set("Access-Control-Allow-Origin", "*");
    if (request.method === "OPTIONS") {
      response.set("Access-Control-Allow-Methods", "POST, OPTIONS");
      response.set("Access-Control-Allow-Headers", "Content-Type");
      return response.status(204).send("");
    }
    if (request.method !== "POST") return response.status(405).json({error: "method_not_allowed"});
    try {
      const body = request.body && typeof request.body === "object" ? request.body : {};
      const result = await service.register({device_id: body.device_id ?? body.deviceId, device_secret: body.device_secret, action: body.action,
        setup_reset_id: body.setup_reset_id, app_version: body.app_version, base_version: body.base_version});
      return response.status(200).json(result);
    } catch (error) {
      const status = error?.publicCode === "unavailable" ? 503 : 400;
      return response.status(status).json({error: "registration_unavailable"});
    }
  };
}
module.exports = {createEnrollment, createRegistrationHandler, normalizeDeviceId, CLAIM_MS, PROVISIONING_LEASE_MS, supportsRestartSetupVersion};
