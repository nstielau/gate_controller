const {test, expect} = require("@playwright/test");
const {readFile} = require("node:fs/promises");
test("drawbridge moves continuously through edge-on with fixed hinges and attached chains", async ({page}) => {
  await page.setContent(await readFile("web/drawbridge-loader.svg", "utf8"));
  const motion = await page.evaluate(() => {
    const svg = document.querySelector("svg");
    svg.pauseAnimations();
    const animations = document.getAnimations();
    animations.forEach(animation => animation.pause());
    let hingeError = 0, chainError = 0, biggestStep = 0, previous;
    for (let frame = 0; frame <= 240; frame++) {
      const time = frame / 60;
      svg.setCurrentTime(time);
      animations.forEach(animation => { animation.currentTime = time * 1000; });
      const matrix = document.querySelector("#bridge-texture").getCTM();
      const project = (x, y) => new DOMPoint(x, y).matrixTransform(matrix);
      for (const [x,y] of [[54,77],[74,85]]) {
        const point = project(x,y);
        hingeError = Math.max(hingeError, Math.hypot(point.x-x,point.y-y));
      }
      const tip = project(44,60), chain = document.querySelector("line");
      chainError = Math.max(chainError, Math.hypot(tip.x-chain.x2.animVal.value, tip.y-chain.y2.animVal.value));
      if (previous) biggestStep = Math.max(biggestStep, Math.hypot(tip.x-previous.x,tip.y-previous.y));
      previous = tip;
    }
    return {hingeError,chainError,biggestStep};
  });
  expect(motion.hingeError).toBeLessThan(.01);
  expect(motion.chainError).toBeLessThan(.03);
  expect(motion.biggestStep).toBeGreaterThan(.1);
  expect(motion.biggestStep).toBeLessThan(1);
});
test("startup errors stay visible instead of leaving a blank page", async ({page}) => {
  await page.addInitScript(() => { window.__scenario = "startup-failure"; });
  await page.goto("/");
  const message = page.locator("#user-state");
  await expect(message).toHaveText("Secure connection couldn't start. Reconnect and reload.");
  await expect(message).toBeInViewport();
  await expect(page.locator("#controls")).toBeHidden();
});
test("centered drawbridge loader animates while securely connecting and loading devices", async ({page}) => {
  await page.addInitScript(() => { window.__scenario = "loading"; });
  await page.goto("/");
  const loader = page.locator("#loading-state");
  await expect(loader).toBeVisible();
  await expect(page.locator("#loading-message")).toHaveText("Securely Connecting");
  const icon = page.locator(".drawbridge-loader img");
  await expect.poll(() => icon.evaluate(image => image.complete && image.naturalWidth === 128)).toBe(true);
  const firstFrame = await icon.screenshot();
  await page.waitForTimeout(550);
  expect((await icon.screenshot()).equals(firstFrame)).toBe(false);
  const aligned = await page.evaluate(() => {
    const icon = document.querySelector(".drawbridge-loader").getBoundingClientRect();
    const text = document.querySelector("#loading-message").getBoundingClientRect();
    return Math.abs(icon.x + icon.width / 2 - text.x - text.width / 2) < 1
      && document.documentElement.scrollHeight <= innerHeight;
  });
  expect(aligned).toBe(true);
  const connectingIcon = await icon.boundingBox();
  const connectingMessage = await page.locator("#loading-message").boundingBox();
  await expect(page.locator("header")).toBeHidden();
  await page.evaluate(() => window.__releaseGateway());
  await expect(page.locator("#loading-message")).toHaveText("Loading devices");
  await expect(page.locator("header")).toBeVisible();
  const loadingIcon = await icon.boundingBox();
  const loadingMessage = await page.locator("#loading-message").boundingBox();
  expect(Math.abs(loadingIcon.y - connectingIcon.y)).toBeLessThan(1);
  expect(Math.abs(loadingIcon.x - connectingIcon.x)).toBeLessThan(1);
  expect(Math.abs(loadingMessage.y - connectingMessage.y)).toBeLessThan(1);
  await expect(page.locator(".drawbridge-loader")).toBeVisible();
  await expect(loader).toBeInViewport();
  await page.evaluate(() => window.__releaseDevices());
  await expect(loader).toBeHidden({timeout: 1000});
  await expect(page.locator("#controls")).toBeVisible();
});
test("reduced motion displays a still castle during loading", async ({page}) => {
  await page.emulateMedia({reducedMotion: "reduce"});
  await page.addInitScript(() => { window.__scenario = "loading"; });
  await page.goto("/");
  const icon = page.locator(".drawbridge-loader img");
  await expect.poll(() => icon.evaluate(image => image.complete && image.naturalWidth === 128)).toBe(true);
  const firstFrame = await icon.screenshot();
  await page.waitForTimeout(300);
  expect((await icon.screenshot()).equals(firstFrame)).toBe(true);
});
test("failed device loading dismisses the loader and shows the error", async ({page}) => {
  await page.addInitScript(() => { window.__scenario = "load-failure"; });
  await page.goto("/");
  await expect(page.locator("#loading-state")).toBeHidden();
  await expect(page.locator("#user-state")).toBeVisible();
  await expect(page.locator("#user-state")).toHaveText("Couldn't load gate access.");
  await expect(page.locator("#controls")).toBeHidden();
});
test("signed-out and unassigned users cannot send commands", async ({page}) => {
  await page.addInitScript(() => { window.__scenario = "signed-out"; });
  await page.goto("/");
  await expect(page.locator("#sign-in")).toBeVisible();
  await expect(page.locator("#controls")).toBeHidden();
  await page.addInitScript(() => { window.__scenario = "unauthorized"; });
  await page.reload();
  await expect(page.locator("#user-state")).toContainText("No gate access");
  await expect(page.locator("#controls")).toBeHidden();
});
test("profile photo opens and dismisses the account menu", async ({page}) => {
  await page.goto("/");
  const menu = page.locator("#account-dropdown");
  await expect(menu).toBeHidden();
  await page.locator("#account-menu-button").click();
  await expect(menu).toBeVisible();
  await expect(page.locator("#refresh")).toBeVisible();
  await expect(page.locator("#rename")).toBeVisible();
  await expect(page.locator("#sign-out")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(menu).toBeHidden();
  await page.locator("#account-menu-button").click();
  await page.locator("main").click({position: {x: 5, y: 300}});
  await expect(menu).toBeHidden();
});
test("all durations, device selection, double tap prevention, and sign-out", async ({page}) => {
  await page.goto("/");
  await expect(page.locator("#controls")).toBeVisible();
  await expect(page.locator(".castle-icon")).toBeVisible();
  await expect(page.locator("#profile-photo")).toBeVisible();
  await expect(page.locator("#account-dropdown")).toBeHidden();
  await expect(page.locator("#user-state")).toBeHidden();
  await page.locator("#device").selectOption("second-device");
  page.on("dialog", dialog => dialog.accept());
  for (const duration of [60, 900, 3600, 21600, 0]) {
    await page.locator('[data-duration="' + duration + '"]').click();
    await expect(page.locator('[data-duration="60"]')).toBeDisabled();
    await expect(page.locator("#result")).toContainText("accepted by broker");
  }
  const commands = await page.evaluate(() => window.__commands);
  expect(commands.map(c => c.durationSeconds)).toEqual([60, 900, 3600, 21600, 0]);
  expect(commands.every(c => c.deviceId === "second-device" && c.issuedAtMs > 0)).toBeTruthy();
  expect(new Set(commands.map(c => c.requestId)).size).toBe(5);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  expect(await page.evaluate(() => document.documentElement.scrollHeight <= window.innerHeight)).toBeTruthy();
  await page.screenshot({path: "artifacts/drawbridge-" + test.info().project.name + ".png", fullPage: true});
  await page.locator("#account-menu-button").click();
  await page.locator("#sign-out").click();
  await expect(page.locator("#controls")).toBeHidden();
});
test("offline app shell loads and never queues commands", async ({page, context, browserName}) => {
  test.skip(browserName !== "chromium", "Playwright service-worker support is Chromium-only; verify iOS offline launch manually.");
  await page.goto("/");
  await expect(page.locator("#controls")).toBeVisible();
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();
  await expect.poll(() => page.evaluate(() => !!navigator.serviceWorker.controller)).toBe(true);
  await context.setOffline(true);
  await page.evaluate(() => { window.__beforeReload = true; });
  await page.goto("/index.html");
  expect(await page.evaluate(() => window.__beforeReload)).toBeUndefined();
  await expect(page.locator(".wordmark")).toBeVisible();
  await expect(page.locator("#offline")).toBeVisible();
  await expect(page.locator('[data-duration="60"]')).toBeDisabled();
  await context.setOffline(false);
  await expect(page.locator('[data-duration="60"]')).toBeEnabled();
  expect(await page.evaluate(() => window.__commands || [])).toEqual([]);
});
test("offline controls disable immediately and reconnect never sends a command", async ({page, context}) => {
  await page.goto("/");
  await expect(page.locator("#controls")).toBeVisible();
  await context.setOffline(true);
  await expect(page.locator("#offline")).toBeVisible();
  await expect(page.locator('[data-duration="60"]')).toBeDisabled();
  await context.setOffline(false);
  await expect(page.locator('[data-duration="60"]')).toBeEnabled();
  expect(await page.evaluate(() => window.__commands || [])).toEqual([]);
});
test("uncertain delivery is never reported as a successful gate action", async ({page}) => {
  await page.addInitScript(() => { window.__scenario = "failure"; });
  await page.goto("/");
  await page.locator('[data-duration="60"]').click();
  await expect(page.locator("#result")).toContainText("Delivery is uncertain");
  expect(await page.evaluate(() => window.__commands.length)).toBe(1);
});
test("accepted hold displays a persistent expected countdown and elapsed progress", async ({page}) => {
  await page.goto("/");
  await page.locator('[data-duration="900"]').click();
  const button = page.locator('[data-duration="900"]');
  await expect(button).toHaveClass(/hold-active/);
  await expect(page.locator("#hold-countdown")).toHaveText(/14:5\d remaining/);
  const initialProgress = Number(await button.evaluate(element => getComputedStyle(element).getPropertyValue("--hold-progress")));
  expect(initialProgress).toBeGreaterThanOrEqual(0);
  await page.waitForTimeout(1100);
  const laterProgress = Number(await button.evaluate(element => getComputedStyle(element).getPropertyValue("--hold-progress")));
  expect(laterProgress).toBeGreaterThan(initialProgress);
  await page.locator("#account-menu-button").click();
  await page.locator("#refresh").click();
  await expect(page.locator("#hold-countdown")).toHaveText(/remaining/);
  await page.locator('[data-duration="0"]').click();
  await expect(button).not.toHaveClass(/hold-active/);
  await expect(page.locator("#hold-countdown")).toBeHidden();
});
test("edit nickname saves selected gate, survives access refresh, and renders as text", async ({page}) => {
  await page.goto("/");
  await page.locator("#device").selectOption("second-device");
  await page.locator("#account-menu-button").click();
  await page.locator("#rename").click();
  await expect(page.locator("#nickname")).toHaveValue("Driveway");
  await page.locator("#nickname").fill("  <Garden gate>  ");
  await page.locator("#nickname-save").click();
  await expect(page.locator("#result")).toHaveText("Gate nickname saved.");
  await expect(page.locator("#device option:checked")).toHaveText("<Garden gate>");
  await page.locator("#account-menu-button").click();
  await page.locator("#refresh").click();
  await expect(page.locator('#device option[value="second-device"]')).toHaveText("<Garden gate>");
  await expect(page.locator('#device option[value="test-device"]')).toHaveText("Garden gate");
  expect(await page.evaluate(() => window.__commands || [])).toEqual([]);
  await page.locator("#account-menu-button").click();
  await page.locator("#rename").click();
  await page.locator("#nickname").fill("   ");
  await page.locator("#nickname-save").click();
  await expect(page.locator("#nickname-result")).toHaveText("Enter a nickname.");
  await page.locator("#nickname-cancel").click();
  await expect(page.locator("#nickname-form")).toBeHidden();
});
test("failed nickname save preserves the existing name and the draft", async ({page}) => {
  await page.addInitScript(() => { window.__scenario = "failure"; });
  await page.goto("/");
  await page.locator("#account-menu-button").click();
  await page.locator("#rename").click();
  await page.locator("#nickname").fill("Front gate");
  await page.locator("#nickname-save").click();
  await expect(page.locator("#nickname-result")).toContainText("Couldn't save");
  await expect(page.locator("#nickname")).toHaveValue("Front gate");
  await expect(page.locator("#device option:checked")).toHaveText("Garden gate");
});
test("assigned users invite by email to the selected device without sending a gate command", async ({page}) => {
  await page.goto("/");
  await page.locator("#device").selectOption("second-device");
  await page.locator("#account-menu-button").click();
  await expect(page.locator("#admin-open")).toBeHidden();
  await page.locator("#invite").click();
  await expect(page.locator("#invite-device")).toHaveText("Invite to Driveway (second-device)");
  await expect(page.locator("#invite-email")).toBeFocused();
  await expect(page.locator("#invite-hint")).toContainText("no email is sent");
  await page.locator("#invite-email").fill("Guest@Example.test");
  await page.locator("#invite-save").click();
  await expect(page.locator("#invite-save")).toBeDisabled();
  await expect(page.locator("#device")).toBeDisabled();
  await expect(page.locator("#invite-result")).toHaveText("Access granted to guest@example.test.");
  await expect(page.locator("#invite-share a")).toHaveAttribute("href", "https://drawbridge-45487.firebaseapp.com");
  const invitations = await page.evaluate(() => window.__invitations);
  expect(invitations).toHaveLength(1);
  expect(invitations[0]).toMatchObject({deviceId: "second-device", email: "Guest@Example.test"});
  expect(invitations[0].requestId).toMatch(/^[a-f0-9-]{36}$/);
  expect(invitations[0].issuedAtMs).toBeGreaterThan(0);
  expect(await page.evaluate(() => window.__commands || [])).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path: "artifacts/invite-" + test.info().project.name + ".png", fullPage: true});
  await page.keyboard.press("Escape");
  await expect(page.locator("#invite-form")).toBeHidden();
  await expect(page.locator("#invite-email")).toHaveValue("");
});
test("invitations validate email, cancel drafts, and stay disabled offline or without access", async ({page, context}) => {
  await page.goto("/");
  await page.locator("#account-menu-button").click();
  await page.locator("#invite").click();
  await page.locator("#invite-email").fill("invalid-email");
  await page.locator("#invite-save").click();
  expect(await page.evaluate(() => window.__invitations || [])).toEqual([]);
  await page.locator("#invite-email").fill("guest@example.test");
  await context.setOffline(true);
  await expect(page.locator("#invite-save")).toBeDisabled();
  await context.setOffline(false);
  await expect(page.locator("#invite-save")).toBeEnabled();
  expect(await page.evaluate(() => window.__invitations || [])).toEqual([]);
  await page.locator("#invite-cancel").click();
  await expect(page.locator("#invite-form")).toBeHidden();
  await expect(page.locator("#invite")).toBeFocused();
  await page.locator("#invite").click();
  await expect(page.locator("#invite-email")).toHaveValue("");
  await page.locator("#rename").click();
  await expect(page.locator("#invite-form")).toBeHidden();
  await page.addInitScript(() => { window.__scenario = "unauthorized"; });
  await page.reload();
  await page.locator("#account-menu-button").click();
  await expect(page.locator("#invite")).toBeDisabled();
});
for (const scenario of ["invite-failure", "invite-revoked"]) {
  test(`${scenario} preserves email and shows the failure without retrying`, async ({page}) => {
    await page.addInitScript(value => { window.__scenario = value; }, scenario);
    await page.goto("/");
    await page.locator("#account-menu-button").click();
    await page.locator("#invite").click();
    await page.locator("#invite-email").fill("guest@example.test");
    await page.locator("#invite-save").click();
    await expect(page.locator("#invite-result")).toContainText(scenario === "invite-failure" ? "Couldn't confirm access" : "You cannot invite users");
    await expect(page.locator("#invite-email")).toHaveValue("guest@example.test");
    await expect(page.locator("#invite-share")).toBeHidden();
    await expect(page.locator("#invite-save")).toBeEnabled();
    expect(await page.evaluate(() => window.__invitations.length)).toBe(1);
    expect(await page.evaluate(() => window.__commands || [])).toEqual([]);
  });
}
test("only administrators see Administration in the profile dropdown", async ({page}) => {
  await page.goto("/");
  await page.locator("#account-menu-button").click();
  await expect(page.locator("#admin-open")).toBeHidden();
  await page.addInitScript(() => { window.__scenario = "admin"; });
  await page.reload();
  await page.locator("#account-menu-button").click();
  await expect(page.locator("#admin-open")).toBeVisible();
});
test("admin manages roles and firmware on mobile without publishing holds", async ({page, context}) => {
  await page.addInitScript(() => { window.__scenario = "admin"; });
  page.on("dialog", dialog => dialog.accept());
  await page.goto("/");
  await page.locator("#account-menu-button").click();
  await page.locator("#admin-open").click();
  await expect(page.locator("#admin-view")).toBeVisible();
  await expect(page.locator("#controls")).toBeHidden();
  await expect(page.getByRole("tab", {name: "Admins", exact: true})).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("#admin-panel-firmware")).toBeHidden();
  await expect(page.locator("#admin-back")).toHaveCount(0);
  await expect(page.locator("#admin-people")).toContainText("nick.stielau@gmail.com");
  await page.locator("#admin-email").fill("jess@example.test");
  await page.getByRole("button", {name: "Add administrator", exact: true}).click();
  await expect(page.locator("#admin-people")).toContainText("jess@example.test");
  await page.getByRole("button", {name: "Remove", exact: true}).click();
  await expect(page.locator("#admin-people")).not.toContainText("jess@example.test");
  const firmwareTab = page.getByRole("tab", {name: "Device Firmware", exact: true});
  await page.getByRole("tab", {name: "Admins", exact: true}).focus();
  await page.keyboard.press("ArrowRight");
  await expect(firmwareTab).toBeFocused();
  await expect(firmwareTab).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("#admin-panel-people")).toBeHidden();
  await page.getByRole("button", {name: "Refresh administration", exact: true}).click();
  await expect(page.getByRole("button", {name: "Refresh administration", exact: true})).toBeEnabled();
  await expect(firmwareTab).toHaveAttribute("aria-selected", "true");
  await page.getByLabel("Firmware release for Garden gate").selectOption("1.0.0");
  await page.getByRole("button", {name: "Assign release", exact: true}).click();
  await expect(page.locator("#admin-devices")).toContainText("Target: 1.0.0");
  await page.getByRole("button", {name: "Pause updates", exact: true}).click();
  await expect(page.locator("#admin-devices")).toContainText("Automatic updates paused.");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path: "artifacts/admin-" + test.info().project.name + ".png", fullPage: true});
  await context.setOffline(true);
  await expect(page.getByRole("button", {name: "Assign release", exact: true})).toBeDisabled();
  await page.getByRole("tab", {name: "Admins", exact: true}).click();
  await expect(page.getByRole("button", {name: "Add administrator", exact: true})).toBeDisabled();
  await context.setOffline(false);
  expect(await page.evaluate(() => window.__commands || [])).toEqual([]);
  await page.getByRole("link", {name: "Drawbridge home"}).click();
  await expect(page.locator("#controls")).toBeVisible();
  expect(await page.evaluate(() => window.__commands || [])).toEqual([]);
  await page.locator("#account-menu-button").click();
  await page.locator("#sign-out").click();
  await expect(page.locator("#admin-view")).toBeHidden();
  await expect(page.locator("#admin-people")).toBeEmpty();
});
test("revoked role cannot open admin data even if its menu was previously visible", async ({page}) => {
  await page.addInitScript(() => { window.__scenario = "admin-revoked"; });
  await page.goto("/");
  await page.locator("#account-menu-button").click();
  await page.locator("#admin-open").click();
  await expect(page.locator("#admin-view")).toBeHidden();
  await expect(page.locator("#result")).toContainText("Administrator access unavailable");
});

