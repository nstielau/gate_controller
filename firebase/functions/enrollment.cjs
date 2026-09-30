const {randomBytes: cryptoRandomBytes} = require("node:crypto");
const {userId, fail} = require("./controller.cjs");

const DEVICE_ID = /^[a-z0-9-]{1,64}$/;
const CLAIM_MS = 2 * 60 * 60 * 1000;
const DEFAULT_BROKER_HOST = "jd3a6164.ala.us-east-1.emqxsl.com";
const DEFAULT_BROKER_PORT = 8883;

function normalizeDeviceId(value) {
  if (typeof value !== "string") fail("invalid-argument", "Enter a valid device ID.");
  const id = value.trim().toLowerCase();
  if (!DEVICE_ID.test(id)) fail("invalid-argument", "Enter a valid device ID.");
  return id;
}

function createEnrollment({db, broker, now = Date.now, randomBytes = cryptoRandomBytes,
  brokerHost = DEFAULT_BROKER_HOST, brokerPort = DEFAULT_BROKER_PORT} = {}) {
  if (!db || !broker) throw new Error("Enrollment dependencies are required");
  function claimRef(id) { return db.doc(`claims/${id}`); }
  function deviceRef(id) { return db.doc(`devices/${id}`); }
  function claimResult(id, record) {
    return {deviceId: id, state: record.state, expiresAtMs: record.expiresAtMs};
  }
  async function claim(request) {
    const uid = userId(request);
    const id = normalizeDeviceId(request?.data?.deviceId);
    const time = now();
    let result;
    await db.runTransaction(async tx => {
      const device = await tx.get(deviceRef(id));
      if (device.exists) fail("failed-precondition", "This device is already registered.");
      const current = await tx.get(claimRef(id));
      const record = current.exists ? current.data() : null;
      if (record && record.state === "pending" && record.expiresAtMs > time) {
        if (record.uid !== uid) fail("failed-precondition", "This device already has an active claim.");
        result = claimResult(id, record);
        return;
      }
      const next = {uid, state: "pending", createdAtMs: time, expiresAtMs: time + CLAIM_MS, attemptId: null};
      tx.set(claimRef(id), next);
      result = claimResult(id, next);
    });
    return result;
  }
  async function status(request) {
    const uid = userId(request);
    const id = normalizeDeviceId(request?.data?.deviceId);
    const snapshot = await db.runTransaction(async tx => tx.get(claimRef(id)));
    if (!snapshot.exists || snapshot.data().uid !== uid) return {deviceId: id, state: "unknown"};
    const record = snapshot.data();
    if (record.state === "pending" && record.expiresAtMs <= now()) return {deviceId: id, state: "expired", expiresAtMs: record.expiresAtMs};
    return claimResult(id, record);
  }
  async function register(request) {
    const id = normalizeDeviceId(request?.deviceId ?? request?.data?.deviceId);
    const time = now();
    const attemptId = randomBytes(12).toString("hex");
    const username = `gate-${id}`;
    const password = randomBytes(24).toString("hex");
    const commandTopic = `gate/v1/devices/${id}/command`;
    const statusTopic = `gate/v1/devices/${id}/status`;
    let owner;
    await db.runTransaction(async tx => {
      const [claimDoc, deviceDoc] = await tx.getAll(claimRef(id), deviceRef(id));
      if (deviceDoc.exists) fail("failed-precondition", "This device is already registered.");
      if (!claimDoc.exists) fail("failed-precondition", "This device is not currently being claimed.");
      const record = claimDoc.data();
      if (record.state !== "pending" || record.expiresAtMs <= time) {
        if (record.state === "pending" && record.expiresAtMs <= time) tx.update(claimRef(id), {state: "expired"});
        fail("failed-precondition", "This device is not currently being claimed.");
      }
      owner = record.uid;
      tx.update(claimRef(id), {state: "provisioning", attemptId, provisioningAtMs: time});
    });
    try {
      await broker.provision({username, password, commandTopic, statusTopic});
    } catch {
      try { await broker.remove(username); } catch {}
      await db.runTransaction(async tx => {
        const current = await tx.get(claimRef(id));
        if (current.exists && current.data().attemptId === attemptId) tx.update(claimRef(id), {state: "pending", attemptId: null, provisioningAtMs: null});
      });
      fail("unavailable", "Device registration is temporarily unavailable. Try again.");
    }
    await db.runTransaction(async tx => {
      const [claimDoc, deviceDoc] = await tx.getAll(claimRef(id), deviceRef(id));
      if (!claimDoc.exists || claimDoc.data().attemptId !== attemptId || deviceDoc.exists) {
        try { await broker.remove(username); } catch {}
        fail("failed-precondition", "This device registration is no longer available.");
      }
      tx.set(deviceRef(id), {
        id, name: id, enabled: true, allowedUsers: [owner],
        commandTopic, statusTopic, mqttUsername: username, credentialVersion: 1,
        registeredAtMs: now(), holdCount: 0, activeHold: null, pendingCommandId: null,
      });
      tx.update(claimRef(id), {state: "registered", registeredAtMs: now(), attemptId: null, provisioningAtMs: null});
    });
    return {deviceId: id, username, password, brokerHost, brokerPort, commandTopic, statusTopic};
  }
  return {claim, status, register, normalizeDeviceId};
}

module.exports = {createEnrollment, normalizeDeviceId, CLAIM_MS};

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
      const result = await service.register({deviceId: body.deviceId ?? body.device_id});
      return response.status(200).json(result);
    } catch (error) {
      const status = error?.publicCode === "unavailable" ? 503 : 400;
      return response.status(status).json({error: "registration_unavailable"});
    }
  };
}

module.exports.createRegistrationHandler = createRegistrationHandler;
