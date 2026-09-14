import {createAdminView} from "./admin.js";
import {createGateway} from "./gateway.js";
const $ = selector => document.querySelector(selector);
const state = $("#user-state"), controls = $("#controls"), result = $("#result");
const buttons = [...document.querySelectorAll("[data-duration]")];
let gateway, user, busy = false, devices = [], generation = 0;
let savingNickname = false;
let countdownTimer;
const adminView = createAdminView({gateway: () => gateway, onClose: () => { controls.hidden = !user || !devices.length; }});
$("#admin-open").onclick = async () => {
  closeAccountMenu(); controls.hidden = true; state.hidden = true;
  try { await adminView.open(); } catch (error) { result.textContent = error.message; }
};
function showLoading(message) {
  $("#loading-message").textContent = message;
  $("#loading-state").hidden = false;
  state.hidden = true;
}
function hideLoading() { $("#loading-state").hidden = true; }
function showProfile(nextUser) {
  const photo = $("#profile-photo");
  const initial = $("#profile-initial");
  const url = typeof nextUser?.photoURL === "string" ? nextUser.photoURL : "";
  photo.hidden = !url;
  initial.hidden = !!url;
  if (url) photo.src = url;
  else photo.removeAttribute("src");
  if (!url && nextUser?.email) initial.textContent = nextUser.email.slice(0, 1).toUpperCase();
}
function closeNickname() {
  $("#nickname-form").hidden = true;
  $("#nickname-result").textContent = "";
}
function closeAccountMenu() {
  closeNickname();
  $("#account-dropdown").hidden = true;
  $("#account-menu-button").setAttribute("aria-expanded", "false");
}
function toggleAccountMenu() {
  const open = $("#account-dropdown").hidden;
  $("#account-dropdown").hidden = !open;
  $("#account-menu-button").setAttribute("aria-expanded", String(open));
  if (!open) closeNickname();
}
function activeHoldForSelectedGate() {
  return devices.find(device => device.id === $("#device").value)?.hold || null;
}
function renderDeviceMetric() {
  const device = devices.find(item => item.id === $("#device").value);
  const metric = $("#device-metric");
  if (!device) { metric.textContent = ""; return; }
  const count = Number.isSafeInteger(device.holdCount) && device.holdCount >= 0 ? device.holdCount : 0;
  metric.textContent = `${count} hold${count === 1 ? "" : "s"} issued`;
}
function formatRemaining(milliseconds) {
  const seconds = Math.ceil(milliseconds / 1000);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = seconds % 60;
  return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`
    : `${minutes}:${String(rest).padStart(2, "0")}`;
}
function renderHold() {
  const hold = activeHoldForSelectedGate();
  const countdown = $("#hold-countdown");
  buttons.forEach(button => { button.classList.remove("hold-active"); button.style.removeProperty("--hold-progress"); });
  if (!hold) { countdown.hidden = true; return; }
  const durationMs = hold.durationSeconds * 1000;
  const remainingMs = hold.startedAtMs + durationMs - Date.now();
  if (remainingMs <= 0) {
    const device = devices.find(item => item.id === $("#device").value);
    if (device) device.hold = null;
    countdown.hidden = true;
    return;
  }
  const button = buttons.find(item => Number(item.dataset.duration) === hold.durationSeconds);
  if (!button) { countdown.hidden = true; return; }
  const progress = Math.min(100, Math.max(0, (1 - remainingMs / durationMs) * 100));
  button.classList.add("hold-active");
  button.style.setProperty("--hold-progress", progress.toFixed(4));
  countdown.hidden = false;
  countdown.textContent = `${formatRemaining(remainingMs)} remaining`;
}
function startCountdown() {
  clearInterval(countdownTimer);
  renderHold();
  renderDeviceMetric();
  countdownTimer = setInterval(renderHold, 1000);
}
function render() {
  const online = navigator.onLine;
  $("#offline").hidden = online;
  $("#connection").hidden = online && !busy && !!user;
  $("#connection").textContent = !online ? "Offline" : busy ? "Sending" : "Connecting";
  const working = busy || savingNickname;
  buttons.forEach(button => { button.disabled = !online || !user || working || !devices.length; });
  $("#device").disabled = working;
  $("#rename").disabled = !online || !user || working || !devices.length;
  $("#nickname").disabled = savingNickname;
  $("#nickname-save").disabled = !online || !user || working;
  $("#nickname-cancel").disabled = savingNickname;
  $("#sign-in").disabled = !online || !gateway;
  $("#account-menu-button").disabled = working;
  $("#sign-out").disabled = working;
  $("#refresh").disabled = working || !online;
  $("#update").disabled = working;
  renderHold();
}
async function loadDevices() {
  closeNickname();
  adminView.close();
  $("#admin-open").hidden = true;
  const current = ++generation;
  devices = [];
  controls.hidden = true;
  render();
  if (!user) { hideLoading(); return; }
  showLoading("Loading devices");
  try {
    const response = await gateway.listDevices();
    if (current !== generation) return;
    devices = response.devices;
    // A role lookup failure must not prevent ordinary gate control.
    gateway.adminSession().then(session => {
      if (current === generation) $("#admin-open").hidden = !session.isAdmin;
    }).catch(() => {});
    const previousId = $("#device").value;
    $("#device").replaceChildren(...devices.map(device => new Option(device.name, device.id)));
    if (devices.some(device => device.id === previousId)) $("#device").value = previousId;
    controls.hidden = devices.length === 0;
    state.hidden = devices.length > 0;
    state.textContent = devices.length ? "" : "No gate access yet. Ask the administrator to add " + user.email + ".";
  } catch (error) {
    if (current !== generation) return;
    state.hidden = false;
    state.textContent = "Couldn't load gate access.";
    result.textContent = error.message || "Reconnect and refresh access.";
  } finally { if (current === generation) hideLoading(); }
  render();
}
$("#account-menu-button").onclick = toggleAccountMenu;
$("#refresh").onclick = () => { closeAccountMenu(); loadDevices(); };
$("#device").onchange = () => { closeNickname(); renderHold(); renderDeviceMetric(); };
$("#rename").onclick = () => {
  const device = devices.find(d => d.id === $("#device").value);
  if (!device) return;
  $("#nickname").value = device.name;
  $("#nickname-form").hidden = false;
  $("#nickname-result").textContent = "";
  $("#nickname").focus();
  $("#nickname").select();
};
$("#nickname-cancel").onclick = () => { closeNickname(); $("#rename").focus(); };
$("#nickname-form").onsubmit = async event => {
  event.preventDefault();
  if (busy || savingNickname || !navigator.onLine || !user || !devices.length) return;
  const deviceId = $("#device").value, nickname = $("#nickname").value.trim();
  if (!nickname) { $("#nickname-result").textContent = "Enter a nickname."; return; }
  const current = generation;
  savingNickname = true;
  $("#nickname-result").textContent = "Saving…";
  render();
  try {
    const updated = await gateway.renameGate({deviceId, nickname});
    if (current !== generation) return;
    const device = devices.find(d => d.id === updated.id);
    if (device) device.name = updated.name;
    const option = [...$("#device").options].find(o => o.value === updated.id);
    if (option) option.textContent = updated.name;
    closeAccountMenu();
    result.textContent = "Gate nickname saved.";
  } catch {
    if (current === generation) $("#nickname-result").textContent = "Couldn't save the nickname. Refresh access to check it, or try again.";
  } finally { savingNickname = false; render(); }
};
$("#sign-in").onclick = async () => {
  try { await gateway.signIn(); }
  catch { result.textContent = "Couldn't start Google sign-in. Please try again."; }
};
$("#sign-out").onclick = async () => {
  try { closeAccountMenu(); await gateway.signOut(); result.textContent = ""; }
  catch { result.textContent = "Couldn't sign out. Please try again."; }
};
buttons.forEach(button => { button.onclick = async () => {
  if (busy || savingNickname || !navigator.onLine || !user || !devices.length) return;
  const durationSeconds = Number(button.dataset.duration);
  if (durationSeconds === 21600 && !window.confirm("Hold this gate open for 6 hours?")) return;
  const data = {deviceId: $("#device").value, durationSeconds, requestId: crypto.randomUUID(), issuedAtMs: Date.now()};
  busy = true;
  result.textContent = "Sending command…";
  render();
  try {
    const response = await gateway.holdGate(data);
    const device = devices.find(item => item.id === data.deviceId);
    if (device) device.hold = response.status === "accepted" ? response.hold || null : null;
    renderHold();
    result.textContent = response.status === "accepted"
      ? (durationSeconds === 0 ? "End-hold command accepted by broker." : "Hold command accepted by broker.") + " Gate movement is not confirmed."
      : "Delivery is uncertain. Check the gate before sending another command.";
  } catch (error) {
    const rejected = ["permission-denied", "unauthenticated", "invalid-argument", "failed-precondition", "resource-exhausted"]
      .some(code => error.code === "functions/" + code);
    result.textContent = rejected ? error.message : "Delivery is uncertain. Check the gate before sending another command.";
  } finally { busy = false; render(); }
}; });
window.addEventListener("online", render);
window.addEventListener("offline", render);
render();
try {
  gateway = await createGateway();
  gateway.onUser(next => {
    adminView.close();
    $("#admin-open").hidden = true;
    user = next;
    document.querySelector("main").classList.toggle("authenticated", !!user);
    showProfile(user);
    result.textContent = "";
    $("#signed-out-hero").hidden = !!user;
    $("#account-menu-button").hidden = !user;
    if (!user) closeAccountMenu();
    if (!user) { ++generation; devices = []; controls.hidden = true; hideLoading(); state.hidden = false; state.textContent = "Sign in to control your gate."; render(); }
    else loadDevices();
  });
  render();
} catch {
  hideLoading();
  state.hidden = false;
  state.textContent = "Secure connection couldn't start. Reconnect and reload.";
}
document.addEventListener("click", event => {
  if (!$(".account-menu").contains(event.target)) closeAccountMenu();
});
document.addEventListener("keydown", event => {
  if (event.key === "Escape" && !$("#account-dropdown").hidden) {
    closeAccountMenu();
    $("#account-menu-button").focus();
  }
});
startCountdown();
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/service-worker.js", {updateViaCache: "none"}).then(async registration => {
    const offerUpdate = () => {
      if (!registration.waiting || !navigator.serviceWorker.controller) return;
      $("#update").hidden = false;
      $("#update").onclick = () => { if (!busy && !savingNickname) { registration.waiting.postMessage("activate"); } };
    };
    offerUpdate();
    registration.addEventListener("updatefound", () => {
      registration.installing?.addEventListener("statechange", offerUpdate);
    });
    navigator.serviceWorker.addEventListener("controllerchange", () => location.reload());
    // Ask for a fresh worker on every launch. This matters for installed mobile
    // apps, which otherwise can remain on an old shell for longer than Safari.
    await registration.update();
    offerUpdate();
  }).catch(() => {});
}