test("firmware shows independently reported base and app versions, including legacy boards", async ({page}) => {
  await page.addInitScript(() => {
    window.__scenario = "admin";
    window.__firmwareReport = {version: "1.0.9", base_version: "1.0.1", state: "current", atMs: Date.now()};
  });
  await page.goto("/");
  await page.locator("#account-menu-button").click();
  await page.locator("#admin-open").click();
  await page.getByRole("tab", {name: "Device Firmware", exact: true}).click();
  await expect(page.locator("#admin-devices")).toContainText("App 1.0.9 · Base 1.0.1");
  await page.evaluate(() => { delete window.__firmwareReport.base_version; });
  await page.getByRole("button", {name: "Refresh administration"}).click();
  await expect(page.locator("#admin-devices")).toContainText("App 1.0.9 · Base not reported");
});

const pairingCode = "a".repeat(64);
const scanUrl = id => `/?device_id=${id}#pair=${pairingCode}`;

test("QR registration requires confirmation even when the user already owns gates", async ({page}) => {
  await page.goto(scanUrl("AB12CD"));
  await expect(page.locator("#device-onboarding")).toBeVisible();
  await expect(page.locator("#controls")).toBeHidden();
  await expect(page.locator("#device-onboarding-id")).toHaveValue("ab12cd");
  await expect(page.locator("#device-onboarding-id")).toHaveAttribute("readonly", "");
  expect(new URL(page.url()).hash).toBe("");
  expect(await page.evaluate(() => window.__claims || [])).toEqual([]);
  await page.locator("#device-onboarding-nickname").fill("  Side gate  ");
  await page.locator("#device-claim").click();
  await expect(page.locator("#device-onboarding-status")).toContainText("Waiting for the device");
  expect(await page.evaluate(() => window.__claims)).toEqual([{deviceId: "ab12cd", pairingCode, nickname: "Side gate"}]);
  expect(await page.evaluate(() => window.__commands || [])).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("first registration waits through provisioning until the device acknowledges setup", async ({page}) => {
  await page.addInitScript(() => { window.__scenario = "claim-success"; });
  await page.goto(scanUrl("ab12cd"));
  await page.locator("#device-claim").click();
  await expect(page.locator("#device-onboarding-status")).toContainText("Waiting for the device");
  await expect(page.locator("#device-onboarding-status")).toContainText("confirm", {timeout: 5000});
  await expect(page.locator("#controls")).toBeHidden();
  await expect(page.locator("#controls")).toBeVisible({timeout: 5000});
  await expect(page.locator("#device")).toHaveValue("ab12cd");
  expect(await page.evaluate(() => sessionStorage.getItem("drawbridge.pairing"))).toBeNull();
  expect(await page.evaluate(() => window.__commands || [])).toEqual([]);
});

test("signed-out QR scan explains registration and survives Google redirect without query parameters", async ({page}) => {
  await page.addInitScript(() => { window.__scenario = "claim-login-redirect"; });
  await page.goto(scanUrl("ab12cd"));
  await expect(page.locator("#signed-out-message")).toContainText("Sign in with Google to register device ab12cd");
  await expect(page.locator("#sign-in")).toBeVisible();
  expect(new URL(page.url()).hash).toBe("");
  await page.locator("#sign-in").click();
  await expect(page.locator("#device-onboarding")).toBeVisible();
  await expect(page.locator("#device-onboarding-id")).toHaveValue("ab12cd");
  expect(new URL(page.url()).search).toBe("");
  expect(await page.evaluate(() => window.__claims || [])).toEqual([]);
  await page.locator("#device-claim").click();
  await expect(page.locator("#device-onboarding-status")).toContainText("Waiting for the device");
});

test("an authorized scanned device opens its own controls without creating a claim", async ({page}) => {
  await page.goto(scanUrl("second-device"));
  await expect(page.locator("#controls")).toBeVisible();
  await expect(page.locator("#device")).toHaveValue("second-device");
  await expect(page.locator("#device-onboarding")).toBeHidden();
  expect(await page.evaluate(() => window.__claims || [])).toEqual([]);
});

test("manual Add explains fresh QR scanning and never registers from an ID alone", async ({page}) => {
  await page.goto("/");
  await page.locator("#account-menu-button").click();
  await page.locator("#add-device").click();
  await expect(page.locator("#device-onboarding-status")).toContainText("Scan a fresh QR code");
  await expect(page.locator("#device-claim")).toBeHidden();
  await page.locator("#device-onboarding-cancel").click();
  await expect(page.locator("#controls")).toBeVisible();
  expect(await page.evaluate(() => window.__claims || [])).toEqual([]);
});

for (const suffix of ["?device_id=ab12cd#pair=bad", "?device_id=ab12cd"]) {
  test(`invalid QR cannot register: ${suffix}`, async ({page}) => {
    await page.goto("/" + suffix);
    await expect(page.locator("#device-onboarding")).toBeVisible();
    await expect(page.locator("#device-onboarding-status")).toContainText("Scan a fresh QR code");
    await expect(page.locator("#device-claim")).toBeHidden();
    expect(new URL(page.url()).hash).toBe("");
    expect(await page.evaluate(() => window.__claims || [])).toEqual([]);
  });
}

test("expired saved scans are discarded after OAuth", async ({page}) => {
  await page.addInitScript(code => sessionStorage.setItem("drawbridge.pairing", JSON.stringify({deviceId: "ab12cd", pairingCode: code, createdAtMs: Date.now() - 7200001})), pairingCode);
  await page.goto("/");
  await expect(page.locator("#controls")).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem("drawbridge.pairing"))).toBeNull();
});

