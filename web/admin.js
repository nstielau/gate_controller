// Loaded UI receives only allowlisted server fields; never receives OTA credentials.
export function createAdminView({gateway, onClose}) {
  const root = document.querySelector("#admin-view"), output = document.querySelector("#admin-result");
  let epoch = 0, working = false;
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
    root.querySelectorAll('button:not([role="tab"]),input,select').forEach(n => { n.disabled = value || !navigator.onLine; });
  }
  async function change(data) {
    if (working || !navigator.onLine) return;
    const current = epoch;
    lock(true); output.textContent = "Saving…";
    try {
      await gateway().adminChange({...data, requestId: crypto.randomUUID(), issuedAtMs: Date.now()});
      if (epoch !== current) return;
      await refresh();
      if (epoch === current) output.textContent = "Saved.";
    } catch {
      if (epoch === current) output.textContent = "Couldn't confirm this change. Refresh to check its status.";
    } finally { if (epoch === current) lock(false); }
  }
  async function refresh() {
    const current = epoch;
    const data = await gateway().adminOverview();
    if (current !== epoch) return;
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
      const report = device.reported;
      card.append(element("p", report ? `App ${report.version} · Base ${report.base_version || "not reported"} · ${report.state} · ${new Date(report.atMs).toLocaleString()}` : "No firmware report yet."));
      card.append(element("p", device.target?.enabled ? `Target: ${device.target.version} (deployment ${device.target.sequence})` : "Automatic updates paused."));
      if (!device.enabled || !device.otaEnrolled) {
        card.append(element("p", !device.enabled ? "Device is disabled." : "USB OTA enrollment required."));
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
  }
  document.querySelector("#admin-grant").onsubmit = event => {
    event.preventDefault();
    const email = document.querySelector("#admin-email").value.trim();
    if (confirm(`Give ${email} administrator access, including firmware targeting and administrator management?`)) change({action: "grantAdmin", email});
  };
  document.querySelector("#admin-refresh").onclick = () => open();
  function close() {
    epoch++; root.hidden = true; working = false; output.textContent = "";
    selectTab(tabs[0]);
    document.querySelector("#admin-people").replaceChildren();
    document.querySelector("#admin-devices").replaceChildren();
    document.querySelector("#admin-email").value = "";
  }
  async function open() {
    const current = ++epoch; root.hidden = false; lock(true); output.textContent = "Loading administration…";
    try { await refresh(); if (current === epoch) output.textContent = ""; }
    catch { if (current === epoch) { close(); onClose(); document.querySelector("#result").textContent = "Administrator access unavailable. Refresh access."; } }
    finally { if (current === epoch) lock(false); }
  }
  window.addEventListener("offline", () => lock(working));
  window.addEventListener("online", () => lock(working));
  return {open, close};
}
