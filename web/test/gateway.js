// Only copied into artifacts/web-test by the explicit --test build.
export async function createGateway() {
  const scenario = window.__scenario || "authorized";
  if (scenario === "loading") await new Promise(resolve => { window.__releaseGateway = resolve; });
  if (scenario === "startup-failure") throw new Error("Gateway initialization failed");
  let callback;
  const devices = [{id: "test-device", name: "Garden gate"}, {id: "second-device", name: "Driveway"}];
  return {
    async adminSession() { return {isAdmin: scenario === "admin" || scenario === "admin-revoked"}; },
    async adminOverview() {
      if (scenario === "admin-revoked") throw new Error("revoked");
      window.__admins ||= [{email: "nick.stielau@gmail.com", owner: true}];
      return {admins: window.__admins, devices: [{id: "test-device", name: "Garden gate", enabled: true, otaEnrolled: true, target: window.__target || null, reported: null}], releases: [{version: "1.0.0"}]};
    },
    async adminChange(data) {
      window.__adminChanges ||= []; window.__adminChanges.push(data);
      if (data.action === "grantAdmin") window.__admins.push({email: data.email, owner: false});
      if (data.action === "revokeAdmin") window.__admins = window.__admins.filter(a => a.email !== data.email);
      if (data.action === "targetFirmware") window.__target = {version: data.version, sequence: 1, enabled: true};
      if (data.action === "pauseFirmware") window.__target = {enabled: false, sequence: 2};
      return {ok: true};
    },
    onUser(fn) { callback = fn; fn(scenario === "signed-out" ? null : {email: "operator@example.test", photoURL: "https://example.test/profile.jpg"}); },
    async signIn() { callback({email: "operator@example.test", photoURL: "https://example.test/profile.jpg"}); },
    async signOut() { callback(null); },
    async listDevices() {
      if (scenario === "loading") await new Promise(resolve => { window.__releaseDevices = resolve; });
      if (scenario === "load-failure") throw new Error("Reconnect and refresh access.");
      return {devices: scenario === "unauthorized" ? [] : devices};
    },
    async renameGate({deviceId, nickname}) {
      if (scenario === "failure") throw new Error("Network disconnected");
      const device = devices.find(d => d.id === deviceId);
      device.name = nickname;
      return {...device};
    },
    async holdGate(data) {
      window.__commands ||= []; window.__commands.push(data);
      await new Promise(resolve => setTimeout(resolve, 250));
      if (scenario === "failure") throw new Error("Network disconnected");
      const device = devices.find(item => item.id === data.deviceId);
      device.hold = data.durationSeconds ? {startedAtMs: Date.now(), durationSeconds: data.durationSeconds} : null;
      return {status: "accepted", commandId: "test-command", hold: device.hold};
    }
  };
}