test("expired claims stop polling and can be retried explicitly", async ({page}) => {
  await page.addInitScript(() => { window.__scenario = "claim-expired"; });
  await page.goto(scanUrl("ab12cd"));
  await page.locator("#device-claim").click();
  await expect(page.locator("#device-onboarding-status")).toContainText("expired");
  await expect(page.locator("#device-claim")).toBeEnabled();
  expect(await page.evaluate(() => window.__claimPolls)).toBe(1);
});

test("registration rejects an already owned device without takeover", async ({page}) => {
  await page.addInitScript(() => { window.__scenario = "claim-owned"; });
  await page.goto(scanUrl("ab12cd"));
  await page.locator("#device-claim").click();
  await expect(page.locator("#device-onboarding-status")).toContainText("already registered");
  await expect(page.locator("#device-claim")).toBeEnabled();
  expect(await page.evaluate(() => window.__commands || [])).toEqual([]);
});

test("offline registration stays disabled and cancel ignores an in-flight response", async ({page, context}) => {
  await page.addInitScript(() => { window.__scenario = "claim-delayed"; });
  await page.goto(scanUrl("ab12cd"));
  await context.setOffline(true);
  await expect(page.locator("#device-claim")).toBeDisabled();
  await context.setOffline(false);
  await expect(page.locator("#device-claim")).toBeEnabled();
  expect(await page.evaluate(() => window.__claims || [])).toEqual([]);
  await page.locator("#device-claim").click();
  await page.locator("#device-onboarding-cancel").click();
  await page.evaluate(() => window.__releaseClaim());
  await expect(page.locator("#controls")).toBeVisible();
  await expect(page.locator("#device-onboarding")).toBeHidden();
  expect(await page.evaluate(() => window.__claimPolls || 0)).toBe(0);
});

