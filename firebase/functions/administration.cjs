const {createHash, timingSafeEqual} = require("node:crypto");
const {userId, fail} = require("./controller.cjs");
const {supportsRestartSetupVersion} = require("./enrollment.cjs");
const {observation, publicReport, lastSeen} = require("./device-observation.cjs");
const OWNER = "nick.stielau@gmail.com";
const hash = value => createHash("sha256").update(value).digest("hex");
const DEVICE = /^[a-z0-9-]{1,64}$/;
const VERSION = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;
function emailAddress(value) {
  if (typeof value !== "string" || value.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) fail("invalid-argument", "Enter a valid Google account email.");
  return value.toLowerCase();
}
function actor(request) {
  const uid = userId(request);
  return {uid, email: emailAddress(request.auth.token.email)};
}
function validateManifest(m) {
  if (!m || m.schema !== 1 || !VERSION.test(m.app_version) || m.app_api_version !== 1 ||
      m.minimum_bootstrap_version !== "1.0.0" || m.circuitpython_major !== 10 ||
      !Array.isArray(m.supported_board_ids) || m.supported_board_ids.length !== 1 ||
      m.supported_board_ids[0] !== "seeed_xiao_esp32_s3_sense" ||
      !Number.isInteger(m.size) || m.size < 1 || m.size > 65536 ||
      !/^[a-f0-9]{64}$/.test(m.sha256) || !/^[a-f0-9]{40}$/.test(m.git_commit) ||
      m.artifact_object !== `firmware/${m.app_version}/${m.sha256}/drawbridge.py`) {
    fail("invalid-argument", "Invalid or incompatible firmware manifest.");
  }
  return Object.fromEntries(["schema", "app_version", "app_api_version", "minimum_bootstrap_version", "circuitpython_major", "supported_board_ids", "size", "sha256", "git_commit", "artifact_object"].map(k => [k, m[k]]));
}
function publicMaintenance(value) {
  if (!value || typeof value !== "object") return null;
  return {
    supportsRestartSetup: value.supportsRestartSetup === true && supportsRestartSetupVersion(value.baseVersion),
    lastSeenAtMs: Number.isSafeInteger(value.lastSeenAtMs) ? value.lastSeenAtMs : null,
    appVersion: typeof value.appVersion === "string" && VERSION.test(value.appVersion) ? value.appVersion : null,
    baseVersion: typeof value.baseVersion === "string" && VERSION.test(value.baseVersion) ? value.baseVersion : null,
  };
}
function publicSetupReset(value) {
  if (!value || !["pending", "awaiting_setup", "provisioning", "complete"].includes(value.state)) return null;
  const result = {state: value.state};
  for (const key of ["requestedAtMs", "acknowledgedAtMs", "provisioningAtMs", "completedAtMs"]) {
    if (Number.isSafeInteger(value[key])) result[key] = value[key];
  }
  return result;
}
function createAdministration(db, now = Date.now) {
  const adminRef = email => db.doc("admins/" + hash(email));
  async function requireAdmin(tx, identity) {
    if (!(await tx.get(adminRef(identity.email))).exists) fail("permission-denied", "Administrator access required.");
  }
  return {
    async session(request) {
      const identity = actor(request);
      return {isAdmin: (await adminRef(identity.email).get()).exists};
    },
    async overview(request) {
      const identity = actor(request);
      return db.runTransaction(async tx => {
        await requireAdmin(tx, identity);
        const [admins, devices, releases] = await Promise.all([
          tx.get(db.collection("admins").limit(200)),
          tx.get(db.collection("devices").limit(200)),
          tx.get(db.collection("firmwareReleases").limit(200))
        ]);
        return {
          admins: admins.docs.map(d => ({email: d.data().email, owner: d.data().email === OWNER})),
          devices: devices.docs.map(d => ({id: d.id, name: d.data().name || d.id,
            enabled: d.data().enabled === true, otaEnrolled: !!d.data().otaCredentialHash,
            target: d.data().firmwareTarget || null, reported: publicReport(d.data().reportedFirmware), observation: observation(d.data()),
            maintenance: publicMaintenance(d.data().maintenance), setupReset: publicSetupReset(d.data().setupReset)})),
          releases: releases.docs.filter(d => d.data().approved === true).map(d => ({version: d.id, sha256: d.data().sha256}))
        };
      });
    },
    async change(request) {
      const identity = actor(request), data = request.data || {}, time = now();
      if (JSON.stringify(data).length > 2048 || !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(data.requestId || "") || !Number.isSafeInteger(data.issuedAtMs) ||
          time - data.issuedAtMs > 60000 || data.issuedAtMs - time > 10000) fail("invalid-argument", "Request expired or invalid. Refresh and try again.");
      if (!["grantAdmin", "revokeAdmin", "targetFirmware", "pauseFirmware", "restartSetup"].includes(data.action)) fail("invalid-argument", "Unknown administrator action.");
      const email = data.action.endsWith("Admin") ? emailAddress(data.email) : null;
      if (data.action === "revokeAdmin" && email === OWNER) fail("failed-precondition", "The owner cannot be removed here.");
      if (!email && !DEVICE.test(data.deviceId || "")) fail("invalid-argument", "Invalid device.");
      if (data.action === "targetFirmware" && !VERSION.test(data.version || "")) fail("invalid-argument", "Choose an approved release.");
      const record = {actor: identity.uid, email, action: data.action, deviceId: data.deviceId || null, version: data.version || null};
      const audit = db.doc("adminAudit/" + hash(identity.uid + ":" + data.requestId));
      return db.runTransaction(async tx => {
        await requireAdmin(tx, identity);
        const existing = await tx.get(audit);
        if (existing.exists) {
          if (existing.data().fingerprint !== hash(JSON.stringify(record))) fail("invalid-argument", "Request ID reused.");
          return {ok: true};
        }
        let deviceRef, device, release;
        if (!email) {
          deviceRef = db.doc("devices/" + data.deviceId);
          device = (await tx.get(deviceRef)).data();
          if (!device) fail("not-found", "Device not found.");
          if (data.action === "targetFirmware") {
            release = (await tx.get(db.doc("firmwareReleases/" + data.version))).data();
            if (!release?.approved || !device.enabled || !device.otaCredentialHash) fail("failed-precondition", "Device must be enabled and enrolled; release must be approved.");
            validateManifest(release);
          }
        }
        if (data.action === "restartSetup") {
          const binding = (await tx.get(db.doc("devicePairingBindings/" + data.deviceId))).data();
          const enrollment = (await tx.get(db.doc("deviceEnrollments/" + data.deviceId))).data();
          const active = device.activeHold;
          if (!device.enabled || device.enrollmentState !== "registered" || enrollment?.state !== "registered" ||
              !/^[a-f0-9]{64}$/.test(binding?.pairingCode || "") || enrollment.claimKey !== hash(data.deviceId + ":" + binding.pairingCode) ||
              !["iv", "tag", "ciphertext"].every(key => typeof enrollment.envelope?.[key] === "string" && enrollment.envelope[key]) ||
              device.commandTopic !== `gate/v1/devices/${data.deviceId}/command` || device.statusTopic !== `gate/v1/devices/${data.deviceId}/status` ||
              device.maintenance?.supportsRestartSetup !== true || !supportsRestartSetupVersion(device.maintenance?.baseVersion) ||
              (device.setupReset && device.setupReset.state !== "complete")) fail("failed-precondition", "Device must be registered and support restarting setup. A USB update may be required.");
          if (device.pendingCommandId || (Number.isSafeInteger(active?.startedAtMs) && Number.isFinite(active?.durationSeconds) &&
              active.durationSeconds > 0 && active.startedAtMs + active.durationSeconds * 1000 > time)) fail("failed-precondition", "Wait until the device has no active or pending hold before restarting setup.");
        }
        if (data.action === "grantAdmin") tx.set(adminRef(email), {email, grantedBy: identity.uid, grantedAtMs: time});
        if (data.action === "revokeAdmin") tx.delete(adminRef(email));
        if (data.action === "restartSetup") {
          tx.update(deviceRef, {enabled: false, setupReset: {id: audit.path.split("/").pop(), state: "pending", requestedAtMs: time, actor: identity.uid}});
        } else if (deviceRef) {
          const sequence = (device.firmwareTarget?.sequence || 0) + 1;
          if (!Number.isSafeInteger(sequence)) fail("failed-precondition", "Deployment sequence exhausted.");
          tx.update(deviceRef, {firmwareTarget: {version: release ? data.version : null, sequence, enabled: !!release}});
        }
        tx.create(audit, {...record, atMs: time, fingerprint: hash(JSON.stringify(record))});
        return {ok: true};
      });
    }
  };
}
function createDeviceService(db, now = Date.now) {
  return {
    async authorize(deviceId, token, operation) {
      if (!DEVICE.test(deviceId || "") || !/^[a-f0-9]{64}$/.test(token || "")) fail("unauthenticated", "Device authentication required.");
      return db.runTransaction(async tx => {
        const ref = db.doc("devices/" + deviceId), device = (await tx.get(ref)).data();
        const expected = device?.otaCredentialHash;
        if (!device?.enabled || !/^[a-f0-9]{64}$/.test(expected || "") || !timingSafeEqual(Buffer.from(hash(token), "hex"), Buffer.from(expected, "hex"))) fail("unauthenticated", "Device authentication required.");
        const stamp = `otaLast${operation}AtMs`, time = now();
        if (time - (device[stamp] || 0) < 10000) fail("resource-exhausted", "Try later.");
        tx.update(ref, {[stamp]: time, lastSeenAtMs: lastSeen(device.lastSeenAtMs, time)});
        return device;
      });
    },
    async manifest(device) {
      const target = device.firmwareTarget;
      if (!target?.enabled) return null;
      const release = (await db.doc("firmwareReleases/" + target.version).get()).data();
      if (!release?.approved) return null;
      return {...validateManifest(release), sequence: target.sequence};
    },
    async report(deviceId, value) {
      if (!value || !["current", "trial", "rolled_back", "error", "disabled"].includes(value.state) ||
          !VERSION.test(value.version || "") || !Number.isSafeInteger(value.sequence) || value.sequence < 0 ||
          (value.reason !== undefined && !/^[a-z_]{1,40}$/.test(value.reason)) ||
          (value.base_version !== undefined && (typeof value.base_version !== "string" || !VERSION.test(value.base_version)))) fail("invalid-argument", "Invalid firmware report.");
      const ref = db.doc("devices/" + deviceId), time = now();
      await db.runTransaction(async tx => {
        const device = (await tx.get(ref)).data();
        const update = {lastSeenAtMs: lastSeen(device?.lastSeenAtMs, device?.reportedFirmware?.atMs, time)};
        if ((lastSeen(device?.reportedFirmware?.atMs) || 0) <= time) {
          update.reportedFirmware = {
            state: value.state, version: value.version, base_version: value.base_version || null, sequence: value.sequence,
            reason: value.reason || null, atMs: time
          };
        }
        tx.update(ref, update);
      });
    }
  };
}
module.exports = {createAdministration, createDeviceService, validateManifest, hash, OWNER, emailAddress};
