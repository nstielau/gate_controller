const {emailAddress, hash} = require("./administration.cjs");
const {userId, canControl, fail} = require("./controller.cjs");

function createDeviceAccess({db, auth, now = Date.now}) {
  return {
    async invite(request) {
      const uid = userId(request);
      const {deviceId, requestId, issuedAtMs} = request.data || {};
      const email = emailAddress(typeof request.data?.email === "string" ? request.data.email.trim() : null);
      if (typeof deviceId !== "string" || !/^[a-z0-9-]{1,64}$/.test(deviceId) ||
          typeof requestId !== "string" || !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(requestId) ||
          !Number.isSafeInteger(issuedAtMs)) fail("invalid-argument", "Invalid invitation request.");
      function checkFreshness() {
        const time = now();
        if (time - issuedAtMs > 60000 || issuedAtMs - time > 10000) fail("failed-precondition", "Request expired. Refresh and try again.");
      }
      checkFreshness();
      const deviceRef = db.doc("devices/" + deviceId);
      const auditRef = db.doc("deviceAccessAudit/" + hash(uid + ":" + requestId.toLowerCase()));
      const record = {actor: uid, action: "inviteDeviceUser", deviceId, email};
      const fingerprint = hash(JSON.stringify(record));
      async function checkAccess(tx) {
        checkFreshness();
        const device = (await tx.get(deviceRef)).data();
        if (!canControl(device, deviceId, uid)) fail("permission-denied", "You cannot invite users to this device. Refresh access.");
        const audit = await tx.get(auditRef);
        if (audit.exists && audit.data().fingerprint !== fingerprint) fail("invalid-argument", "Request ID reused.");
        return {device, complete: audit.exists};
      }
      // Check authorization before looking up or reserving any Auth account.
      if ((await db.runTransaction(checkAccess)).complete) return {ok: true, email, deviceId};
      let recipient;
      try { recipient = await auth.getUserByEmail(email); }
      catch (error) {
        if (error.code !== "auth/user-not-found") throw error;
        try { recipient = await auth.createUser({email, emailVerified: false}); }
        catch (creationError) {
          if (creationError.code !== "auth/email-already-exists") throw creationError;
          recipient = await auth.getUserByEmail(email);
        }
      }
      if (recipient.disabled) fail("failed-precondition", "This account cannot receive device access.");
      // Auth calls stay outside retryable transactions. Recheck access to the
      // device at the actual write, preserving concurrent grants and revocations.
      await db.runTransaction(async tx => {
        const {device, complete} = await checkAccess(tx);
        if (complete) return;
        const allowedUsers = [...new Set([...device.allowedUsers, recipient.uid])];
        tx.update(deviceRef, {allowedUsers});
        tx.create(auditRef, {...record, recipientUid: recipient.uid, fingerprint, atMs: now()});
      });
      return {ok: true, email, deviceId};
    }
  };
}
module.exports = {createDeviceAccess};
