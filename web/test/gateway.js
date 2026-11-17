// Only copied into artifacts/web-test by the explicit --test build.
export async function createGateway() {
  const scenario = window.__scenario || "authorized";
  if (scenario === "loading") await new Promise(resolve => { window.__releaseGateway = resolve; });
  if (scenario === "startup-failure") throw new Error("Gateway initialization failed");
  let callback;
  let claimPolls = 0;
  let devices = ["claim-success", "claim-expired"].includes(scenario)
    ? [] : [{id: "test-device", name: "Garden gate"}, {id: "second-device", name: "Driveway"}];
  return {
    async createDeviceClaim(data) {
      window.__claims ||= []; window.__claims.push({...data});
      if (scenario === "claim-delayed") await new Promise(resolve => { window.__releaseClaim = resolve; });
      if (scenario === "claim-owned") throw Object.assign(new Error("Device already registered. Ask its owner for access."), {code: "functions/permission-denied"});
      return {deviceId: data.deviceId.trim().toLowerCase(), state: "pending", expiresAtMs: Date.now() + 7200000};
    },
    async deviceClaimStatus(data) {
      claimPolls++;
      window.__claimPolls = claimPolls;
      if (scenario === "claim-expired") return {deviceId: data.deviceId, state: "expired", expiresAtMs: Date.now() - 1};
      if (scenario === "claim-success" && claimPolls === 2) return {deviceId: data.deviceId, state: "provisioning"};
      if (scenario === "claim-success" && claimPolls >= 3) {
        if (!devices.some(device => device.id === data.deviceId)) devices.push({id: data.deviceId, name: data.deviceId});
        return {deviceId: data.deviceId, state: "registered"};
      }
      return {deviceId: data.deviceId, state: "pending", expiresAtMs: Date.now() + 7200000};
    },
    async adminSession() { return {isAdmin: scenario === "admin" || scenario === "admin-revoked"}; },
    async inviteDeviceUser(data) {
      window.__invitations ||= []; window.__invitations.push(data);
      await new Promise(resolve => setTimeout(resolve, 250));
      if (scenario === "invite-revoked") throw Object.assign(new Error("You cannot invite users to this device. Refresh access."), {code: "functions/permission-denied"});
      if (scenario === "invite-failure") throw new Error("Network disconnected");
      return {ok: true, email: data.email.toLowerCase(), deviceId: data.deviceId};
    },
    async adminOverview() {
      if (scenario === "admin-revoked") throw new Error("revoked");
      window.__admins ||= [{email: "nick.stielau@gmail.com", owner: true}];
      return {admins: window.__admins, devices: [{id: "test-device", name: "Garden gate", enabled: true, otaEnrolled: true, target: window.__target || null, reported: window.__firmwareReport || null}], releases: [{version: "1.0.0"}]};
    },
    async adminChange(data) {
      window.__adminChanges ||= []; window.__adminChanges.push(data);
      if (data.action === "grantAdmin") window.__admins.push({email: data.email, owner: false});
      if (data.action === "revokeAdmin") window.__admins = window.__admins.filter(a => a.email !== data.email);
      if (data.action === "targetFirmware") window.__target = {version: data.version, sequence: 1, enabled: true};
      if (data.action === "pauseFirmware") window.__target = {enabled: false, sequence: 2};
      return {ok: true};
    },
    onUser(fn) { callback = fn; fn((scenario === "signed-out" || (scenario === "claim-login-redirect" && !sessionStorage.getItem("test.signedIn"))) ? null : {email: "operator@example.test", photoURL: "https://example.test/profile.jpg"}); },
    async signIn() { if (scenario === "claim-login-redirect") { sessionStorage.setItem("test.signedIn", "1"); location.assign("/"); return; } callback({email: "operator@example.test", photoURL: "https://example.test/profile.jpg"}); },
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
