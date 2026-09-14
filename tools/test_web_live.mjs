// No login credentials or physical gate commands are used by this check.
import {chromium} from "@playwright/test";
import assert from "node:assert/strict";
const canonical = "https://drawbridge-45487.firebaseapp.com";
const browser = await chromium.launch();
try {
  for (const origin of ["https://drawbridge.stielau.us", "https://drawbridge-45487.web.app", canonical]) {
    const context = await browser.newContext();
    try {
      const page = await context.newPage();
      await page.goto(origin);
      await page.waitForURL(canonical + "/", {timeout: 30000});
      await page.locator("#sign-in").waitFor({state: "visible"});
      await page.locator("#sign-in").click();
      await page.waitForURL("https://accounts.google.com/**", {timeout: 30000});
      await page.waitForLoadState("domcontentloaded");
      const url = new URL(page.url());
      assert.equal(url.searchParams.get("redirect_uri"), canonical + "/__/auth/handler");
      assert.equal((await page.locator("body").innerText()).includes("redirect_uri_mismatch"), false);
      assert.equal(url.pathname.includes("/error"), false);
      console.log("PASS: " + origin + " reaches Google sign-in with the accepted callback");
    } finally { await context.close(); }
  }
  for (const name of ["listDevices", "holdGate", "renameGate", "adminSession", "adminOverview", "adminChange"]) {
    const response = await fetch("https://us-east1-drawbridge-45487.cloudfunctions.net/" + name, {
      method: "POST", headers: {"Content-Type": "application/json", Origin: canonical},
      body: JSON.stringify({data: {}}), signal: AbortSignal.timeout(30000)
    });
    assert.equal(response.status, 401);
    assert.equal((await response.json()).error.status, "UNAUTHENTICATED");
    console.log("PASS: " + name + " rejects unauthenticated requests");
  }
  for (const route of ["manifest", "artifact?sequence=1", "report"]) {
    const response = await fetch(canonical + "/device-api/v1/" + route, {
      method: route === "report" ? "POST" : "GET", signal: AbortSignal.timeout(30000)
    });
    assert.equal(response.status, 401);
    assert.match(response.headers.get("cache-control"), /no-store/);
    console.log("PASS: firmware " + route + " rejects unauthenticated devices and disables caching");
  }
} finally { await browser.close(); }
