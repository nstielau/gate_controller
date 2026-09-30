const {Buffer} = require("node:buffer");

function fail(message = "EMQX provisioning failed") {
  const error = new Error(message);
  error.publicCode = "internal";
  throw error;
}

function normalizeBaseUrl(value) {
  if (typeof value !== "string" || !value.trim()) fail();
  const raw = value.trim().replace(/\/+$/, "");
  const withScheme = /^[a-z][a-z\d+.-]*:\/\//i.test(raw) ? raw : `https://${raw}`;
  try {
    const parsed = new URL(withScheme);
    if (parsed.protocol !== "https:") fail();
    return parsed.toString().replace(/\/$/, "");
  } catch {
    fail();
  }
}

function createEmqxClient({baseUrl, appId, appSecret, request} = {}) {
  const base = normalizeBaseUrl(baseUrl);
  if (typeof appId !== "string" || !appId || typeof appSecret !== "string" || !appSecret) fail(); // pragma: allowlist secret
  const auth = "Basic " + Buffer.from(`${appId}:${appSecret}`).toString("base64");
  const send = request || (async call => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(new URL(call.path.replace(/^\//, ""), `${base}/`).toString(), {
        method: call.method,
        headers: {Authorization: auth, Accept: "application/json", "Content-Type": "application/json"},
        body: call.body === undefined ? undefined : JSON.stringify(call.body),
        signal: controller.signal,
      });
      return {status: response.status, json: () => response.json()};
    } finally {
      clearTimeout(timer);
    }
  });
  async function call(method, path, body, expected) {
    let response;
    try {
      response = await send({method, path, body, headers: {Authorization: auth}});
    } catch {
      fail();
    }
    if (!response || !expected.includes(response.status)) fail();
    return response;
  }
  async function provision({username, password, commandTopic, statusTopic}) {
    if (![username, password, commandTopic, statusTopic].every(value => typeof value === "string" && value)) fail();
    const created = await call("POST", "/authentication/password_based%3Abuilt_in_database/users", {user_id: username, password}, [201, 409]);
    // A deterministic username makes retries safe. If EMQX reports an existing
    // user, reset its password before replacing the ACL rules.
    if (created.status === 409) await call("PUT", `/authentication/password_based%3Abuilt_in_database/users/${encodeURIComponent(username)}`, {password}, [200]);
    await call("PUT", `/authorization/sources/built_in_database/rules/users/${encodeURIComponent(username)}`, {
      username,
      rules: [
        {action: "subscribe", permission: "allow", topic: commandTopic, qos: [1], retain: "all"},
        {action: "publish", permission: "allow", topic: statusTopic, qos: [0, 1], retain: "all"},
        {action: "all", permission: "deny", topic: "#"},
      ],
    }, [204]);
  }
  async function remove(username) {
    if (typeof username !== "string" || !username) return;
    await call("DELETE", `/authorization/sources/built_in_database/rules/users/${encodeURIComponent(username)}`, undefined, [204, 404]);
    await call("DELETE", `/authentication/password_based%3Abuilt_in_database/users/${encodeURIComponent(username)}`, undefined, [204, 404]);
  }
  return {provision, remove};
}

module.exports = {createEmqxClient};
