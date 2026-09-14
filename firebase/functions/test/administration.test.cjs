const {test} = require("node:test");
const assert = require("node:assert/strict");
const {createAdministration, validateManifest} = require("../administration.cjs");
const m = {schema: 1, app_version: "1.0.0", app_api_version: 1, minimum_bootstrap_version: "1.0.0", circuitpython_major: 10, supported_board_ids: ["seeed_xiao_esp32_s3_sense"], size: 100, sha256: "a".repeat(64), git_commit: "b".repeat(40), artifact_object: "firmware/1.0.0/" + "a".repeat(64) + "/drawbridge.py"};
test("firmware manifests constrain board, bootstrap, digest, size and object location", () => {
  assert.deepEqual(validateManifest({...m, unlisted: "must not escape"}), m);
  for (const changes of [{app_version: "../bad"}, {app_version: "01.0.0"}, {schema: true}, {app_api_version: 2}, {size: 65537}, {size: 0}, {size: 1.2}, {sha256: "bad"}, {circuitpython_major: 9}, {supported_board_ids: ["other"]}, {artifact_object: "https://evil.example/app.py"}, {minimum_bootstrap_version: "99.0.0"}]) {
    assert.throws(() => validateManifest({...m, ...changes}), {publicCode: "invalid-argument"});
  }
});
test("admin calls reject missing or nonverified Google identity before database access", async () => {
  const api = createAdministration({doc() { throw new Error("must not reach DB"); }});
  for (const auth of [undefined, {uid: "user", token: {email: "nick.stielau@gmail.com", email_verified: false, firebase: {sign_in_provider: "google.com"}}}, {uid: "user", token: {email: "nick.stielau@gmail.com", email_verified: true, firebase: {sign_in_provider: "password"}}}]) {
    await assert.rejects(api.session({auth}), e => ["unauthenticated", "permission-denied"].includes(e.publicCode));
    await assert.rejects(api.overview({auth}), e => ["unauthenticated", "permission-denied"].includes(e.publicCode));
    await assert.rejects(api.change({auth}), e => ["unauthenticated", "permission-denied"].includes(e.publicCode));
  }
});
