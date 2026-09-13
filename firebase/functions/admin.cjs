// Local IAM-authorized administration. Excluded from Functions deployment.
const {execFileSync} = require("node:child_process");
const {Firestore, FieldValue} = require("@google-cloud/firestore");
const {OAuth2Client} = require("google-auth-library");
const [action, email, deviceId = "b3640c"] = process.argv.slice(2);
if (!["grant", "revoke", "enable", "disable"].includes(action) || !email || !/^[a-z0-9-]{1,64}$/.test(deviceId)) {
  console.error("Usage: node firebase/functions/admin.cjs grant|revoke|enable|disable EMAIL [DEVICE_ID]");
  process.exit(1);
}
if (process.env.FIRESTORE_EMULATOR_HOST || process.env.FIREBASE_AUTH_EMULATOR_HOST) throw new Error("Unset emulator variables before administering production");
const accessToken = execFileSync("gcloud", ["auth", "print-access-token", "--account", "nick.stielau@gmail.com"], {encoding: "utf8"}).trim();
const authClient = new OAuth2Client();
authClient.setCredentials({access_token: accessToken});
authClient.quotaProjectId = "drawbridge-45487";
async function authRequest(path, data) {
  const response = await fetch("https://identitytoolkit.googleapis.com/v1/projects/drawbridge-45487/" + path, {
    method: "POST", headers: {Authorization: "Bearer " + accessToken, "Content-Type": "application/json", "x-goog-user-project": "drawbridge-45487"},
    body: JSON.stringify(data), signal: AbortSignal.timeout(15000)
  });
  const body = await response.json();
  if (!response.ok) throw new Error("Authentication API: " + response.status + " " + body.error?.status);
  return body;
}
(async () => {
  const db = new Firestore({projectId: "drawbridge-45487", authClient});
  const ref = db.doc("devices/" + deviceId);
  if (action === "enable" || action === "disable") {
    await ref.update({enabled: action === "enable"});
  } else {
    const found = await authRequest("accounts:lookup", {email: [email]});
    let uid = found.users?.[0]?.localId;
    if (!uid) {
      if (action !== "grant") throw new Error("User does not exist");
      // Reserve this email's UID. Verification and Google sign-in still occur at login.
      uid = (await authRequest("accounts", {email, emailVerified: false})).localId;
    }
    if (!uid) throw new Error("No user ID returned");
    await db.runTransaction(async tx => {
      const doc = await tx.get(ref);
      if (!doc.exists && action === "revoke") throw new Error("Device does not exist");
      if (!doc.exists) tx.create(ref, {name: "Gate " + deviceId, enabled: true, commandTopic: "gate/v1/devices/" + deviceId + "/command", allowedUsers: [uid]});
      else tx.update(ref, {allowedUsers: action === "grant" ? FieldValue.arrayUnion(uid) : FieldValue.arrayRemove(uid)});
    });
  }
  console.log(action + " completed for " + deviceId);
  await db.terminate();
})().catch(error => { console.error("Administration failed:", error.code || "unknown error", String(error.message).replaceAll(accessToken, "[redacted]")); process.exitCode = 1; });
