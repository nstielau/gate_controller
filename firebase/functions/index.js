const {onCall, HttpsError} = require("firebase-functions/v2/https");
const {defineSecret} = require("firebase-functions/params");
const {initializeApp} = require("firebase-admin/app");
const {getFirestore} = require("firebase-admin/firestore");
const {createController} = require("./controller.cjs");
const {createStore} = require("./store.cjs");
const {publishHold} = require("./mqtt.cjs");
initializeApp();
const username = defineSecret("MQTT_USERNAME");
const password = defineSecret("MQTT_PASSWORD");
const ca = defineSecret("MQTT_CA_PEM");
const controller = createController({
  store: createStore(getFirestore()),
  publish: (topic, payload) => publishHold(topic, payload, {
    username: username.value(), password: password.value(), ca: ca.value()
  })
});
const options = {
  region: "us-east1", enforceAppCheck: true, maxInstances: 2,
  minInstances: 0, timeoutSeconds: 30, memory: "256MiB",
  serviceAccount: "drawbridge-functions@drawbridge-45487.iam.gserviceaccount.com",
  cors: ["https://drawbridge-45487.web.app", "https://drawbridge-45487.firebaseapp.com"]
};
function callable(handler) {
  return async request => {
    try { return await handler(request); }
    catch (error) {
      if (error.publicCode) throw new HttpsError(error.publicCode, error.message);
      console.error("Drawbridge request failed", {code: "internal"});
      throw new HttpsError("internal", "Request could not be completed. Check the gate before trying again.");
    }
  };
}
exports.listDevices = onCall(options, callable(controller.listDevices));
exports.renameGate = onCall(options, callable(controller.renameGate));
exports.holdGate = onCall({...options, secrets: [username, password, ca]}, callable(controller.holdGate));