test("compact QR links open registration for existing accounts", async ({page}) => {
  await page.goto(`/?d=ab12cd#p=${pairingCode}`);
  await expect(page.locator("#device-onboarding")).toBeVisible();
  await expect(page.locator("#device-onboarding-id")).toHaveValue("ab12cd");
  expect(new URL(page.url()).hash).toBe("");
  expect(await page.evaluate(() => window.__claims || [])).toEqual([]);
});

async function openSetupAdmin(page, device = {}) {
  await page.addInitScript(value => {
    window.__scenario = "admin";
    window.__setupDevice = {id: "test-device", name: "Garden gate", enabled: true, otaEnrolled: false,
      maintenance: {supportsRestartSetup: true, lastSeenAtMs: Date.now(), appVersion: "1.0.0", baseVersion: "1.0.13"}, ...value};
  }, device);
  await page.goto("/");
  await page.locator("#account-menu-button").click();
  await page.locator("#admin-open").click();
  await page.getByRole("tab", {name: "Device Firmware", exact: true}).click();
}

test("restart setup supports non-OTA devices, confirms cleanup, and sends only one explicit request", async ({page}) => {
  await openSetupAdmin(page);
  const restart = page.getByRole("button", {name: "Restart setup", exact: true});
  await expect(restart).toBeVisible();
  page.once("dialog", dialog => {
    expect(dialog.message()).toContain("saved Wi-Fi and MQTT");
    expect(dialog.message()).toContain("identity and access");
    return dialog.dismiss();
  });
  await restart.click();
  expect(await page.evaluate(() => window.__adminChanges || [])).toEqual([]);
  page.once("dialog", dialog => dialog.accept());
  await restart.click();
  await expect(page.locator("#admin-devices")).toContainText("Restart setup queued");
  const changes = await page.evaluate(() => window.__adminChanges);
  expect(changes).toHaveLength(1);
  expect(changes[0]).toMatchObject({action: "restartSetup", deviceId: "test-device"});
  expect(changes[0].requestId).toMatch(/^[a-f0-9-]{36}$/);
  expect(changes[0].issuedAtMs).toBeGreaterThan(0);
  await expect(restart).toBeDisabled();
  expect(await page.evaluate(() => window.__commands || [])).toEqual([]);
});

