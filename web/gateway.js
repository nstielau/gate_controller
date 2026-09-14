import {initializeApp} from "firebase/app";
import {getAuth, onAuthStateChanged, GoogleAuthProvider, signInWithRedirect, getRedirectResult, signOut} from "firebase/auth";
import {getFunctions, httpsCallable} from "firebase/functions";
import {initializeAppCheck, ReCaptchaEnterpriseProvider} from "firebase/app-check";
import {firebaseConfig} from "./firebase-config.js";
import {appCheckSiteKey} from "./app-check-config.js";
import {AUTH_DOMAIN, canonicalAppUrl} from "./origin.mjs";
export async function createGateway() {
  const canonical = canonicalAppUrl(location.href);
  if (canonical) {
    location.replace(canonical);
    // Do not initialize auth or register a service worker on the old origin.
    return new Promise(() => {});
  }
  const app = initializeApp({...firebaseConfig, authDomain: AUTH_DOMAIN});
  initializeAppCheck(app, {provider: new ReCaptchaEnterpriseProvider(appCheckSiteKey), isTokenAutoRefreshEnabled: true});
  const auth = getAuth(app);
  await getRedirectResult(auth);
  const functions = getFunctions(app, "us-east1");
  const list = httpsCallable(functions, "listDevices", {timeout: 30000});
  const hold = httpsCallable(functions, "holdGate", {timeout: 30000});
  const rename = httpsCallable(functions, "renameGate", {timeout: 30000});
  return {
    adminSession: async () => (await httpsCallable(functions, "adminSession")({})).data,
    adminOverview: async () => (await httpsCallable(functions, "adminOverview")({})).data,
    adminChange: async data => (await httpsCallable(functions, "adminChange")(data)).data,
    onUser: callback => onAuthStateChanged(auth, callback),
    signIn: () => signInWithRedirect(auth, new GoogleAuthProvider()),
    signOut: () => signOut(auth),
    listDevices: async () => (await list({})).data,
    holdGate: async data => (await hold(data)).data,
    renameGate: async data => (await rename(data)).data
  };
}
