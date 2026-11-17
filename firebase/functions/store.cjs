const {canControl, fail} = require("./controller.cjs");
const {createHash} = require("node:crypto");
const {FieldValue} = require("firebase-admin/firestore");
function createStore(db) {
  return {
    async rename({uid, deviceId, name}) {
      const ref = db.doc(`devices/${deviceId}`);
      await db.runTransaction(async tx => {
        const doc = await tx.get(ref);
        if (!canControl(doc.data(), deviceId, uid)) fail("permission-denied", "You cannot rename this gate.");
        tx.update(ref, {name});
      });
    },
    async list(uid) {
      const result = await db.collection("devices").where("allowedUsers", "array-contains", uid).get();
      return result.docs.map(doc => ({...doc.data(), id: doc.id}));
    },
    async reserve({id, uid, deviceId, durationSeconds, time}) {
      const deviceRef = db.doc(`devices/${deviceId}`);
      const commandRef = db.doc(`commands/${id}`);
      return db.runTransaction(async tx => {
        const [deviceDoc, commandDoc] = await tx.getAll(deviceRef, commandRef);
        const device = deviceDoc.data();
        if (!canControl(device, deviceId, uid)) fail("permission-denied", "You cannot control this gate.");
        if (commandDoc.exists) {
          const command = commandDoc.data();
          if (command.uid !== uid || command.deviceId !== deviceId || command.durationSeconds !== durationSeconds) {
            fail("invalid-argument", "Request ID was already used for another command.");
          }
          return {fresh: false, status: command.status};
        }
        // The cooldown does not bound broker latency. Keep the one in-flight
        // pointer until its matching result finishes; another publish must not
        // replace it and hide pending delivery from a setup reset transaction.
        if (device.pendingCommandId != null) {
          fail("resource-exhausted", "A gate command is still pending. Check the gate before trying again.");
        }
        if (Number.isFinite(device.lastRequestedAtMs) && time - device.lastRequestedAtMs < 3000) {
          fail("resource-exhausted", "Please wait a few seconds before another command.");
        }
        tx.create(commandRef, {uid, deviceId, durationSeconds, status: "pending", createdAtMs: time});
        tx.update(deviceRef, {lastRequestedAtMs: time, pendingCommandId: id});
        return {fresh: true, topic: device.commandTopic};
      });
    },
    async finish({id, status, deviceId, durationSeconds, time}) {
      const commandRef = db.doc(`commands/${id}`);
      const deviceRef = db.doc(`devices/${deviceId}`);
      await db.runTransaction(async tx => {
        const [command, device] = await tx.getAll(commandRef, deviceRef);
        if (!command.exists || command.data().status !== "pending") return;
        tx.update(commandRef, {status, completedAtMs: time});
        if (status === "accepted" && command.data().durationSeconds > 0) {
          const previous = Number.isSafeInteger(device.data()?.holdCount) ? device.data().holdCount : 0;
          tx.update(deviceRef, {holdCount: previous + 1});
          // The reserved command supplies identity. The pending transition makes
          // all three counters atomic and idempotent, including transaction retries.
          const uid = command.data().uid;
          const person = createHash("sha256").update(uid).digest("hex");
          for (const path of [`usagePeople/${person}`, `devices/${deviceId}/usagePeople/${person}`]) {
            tx.set(db.doc(path), {uid, holdCount: FieldValue.increment(1)}, {merge: true});
          }
        }
        // A later command may already be in flight. Never let an older result
        // overwrite its visible hold state.
        if (!device.exists || device.data().pendingCommandId !== id) return;
        const activeHold = status === "accepted" && durationSeconds > 0
          ? {startedAtMs: time, durationSeconds} : null;
        tx.update(deviceRef, {activeHold, pendingCommandId: null});
      });
    }
  };
}
module.exports = {createStore};
