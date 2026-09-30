const {onCall, HttpsError} = require("firebase-functions/v2/https");
const {defineSecret} = require("firebase-functions/params");
const {initializeApp} = require("firebase-admin/app");
const {getFirestore} = require("firebase-admin/firestore");
const {getAuth} = require("firebase-admin/auth");
const {createDeviceAccess} = require("./device-access.cjs");
const {createEnrollment, createRegistrationHandler} = require("./enrollment.cjs");
const {createEmqxClient} = require("./emqx.cjs");
const {createController} = require("./controller.cjs");
const {createStore} = require("./store.cjs");
const {publishHold} = require("./mqtt.cjs");
initializeApp();
const username = defineSecret("MQTT_USERNAME");
const password = defineSecret("MQTT_PASSWORD");
const ca = defineSecret("MQTT_CA_PEM");
const emqxApiUrl = defineSecret("EMQX_API_URL");
const emqxAppId = defineSecret("EMQX_APP_ID");
const emqxAppSecret = defineSecret("EMQX_APP_SECRET");
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
const enrollment = createEnrollment({
  db: getFirestore(),
  broker: {
    provision: value => createEmqxClient({baseUrl: emqxApiUrl.value(), appId: emqxAppId.value(), appSecret: emqxAppSecret.value()}).provision(value),
    remove: usernameValue => createEmqxClient({baseUrl: emqxApiUrl.value(), appId: emqxAppId.value(), appSecret: emqxAppSecret.value()}).remove(usernameValue),
  },
});
exports.createDeviceClaim = onCall(options, callable(enrollment.claim));
exports.deviceClaimStatus = onCall(options, callable(enrollment.status));
exports.deviceRegister = onRequest({...options, enforceAppCheck: undefined, secrets: [emqxApiUrl, emqxAppId, emqxAppSecret]}, createRegistrationHandler(enrollment));

const {onRequest} = require("firebase-functions/v2/https");
const {getStorage} = require("firebase-admin/storage");
const {createAdministration, createDeviceService} = require("./administration.cjs");
const administration = createAdministration(getFirestore());
const deviceService = createDeviceService(getFirestore());
exports.adminSession = onCall(options, callable(administration.session));
exports.adminOverview = onCall(options, callable(administration.overview));
exports.adminChange = onCall(options, callable(administration.change));
const deviceAccess = createDeviceAccess({db: getFirestore(), auth: getAuth()});
exports.inviteDeviceUser = onCall(options, callable(deviceAccess.invite));
const {createFirmwareHandler} = require("./firmware-http.cjs");
exports.firmwareDevice = onRequest({...options, enforceAppCheck: undefined, cors: false},
  createFirmwareHandler(deviceService, getStorage().bucket("drawbridge-45487-firmware")));