test("restart setup explains USB updates and blocks disabled or unsupported devices", async ({page}) => {
  await openSetupAdmin(page, {maintenance: null});
  await expect(page.locator("#admin-devices")).toContainText("USB update required to restart setup");
  await expect(page.getByRole("button", {name: "Restart setup", exact: true})).toHaveCount(0);
  await page.evaluate(() => { window.__setupDevice.maintenance = {supportsRestartSetup: true, lastSeenAtMs: Date.now()}; window.__setupDevice.enabled = false; });
  await page.getByRole("button", {name: "Refresh administration"}).click();
  await expect(page.getByRole("button", {name: "Restart setup", exact: true})).toBeDisabled();
});

test("restart setup pending status distinguishes a device waiting offline and refreshes through confirmed setup", async ({page}) => {
  await page.clock.install();
  await openSetupAdmin(page, {enabled: false, maintenance: {supportsRestartSetup: true, lastSeenAtMs: Date.now() - 120000}, setupReset: {state: "pending", requestedAtMs: Date.now()}});
  await expect(page.locator("#admin-devices")).toContainText("Waiting for the device to reconnect");
  await page.evaluate(() => { window.__setupDevice.setupReset.state = "awaiting_setup"; });
  await page.clock.fastForward(5000);
  await expect(page.locator("#admin-devices")).toContainText("Set up Wi-Fi on the device, then scan its QR code");
  await page.evaluate(() => { window.__setupDevice.setupReset.state = "provisioning"; });
  await page.clock.fastForward(5000);
  await expect(page.locator("#admin-devices")).toContainText("Waiting for the device to confirm connection");
  await page.evaluate(() => { window.__setupDevice.setupReset.state = "complete"; window.__setupDevice.enabled = true; });
  await page.clock.fastForward(5000);
  await expect(page.locator("#admin-devices")).toContainText("Setup complete");
  const reads = await page.evaluate(() => window.__adminReads);
  await page.clock.fastForward(15000);
  expect(await page.evaluate(() => window.__adminReads)).toBe(reads);
  expect(await page.evaluate(() => window.__adminChanges || [])).toEqual([]);
});

