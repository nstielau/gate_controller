// Only copied into .artifacts/web-test by the explicit --test build.
export async function createGateway() {
  const scenario = window.__scenario || "authorized";
  if (scenario === "startup-failure") throw new Error("Gateway initialization failed");
  let callback;
  const devices = [{id: "test-device", name: "Garden gate"}, {id: "second-device", name: "Driveway"}];
  return {
    onUser(fn) { callback = fn; fn(scenario === "signed-out" ? null : {email: "operator@example.test", photoURL: "https://example.test/profile.jpg"}); },
    async signIn() { callback({email: "operator@example.test", photoURL: "https://example.test/profile.jpg"}); },
    async signOut() { callback(null); },
    async listDevices() { return {devices: scenario === "unauthorized" ? [] : devices}; },
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
