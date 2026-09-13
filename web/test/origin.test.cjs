const {test} = require("node:test");
const assert = require("node:assert/strict");
test("web.app redirects to the provisioned OAuth domain and canonical links stay put", async () => {
  const {AUTH_DOMAIN, canonicalAppUrl} = await import("../origin.mjs");
  assert.equal(AUTH_DOMAIN, "drawbridge-45487.firebaseapp.com");
  assert.equal(canonicalAppUrl("https://drawbridge-45487.web.app/"), "https://" + AUTH_DOMAIN + "/");
  assert.equal(canonicalAppUrl("https://drawbridge-45487.web.app/index.html?source=bookmark#gate"), "https://" + AUTH_DOMAIN + "/index.html?source=bookmark#gate");
  assert.equal(canonicalAppUrl("https://" + AUTH_DOMAIN + "/"), null);
  assert.equal(canonicalAppUrl("https://drawbridge.stielau.us/"), "https://" + AUTH_DOMAIN + "/");
  assert.equal(canonicalAppUrl("https://drawbridge.stielau.us/?source=bookmark#gate"), "https://" + AUTH_DOMAIN + "/?source=bookmark#gate");
  assert.throws(() => canonicalAppUrl("https://unexpected.example/"));
});