test("restart setup never retries an uncertain mutation and prevents repeated clicks while saving", async ({page}) => {
  await openSetupAdmin(page);
  await page.evaluate(() => { window.__delayAdminChange = true; window.__failAdminChange = true; });
  page.on("dialog", dialog => dialog.accept());
  const restart = page.getByRole("button", {name: "Restart setup", exact: true});
  await restart.click();
  await expect(restart).toBeDisabled();
  await restart.dispatchEvent("click");
  await page.evaluate(() => window.__releaseAdminChange());
  await expect(page.locator("#admin-result")).toContainText("Couldn't confirm this change");
  await expect(restart).toBeEnabled();
  expect(await page.evaluate(() => window.__adminChanges.length)).toBe(1);
  expect(await page.evaluate(() => window.__commands || [])).toEqual([]);
});

test("restart setup polling pauses offline and discards a stale refresh after sign-out", async ({page, context}) => {
  await page.clock.install();
  await openSetupAdmin(page, {enabled: false, setupReset: {state: "pending", requestedAtMs: Date.now()}});
  await context.setOffline(true);
  const reads = await page.evaluate(() => window.__adminReads);
  await page.clock.fastForward(15000);
  expect(await page.evaluate(() => window.__adminReads)).toBe(reads);
  await context.setOffline(false);
  await page.evaluate(() => { window.__delayAdminOverview = true; });
  await page.clock.fastForward(5000);
  await expect.poll(() => page.evaluate(() => typeof window.__releaseAdminOverview)).toBe("function");
  await page.locator("#account-menu-button").click();
  await page.locator("#sign-out").click();
  await page.evaluate(() => window.__releaseAdminOverview());
  await expect(page.locator("#admin-view")).toBeHidden();
  await expect(page.locator("#admin-devices")).toBeEmpty();
  const afterSignout = await page.evaluate(() => window.__adminReads);
  await page.clock.fastForward(15000);
  expect(await page.evaluate(() => window.__adminReads)).toBe(afterSignout);
});


