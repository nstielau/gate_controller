const {defineConfig, devices} = require("@playwright/test");
module.exports = defineConfig({
  testDir: "web/test", testMatch: "*.spec.cjs", workers: 2,
  use: {baseURL: "http://127.0.0.1:4173", screenshot: "only-on-failure"},
  projects: [
    {name: "mobile-chromium", use: {...devices["Pixel 7"]}},
    {name: "mobile-webkit", use: {...devices["iPhone 13"]}}
  ],
  webServer: {command: "node tools/build_web.mjs --test && .venv/bin/python -m http.server 4173 --bind 127.0.0.1 --directory artifacts/web-test", url: "http://127.0.0.1:4173", reuseExistingServer: false}
});
