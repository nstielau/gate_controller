const {emailAddress, hash} = require("./administration.cjs");
const {userId, publicHoldCount, fail} = require("./controller.cjs");
const LIMIT = 200;
const DEVICE = /^[a-z0-9-]{1,64}$/;
function text(value, length) {
  return typeof value === "string" && value.trim() ? value.slice(0, length) : null;
}
function createStatistics({db, auth}) {
  return {
    async read(request) {
      userId(request);
      const email = emailAddress(request.auth.token.email);
      const data = request.data === undefined ? {} : request.data;
      if (!data || typeof data !== "object" || Array.isArray(data) ||
          Object.keys(data).some(key => key !== "deviceId") ||
          (Object.hasOwn(data, "deviceId") && (typeof data.deviceId !== "string" || !DEVICE.test(data.deviceId)))) {
        fail("invalid-argument", "Invalid statistics request.");
      }
      const adminRef = db.doc("admins/" + hash(email));
      async function requireAdmin(tx) {
        if (!(await tx.get(adminRef)).exists) fail("permission-denied", "Administrator access required.");
      }
      const result = await db.runTransaction(async tx => {
        await requireAdmin(tx);
        if (!data.deviceId) {
          const snapshot = await tx.get(db.collection("devices").limit(LIMIT + 1));
          const devices = snapshot.docs.slice(0, LIMIT).map(doc => ({
            id: doc.id, name: text(doc.data().name, 80) || doc.id, holdCount: publicHoldCount(doc.data().holdCount)
          }));
          devices.sort((a, b) => a.name.localeCompare(b.name) || a.id.localeCompare(b.id));
          return {devices, truncated: snapshot.docs.length > LIMIT};
        }
        const deviceRef = db.doc("devices/" + data.deviceId);
        if (!(await tx.get(deviceRef)).exists) fail("not-found", "Device not found.");
        const snapshot = await tx.get(db.collection(deviceRef.path + "/usagePeople").orderBy("holdCount", "desc").limit(LIMIT + 1));
        // Only an exact private UID/hash binding may be resolved to an identity.
        const people = snapshot.docs.slice(0, LIMIT).filter(doc => {
          const uid = doc.data().uid;
          return typeof uid === "string" && uid.length > 0 && uid.length <= 128 && doc.id === hash(uid);
        }).map(doc => ({id: doc.id, uid: doc.data().uid, holdCount: publicHoldCount(doc.data().holdCount)}));
        people.sort((a, b) => b.holdCount - a.holdCount || a.id.localeCompare(b.id));
        return {deviceId: data.deviceId, people, truncated: snapshot.docs.length > LIMIT};
      });
      if (!result.people) return result;
      const identities = new Map();
      // Firebase Auth permits at most 100 identifiers per call. Keep external
      // requests outside the transaction so retries cannot repeat them.
      for (let start = 0; start < result.people.length; start += 100) {
        const batch = result.people.slice(start, start + 100).map(({uid}) => ({uid}));
        const resolved = await auth.getUsers(batch);
        const missing = new Set(resolved.notFound.map(({uid}) => uid));
        const users = new Map(resolved.users.map(user => [user.uid, user]));
        for (const {uid} of batch) {
          if (!users.has(uid) && !missing.has(uid)) throw new Error("Incomplete identity lookup.");
          identities.set(uid, users.get(uid));
        }
      }
      if (result.people.length) await db.runTransaction(requireAdmin);
      return {
        deviceId: result.deviceId,
        people: result.people.map(({id, uid, holdCount}) => ({
          id, name: text(identities.get(uid)?.displayName, 80), email: text(identities.get(uid)?.email, 254), holdCount
        })),
        truncated: result.truncated
      };
    }
  };
}
module.exports = {createStatistics};