test("restart setup ignores an older polling snapshot after a newer manual refresh", async ({page}) => {
  await page.clock.install();
  await openSetupAdmin(page, {enabled: false, setupReset: {state: "pending", requestedAtMs: Date.now()}});
  await page.evaluate(() => { window.__delayAdminOverview = true; });
  await page.clock.fastForward(5000);
  await expect.poll(() => page.evaluate(() => typeof window.__releaseAdminOverview)).toBe("function");
  await page.evaluate(() => {
    window.__delayAdminOverview = false;
    window.__setupDevice.setupReset.state = "complete";
    window.__setupDevice.enabled = true;
  });
  await page.getByRole("button", {name: "Refresh administration"}).click();
  await expect(page.locator("#admin-devices")).toContainText("Setup complete");
  await page.evaluate(() => window.__releaseAdminOverview());
  await expect(page.locator("#admin-devices")).toContainText("Setup complete");
  const reads = await page.evaluate(() => window.__adminReads);
  await page.clock.fastForward(15000);
  expect(await page.evaluate(() => window.__adminReads)).toBe(reads);
  expect(await page.evaluate(() => window.__adminChanges || [])).toEqual([]);
});


test("restart setup ignores an old read failure after a newer admin mutation", async ({page}) => {
  await page.clock.install();
  await openSetupAdmin(page, {enabled: false, setupReset: {state: "pending", requestedAtMs: Date.now()}});
  await page.evaluate(() => { window.__delayAdminOverview = true; window.__failAdminOverview = true; });
  await page.clock.fastForward(5000);
  await expect.poll(() => page.evaluate(() => typeof window.__releaseAdminOverview)).toBe("function");
  await page.evaluate(() => { window.__delayAdminOverview = false; window.__failAdminOverview = false; });
  await page.getByRole("tab", {name: "Admins", exact: true}).click();
  await page.locator("#admin-email").fill("friend@example.test");
  page.on("dialog", dialog => dialog.accept());
  await page.getByRole("button", {name: "Add administrator", exact: true}).click();
  await expect(page.locator("#admin-result")).toHaveText("Saved.");
  await page.evaluate(() => window.__releaseAdminOverview());
  await expect(page.locator("#admin-result")).toHaveText("Saved.");
});

test("a persisted claim across restart setup asks for on-device Wi-Fi and a fresh QR scan", async ({page}) => {
  await page.clock.install();
  await page.addInitScript(code => {
    window.__scenario = "claim-awaiting-setup";
    sessionStorage.setItem("drawbridge.pairing", JSON.stringify({deviceId: "ab12cd", pairingCode: code, createdAtMs: Date.now(), submitted: true}));
  }, pairingCode);
  await page.goto("/");
  await expect(page.locator("#device-onboarding-status")).toHaveText("Set up Wi-Fi on the device, then scan its QR code.");
  await expect(page.locator("#controls")).toBeHidden();
  await page.clock.fastForward(10000);
  expect(await page.evaluate(() => window.__claimPolls)).toBe(1);
  expect(await page.evaluate(() => window.__claims || [])).toEqual([]);
  expect(await page.evaluate(() => window.__commands || [])).toEqual([]);
});
