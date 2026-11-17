// Loaded UI receives only allowlisted server fields; never receives OTA credentials.
export function createAdminView({gateway, onClose}) {
  const root = document.querySelector("#admin-view"), output = document.querySelector("#admin-result");
  let epoch = 0, refreshEpoch = 0, working = false;
  let refreshTimer, pendingSetup = false;
  const setupStates = new Set(["pending", "awaiting_setup", "provisioning"]);
  function stopPolling() { clearTimeout(refreshTimer); refreshTimer = undefined; }
  function schedulePolling() {
    stopPolling();
    if (root.hidden || working || !navigator.onLine || !pendingSetup) return;
    const current = epoch;
    refreshTimer = setTimeout(async () => {
      const request = refreshEpoch + 1;
      try { await refresh(); }
      catch { if (current === epoch && request === refreshEpoch && !root.hidden && navigator.onLine) output.textContent = "Couldn't refresh setup status. Reconnect or refresh administration."; }
      finally { if (current === epoch && request === refreshEpoch) schedulePolling(); }
    }, 5000);
  }
  function setupStatus(device) {
    const state = device.setupReset?.state;
    if (state === "pending") {
      const seen = device.maintenance?.lastSeenAtMs;
      const recentlyOnline = Number.isFinite(seen) && Date.now() - seen <= 60000 && seen <= Date.now() + 10000;
      return recentlyOnline ? "Restart setup queued. The device will apply it when idle." : "Restart setup queued. Waiting for the device to reconnect.";
    }
    if (state === "awaiting_setup") return "Set up Wi-Fi on the device, then scan its QR code to register again. Existing access is preserved.";
    if (state === "provisioning") return "Setting up the device. Waiting for the device to confirm connection.";
    if (state === "complete") return "Setup complete. The device confirmed registration.";
    return "";
  }
  function appendSetup(card, device) {
    const status = setupStatus(device);
    if (status) { const message = element("p", status); message.className = "setup-status"; message.setAttribute("role", "status"); card.append(message); }
    if (device.maintenance?.supportsRestartSetup !== true) {
      card.append(element("p", "USB update required to restart setup on this device."));
      return;
    }
    const restart = element("button", "Restart setup"); restart.type = "button";
    restart.dataset.unavailable = String(!device.enabled || setupStates.has(device.setupReset?.state));
    restart.onclick = () => {
      if (working || !navigator.onLine || restart.dataset.unavailable === "true") return;
      if (confirm(`Restart setup for ${device.name}? This clears saved Wi-Fi and MQTT settings on the device. Its identity and access stay the same. Set up Wi-Fi on the device and scan its QR code again. The device applies this when idle.`)) {
        change({action: "restartSetup", deviceId: device.id});
      }
    };
    card.append(restart);
  }
  const element = (tag, text) => { const node = document.createElement(tag); node.textContent = text; return node; };
  const tabs = [...root.querySelectorAll('[role="tab"]')];
  function selectTab(selected) {
    tabs.forEach(tab => {
      const active = tab === selected;
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
      document.getElementById(tab.getAttribute("aria-controls")).hidden = !active;
    });
  }
  tabs.forEach((tab, index) => {
    tab.onclick = () => selectTab(tab);
    tab.onkeydown = event => {
      const next = {ArrowRight: (index + 1) % tabs.length, ArrowLeft: (index + tabs.length - 1) % tabs.length, Home: 0, End: tabs.length - 1}[event.key];
      if (next === undefined) return;
      event.preventDefault();
      selectTab(tabs[next]); tabs[next].focus();
    };
  });
  function lock(value) {
    working = value;
    root.querySelectorAll('button:not([role="tab"]),input,select').forEach(n => { n.disabled = value || !navigator.onLine || n.dataset.unavailable === "true"; });
  }
  async function change(data) {
    if (working || !navigator.onLine || root.hidden) return;
    stopPolling(); ++refreshEpoch;
    const current = epoch;
    lock(true); output.textContent = "Saving…";
    try {
      await gateway().adminChange({...data, requestId: crypto.randomUUID(), issuedAtMs: Date.now()});
      if (epoch !== current) return;
      await refresh();
      if (epoch === current) output.textContent = data.action === "restartSetup" ? "Restart setup requested. Check the device status below." : "Saved.";
    } catch {
      if (epoch === current) output.textContent = "Couldn't confirm this change. Refresh to check its status.";
    } finally { if (epoch === current) { lock(false); schedulePolling(); } }
  }
  async function refresh() {
    const current = epoch, request = ++refreshEpoch;
    const data = await gateway().adminOverview();
    if (current !== epoch || request !== refreshEpoch || root.hidden || !navigator.onLine) return;
    pendingSetup = data.devices.some(device => setupStates.has(device.setupReset?.state));
    const admins = document.querySelector("#admin-people");
    admins.replaceChildren(...data.admins.map(person => {
      const row = element("li", ""), name = element("span", person.email);
      row.append(name);
      if (person.owner) row.append(element("small", "Owner"));
      else {
        const remove = element("button", "Remove"); remove.type = "button"; remove.className = "quiet";
        remove.onclick = () => {
          if (confirm(`Remove administrator access for ${person.email}?`)) change({action: "revokeAdmin", email: person.email});
        };
        row.append(remove);
      }
      return row;
    }));
    document.querySelector("#admin-devices").replaceChildren(...data.devices.map(device => {
      const card = element("article", "");
      card.append(element("h3", device.name), element("p", `Device: ${device.id}`));
      appendSetup(card, device);
      const report = device.reported;
      card.append(element("p", report ? `App ${report.version} · Base ${report.base_version || "not reported"} · ${report.state} · ${new Date(report.atMs).toLocaleString()}` : "No firmware report yet."));
      card.append(element("p", device.target?.enabled ? `Target: ${device.target.version} (deployment ${device.target.sequence})` : "Automatic updates paused."));
      if (!device.enabled || !device.otaEnrolled) {
        card.append(element("p", !device.enabled ? "Device is disabled." : "OTA updates are not enabled for this device."));
        return card;
      }
      const label = element("label", "Firmware release"), select = element("select", "");
      select.setAttribute("aria-label", `Firmware release for ${device.name}`);
      select.append(new Option("Choose a release", ""), ...data.releases.map(r => new Option(r.version, r.version)));
      label.append(select); card.append(label);
      const assign = element("button", "Assign release"); assign.type = "button";
      assign.onclick = () => {
        if (select.value && confirm(`Assign firmware ${select.value} to ${device.name}? It will update when idle.`)) change({action: "targetFirmware", deviceId: device.id, version: select.value});
      };
      const pause = element("button", "Pause updates"); pause.type = "button"; pause.className = "quiet";
      pause.onclick = () => change({action: "pauseFirmware", deviceId: device.id});
      card.append(assign, pause); return card;
    }));
    lock(working);
  }
  document.querySelector("#admin-grant").onsubmit = event => {
    event.preventDefault();
    const email = document.querySelector("#admin-email").value.trim();
    if (confirm(`Give ${email} administrator access, including firmware targeting and administrator management?`)) change({action: "grantAdmin", email});
  };
  document.querySelector("#admin-refresh").onclick = () => open();
  function close() {
    epoch++; ++refreshEpoch; stopPolling(); pendingSetup = false; root.hidden = true; working = false; output.textContent = "";
    selectTab(tabs[0]);
    document.querySelector("#admin-people").replaceChildren();
    document.querySelector("#admin-devices").replaceChildren();
    document.querySelector("#admin-email").value = "";
  }
  async function open() {
    stopPolling();
    const current = ++epoch; root.hidden = false; lock(true); output.textContent = "Loading administration…";
    try { await refresh(); if (current === epoch) output.textContent = ""; }
    catch { if (current === epoch) { close(); onClose(); document.querySelector("#result").textContent = "Administrator access unavailable. Refresh access."; } }
    finally { if (current === epoch) { lock(false); schedulePolling(); } }
  }
  window.addEventListener("offline", () => { stopPolling(); ++refreshEpoch; lock(working); });
  window.addEventListener("online", () => { lock(working); schedulePolling(); });
  return {open, close};
}
