const {test} = require("node:test");
const assert = require("node:assert/strict");
const {createFirmwareHandler} = require("../firmware-http.cjs");
const {hash} = require("../administration.cjs");
function fixture() {
  const bytes = Buffer.from("application");
  const manifest = {sequence: 4, size: bytes.length, sha256: hash(bytes), artifact_object: "approved/object"};
  let downloads = 0, reports = 0;
  const service = {
    async authorize(id, token) {
      if (id !== "device" || token !== "a".repeat(64)) throw {publicCode: "unauthenticated"};
      return {};
    },
    async manifest() { return manifest; },
    async report() { reports++; }
  };
  const bucket = {file(name) {
    assert.equal(name, manifest.artifact_object);
    return {async getMetadata() { return [{size: bytes.length}]; }, async download() { downloads++; return [bytes]; }};
  }};
  const handler = createFirmwareHandler(service, bucket);
  async function request(route, options = {}) {
    const response = {code: 200, headers: {}, set(k, v) { this.headers[k] = v; return this; },
      status(code) { this.code = code; return this; }, end() { return this; },
      json(value) { this.body = value; return this; }, send(value) { this.body = value; return this; }};
    await handler({path: "/device-api/v1/" + route, method: "GET", query: {sequence: "4"},
      get(name) { return {"X-Device-ID": "device", Authorization: "Bearer " + "a".repeat(64)}[name]; }, ...options}, response);
    assert.equal(response.headers["Cache-Control"], "no-store");
    return response;
  }
  return {request, service, manifest, bytes, counts: () => ({downloads, reports})};
}
test("firmware HTTP authenticates every operation and accepts only bounded routes and bodies", async () => {
  const f = fixture();
  for (const route of ["manifest", "artifact", "report"]) {
    const r = await f.request(route, {method: route === "report" ? "POST" : "GET", get: () => undefined});
    assert.equal(r.code, 401);
  }
  assert.equal((await f.request("manifest", {get: name => name === "X-Device-ID" ? "device" : "a".repeat(64)})).code, 401);
  assert.equal((await f.request("unknown")).code, 404);
  assert.equal((await f.request("report", {method: "POST", rawBody: Buffer.alloc(4097)})).code, 413);
  assert.deepEqual(f.counts(), {downloads: 0, reports: 0});
});
test("firmware HTTP serves only the selected verified artifact and handles paused targets", async () => {
  const f = fixture();
  assert.deepEqual((await f.request("manifest")).body, f.manifest);
  assert.equal((await f.request("artifact", {query: {sequence: "3"}})).code, 409);
  assert.equal(f.counts().downloads, 0);
  assert.deepEqual((await f.request("artifact")).body, f.bytes);
  f.manifest.sha256 = "b".repeat(64);
  assert.equal((await f.request("artifact")).code, 503);
  f.service.manifest = async () => null;
  assert.equal((await f.request("artifact")).code, 204);
  assert.equal((await f.request("report", {method: "POST", body: {}})).code, 204);
  assert.equal(f.counts().reports, 1);
});
